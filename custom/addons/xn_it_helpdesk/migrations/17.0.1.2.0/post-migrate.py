# -*- coding: utf-8 -*-
"""Management approval: seed the IT Support team's Default Approver.

The post_init_hook only runs on a fresh install; databases that already
have the module get the same seed here.
"""
from odoo import api, SUPERUSER_ID
from odoo.addons.xn_it_helpdesk import set_default_approver


def migrate(cr, version):
    if not version:
        return
    set_default_approver(api.Environment(cr, SUPERUSER_ID, {}))
