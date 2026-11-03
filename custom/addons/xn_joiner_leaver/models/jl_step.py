# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .jl_role import ROLES

PROCESSES = [
    ('join', 'Joining'),
    ('leave', 'Leaving'),
]


class XnJlStep(models.Model):
    _name = 'xn.jl.step'
    _description = 'Joiner/Leaver Checklist Step'
    _order = 'process, sequence, id'

    name = fields.Char(required=True)
    process = fields.Selection(PROCESSES, required=True, default='join')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    code = fields.Char(string='KRA ID', help="Row in the KRA register, if any.")
    role = fields.Selection(
        ROLES, required=True, default='hr',
        help="Who gets the step. Reporting Manager is the employee's manager; "
             "if the manager has no Odoo user the step goes to HR.")
    anchor = fields.Selection([
        ('start', 'From the start of the checklist'),
        ('date', 'From the joining date / last working day'),
        ('after', 'From when another step is done'),
    ], required=True, default='start')
    days = fields.Integer(
        string='Working Days',
        help="Working days after the anchor; negative for before (e.g. -1 = "
             "the working day before the joining date).")
    after_step_id = fields.Many2one(
        'xn.jl.step', string='After Step', ondelete='restrict',
        domain="[('process', '=', process), ('id', '!=', id)]")
    exit_types = fields.Selection([
        ('all', 'All exits'),
        ('resignation', 'Resignations only'),
        ('termination', 'Terminations only'),
    ], string='Applies To', default='all',
        help="Leaving steps only.")
    condition = fields.Selection([
        ('bond', 'Only when a bond is required'),
    ], help="Leave empty for a step every checklist gets.")
    external = fields.Boolean(
        string='Waits on Someone Outside',
        help="The step waits on the candidate, the leaver or a courier. The "
             "owner gets reminders to chase it, but it is never escalated.")
    escalate_after = fields.Integer(
        string='Escalate After (working days late)', default=2,
        help="0 escalates on the first working day the step is late.")
    urgent = fields.Boolean(
        help="Alert the owner and the Operations Manager on the evening of "
             "the due date if the step is still open (e.g. disabling access).")
    proof_required = fields.Char(
        string='Proof',
        help="What must be attached before the step can be marked done. "
             "Leave empty when no attachment is needed.")
    note = fields.Text(help="Shown on the task.")

    @api.constrains('anchor', 'after_step_id', 'process')
    def _check_after_step(self):
        for step in self:
            if step.anchor == 'after' and not step.after_step_id:
                raise ValidationError(_(
                    "\"%s\" runs after another step: choose which one.", step.name))
            if step.after_step_id and step.after_step_id.process != step.process:
                raise ValidationError(_(
                    "\"%s\" can only follow a step of the same process.", step.name))
            seen = step
            prev = step.after_step_id
            while prev:
                if prev in seen:
                    raise ValidationError(_(
                        "\"%s\" depends on itself through its After Step chain.",
                        step.name))
                seen |= prev
                prev = prev.after_step_id

    @api.constrains('escalate_after')
    def _check_escalate_after(self):
        if any(step.escalate_after < 0 for step in self):
            raise ValidationError(_("Escalate After cannot be negative."))
