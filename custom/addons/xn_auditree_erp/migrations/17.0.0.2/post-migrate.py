# -*- coding: utf-8 -*-
"""Move half-day requests to the First Day / Last Day dropdowns.

The two checkboxes "First Day: Afternoon Only" (xn_start_half) and "Last Day:
Morning Only" (xn_end_half) were replaced by the xn_first_day / xn_last_day
selections, which also allow a morning-only first day and an afternoon-only
last day. Requests saved with a checkbox ticked get the equivalent dropdown
value, so their dates and durations do not change; the old columns are then
dropped (Odoo leaves the columns of removed fields behind).
"""
import logging

_logger = logging.getLogger(__name__)


def _has_column(cr, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'hr_leave' AND column_name = %s
    """, (column,))
    return bool(cr.fetchone())


def migrate(cr, version):
    """Copy xn_start_half / xn_end_half into xn_first_day / xn_last_day."""
    for old, new, value in (('xn_start_half', 'xn_first_day', 'pm'),
                            ('xn_end_half', 'xn_last_day', 'am')):
        if not _has_column(cr, old):
            continue
        cr.execute(f"UPDATE hr_leave SET {new} = %s WHERE {old} IS TRUE", (value,))
        _logger.info("xn_auditree_erp: %s request(s) moved from %s to %s = %s",
                     cr.rowcount, old, new, value)
        cr.execute(f"ALTER TABLE hr_leave DROP COLUMN {old}")
