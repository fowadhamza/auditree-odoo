# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

# Who does each role's steps, matched by login.
ROLE_LOGINS = {
    'hr': 'shaik.danyal@auditree.com',
    'hr_head': 'sharook.mohamed@auditree.com',
    'ops': 'ghazala.nishath@auditree.com',
    'accounts': 'ayesha.siddiqua@auditree.com',
    'it': 'it@auditree.com',
    'admin': 'mohammed.junaid@auditree.com',
}


def post_init_hook(env):
    """Fill the roles from ROLE_LOGINS and give the role holders access.

    A missing user leaves the role empty and is logged; it does not stop
    the install.
    """
    Users = env['res.users']
    roles = env['xn.jl.role'].search([])
    for role in roles:
        login = ROLE_LOGINS.get(role.code)
        if not login or role.user_id:
            continue
        user = Users.search([
            '|', ('login', '=ilike', login), ('email', '=ilike', login),
        ], limit=1)
        if user:
            role.user_id = user
        else:
            _logger.info("xn_joiner_leaver: no user %s, role %s left empty",
                         login, role.code)
    users = roles.user_id
    group = env.ref('project.group_project_user')
    missing = users.filtered(lambda u: group not in u.groups_id)
    if missing:
        missing.write({'groups_id': [(4, group.id)]})
        _logger.info("xn_joiner_leaver: granted Project User to %s",
                     ', '.join(missing.mapped('login')))
    # HR and the Operations Manager follow the project, so they see every
    # step, not only their own. The HR Head only follows the LWD step.
    project = env.ref('xn_joiner_leaver.project_joiner_leaver')
    watchers = roles.filtered(lambda r: r.code in ('hr', 'ops')).user_id
    if watchers:
        project.message_subscribe(partner_ids=watchers.partner_id.ids)
