# -*- coding: utf-8 -*-
from odoo import models, api, _
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
        """Notify the employee's Time Off approver about a new allocation request.

        The approver gets an approval activity (systray clock icon), which core
        hr_holidays marks done on approval and removes on refusal, plus an email.
        Only single-employee requests still awaiting approval are notified:
        auto-validated types and HR bulk grants (company / department / tag /
        multi-employee) are skipped, as is an approver requesting for themselves.
        The mail is queued, so a mail-server problem never blocks the request.
        """
        template = self.env.ref(
            'xn_auditree_erp.email_template_leave_allocation_request',
            raise_if_not_found=False)
        for allocation in self:
            if allocation.state != 'confirm' or allocation.holiday_type != 'employee':
                continue
            if allocation.multi_employee or not allocation.employee_id:
                continue
            approver = allocation.employee_id.leave_manager_id
            if not approver or approver == self.env.user:
                continue
            allocation._xn_schedule_approver_activity(approver)
            if not template or not approver.partner_id.email:
                continue
            try:
                template.sudo().send_mail(
                    allocation.id,
                    email_values={'recipient_ids': [(4, approver.partner_id.id)]})
            except Exception:
                _logger.warning(
                    "Could not queue allocation request email for allocation %s",
                    allocation.id, exc_info=True)

    def _xn_schedule_approver_activity(self, approver):
        """Give the approver an approval activity unless core already did.

        Core only schedules one for the leave type's responsible_ids. Created
        with mail_activity_quick_update so the activity does not send its own
        "assigned to you" email on top of the request email.
        """
        self.ensure_one()
        activity_type = self.env.ref(
            'hr_holidays.mail_act_leave_allocation_approval', raise_if_not_found=False)
        if not activity_type:
            return
        existing = self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == approver)
        if existing:
            return
        try:
            self.sudo().with_context(mail_activity_quick_update=True).activity_schedule(
                activity_type_id=activity_type.id,
                user_id=approver.id,
                note=_('New Allocation Request from %(employee)s: %(count)s Days of %(type)s',
                       employee=self.employee_id.name,
                       count=self.number_of_days_display,
                       type=self.holiday_status_id.name))
        except Exception:
            _logger.warning(
                "Could not schedule approval activity for allocation %s",
                self.id, exc_info=True)
