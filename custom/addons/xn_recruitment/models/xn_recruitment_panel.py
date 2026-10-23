# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .hr_recruitment_stage import INTERVIEW_ROUNDS, ROUND_ORDER, ROUNDS


class XnRecruitmentPanel(models.Model):
    _name = 'xn.recruitment.panel'
    _description = 'Interview Panel'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    line_ids = fields.One2many(
        'xn.recruitment.panel.line', 'panel_id', string='Interviewers per Round', copy=True)
    job_ids = fields.One2many('hr.job', 'xn_panel_id', string='Job Positions')

    def _xn_interviewers(self, round_key):
        """Active internal users who interview in round_key on this panel."""
        self.ensure_one()
        users = self.line_ids.filtered(lambda line: line.round == round_key).user_ids
        return users.filtered(lambda user: user.active and not user.share)


class XnRecruitmentPanelLine(models.Model):
    _name = 'xn.recruitment.panel.line'
    _description = 'Interview Panel Round'
    _order = 'round_order, id'

    panel_id = fields.Many2one(
        'xn.recruitment.panel', required=True, ondelete='cascade', index=True)
    round = fields.Selection(
        [(key, label) for key, label in ROUNDS if key in INTERVIEW_ROUNDS],
        required=True)
    round_order = fields.Integer(compute='_compute_round_order', store=True)
    user_ids = fields.Many2many(
        'res.users', string='Interviewers', domain=[('share', '=', False)])

    _sql_constraints = [
        ('panel_round_uniq', 'unique(panel_id, round)',
         'Each round can appear only once per panel.'),
    ]

    @api.depends('round')
    def _compute_round_order(self):
        for line in self:
            line.round_order = ROUND_ORDER.get(line.round, 0)
