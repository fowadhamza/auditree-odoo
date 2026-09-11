# -*- coding: utf-8 -*-
"""Data endpoint for the Forecast dashboard client action.

One RPC returns every figure the dashboard draws. Everything is derived from
the generated tables (forecast.monthly.line and forecast.cash.flow.month), so
the dashboard can never disagree with the P&L and Cash Flow reports - if a
number looks wrong here, the fix is Settings > Recalculate, not this file.

Totals follow the same definitions as the source web app's computePnl:
  total revenue   = revenue lines
  total expenses  = salary lines + expense lines   (adjustments excluded)
  net profit      = revenue - total expenses       (before tax)
"""
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api

# Below this closing balance a month is called out as a cash risk. 10 lakh,
# the same threshold the web app's dashboard banner uses.
LOW_CASH_THRESHOLD = 1000000.0


class ForecastConfigDashboard(models.Model):
    _inherit = 'forecast.config'

    @api.model
    def get_dashboard_data(self):
        """Return every figure the Forecast dashboard renders.

        Reads are done as the calling user on purpose: a user without the
        Forecast group hits an AccessError here rather than being served
        firm-wide financials.
        """
        config = self.search([], limit=1)
        if not config:
            return {'has_data': False,
                    'message': "No forecast window is configured yet. "
                               "Open Forecast > Settings to set one up."}

        Line = self.env['forecast.monthly.line']
        CashMonth = self.env['forecast.cash.flow.month']
        months = config._month_list()
        cash_rows = CashMonth.search([], order='month')

        if not Line.search_count([]) and not cash_rows:
            return {'has_data': False,
                    'message': "The forecast has not been generated yet. "
                               "Open Forecast > Settings and press Recalculate."}

        totals = self._dashboard_totals(Line)
        cash = self._dashboard_cash(cash_rows)
        headcount = self._dashboard_headcount()

        net_profit = totals['revenue'] - totals['expenses']
        margin_pct = (net_profit / totals['revenue'] * 100.0) if totals['revenue'] else 0.0
        salary_pct = (totals['salary'] / totals['revenue'] * 100.0) if totals['revenue'] else 0.0

        return {
            'has_data': True,
            'window': {
                'start': self._month_label(config.window_start),
                'end': self._month_label(config.window_end),
                'total_months': len(months),
                'elapsed_months': self._elapsed_months(config, months),
                'last_recomputed': config.last_recomputed and
                                   fields.Datetime.to_string(config.last_recomputed) or False,
            },
            'kpi': {
                'total_revenue': totals['revenue'],
                'total_expenses': totals['expenses'],
                'net_profit': net_profit,
                'closing_cash': cash['closing_cash'],
                'margin_pct': margin_pct,
                'salary_to_revenue_pct': salary_pct,
                'billable_count': headcount['billable'],
                'internal_count': headcount['internal'],
                'min_closing_balance': cash['min_closing'],
                'min_closing_month': cash['min_month'],
                'low_cash_threshold': LOW_CASH_THRESHOLD,
            },
            'cash_trend': cash['trend'],
            'inflow_outflow': self._dashboard_inflow_outflow(Line, cash_rows),
            'monthly_profit': self._dashboard_monthly_profit(Line, months),
            'revenue_by_client': self._dashboard_revenue_by_client(Line),
            'expense_breakdown': self._dashboard_expense_breakdown(Line, totals['salary']),
            'leaving_soon': self._dashboard_leaving_soon(config),
        }

    # -- helpers -------------------------------------------------------------

    @api.model
    def _month_label(self, value):
        return value.strftime('%b %Y') if value else ''

    @api.model
    def _elapsed_months(self, config, months):
        """Whole months from the window start to this month, clamped to the window."""
        if not months:
            return 0
        today = fields.Date.context_today(self).replace(day=1)
        start = config.window_start.replace(day=1)
        elapsed = (today.year - start.year) * 12 + (today.month - start.month)
        return max(0, min(len(months), elapsed))

    @api.model
    def _sum_by(self, Line, domain, group_field):
        """{group value: summed amount} for one read_group, blanks folded together.

        Only for non-date fields - read_group applies its own month granularity
        and label format to a Date, which would not line up with the month keys
        used elsewhere here. Use _sum_by_month for those.
        """
        rows = Line.read_group(domain, ['amount:sum'], [group_field])
        result = {}
        for row in rows:
            key = row[group_field]
            if isinstance(key, tuple):
                key = key[1]
            result[key or 'Uncategorised'] = row['amount']
        return result

    @api.model
    def _sum_by_month(self, Line, domain):
        """{date(first of month): summed amount}, aggregated in Python.

        The month field already holds the first of the month, so grouping on
        the raw date value keeps the keys exact and comparable.
        """
        result = {}
        for line in Line.search(domain):
            key = line.month.replace(day=1)
            result[key] = result.get(key, 0.0) + line.amount
        return result

    @api.model
    def _dashboard_totals(self, Line):
        by_type = self._sum_by(Line, [], 'line_type')
        salary = by_type.get('salary', 0.0)
        expense = by_type.get('expense', 0.0)
        return {
            'revenue': by_type.get('revenue', 0.0),
            'salary': salary,
            'other_expense': expense,
            'expenses': salary + expense,
        }

    @api.model
    def _dashboard_headcount(self):
        """Active billable and internal headcount, the two the tiles report."""
        Employee = self.env['forecast.employee']
        return {
            'billable': Employee.search_count([
                ('active', '=', True), ('employee_type', '=', 'client_billable')]),
            'internal': Employee.search_count([
                ('active', '=', True), ('employee_type', '=', 'internal_support')]),
        }

    @api.model
    def _dashboard_cash(self, cash_rows):
        trend = [{'label': self._month_label(row.month),
                  'value': row.closing_balance} for row in cash_rows]
        if not cash_rows:
            return {'trend': [], 'closing_cash': 0.0, 'min_closing': 0.0, 'min_month': ''}
        worst = min(cash_rows, key=lambda r: r.closing_balance)
        return {
            'trend': trend,
            'closing_cash': cash_rows[-1].closing_balance,
            'min_closing': worst.closing_balance,
            'min_month': self._month_label(worst.month),
        }

    @api.model
    def _dashboard_inflow_outflow(self, Line, cash_rows):
        """Cash inflow against salary and non-salary outflow, per month.

        Inflow comes from the cash summary because revenue is collected on a
        one-month lag; the outflow split is not stored there, so it is read
        back from the lines.
        """
        salary_by_month = self._sum_by_month(Line, [('line_type', '=', 'salary')])
        other_out_by_month = self._sum_by_month(
            Line, [('line_type', 'in', ('expense', 'cash_other')),
                   ('direction', '=', 'outflow')])
        series = []
        for row in cash_rows:
            key = row.month.replace(day=1)
            series.append({
                'label': self._month_label(row.month),
                'inflow': row.total_inflow,
                'salary_out': salary_by_month.get(key, 0.0),
                'expense_out': other_out_by_month.get(key, 0.0),
            })
        return series

    @api.model
    def _dashboard_monthly_profit(self, Line, months):
        """Accrual revenue, expenses and net profit per month - no collection lag."""
        revenue = self._sum_by_month(Line, [('line_type', '=', 'revenue')])
        salary = self._sum_by_month(Line, [('line_type', '=', 'salary')])
        expense = self._sum_by_month(Line, [('line_type', '=', 'expense')])
        series = []
        for month in months:
            key = month.replace(day=1)
            rev = revenue.get(key, 0.0)
            exp = salary.get(key, 0.0) + expense.get(key, 0.0)
            series.append({'label': self._month_label(month), 'revenue': rev,
                           'expenses': exp, 'net': rev - exp})
        return series

    @api.model
    def _dashboard_revenue_by_client(self, Line):
        totals = self._sum_by(Line, [('line_type', '=', 'revenue')], 'client_id')
        rows = [{'name': name, 'value': value} for name, value in totals.items()]
        return sorted(rows, key=lambda r: r['value'], reverse=True)

    @api.model
    def _dashboard_expense_breakdown(self, Line, salary_total):
        """Expense categories, with salary folded in as 'Labour cost'."""
        totals = self._sum_by(Line, [('line_type', '=', 'expense')], 'category')
        if salary_total:
            totals['Labour cost'] = totals.get('Labour cost', 0.0) + salary_total
        rows = [{'name': name, 'value': value} for name, value in totals.items()]
        return sorted(rows, key=lambda r: r['value'], reverse=True)

    @api.model
    def _dashboard_leaving_soon(self, config):
        """Active employees whose end date falls inside the forecast window."""
        employees = self.env['forecast.employee'].search([
            ('active', '=', True),
            ('end_date', '!=', False),
            ('end_date', '<=', config.window_end + relativedelta(months=1, days=-1)),
        ], order='end_date')
        return [{'name': emp.name, 'month': self._month_label(emp.end_date)}
                for emp in employees]
