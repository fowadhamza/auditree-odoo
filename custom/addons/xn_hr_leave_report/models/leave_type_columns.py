# -*- coding: utf-8 -*-
"""Shared leave-type column definitions for the wide-format reports.

Leave types are resolved by NAME, not hardcoded database id - auto-generated
ids are not portable across environments (dev, staging, a fresh DR restore
can all assign different ids to the same leave type). See
hr_leave_balance_report.py for the incident this fixes.

Adding a new leave type to either wide report means adding an entry here
and running an -u upgrade on xn_hr_leave_report. A SQL view requires a
fixed, known-at-creation-time column list, so a per-type column can't
appear automatically without a schema (and therefore code) change
somewhere.
"""
import logging

_logger = logging.getLogger(__name__)

# (column_prefix, leave type name, output label)
LEAVE_TYPE_COLUMNS = [
    ('casual', 'Casual Leave', 'Casual'),
    ('sick', 'Sick Leave', 'Sick'),
    ('earned', 'Earned Leave balance b/f', 'Earned b/f'),
    ('maternity', 'Maternity Leave', 'Maternity'),
    ('compoff', 'Comp-off', 'Comp-off'),
]


def resolve_leave_type_ids(cr):
    """Look up each configured leave type's database id by name.

    Returns a dict of column_prefix -> id (or None if that type is
    missing/inactive in this database - a warning is logged and the
    caller is expected to treat None as "match nothing").
    """
    type_ids = {}
    for key, name, _label in LEAVE_TYPE_COLUMNS:
        cr.execute(
            "SELECT id FROM hr_leave_type WHERE name->>'en_US' = %s AND active = True LIMIT 1",
            (name,),
        )
        row = cr.fetchone()
        if not row:
            _logger.warning(
                "xn_hr_leave_report: leave type '%s' not found (or inactive) in "
                "this database - its columns will show zero. Check Time Off > "
                "Configuration > Time Off Types.", name,
            )
            type_ids[key] = None
        else:
            type_id = row[0]
            assert isinstance(type_id, int)
            type_ids[key] = type_id
    return type_ids


def sql_id_literal(type_ids, key):
    """SQL literal for a leave type id, or NULL if unresolved (a FILTER on
    `= NULL` never matches, so the aggregate safely comes out as 0)."""
    type_id = type_ids[key]
    return str(type_id) if type_id is not None else 'NULL'
