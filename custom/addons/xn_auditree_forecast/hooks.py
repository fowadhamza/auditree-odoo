# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Firm partners this module is restricted to. Update here if partners change.
FORECAST_USER_LOGINS = [
    'sharook.mohamed@auditree.com',
    'fowad.hamza@auditree.com',
    'athif.azad@auditree.com',
    'syed.faraz@auditree.com',
]


def post_init_hook(env):
    """Best-effort: grant the Forecast User group to the known partner logins.

    Never fails install - if a login is missing, log a warning so an admin can
    assign the group manually from Settings > Users & Companies > Groups.
    """
    group = env.ref('xn_auditree_forecast.group_forecast_user', raise_if_not_found=False)
    if not group:
        return
    users = env['res.users'].search([('login', 'in', FORECAST_USER_LOGINS)])
    found_logins = users.mapped('login')
    missing = [login for login in FORECAST_USER_LOGINS if login not in found_logins]
    if missing:
        _logger.warning(
            "xn_auditree_forecast: no user found for login(s) %s; "
            "assign the 'Forecast User' group to them manually.", missing)
    if users:
        group.write({'users': [(4, u.id) for u in users]})
