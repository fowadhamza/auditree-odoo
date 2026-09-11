# -*- coding: utf-8 -*-
"""One-off backfill: set forecast.salary.plan.end_date for rows imported
before the end_date field existed. For each employee's cycles (ordered by
effective_date), each cycle's end_date is set to the day before the next
cycle's effective_date; the last (most recent) cycle is left ongoing (empty).

Run via: python3 odoo-bin shell --config=... -d DB < backfill_salary_plan_end_dates.py
"""
from datetime import timedelta

Plan = env['forecast.salary.plan']  # noqa: F821 - `env` injected by odoo-bin shell
plans = Plan.search([], order='employee_id, effective_date')

by_employee = {}
for plan in plans:
    by_employee.setdefault(plan.employee_id.id, []).append(plan)

updated = 0
for cycles in by_employee.values():
    for current, nxt in zip(cycles, cycles[1:]):
        current.end_date = nxt.effective_date - timedelta(days=1)
        updated += 1
    cycles[-1].end_date = False  # most recent cycle stays ongoing

env.cr.commit()
print('Backfilled end_date on %d salary plan rows.' % updated)
