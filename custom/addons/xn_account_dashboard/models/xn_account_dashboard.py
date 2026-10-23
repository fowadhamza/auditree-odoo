# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import date_utils

INCOME_TYPES = ("income", "income_other")
EXPENSE_TYPES = ("expense", "expense_depreciation", "expense_direct_cost")

# (upper bound in days overdue, label). None is open-ended.
AGE_BUCKETS = [(0, "Not yet due"), (30, "1-30 days"), (60, "31-60 days"),
               (90, "61-90 days"), (None, "Over 90 days")]


class XnAccountDashboard(models.AbstractModel):
    """Data behind the Accounts Overview client action.

    Everything is read with the caller's own access rights - no sudo() - so
    record rules and multi-company restrictions apply exactly as they do in
    the journal lists the figures open.
    """

    _name = "xn.account.dashboard"
    _description = "Accounts Overview data"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _xn_check_access(self):
        if not self.env.user.has_group("account.group_account_readonly"):
            raise AccessError(_("The accounts overview needs access to accounting."))

    def _xn_fiscal_year(self, day):
        """April-March here, from the company's own fiscal year end.

        res.company.compute_fiscalyear_dates is not used on purpose: in
        Community it ignores fiscalyear_last_month and returns the calendar
        year (see account/models/company.py), which would make "this year"
        January-December.
        """
        company = self.env.company
        return date_utils.get_fiscal_year(
            day,
            day=company.fiscalyear_last_day,
            month=int(company.fiscalyear_last_month),
        )

    def _xn_base(self):
        return [("parent_state", "=", "posted"),
                ("company_id", "in", self.env.companies.ids)]

    def _xn_account_ids(self, types):
        return self.env["account.account"].search([
            ("account_type", "in", types),
            ("company_id", "in", self.env.companies.ids),
        ]).ids

    @api.model
    def _xn_overdue(self, today):
        # Opening-balance lines are plain journal items with no due date, so
        # the entry date stands in for it.
        return ["|", ("date_maturity", "<", today),
                "&", ("date_maturity", "=", False), ("date", "<", today)]

    def _xn_domains(self):
        """Every clickable figure, as (model, title, domain).

        A figure and the list it opens come from the same entry here, so they
        cannot disagree.
        """
        today = fields.Date.context_today(self)
        fy_from, _fy_to = self._xn_fiscal_year(today)
        base = self._xn_base()
        open_items = [("reconciled", "=", False), ("amount_residual", "!=", 0)]
        receivable = base + open_items + [("account_id.account_type", "=", "asset_receivable")]
        payable = base + open_items + [("account_id.account_type", "=", "liability_payable")]
        aml = "account.move.line"
        return {
            "receivable": (aml, _("Open receivables"), receivable),
            "receivable_overdue": (aml, _("Overdue receivables"),
                                   receivable + self._xn_overdue(today)),
            "payable": (aml, _("Open payables"), payable),
            "payable_overdue": (aml, _("Overdue payables"),
                                payable + self._xn_overdue(today)),
            "income_fy": (aml, _("Income this financial year"), base + [
                ("account_id", "in", self._xn_account_ids(INCOME_TYPES)),
                ("date", ">=", fy_from), ("date", "<=", today)]),
            "expense_fy": (aml, _("Expenses this financial year"), base + [
                ("account_id", "in", self._xn_account_ids(EXPENSE_TYPES)),
                ("date", ">=", fy_from), ("date", "<=", today)]),
            "bank_unmatched": ("account.bank.statement.line", _("Bank lines to match"), [
                ("is_reconciled", "=", False),
                ("company_id", "in", self.env.companies.ids)]),
            "draft_entries": ("account.move", _("Draft entries"), [
                ("state", "=", "draft"),
                ("company_id", "in", self.env.companies.ids)]),
        }

    def _xn_open_items(self, domain, sign, today):
        """Total, overdue, ageing buckets and the five largest partners."""
        lines = self.env["account.move.line"].search_read(
            domain, ["amount_residual", "date_maturity", "date", "partner_id"])
        buckets = [{"label": label, "value": 0.0} for _limit, label in AGE_BUCKETS]
        partners = {}
        total = overdue = 0.0
        for line in lines:
            amount = sign * line["amount_residual"]
            due = line["date_maturity"] or line["date"]
            days = (today - due).days
            total += amount
            if days > 0:
                overdue += amount
            for index, (limit, _label) in enumerate(AGE_BUCKETS):
                if limit is None or days <= limit:
                    buckets[index]["value"] += amount
                    break
            name = line["partner_id"][1] if line["partner_id"] else _("No partner")
            partners[name] = partners.get(name, 0.0) + amount
        top = sorted(partners.items(), key=lambda item: -abs(item[1]))[:5]
        return {
            "total": total,
            "overdue": overdue,
            "count": len(lines),
            "buckets": buckets,
            "top": [{"name": name, "value": value} for name, value in top],
        }

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @api.model
    def xn_data(self):
        """Everything the page shows, in one round trip."""
        self._xn_check_access()
        today = fields.Date.context_today(self)
        fy_from, fy_to = self._xn_fiscal_year(today)
        domains = self._xn_domains()
        aml = self.env["account.move.line"]
        currency = self.env.company.currency_id

        # Cash: each bank / cash journal's own account, in the books.
        cash = []
        journals = self.env["account.journal"].search([
            ("type", "in", ("bank", "cash")),
            ("company_id", "in", self.env.companies.ids),
        ])
        Line = self.env["account.bank.statement.line"]
        for journal in journals:
            account = journal.default_account_id
            balance = 0.0
            if account:
                balance = sum(aml.search(self._xn_base() + [
                    ("account_id", "=", account.id)]).mapped("balance"))
            unmatched = Line.search([("journal_id", "=", journal.id),
                                     ("is_reconciled", "=", False)])
            last = Line.search([("journal_id", "=", journal.id)], order="date desc", limit=1)
            cash.append({
                "id": journal.id,
                "name": journal.name,
                "type": journal.type,
                "balance": balance,
                "unmatched": len(unmatched),
                "unmatched_amount": sum(unmatched.mapped("amount")),
                "last_date": fields.Date.to_string(last.date) if last else False,
            })

        receivable = self._xn_open_items(domains["receivable"][2], 1, today)
        payable = self._xn_open_items(domains["payable"][2], -1, today)

        # Profit and loss, one row per month of the financial year.
        def by_month(domain):
            groups = aml._read_group(domain, groupby=["date:month"], aggregates=["balance:sum"])
            return {month.strftime("%Y-%m"): total for month, total in groups}

        income = by_month(domains["income_fy"][2])
        expense = by_month(domains["expense_fy"][2])
        months = []
        month = fy_from.replace(day=1)
        while month <= fy_to:
            key = month.strftime("%Y-%m")
            inc = -income.get(key, 0.0)
            exp = expense.get(key, 0.0)
            months.append({
                "key": key,
                "label": month.strftime("%b"),
                "income": inc,
                "expense": exp,
                "profit": inc - exp,
                "future": month > today,
                "current": key == today.strftime("%Y-%m"),
            })
            month += relativedelta(months=1)

        this_month = next((m for m in months if m["current"]), None)
        income_fy = sum(m["income"] for m in months)
        expense_fy = sum(m["expense"] for m in months)

        return {
            "today": fields.Date.to_string(today),
            "fy_from": fields.Date.to_string(fy_from),
            "fy_to": fields.Date.to_string(fy_to),
            "fy_label": "FY %s-%s" % (fy_from.year, str(fy_to.year)[-2:]),
            "currency": {"name": currency.name, "symbol": currency.symbol,
                         "position": currency.position},
            "cash": cash,
            "receivable": receivable,
            "payable": payable,
            "pnl": {
                "months": months,
                "income_fy": income_fy,
                "expense_fy": expense_fy,
                "profit_fy": income_fy - expense_fy,
                "income_month": this_month["income"] if this_month else 0.0,
                "expense_month": this_month["expense"] if this_month else 0.0,
                "profit_month": this_month["profit"] if this_month else 0.0,
            },
            "attention": {
                "bank_unmatched": sum(row["unmatched"] for row in cash),
                "bank_unmatched_amount": sum(row["unmatched_amount"] for row in cash),
                "draft_entries": self.env["account.move"].search_count(domains["draft_entries"][2]),
                "receivable_overdue": receivable["overdue"],
                "payable_overdue": payable["overdue"],
            },
        }

    @api.model
    def xn_open(self, key):
        """The list behind a figure, built from the same domain that counted it."""
        self._xn_check_access()
        model, name, domain = self._xn_domains()[key]
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "domain": domain,
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "context": {"create": False},
        }

    @api.model
    def xn_open_journal(self, journal_id):
        """A bank or cash journal's statement lines, for the cash table."""
        self._xn_check_access()
        journal = self.env["account.journal"].browse(journal_id).exists()
        if not journal:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": journal.name,
            "res_model": "account.bank.statement.line",
            "domain": [("journal_id", "=", journal.id)],
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "context": {"create": False},
        }
