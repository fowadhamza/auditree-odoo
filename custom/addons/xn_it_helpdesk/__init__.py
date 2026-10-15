# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Turn off helpdesk_mgmt's auto-assignment and seed the IT team.

    helpdesk_mgmt assigns a new ticket to whoever creates it by default, which
    would make every employee the assignee of their own ticket. The IT team
    starts with whoever already holds the Helpdesk User group (the admin, at
    install time); the IT administrator adds the rest.
    """
    env['res.company'].search([]).write({'helpdesk_mgmt_ticket_auto_assign': False})
    team = env.ref('xn_it_helpdesk.team_it_support', raise_if_not_found=False)
    agents = env.ref('helpdesk_mgmt.group_helpdesk_user').users.filtered(
        lambda u: u.active and not u.share)
    if team and agents:
        team.write({'user_ids': [(4, user.id) for user in agents]})
