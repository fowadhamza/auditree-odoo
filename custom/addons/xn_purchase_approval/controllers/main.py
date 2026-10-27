# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq


class XnPurchaseReview(http.Controller):
    """Approval page for purchase orders.

    The approver does not need Purchase access rights, so the order is read
    with sudo -- but only after checking that the logged-in user is the
    order's approver and the link's token matches. Approve and Reject are
    POSTs (with CSRF), never GETs: Outlook Safe Links and similar scanners
    open every link in an email, and must not be able to approve anything.
    """

    def _xn_get_order(self, order_id, token):
        order = request.env['purchase.order'].sudo().browse(order_id).exists()
        if (not order or not order.xn_approval_token or not token
                or not consteq(order.xn_approval_token, token)
                or order.xn_approver_id != request.env.user):
            raise NotFound()
        return order

    def _xn_attachments(self, order):
        return request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'purchase.order'), ('res_id', '=', order.id),
        ])

    def _xn_render(self, order, token, error=None):
        return request.render('xn_purchase_approval.review_page', {
            'order': order,
            'token': token,
            'attachments': self._xn_attachments(order),
            'lines': order.order_line.filtered(lambda l: not l.display_type),
            'error': error,
        })

    @http.route('/xn_purchase/review/<int:order_id>', type='http',
                auth='user', methods=['GET'])
    def review(self, order_id, token=None, **kw):
        return self._xn_render(self._xn_get_order(order_id, token), token)

    @http.route('/xn_purchase/review/<int:order_id>/approve', type='http',
                auth='user', methods=['POST'])
    def approve(self, order_id, token=None, **kw):
        order = self._xn_get_order(order_id, token)
        if order.state == 'to approve':
            order.button_approve()
        return self._xn_render(order, token)

    @http.route('/xn_purchase/review/<int:order_id>/reject', type='http',
                auth='user', methods=['POST'])
    def reject(self, order_id, token=None, reason=None, **kw):
        order = self._xn_get_order(order_id, token)
        reason = (reason or '').strip()
        if not reason:
            return self._xn_render(
                order, token, error=_("Please give a reason for rejecting."))
        if order.state == 'to approve':
            try:
                order.xn_reject(reason)
            except UserError as e:
                return self._xn_render(order, token, error=e.args[0])
        return request.render('xn_purchase_approval.review_done', {
            'order': order,
            'message': _("%s was rejected and sent back to %s.",
                         order.name,
                         order.xn_requested_by_id.name or _("the requester")),
        })

    @http.route('/xn_purchase/review/<int:order_id>/attachment/<int:att_id>',
                type='http', auth='user', methods=['GET'])
    def attachment(self, order_id, att_id, token=None, **kw):
        order = self._xn_get_order(order_id, token)
        att = self._xn_attachments(order).filtered(lambda a: a.id == att_id)
        if not att:
            raise NotFound()
        return request.env['ir.binary']._get_stream_from(att).get_response()
