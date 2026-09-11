# -*- coding: utf-8 -*-
from . import models

# The vendor dashboard's own menu, hidden while this module is installed so a
# database carrying both does not show two identical "Dashboard" apps. Absent
# on any database without hrms_dashboard, where both hooks simply do nothing.
VENDOR_MENU = "hrms_dashboard.hrms_dashboard_menu_root"


def _set_vendor_menu(env, active):
    menu = env.ref(VENDOR_MENU, raise_if_not_found=False)
    if menu:
        menu.sudo().active = active


def post_init_hook(env):
    _set_vendor_menu(env, False)


def uninstall_hook(env):
    """Put the vendor menu back, so uninstalling leaves no trace."""
    _set_vendor_menu(env, True)
