# -*- coding: utf-8 -*-
import logging
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    xn_requested_by_id = fields.Many2one(
        'res.users', string='Requested By', tracking=True,
        default=lambda self: self.env.user,
        help="Who raised the purchase. Told when it is approved or rejected.")
    xn_employee_id = fields.Many2one(
        'hr.employee', string='For Employee', tracking=True,
        help="The employee the purchase is for, e.g. a new joiner's licence.")
    xn_approver_id = fields.Many2one(
        'res.users', string='Approver', readonly=True, copy=False,
        tracking=True,
        help="Set from the approval rules when the order is confirmed.")
    xn_approval_token = fields.Char(copy=False, readonly=True)
    xn_rejection_reason = fields.Text(
        string='Rejection Reason', readonly=True, copy=False)
    xn_review_url = fields.Char(compute='_compute_xn_review_url')
    xn_is_approver = fields.Boolean(compute='_compute_xn_is_approver')
    xn_paid_by_card = fields.Boolean(
        string='Paid by Card', tracking=True,
        help="Paid with a company card or similar, not by bank transfer, "
             "so no vendor bank account is needed.")
    xn_vendor_bank_id = fields.Many2one(
        'res.partner.bank', string='Vendor Bank Account', tracking=True,
        compute='_compute_xn_vendor_bank_id', store=True, readonly=False,
        domain="[('partner_id', '=', commercial_partner_id)]",
        help="Where the payment goes. Must be marked as trusted on the "
             "vendor's bank account before the order can be confirmed.")
    xn_vendor_bank_trusted = fields.Boolean(
        related='xn_vendor_bank_id.allow_out_payment', string='Bank Trusted')
    commercial_partner_id = fields.Many2one(
        related='partner_id.commercial_partner_id')

    @api.depends('partner_id')
    def _compute_xn_vendor_bank_id(self):
        for order in self:
            banks = order.partner_id.commercial_partner_id.bank_ids
            order.xn_vendor_bank_id = (
                banks.filtered('allow_out_payment')[:1] or banks[:1])

    @api.depends('xn_approval_token')
    def _compute_xn_review_url(self):
        for order in self:
            order.xn_review_url = order.xn_approval_token and (
                '%s/xn_purchase/review/%s?token=%s' % (
                    order.get_base_url(), order.id, order.xn_approval_token))

    @api.depends_context('uid')
    @api.depends('xn_approver_id')
    def _compute_xn_is_approver(self):
        for order in self:
            order.xn_is_approver = order.xn_approver_id == self.env.user

    # ------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------

    def _approval_allowed(self):
        """Orders governed by an approval rule need their named approver.

        Core lets any Purchase Manager approve. Once a rule has assigned an
        approver, only that user can approve, whatever their groups.
        """
        self.ensure_one()
        if self.xn_approver_id:
            return self.xn_approver_id == self.env.user
        return super()._approval_allowed()

    def _xn_check_payment_details(self):
        self.ensure_one()
        if self.xn_paid_by_card:
            return
        bank = self.xn_vendor_bank_id
        if not bank:
            raise UserError(_(
                "%(order)s: choose the vendor bank account the payment will "
                "go to, or tick 'Paid by Card'. Add the account on the "
                "vendor's contact (Accounting tab) if it is not there yet.",
                order=self.name))
        if not bank.allow_out_payment:
            raise UserError(_(
                "%(order)s: the bank account %(acc)s is not trusted yet. "
                "Confirm the details with %(vendor)s by phone, then someone "
                "with the 'Validate bank account' right marks it as trusted "
                "(Send Money) on the vendor's contact.",
                order=self.name, acc=bank.acc_number,
                vendor=self.partner_id.commercial_partner_id.name))

    def button_confirm(self):
        for order in self:
            if order.state not in ('draft', 'sent'):
                continue
            order._xn_check_payment_details()
            rule = self.env['xn.purchase.approval.rule']._xn_find_for_order(order)
            order.write({
                'xn_approver_id': rule.approver_id.id,
                'xn_approval_token': secrets.token_urlsafe(32) if rule else False,
                'xn_rejection_reason': False,
            })
        res = super().button_confirm()
        for order in self.filtered(
                lambda o: o.state == 'to approve' and o.xn_approver_id):
            order._xn_send_approval_request()
        return res

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        for order in self.filtered(lambda o: o.state in ('purchase', 'done')):
            order._xn_create_draft_bill()
        return res

    def button_draft(self):
        self.write({'xn_approver_id': False, 'xn_approval_token': False})
        return super().button_draft()

    def _xn_send_approval_request(self):
        self.ensure_one()
        template = self.env.ref('xn_purchase_approval.mail_template_approval_request')
        template.send_mail(self.id)
        self.message_post(body=_(
            "Approval requested from %s.", self.xn_approver_id.name))

    def xn_action_open_review(self):
        """Open the approval page from the backend form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.xn_review_url,
            'target': 'self',
        }

    def xn_reject(self, reason):
        """Send a pending order back to draft. Called by the review page."""
        self.ensure_one()
        if self.state != 'to approve' or not self._approval_allowed():
            raise UserError(_("You cannot reject this order."))
        approver = self.env.user
        self.write({
            'state': 'draft',
            'xn_rejection_reason': reason,
            'xn_approver_id': False,
            'xn_approval_token': False,
        })
        partners = (self.xn_requested_by_id | self.user_id).partner_id
        self.message_post(
            body=_("Rejected by %(user)s: %(reason)s",
                   user=approver.name, reason=reason),
            partner_ids=partners.ids,
            subtype_xmlid='mail.mt_comment')

    # ------------------------------------------------------------
    # Vendor bill
    # ------------------------------------------------------------

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.xn_vendor_bank_id and not self.xn_paid_by_card:
            vals['partner_bank_id'] = self.xn_vendor_bank_id.id
        return vals

    def _xn_create_draft_bill(self):
        """Create a draft vendor bill with the order's attachments.

        Only for lines billed on ordered quantity (services such as
        licences); goods billed on receipt wait for the receipt as usual.
        A failure here never blocks the approval -- it is noted instead.
        """
        self.ensure_one()
        if self.invoice_ids:
            return
        if self.invoice_status != 'to invoice':
            self.message_post(body=_(
                "No draft vendor bill yet: nothing is billable until the "
                "goods are received. For services such as licences, set the "
                "product's Control Policy to 'On ordered quantities' so the "
                "bill is created on approval."))
            return
        try:
            with self.env.cr.savepoint():
                self.action_create_invoice()
        except UserError as e:
            _logger.info("xn_purchase_approval: no draft bill for %s: %s",
                         self.name, e)
            self.message_post(body=_(
                "No draft vendor bill was created: %s", e.args[0]))
            return
        bills = self.invoice_ids.filtered(lambda m: m.state == 'draft')
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'purchase.order'), ('res_id', '=', self.id),
        ])
        for bill in bills:
            for att in attachments:
                att.copy({'res_model': 'account.move', 'res_id': bill.id})
            bill.message_post(body=_(
                "Created from %s after approval.", self._get_html_link()))
