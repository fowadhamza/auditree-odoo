# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api

# Cash movement categories that are settings (consumed directly by the cash
# flow engine), not regular flow line items.
META_CASH_CATEGORIES = ('Opening Balance', 'Opening Accounts Receivable')


class ForecastConfig(models.Model):
    _name = 'forecast.config'
    _description = 'Forecast Settings'
    _rec_name = 'name'

    name = fields.Char(default='Forecast Settings', required=True)
    window_start = fields.Date(required=True,
                                default=lambda self: fields.Date.today().replace(day=1))
    window_end = fields.Date(required=True,
                              default=lambda self: fields.Date.today().replace(day=1) + relativedelta(months=14))
    last_recomputed = fields.Datetime(readonly=True)

    @api.model
    def get_config(self):
        """Return the single Forecast Settings record, creating it if missing."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config

    def _month_list(self):
        self.ensure_one()
        months = []
        cur = self.window_start.replace(day=1)
        end = self.window_end.replace(day=1)
        while cur <= end:
            months.append(cur)
            cur = cur + relativedelta(months=1)
        return months

    def action_recalculate(self):
        self.ensure_one()
        months = self._month_list()

        Line = self.env['forecast.monthly.line'].sudo()
        CashMonth = self.env['forecast.cash.flow.month'].sudo()
        Line.search([]).unlink()
        CashMonth.search([]).unlink()

        lines_to_create = []
        lines_to_create += self._generate_revenue_lines(months)
        lines_to_create += self._generate_salary_lines(months)
        lines_to_create += self._generate_expense_lines(months)
        lines_to_create += self._generate_cash_movement_lines(months)
        lines_to_create += self._generate_adjustment_lines(months)
        if lines_to_create:
            Line.create(lines_to_create)

        self._generate_cash_flow_summary(months)
        self.last_recomputed = fields.Datetime.now()
        return True

    def action_advance_window(self):
        self.ensure_one()
        self.window_start = self.window_start + relativedelta(months=1)
        self.window_end = self.window_end + relativedelta(months=1)
        return self.action_recalculate()

    # -- generation helpers --------------------------------------------------

    def _generate_revenue_lines(self, months):
        lines = []
        assignments = self.env['forecast.revenue.assignment'].search([])
        overrides = self.env['forecast.revenue.override'].search([])
        override_map = {}
        for ov in overrides:
            override_map[(ov.revenue_assignment_id.id, ov.month.replace(day=1))] = ov.amount

        for month in months:
            for assign in assignments:
                start = assign.start_month.replace(day=1)
                end = assign.end_month.replace(day=1) if assign.end_month else None
                if month < start or (end and month > end):
                    continue
                amount = override_map.get((assign.id, month), assign.monthly_amount_inr)
                lines.append({
                    'month': month,
                    'line_type': 'revenue',
                    'direction': 'inflow',
                    'employee_id': assign.employee_id.id,
                    'client_id': assign.client_id.id,
                    'category': assign.client_id.category,
                    'amount': amount,
                    'description': assign.employee_id.name,
                })
        return lines

    def _generate_salary_lines(self, months):
        lines = []
        employees = self.env['forecast.employee'].search([])
        plans = self.env['forecast.salary.plan'].search([], order='effective_date')
        plans_by_employee = {}
        for plan in plans:
            plans_by_employee.setdefault(plan.employee_id.id, []).append(plan)

        for month in months:
            for emp in employees:
                emp_start = emp.start_date.replace(day=1) if emp.start_date else None
                emp_end = emp.end_date.replace(day=1) if emp.end_date else None
                if emp_start and month < emp_start:
                    continue
                if emp_end and month > emp_end:
                    continue
                applicable = [p for p in plans_by_employee.get(emp.id, [])
                              if p.effective_date.replace(day=1) <= month
                              and (not p.end_date or month <= p.end_date.replace(day=1))]
                if not applicable:
                    continue
                plan = applicable[-1]  # latest effective_date <= month (no-overlap constraint keeps this unique)
                lines.append({
                    'month': month,
                    'line_type': 'salary',
                    'direction': 'outflow',
                    'employee_id': emp.id,
                    'category': 'Salary',
                    # total_ctc is annual; monthly cost = annual / 12.
                    'amount': plan.total_ctc / 12.0,
                    'description': emp.name,
                })
        return lines

    def _generate_expense_lines(self, months):
        lines = []
        month_set = set(months)
        expense_lines = self.env['forecast.expense.line'].search([])

        for exp in expense_lines:
            start = exp.start_month.replace(day=1)
            end = exp.end_month.replace(day=1) if exp.end_month else self.window_end.replace(day=1)
            step = 3 if exp.recurrence == 'quarterly' else 1

            occurrence_months = []
            cur = start
            while cur <= end:
                occurrence_months.append(cur)
                if exp.recurrence == 'one_time':
                    break
                cur = cur + relativedelta(months=step)
            if not occurrence_months:
                continue

            per_occurrence = exp.annual_total if exp.recurrence == 'one_time' \
                else exp.annual_total / len(occurrence_months)

            for month in occurrence_months:
                if month not in month_set:
                    continue
                lines.append({
                    'month': month,
                    'line_type': 'expense',
                    'direction': 'outflow',
                    'category': exp.category or exp.name,
                    'amount': per_occurrence,
                    'description': exp.name,
                })
        return lines

    def _generate_cash_movement_lines(self, months):
        lines = []
        month_set = set(months)
        # Opening Balance / Opening Accounts Receivable are settings, not flow
        # line items - _generate_cash_flow_summary consumes them separately.
        movements = self.env['forecast.cash.movement'].search([
            ('category', 'not in', META_CASH_CATEGORIES),
        ])
        for mv in movements:
            month = mv.date.replace(day=1)
            if month not in month_set:
                continue
            lines.append({
                'month': month,
                'line_type': 'cash_other',
                'direction': mv.movement_type,
                'category': mv.category,
                'amount': mv.amount,
                'description': mv.description,
            })
        return lines

    def _generate_adjustment_lines(self, months):
        lines = []
        month_set = set(months)
        adjustments = self.env['forecast.financial.adjustment'].search([])
        adjustment_labels = dict(adjustments._fields['adjustment_type'].selection)
        for adj in adjustments:
            month = adj.month.replace(day=1)
            if month not in month_set:
                continue
            lines.append({
                'month': month,
                'line_type': 'adjustment',
                'direction': 'outflow',
                'category': adjustment_labels.get(adj.adjustment_type),
                'amount': adj.amount,
                'description': adj.notes,
            })
        return lines

    def _generate_cash_flow_summary(self, months):
        self.ensure_one()
        CashMonth = self.env['forecast.cash.flow.month'].sudo()
        Line = self.env['forecast.monthly.line'].sudo()

        # Opening Balance / Opening Accounts Receivable are tagged cash movements
        # (category, not date) - matches the source app's convention so they can
        # be seeded via Other Cash Movements without a schema change.
        opening_balance = self._sum_tagged_cash_movement('Opening Balance')
        opening_accounts_receivable = self._sum_tagged_cash_movement('Opening Accounts Receivable')

        # Revenue is collected on a 1-month lag (Net-30 style, matching the
        # source workbook's cash sheet): month 0 collects the opening accounts
        # receivable instead of that month's own billings; month i (i>=1)
        # collects month (i-1)'s revenue accrual. Salary/expense/other cash
        # movements have no lag.
        revenue_accrual_by_month = {
            month: sum(Line.search([('month', '=', month), ('line_type', '=', 'revenue')]).mapped('amount'))
            for month in months
        }

        running_opening = opening_balance
        for i, month in enumerate(months):
            revenue_cash_inflow = opening_accounts_receivable if i == 0 \
                else revenue_accrual_by_month.get(months[i - 1], 0.0)

            other_lines = Line.search([
                ('month', '=', month),
                ('line_type', 'in', ('salary', 'expense', 'cash_other')),
            ])
            outflow = sum(other_lines.filtered(lambda l: l.direction == 'outflow').mapped('amount'))
            other_inflow = sum(other_lines.filtered(
                lambda l: l.direction == 'inflow' and l.line_type == 'cash_other').mapped('amount'))

            inflow = revenue_cash_inflow + other_inflow
            closing = running_opening + inflow - outflow
            CashMonth.create({
                'month': month,
                'opening_balance': running_opening,
                'total_inflow': inflow,
                'total_outflow': outflow,
                'closing_balance': closing,
            })
            running_opening = closing

    def _sum_tagged_cash_movement(self, category):
        movements = self.env['forecast.cash.movement'].search([('category', '=', category)])
        return sum(m.amount if m.movement_type == 'inflow' else -m.amount for m in movements)
