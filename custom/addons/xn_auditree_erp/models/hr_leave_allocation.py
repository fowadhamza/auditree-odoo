# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    @api.model_create_multi
    def create(self, vals_list):
        allocations = super().create(vals_list)
        if not self.env.context.get('import_file'):
            allocations._xn_notify_leave_approver()
        return allocations

    def _xn_notify_leave_approver(self):
        """Email the employee's Time Off approver about a new allocation request.

        Only single-employee requests still awaiting approval are notified:
        auto-validated types and HR bulk grants (company / department / tag /
        multi-employee) are skipped, as is an approver requesting for themselves.
        The mail is queued, so a mail-server problem never blocks the request.
        """
        template = self.env.ref(
            'xn_auditree_erp.email_template_leave_allocation_request',
            raise_if_not_found=False)
        if not template:
            return
        for allocation in self:
            if allocation.state != 'confirm' or allocation.holiday_type != 'employee':
                continue
            if allocation.multi_employee or not allocation.employee_id:
                continue
            approver = allocation.employee_id.leave_manager_id
            if not approver or not approver.partner_id.email or approver == self.env.user:
                continue
            try:
                template.sudo().send_mail(
                    allocation.id,
                    email_values={'recipient_ids': [(4, approver.partner_id.id)]})
            except Exception:
                _logger.warning(
                    "Could not queue allocation request email for allocation %s",
                    allocation.id, exc_info=True)
