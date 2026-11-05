# -*- coding: utf-8 -*-
import logging

from odoo import models, _

_logger = logging.getLogger(__name__)


class HrResignation(models.Model):
    _inherit = 'hr.resignation'

    def action_approve_resignation(self):
        """Start the exit checklist when a resignation is approved.

        The last working day is the approved one (confirmation date plus the
        contract's notice days), else the one the employee asked for. An
        employee who already has an exit checklist running is left alone.
        """
        res = super().action_approve_resignation()
        Checklist = self.env['xn.jl.checklist'].sudo()
        for resignation in self:
            lwd = (resignation.approved_revealing_date
                   or resignation.expected_revealing_date)
            if not lwd or Checklist.search_count([
                ('employee_id', '=', resignation.employee_id.id),
                ('process', '=', 'leave'),
                ('state', '=', 'running'),
            ]):
                continue
            checklist = Checklist.create({
                'employee_id': resignation.employee_id.id,
                'process': 'leave',
                'date': lwd,
                'exit_type': ('resignation' if resignation.resignation_type == 'resigned'
                              else 'termination'),
            })
            resignation.message_post(body=_(
                "Exit checklist started: %s steps, last working day %s.",
                len(checklist.task_ids), lwd))
            _logger.info("xn_joiner_leaver: exit checklist %s started from "
                         "resignation %s", checklist.id, resignation.id)
        return res
