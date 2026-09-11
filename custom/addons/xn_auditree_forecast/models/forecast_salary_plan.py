# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ForecastSalaryPlan(models.Model):
    _name = 'forecast.salary.plan'
    _description = 'Forecast Salary Cycle'
    # Group cycles by employee first so an employee's raise history stays
    # together instead of being scattered across the whole list by date.
    _order = 'employee_id, effective_date'

    employee_id = fields.Many2one('forecast.employee', required=True, ondelete='cascade')
    # CTC fields are ANNUAL totals (standard Indian payroll convention) - the
    # forecast engine divides by 12 to get the monthly salary cost.
    fixed_ctc = fields.Float(required=True, string='Fixed CTC (Annual)')
    variable_ctc = fields.Float(default=0.0, string='Variable CTC (Annual)')
    effective_date = fields.Date(required=True, string='From')
    end_date = fields.Date(string='To', help="Last month this cycle applies to (inclusive). "
                                              "Leave empty for an ongoing/current cycle.")
    hike_pct = fields.Float(string='Next Hike %',
                             help="Informational only; apply a hike by creating a new "
                                  "salary cycle effective from the review date.")
    next_review_date = fields.Date()
    total_ctc = fields.Float(compute='_compute_total_ctc', store=True, string='Total CTC (Annual)')
    monthly_cost = fields.Float(compute='_compute_total_ctc', store=True, string='Monthly',
                                help="(Fixed + Variable) / 12 - the monthly salary cost "
                                     "the forecast charges for every month in this cycle.")
    period_label = fields.Char(compute='_compute_period_label', string='Period')

    @api.depends('fixed_ctc', 'variable_ctc')
    def _compute_total_ctc(self):
        for rec in self:
            rec.total_ctc = rec.fixed_ctc + rec.variable_ctc
            rec.monthly_cost = rec.total_ctc / 12.0

    @api.depends('effective_date', 'end_date')
    def _compute_period_label(self):
        for rec in self:
            rec.period_label = rec._format_period()

    def _format_period(self):
        """Human-readable month range, e.g. 'Jul 2026 - ongoing'."""
        self.ensure_one()
        if not self.effective_date:
            return ''
        start = self.effective_date.strftime('%b %Y')
        end = self.end_date.strftime('%b %Y') if self.end_date else 'ongoing'
        return '%s - %s' % (start, end)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%s)' % (rec.employee_id.name or '', rec._format_period())

    @api.model
    def default_get(self, fields_list):
        """Prefill 'From' with the month after the employee's latest cycle.

        Mirrors the web app's '+ Add cycle' behaviour so a hike cycle slots in
        straight after the previous one instead of colliding with it.
        """
        defaults = super().default_get(fields_list)
        employee_id = defaults.get('employee_id') or self.env.context.get('default_employee_id')
        if 'effective_date' in fields_list and not defaults.get('effective_date') and employee_id:
            last = self.search([('employee_id', '=', employee_id)],
                               order='effective_date desc', limit=1)
            if last and last.end_date:
                defaults['effective_date'] = last.end_date.replace(day=1) + relativedelta(months=1)
            else:
                defaults['effective_date'] = fields.Date.context_today(self).replace(day=1)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-close an open-ended prior cycle so adding a later one (e.g. an
        # October hike) reads as Jul->Sep / Oct->ongoing instead of failing the
        # overlap check. Same rule the web app applies on POST.
        for vals in vals_list:
            employee_id = vals.get('employee_id')
            effective_date = vals.get('effective_date')
            if employee_id and effective_date:
                self._close_open_cycles_before(employee_id, fields.Date.to_date(effective_date))
        return super().create(vals_list)

    @api.model
    def _close_open_cycles_before(self, employee_id, new_start):
        """End any open-ended cycle that starts before new_start.

        The previous cycle is closed on the month before new_start. Cycles that
        start on or after new_start are left alone - those are genuine overlaps
        and the constraint should reject them.
        """
        new_start = new_start.replace(day=1)
        prior_end = new_start - relativedelta(months=1)
        open_priors = self.search([
            ('employee_id', '=', employee_id),
            ('end_date', '=', False),
            ('effective_date', '<', new_start),
        ])
        for plan in open_priors:
            if plan.effective_date.replace(day=1) <= prior_end:
                plan.end_date = prior_end

    @api.constrains('employee_id', 'effective_date', 'end_date')
    def _check_no_overlap(self):
        for rec in self:
            if rec.end_date and rec.end_date < rec.effective_date:
                raise ValidationError(
                    "%s: the salary cycle 'To' date (%s) is before its 'From' date (%s)." % (
                        rec.employee_id.name, rec.end_date, rec.effective_date))
            others = self.search([
                ('employee_id', '=', rec.employee_id.id),
                ('id', '!=', rec.id),
            ])
            far_future = fields.Date.from_string('9999-12-31')
            rec_end = rec.end_date or far_future
            for other in others:
                other_end = other.end_date or far_future
                if rec.effective_date <= other_end and other.effective_date <= rec_end:
                    raise ValidationError(
                        "%s already has a salary cycle %s that overlaps with %s. "
                        "Close the previous cycle (set its 'To' date) before "
                        "starting a new one." % (
                            rec.employee_id.name, other._format_period(),
                            rec._format_period()))
