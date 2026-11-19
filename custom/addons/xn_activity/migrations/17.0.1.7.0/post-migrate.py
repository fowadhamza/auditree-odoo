# -*- coding: utf-8 -*-
"""17.0.1.7.0

Smarter Target labels: In Progress for today, Weekend / Holiday / On Leave
instead of a grade, half the target on half-day leave, less the hours of
hourly leave. Existing rows get the new columns (leave kind, leave hours,
day target) and their new label:

1. Days whose 5-minute data is still stored are rebuilt, which reads leave
   again and fills leave_kind / leave_hours.
2. Every row is then re-graded from its stored columns (this also covers
   older days whose 5-minute data is gone).
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Day = env['xn.activity.day']
    cr.execute("SELECT DISTINCT day_key, local_date FROM xn_activity_slot")
    pairs = cr.fetchall()
    Day._xn_recompute(pairs)
    graded = Day._xn_refresh_status()
    cr.execute("""SELECT productive_status, count(*) FROM xn_activity_day
                  GROUP BY 1 ORDER BY 1""")
    _logger.info("xn_activity: rebuilt %s days, re-graded %s rows: %s",
                 len(pairs), graded, cr.fetchall())
