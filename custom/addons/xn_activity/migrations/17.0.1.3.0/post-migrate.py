# -*- coding: utf-8 -*-
"""17.0.1.3.0: fewer indexes on the slot table.

Odoo keeps an index after index=True is removed from a field, so the three
single-column indexes this version stops declaring are dropped here. Their
queries are served by xn_activity_slot_day_idx (day_key, local_date) and
xn_activity_slot_device_date_idx (device_id, local_date), which the model's
init() creates during the upgrade, before this script runs.
"""
import logging

_logger = logging.getLogger(__name__)

DROPPED = [
    'xn_activity_slot__device_id_index',
    'xn_activity_slot__day_key_index',
    'xn_activity_slot__slot_start_index',
]


def migrate(cr, version):
    for name in DROPPED:
        cr.execute('DROP INDEX IF EXISTS "%s"' % name)
    _logger.info("xn_activity: dropped redundant slot indexes %s",
                 ', '.join(DROPPED))
