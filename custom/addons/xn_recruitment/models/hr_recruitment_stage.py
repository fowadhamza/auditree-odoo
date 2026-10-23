# -*- coding: utf-8 -*-
from odoo import api, fields, models

# The hiring steps HR works with, in order. Stages are matched to a step by
# xn_round, never by name or id, so HR can rename stages freely.
ROUNDS = [
    ('cold_call', 'Cold Call Shortlist'),
    ('hr_call', 'HR Initial Call'),
    ('round1', 'Round 1'),
    ('round2', 'Round 2'),
    ('final', 'Final Round'),
    ('decision', 'Decision Making'),
    ('offer', 'Selected / Offer'),
    ('joined', 'Joined'),
]
ROUND_ORDER = {key: index + 1 for index, (key, _label) in enumerate(ROUNDS)}
ROUND_LABELS = dict(ROUNDS)

# Steps with an interviewer: entering one hands the candidate to its panel.
INTERVIEW_ROUNDS = ('round1', 'round2', 'final', 'decision')


class HrRecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    xn_round = fields.Selection(
        ROUNDS, string='Hiring Step',
        help="Which step of the Auditree hiring process this stage is. Interview "
             "rounds email the job's interview panel; the step order drives the "
             "hiring reports.")
    xn_round_order = fields.Integer(
        compute='_compute_xn_round_order', store=True, string='Step Order')

    @api.depends('xn_round')
    def _compute_xn_round_order(self):
        for stage in self:
            stage.xn_round_order = ROUND_ORDER.get(stage.xn_round, 0)
