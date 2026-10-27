# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    xn_period_start = fields.Date(
        string='Period From',
        help="First day billed, e.g. a new joiner's start date.")
    xn_period_end = fields.Date(
        string='Period To',
        help="Last day billed, normally the day before the vendor's next "
             "billing date.")
    xn_monthly_price = fields.Float(
        string='Monthly Price', digits='Product Price',
        help="Price for one full month. With a period set, the unit price "
             "becomes the pro-rata share: monthly price x days billed / days "
             "in the billing month that ends on 'Period To'.")
    xn_period_days = fields.Integer(
        string='Days', compute='_compute_xn_period_days')

    @api.depends('xn_period_start', 'xn_period_end')
    def _compute_xn_period_days(self):
        for line in self:
            if line.xn_period_start and line.xn_period_end:
                line.xn_period_days = (
                    line.xn_period_end - line.xn_period_start).days + 1
            else:
                line.xn_period_days = 0

    @api.constrains('xn_period_start', 'xn_period_end')
    def _check_xn_period(self):
        for line in self:
            if (line.xn_period_start and line.xn_period_end
                    and line.xn_period_end < line.xn_period_start):
                raise ValidationError(_(
                    "'Period To' cannot be before 'Period From'."))

    @api.model
    def _xn_prorata_price(self, monthly_price, start, end):
        """Pro-rata share of ``monthly_price`` for ``start``..``end``.

        The billing month is the one ending on ``end``: a period ending on
        8 Nov is billed against 9 Oct - 8 Nov (31 days), so 27 Oct - 8 Nov
        is 13/31 of a month.
        """
        cycle_start = end + relativedelta(days=1, months=-1)
        cycle_days = (end - cycle_start).days + 1
        days = (end - start).days + 1
        return monthly_price * days / cycle_days

    @api.depends('xn_monthly_price', 'xn_period_start', 'xn_period_end')
    def _compute_price_unit_and_date_planned_and_name(self):
        # Core resets price_unit to the vendor pricelist whenever the
        # quantity changes; re-apply the pro-rata price on top. price_unit
        # stays editable, so the vendor's PI figure can still be typed over
        # it when their rounding differs.
        super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            if not line.xn_monthly_price or line.invoice_lines:
                continue
            if line.xn_period_start and line.xn_period_end \
                    and line.xn_period_end >= line.xn_period_start:
                line.price_unit = self._xn_prorata_price(
                    line.xn_monthly_price, line.xn_period_start,
                    line.xn_period_end)
            else:
                line.price_unit = line.xn_monthly_price

    def _prepare_account_move_line(self, move=False):
        vals = super()._prepare_account_move_line(move=move)
        if self.xn_period_start and self.xn_period_end:
            vals['name'] = '%s (%s - %s)' % (
                vals.get('name') or self.name,
                self.xn_period_start.strftime('%d %b %Y'),
                self.xn_period_end.strftime('%d %b %Y'))
        return vals
