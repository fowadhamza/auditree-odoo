# -*- coding: utf-8 -*-
from . import controllers
from . import models

# Shared IT mailbox login: on the IT team even though it is a shared account.
IT_TEAM_LOGINS = ['it@auditree.com']


def post_init_hook(env):
    """Turn off helpdesk_mgmt's auto-assignment and seed the IT team.

    helpdesk_mgmt assigns a new ticket to whoever creates it by default, which
    would make every employee the assignee of their own ticket. The IT team
    starts with whoever already holds the Helpdesk User group (the admin, at
    install time) plus the logins in IT_TEAM_LOGINS that exist in this
    database; the IT administrator adds the rest.
    """
    env['res.company'].search([]).write({'helpdesk_mgmt_ticket_auto_assign': False})

    group = env.ref('helpdesk_mgmt.group_helpdesk_user')
    it_logins = env['res.users'].search([('login', 'in', IT_TEAM_LOGINS)])
    if it_logins:
        group.write({'users': [(4, user.id) for user in it_logins]})

    team = env.ref('xn_it_helpdesk.team_it_support', raise_if_not_found=False)
    agents = group.users.filtered(lambda u: u.active and not u.share)
    if team and agents:
        team.write({'user_ids': [(4, user.id) for user in agents]})
