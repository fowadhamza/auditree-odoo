# -*- coding: utf-8 -*-
"""17.0.1.2.0: meetings count as active.

The preloaded app list is noupdate, so the new "Count Idle as Active" flag
on Teams and Zoom is set here for databases installed before this version.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE xn_activity_app SET idle_as_active = true
         WHERE name IN ('ms-teams', 'teams', 'zoom')
           AND idle_as_active IS NOT TRUE
    """)
    _logger.info("xn_activity: idle counts as active for %s meeting apps",
                 cr.rowcount)
