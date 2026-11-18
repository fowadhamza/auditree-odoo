# -*- coding: utf-8 -*-
"""17.0.1.4.0: Windows / System flag on apps.

New apps get the flag from SYSTEM_APPS when they are first seen; this sets
it on apps that already exist (the preloaded list is noupdate, and apps
such as 'widgets' were created by the ingest endpoint). Only apps still
unflagged are touched, so a later manual change in the UI is not undone.
"""
import logging

from odoo.addons.xn_activity.models.activity_app import SYSTEM_APPS

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE xn_activity_app SET is_system = true
         WHERE name IN %s AND is_system IS NOT TRUE
    """, (tuple(sorted(SYSTEM_APPS)),))
    _logger.info("xn_activity: %s apps flagged Windows / System", cr.rowcount)
