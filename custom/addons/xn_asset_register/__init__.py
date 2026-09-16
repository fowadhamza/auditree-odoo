# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)


def _strip_inherited_equipment_manager(env):
    """Remove Equipment Manager from users who never chose to have it.

    hr_maintenance grants maintenance.group_equipment_manager to every HR
    Officer through implied_ids. The security data undoes that implication,
    but Odoo materialises implied groups into res.groups.users when the
    implication is created and does not walk them back when it is removed --
    so on a database where hr_maintenance has already been installed the HR
    Officers keep the group directly.

    They would not see the Maintenance menus, which are gated on Asset
    Register Manager, but they would still get the Equipment smart button on
    employee forms and the cost field. Neither was asked for.

    Only users who do not hold Asset Register Manager are touched, so the
    people genuinely responsible for the register are unaffected.
    """
    equipment_manager = env.ref('maintenance.group_equipment_manager',
                                raise_if_not_found=False)
    register_manager = env.ref('xn_asset_register.group_asset_register_manager',
                               raise_if_not_found=False)
    if not equipment_manager or not register_manager:
        return

    strip = equipment_manager.users - register_manager.users
    # Never lock out the superuser; it holds the group by way of base data.
    strip -= env.ref('base.user_root', raise_if_not_found=False) or env['res.users']
    if not strip:
        return

    equipment_manager.sudo().write({'users': [(3, u.id) for u in strip]})
    _logger.info(
        "xn_asset_register: removed Equipment Manager from %d user(s) who "
        "inherited it from the HR Officer role: %s",
        len(strip), ', '.join(sorted(strip.mapped('login'))))


def post_init_hook(env):
    _strip_inherited_equipment_manager(env)
