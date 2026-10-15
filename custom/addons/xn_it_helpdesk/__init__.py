# -*- coding: utf-8 -*-
from . import controllers
from . import models

# Shared IT mailbox login: on the IT team even though it is a shared account.
IT_TEAM_LOGINS = ['it@auditree.com']

# Production trial: the only employees given "Raise IT Tickets" on install.
# Going live means giving that group to everyone; edit nothing here for that.
TRIAL_REQUESTER_LOGINS = ['junaid.k@auditree.com', 'ayesha.siddiqua@auditree.com']


def post_init_hook(env):
    """Turn off helpdesk_mgmt's auto-assignment and seed the users.

    helpdesk_mgmt assigns a new ticket to whoever creates it by default, which
    would make every employee the assignee of their own ticket. The IT team
    starts with whoever already holds the Helpdesk User group (the admin, at
    install time) plus the logins in IT_TEAM_LOGINS; requesters start with
    TRIAL_REQUESTER_LOGINS. Logins missing from this database are skipped.
    """
    env['res.company'].search([]).write({'helpdesk_mgmt_ticket_auto_assign': False})
    Users = env['res.users'].with_context(active_test=False)

    it_group = env.ref('helpdesk_mgmt.group_helpdesk_user')
    it_users = Users.search([('login', 'in', IT_TEAM_LOGINS)])
    if it_users:
        it_group.write({'users': [(4, user.id) for user in it_users]})

    trial_users = Users.search([('login', 'in', TRIAL_REQUESTER_LOGINS)])
    if trial_users:
        env.ref('xn_it_helpdesk.group_xn_helpdesk_requester').write(
            {'users': [(4, user.id) for user in trial_users]})

    team = env.ref('xn_it_helpdesk.team_it_support', raise_if_not_found=False)
    agents = it_group.users.filtered(lambda u: u.active and not u.share)
    if team and agents:
        team.write({'user_ids': [(4, user.id) for user in agents]})
