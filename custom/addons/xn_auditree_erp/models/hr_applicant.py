from odoo import models, fields, api


class HRApplicant(models.Model):
    _inherit = "hr.applicant"

    is_hired_stage=fields.Boolean(related='stage_id.hired_stage',string="Is hire stage",store=True)
    is_hide_revert_back=fields.Boolean(compute="_compute_hide_revert_back",string="Is Hide Revert Back")

    AVAILABLE_PRIORITIES = [
        ('0', 'Not Eligible'),
        ('1', 'Not Eligible'),
        ('2', 'Poor'),
        ('3', 'Average'),
        ('4', 'Good'),
        ('5', 'Excellent')
    ]

    priority = fields.Selection(AVAILABLE_PRIORITIES, "Evaluation", default='0')

    @api.depends('stage_id')
    def _compute_hide_revert_back(self):
        for rec in self:
            rec.is_hide_revert_back = rec.stage_id.sequence == 0

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            for rec in self:
                rec._send_stage_approval_email()
        return res

    def _send_stage_approval_email(self):
        self.ensure_one()
        if not self.stage_id:
            return
        template = self.env.ref('xn_auditree_erp.email_template_job_appli_approve', raise_if_not_found=False)
        if not template:
            return
        approver_line = self.department_id.stage_approval_lines.filtered(lambda l: l.stage_id.id == self.stage_id.id)
        email_to = approver_line.approve_user_ids.partner_id.ids
        if email_to:
            template.send_mail(self.id, force_send=True, email_values={'recipient_ids': email_to})



    def approve_and_move_next(self):
        for rec in self:
             stage_ids = self.env['hr.recruitment.stage'].search([
                 '|',
                 ('job_ids', '=', False),
                 ('job_ids', '=', rec.job_id.id),

             ], order='sequence asc')
             sequences=stage_ids.mapped('sequence')
             next_sequence=rec.stage_id.sequence+1
             print("next_sequence",next_sequence,sequences)
             if next_sequence in sequences:
                 next_stage=stage_ids.filtered(lambda r: r.sequence == next_sequence)
                 print("next_stage",next_stage.name)
                 rec.update({'stage_id':next_stage.id})

    def revert_and_move_back(self):
        for rec in self:
            stage_ids = self.env['hr.recruitment.stage'].search([
                '|',
                ('job_ids', '=', False),
                ('job_ids', '=', rec.job_id.id),

            ], order='sequence asc')
            sequences = stage_ids.mapped('sequence')
            next_sequence = rec.stage_id.sequence - 1
            if next_sequence in sequences:
                next_stage = stage_ids.filtered(lambda r: r.sequence == next_sequence)
                rec.update({'stage_id': next_stage.id})
