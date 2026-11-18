# -*- coding: utf-8 -*-
"""17.0.1.4.0

1. Windows / System flag on apps. New apps get the flag from SYSTEM_APPS
   when they are first seen; this sets it on apps that already exist (the
   preloaded list is noupdate, and apps such as 'widgets' were created by
   the ingest endpoint). Only apps still unflagged are touched, so a later
   manual change in the UI is not undone.
2. Board of Directors group. "View All Employees" was given by hand to the
   board; HR Officers have it only through implied_ids. Everyone who has it
   without HR rights is moved up to the new Board group, which alone sees
   the names in the dashboard's "Worth a conversation" panel.
"""
import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.xn_activity.models.activity_app import SYSTEM_APPS

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE xn_activity_app SET is_system = true
         WHERE name IN %s AND is_system IS NOT TRUE
    """, (tuple(sorted(SYSTEM_APPS)),))
    _logger.info("xn_activity: %s apps flagged Windows / System", cr.rowcount)

    env = api.Environment(cr, SUPERUSER_ID, {})
    viewer = env.ref('xn_activity.group_xn_activity_viewer')
    board = env.ref('xn_activity.group_xn_activity_board')
    hr_user = env.ref('hr.group_hr_user')
    users = viewer.with_context(active_test=False).users.filtered(
        lambda u: hr_user not in u.groups_id and board not in u.groups_id)
    if users:
        users.write({'groups_id': [(4, board.id)]})
    _logger.info("xn_activity: Board of Directors group given to %s",
                 ', '.join(users.mapped('login')) or 'nobody')
