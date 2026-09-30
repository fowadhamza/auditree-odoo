# -*- coding: utf-8 -*-
"""Shared balance SQL generation, used by both hr.leave.balance.report
(as-of-today) and hr.leave.balance.snapshot (as-of-any-month). Kept in one
place because this math is genuinely tricky and the two reports diverging
from each other silently is exactly the bug this module exists to prevent.

Goal: both reports show the same number as Odoo's own Time Off dashboard
(hr.leave.type.get_allocation_data -> virtual_remaining_leaves). That
dashboard is what employees see and what Odoo checks when a request is
submitted, so a report that disagrees with it is wrong by definition. The
rules below mirror hr.employee._get_consumed_leaves in hr_holidays:

1. Only allocations that are VALID on the target date count
   (date_from <= target <= date_to, or no date_to). An expired allocation
   contributes nothing, even if days were left on it.
2. Nothing carries over from one allocation to the next. Odoo only carries
   over inside a single allocation, at its own carry-over date. If staff are
   meant to keep unused days from a previous year, HR must record them as an
   allocation - see CARRY_OVER_ACROSS_ALLOCATIONS below.
3. Requests waiting for approval (confirm / validate1) are subtracted
   together with approved ones - the dashboard's "virtual" balance.
4. One-time/manual allocations: for "right now" (target date >= today),
   every request inside the allocation's period counts, including ones
   booked for a future date - the dashboard does the same. Accrual
   allocations: a request dated after the target date is never charged -
   Odoo does not charge future requests to an accrual either, since the
   days for them have not accrued yet. For a past month-end, only requests
   dated on or before that month-end count, so a historical row is not
   reduced by leave taken later.
5. Accrual allocations: for "right now" the allocation's stored
   number_of_days is used - it is exactly what Odoo's accrual cron has
   granted, proration included. For a past month-end there is no stored
   history, so it is projected (monthly rate x months elapsed, capped by the
   plan maximum and by what has actually been granted to date).
6. Overdraft: if the leave type allows a negative balance and an employee
   took more APPROVED leave than an EARLIER accrual allocation granted,
   Odoo keeps subtracting that excess from the current figure. So does this
   SQL. Requests still pending on an expired allocation are not counted.

Units: the dashboard shows hour-based types (Comp-off) in hours; these
reports always show days.
"""

# Odoo carries nothing from one allocation to the next. Set to True only if
# the reports should ADD unused days from the preceding accrual period
# (capped by that period's plan rules), which makes them disagree with the
# Time Off dashboard unless HR records the same carry-over as an allocation.
CARRY_OVER_ACROSS_ALLOCATIONS = False

# Leave states the dashboard subtracts: approved plus waiting for approval.
COUNTED_LEAVE_STATES = "('confirm', 'validate1', 'validate')"


def leave_cutoff_expr(month_end_expr):
    """Latest leave date that counts for a target date: no limit when the
    target is today or later (rule 4), otherwise the target date itself."""
    return (
        "(CASE WHEN {m} >= CURRENT_DATE THEN 'infinity'::date ELSE {m} END)"
        .format(m=month_end_expr)
    )


def build_accrual_ctes(type_id, key):
    """SQL text for the per-period metadata + carry-over CTEs for one leave
    type. These are period-level (per allocation row), independent of any
    particular 'as of' date, so both callers can share them unchanged.
    """
    if CARRY_OVER_ACROSS_ALLOCATIONS:
        carryover_sql = (
            "COALESCE(LAG(own_carryover_contribution) "
            "OVER (PARTITION BY employee_id ORDER BY date_from), 0)"
        )
    else:
        carryover_sql = "0"
    return """
        accrual_meta_{key} AS (
            SELECT
                la.id AS allocation_id, la.employee_id, la.date_from,
                COALESCE(la.date_to, 'infinity'::date) AS date_to,
                la.number_of_days AS stored_days,
                apl.added_value AS monthly_rate, apl.maximum_leave AS cap,
                apl.postpone_max_days AS carryover_cap, apl.action_with_unused_accruals
            FROM hr_leave_allocation la
            JOIN hr_leave_accrual_plan ap ON ap.id = la.accrual_plan_id
            JOIN hr_leave_accrual_level apl ON apl.accrual_plan_id = ap.id
            WHERE la.holiday_status_id = {type_id} AND la.allocation_type = 'accrual'
              AND la.state = 'validate'
        ),
        period_end_{key} AS (
            SELECT am.*,
                COALESCE((
                    SELECT SUM(hl.number_of_days) FROM hr_leave hl
                    WHERE hl.employee_id = am.employee_id AND hl.holiday_status_id = {type_id}
                      AND hl.state = 'validate'
                      AND hl.date_from::date >= am.date_from AND hl.date_from::date <= am.date_to
                ), 0) AS taken_during_period
            FROM accrual_meta_{key} am
        ),
        own_carryover_{key} AS (
            -- Only used when CARRY_OVER_ACROSS_ALLOCATIONS is True. Uses the
            -- allocation's real stored number_of_days as the period's ending
            -- accrued total, not a recomputed rate x months figure.
            SELECT *,
                CASE WHEN action_with_unused_accruals = 'lost' THEN 0
                     ELSE LEAST(GREATEST(stored_days - taken_during_period, 0), carryover_cap)
                END AS own_carryover_contribution
            FROM period_end_{key}
        ),
        carryover_in_{key} AS (
            SELECT allocation_id, employee_id, date_from, date_to, stored_days, monthly_rate, cap,
                {carryover_sql} AS carryover_days
            FROM own_carryover_{key}
        )
    """.format(key=key, type_id=type_id, carryover_sql=carryover_sql)


def _accrued_expr(month_end_expr):
    """Accrued-to-date for the period row `ci` (rule 5)."""
    return """(CASE WHEN {month_end} >= CURRENT_DATE THEN ci.stored_days
                ELSE LEAST(
                    ci.monthly_rate * (
                        (EXTRACT(YEAR FROM {month_end}) - EXTRACT(YEAR FROM ci.date_from)) * 12
                        + (EXTRACT(MONTH FROM {month_end}) - EXTRACT(MONTH FROM ci.date_from)) + 1
                    ),
                    ci.cap,
                    ci.stored_days
                ) END + ci.carryover_days)""".format(month_end=month_end_expr)


def _period_from(key, employee_id_expr, month_end_expr):
    """FROM/WHERE picking the accrual period valid on the target date
    (rule 1). When periods overlap, the newest one wins."""
    return """FROM carryover_in_{key} ci
        WHERE ci.employee_id = {employee_id}
          AND ci.date_from <= {month_end} AND ci.date_to >= {month_end}
        ORDER BY ci.date_from DESC
        LIMIT 1""".format(key=key, employee_id=employee_id_expr, month_end=month_end_expr)


def build_accrual_allocated_expr(type_id, key, employee_id_expr, month_start_expr, month_end_expr):
    """Scalar-subquery SQL text: accrued-to-date (+ carry-over, if enabled)
    for the ONE accrual period valid on the target date - i.e. Allocated,
    before subtracting Taken. Kept separate from the balance expression so
    callers that want an Allocated/Taken/Balance breakdown can show
    Taken = Allocated - Balance without a third redundant subquery.
    """
    return """(
        SELECT {accrued}
        {period}
    )""".format(
        accrued=_accrued_expr(month_end_expr),
        period=_period_from(key, employee_id_expr, month_end_expr),
    )


def build_accrual_balance_expr(type_id, key, employee_id_expr, month_start_expr, month_end_expr):
    """Scalar-subquery SQL text: the balance for one accrual leave type as of
    `month_end_expr`, for the employee identified by `employee_id_expr`.

    Requires build_accrual_ctes(type_id, key) to already be included in the
    query's WITH clause.
    """
    return """(
        SELECT {accrued}
            - COALESCE((
                SELECT SUM(hl.number_of_days) FROM hr_leave hl
                WHERE hl.employee_id = {employee_id} AND hl.holiday_status_id = {type_id}
                  AND hl.state IN {states}
                  AND hl.date_from::date >= ci.date_from
                  AND hl.date_from::date <= LEAST(ci.date_to, {month_end})
            ), 0)
            - CASE WHEN (SELECT lt.allows_negative FROM hr_leave_type lt WHERE lt.id = {type_id})
                   THEN COALESCE((
                       SELECT SUM(GREATEST(pe.taken_during_period - pe.stored_days, 0))
                       FROM period_end_{key} pe
                       WHERE pe.employee_id = {employee_id} AND pe.date_to < ci.date_from
                   ), 0)
                   ELSE 0 END
        {period}
    )""".format(
        accrued=_accrued_expr(month_end_expr),
        employee_id=employee_id_expr, type_id=type_id, key=key,
        states=COUNTED_LEAVE_STATES, month_end=month_end_expr,
        period=_period_from(key, employee_id_expr, month_end_expr),
    )


def _valid_regular_allocation(alias, employee_id_expr, type_id, month_end_expr):
    """WHERE fragment: a validated one-time/manual allocation valid on the
    target date (rule 1)."""
    return """{a}.employee_id = {employee_id} AND {a}.holiday_status_id = {type_id}
                  AND {a}.allocation_type != 'accrual' AND {a}.state = 'validate'
                  AND {a}.date_from <= {month_end}
                  AND ({a}.date_to IS NULL OR {a}.date_to >= {month_end})""".format(
        a=alias, employee_id=employee_id_expr, type_id=type_id, month_end=month_end_expr,
    )


def build_regular_allocated_expr(type_id, employee_id_expr, month_end_expr):
    """Scalar-subquery SQL text: days granted by one-time/manual allocations
    valid on the target date."""
    return """(
        SELECT SUM(a2.number_of_days) FROM hr_leave_allocation a2
        WHERE {valid}
    )""".format(valid=_valid_regular_allocation('a2', employee_id_expr, type_id, month_end_expr))


def build_regular_taken_expr(type_id, employee_id_expr, month_end_expr):
    """Scalar-subquery SQL text: approved + pending leave that falls inside a
    one-time/manual allocation valid on the target date (rules 3 and 4).
    Leave outside every valid allocation is not charged here - the
    dashboard does not charge it to the balance either."""
    return """(
        SELECT SUM(l2.number_of_days) FROM hr_leave l2
        WHERE l2.employee_id = {employee_id} AND l2.holiday_status_id = {type_id}
          AND l2.state IN {states}
          AND l2.date_from::date <= {cutoff}
          AND EXISTS (
              SELECT 1 FROM hr_leave_allocation a3
              WHERE {valid}
                AND l2.date_from::date >= a3.date_from
                AND l2.date_from::date <= COALESCE(a3.date_to, 'infinity'::date)
          )
    )""".format(
        employee_id=employee_id_expr, type_id=type_id, states=COUNTED_LEAVE_STATES,
        cutoff=leave_cutoff_expr(month_end_expr),
        valid=_valid_regular_allocation('a3', employee_id_expr, type_id, month_end_expr),
    )
