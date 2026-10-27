# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from odoo.addons.xn_recruitment.hooks import _setup_handover_cc


def migrate(cr, version):
    """Existing databases: fill the handover Cc list (the hook only runs on install)."""
    if not version:
        return
    _setup_handover_cc(api.Environment(cr, SUPERUSER_ID, {}))
