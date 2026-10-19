# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import date_utils, float_compare
import logging

_logger = logging.getLogger(__name__)

LIMIT_PERIOD_LABELS = {
    'request': 'per request',
    'month': 'per month',
    'year': 'per year',
}


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    xn_limit_days = fields.Float(
        string='Max Days Allowed',
        help="Only for time off types that do not require an allocation. "
             "Caps how many days an employee can request in the chosen "
             "period. 0 means no limit.")
    xn_limit_period = fields.Selection(
        [('request', 'Per Request'),
         ('month', 'Per Month'),
         ('year', 'Per Year')],
        string='Limit Period', default='year', required=True)

    @api.constrains('xn_limit_days')
    def _xn_check_limit_days(self):
        for leave_type in self:
            if leave_type.xn_limit_days < 0:
                raise ValidationError(_("Max Days Allowed cannot be negative."))


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    @api.constrains('holiday_status_id', 'employee_id', 'number_of_days',
                    'request_date_from', 'state')
    def _xn_check_leave_type_limit(self):
        """Enforce the day cap set on time off types without allocation.

        Refused and archived (cancelled) requests do not count. For the month
        and year periods a request is counted in full against the period its
        start date falls in.
        """
        for leave in self:
            leave_type = leave.holiday_status_id
            if (leave_type.requires_allocation != 'no'
                    or leave_type.xn_limit_days <= 0
                    or leave.state == 'refuse'
                    or not leave.employee_id
                    or not leave.request_date_from):
                continue
            limit = leave_type.xn_limit_days
            period = leave_type.xn_limit_period
            if period == 'request':
                taken = leave.number_of_days
            else:
                start = date_utils.start_of(leave.request_date_from, period)
                end = date_utils.end_of(leave.request_date_from, period)
                others = self.sudo().search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', leave_type.id),
                    ('state', '!=', 'refuse'),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ])
                taken = sum((others | leave).mapped('number_of_days'))
            if float_compare(taken, limit, precision_digits=2) > 0:
                raise ValidationError(_(
                    "%(type)s allows at most %(limit)s day(s) %(period)s. "
                    "This request would bring %(employee)s to %(taken)s day(s).",
                    type=leave_type.name,
                    limit='%g' % limit,
                    period=LIMIT_PERIOD_LABELS[period],
                    employee=leave.employee_id.name,
                    taken='%g' % round(taken, 2),
                ))
