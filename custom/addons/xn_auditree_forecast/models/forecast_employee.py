# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ForecastEmployee(models.Model):
    _name = 'forecast.employee'
    _description = 'Forecast Employee'
    _order = 'name'

    name = fields.Char(required=True)
    auditree_title = fields.Char(string='Auditree Title')
    client_role = fields.Char(string='Client Role')
    employee_type = fields.Selection([
        ('client_billable', 'Client Billable'),
        ('internal_support', 'Internal / Support'),
        ('partner', 'Partner'),
    ], required=True, default='client_billable',
        help="Only Client Billable employees contribute to revenue totals.")
    start_date = fields.Date(required=True)
    end_date = fields.Date()
    active = fields.Boolean(default=True)

    # One employee owns every salary cycle they have ever been on. The cycles
    # live here rather than in a flat cross-employee list so a raise history is
    # edited in one place - see the 'Salary Cycles' page on the form.
    salary_plan_ids = fields.One2many('forecast.salary.plan', 'employee_id', string='Salary Cycles')
    # Stored so the list view can search, sort and total on it.
    salary_plan_count = fields.Integer(compute='_compute_salary_plan_count', store=True,
                                       string='Salary Cycles')
    # The "current" figures depend on today's date, so they are recomputed on
    # read rather than stored - a stored value would go stale overnight.
    current_period = fields.Char(compute='_compute_salary_summary', string='Current Period')
    current_fixed_ctc = fields.Float(compute='_compute_salary_summary', string='Fixed CTC (Annual)')
    current_variable_ctc = fields.Float(compute='_compute_salary_summary',
                                        string='Variable CTC (Annual)')
    current_total_ctc = fields.Float(compute='_compute_salary_summary', string='Total CTC (Annual)')
    current_monthly_cost = fields.Float(compute='_compute_salary_summary', string='Monthly Cost')

    @api.depends('salary_plan_ids')
    def _compute_salary_plan_count(self):
        for rec in self:
            rec.salary_plan_count = len(rec.salary_plan_ids)

    @api.depends('salary_plan_ids', 'salary_plan_ids.effective_date',
                 'salary_plan_ids.end_date', 'salary_plan_ids.fixed_ctc',
                 'salary_plan_ids.variable_ctc')
    def _compute_salary_summary(self):
        today = fields.Date.context_today(self)
        for rec in self:
            cycles = rec.salary_plan_ids.sorted('effective_date')
            current = rec._current_cycle(cycles, today)
            rec.current_period = current._format_period() if current else ''
            rec.current_fixed_ctc = current.fixed_ctc if current else 0.0
            rec.current_variable_ctc = current.variable_ctc if current else 0.0
            rec.current_total_ctc = current.total_ctc if current else 0.0
            rec.current_monthly_cost = current.monthly_cost if current else 0.0

    @api.model
    def _current_cycle(self, cycles, today):
        """The cycle covering this month, else the most recent one, else empty.

        Cycles are month-granular - 'To' holds a month, not an exact last day -
        so compare month starts the same way the forecast engine does. Comparing
        raw dates would treat a cycle ending 'Sep' as over on 2 September.
        """
        month = today.replace(day=1)
        for cycle in reversed(cycles):
            if not cycle.effective_date:
                continue
            starts = cycle.effective_date.replace(day=1)
            ends = cycle.end_date.replace(day=1) if cycle.end_date else None
            if starts <= month and (ends is None or month <= ends):
                return cycle
        return cycles[-1] if cycles else self.env['forecast.salary.plan']

    def action_view_salary_plans(self):
        """Open this employee's cycles as a standalone editable list."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Salary Cycles - %s' % self.name,
            'res_model': 'forecast.salary.plan',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
