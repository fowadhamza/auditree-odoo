# -*- coding: utf-8 -*-
"""Shared accrual-balance SQL generation, used by both hr.leave.balance.report
(as-of-today) and hr.leave.balance.snapshot (as-of-any-month). Kept in one
place because this math is genuinely tricky and the two reports diverging
from each other silently is exactly the bug this module exists to prevent
(see the commit history for how that played out the first time).

Carry-over logic: for a leave type on an accrual plan, an employee often has
more than one accrual allocation row over time (e.g. an old plan superseded
by a new one at a policy change - see the Leave Policy cross-check). Only
the CURRENT/active period's own accrual is projected via
monthly_rate x months_elapsed; a PRIOR period's contribution is whatever
carries over from it, per that period's own plan rules:

    carryover = 0                                            if action_with_unused_accruals == 'lost'
    carryover = min(max(period's real ending balance, 0), postpone_max_days)   otherwise

Critically, "period's real ending balance" uses the allocation's actual
STORED number_of_days at period end - not monthly_rate x months_in_period
recomputed - because a superseded plan's accrual often stops before its
nominal date_to (the employee was switched to the new plan first), so the
stored value is the only source of truth for how much really accrued.
"""


def build_accrual_ctes(type_id, key):
    """SQL text for the per-period metadata + carry-over CTEs for one leave
    type. These are period-level (per allocation row), independent of any
    particular 'as of' date, so both callers can share them unchanged.
    """
    return """
        accrual_meta_{key} AS (
            SELECT
                la.id AS allocation_id, la.employee_id, la.date_from, la.date_to,
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
            -- Uses the allocation's real stored number_of_days as the period's ending
            -- accrued total (ground truth), NOT a recomputed rate x months figure - a
            -- superseded plan frequently stops accruing before its nominal date_to.
            SELECT *,
                CASE WHEN action_with_unused_accruals = 'lost' THEN 0
                     ELSE LEAST(GREATEST(stored_days - taken_during_period, 0), carryover_cap)
                END AS own_carryover_contribution
            FROM period_end_{key}
        ),
        carryover_in_{key} AS (
            SELECT allocation_id, employee_id, date_from, date_to, monthly_rate, cap,
                COALESCE(
                    LAG(own_carryover_contribution) OVER (PARTITION BY employee_id ORDER BY date_from),
                    0
                ) AS carryover_days
            FROM own_carryover_{key}
        )
    """.format(key=key, type_id=type_id)


def build_accrual_allocated_expr(type_id, key, employee_id_expr, month_start_expr, month_end_expr):
    """Scalar-subquery SQL text: accrued-to-date + carry-over for the ONE
    accrual period covering the target month (see build_accrual_balance_expr
    for period selection) - i.e. Allocated, before subtracting Taken. Kept
    separate from the balance expression so callers that want an
    Allocated/Taken/Balance breakdown (not just a bare balance) can show
    Taken = Allocated - Balance without a third redundant subquery.
    """
    return """(
        SELECT
            LEAST(
                ci.monthly_rate * (
                    (EXTRACT(YEAR FROM {month_end}) - EXTRACT(YEAR FROM ci.date_from)) * 12
                    + (EXTRACT(MONTH FROM {month_end}) - EXTRACT(MONTH FROM ci.date_from)) + 1
                ),
                ci.cap
            ) + ci.carryover_days
        FROM carryover_in_{key} ci
        WHERE ci.employee_id = {employee_id}
          AND ci.date_from <= {month_end} AND ci.date_to >= {month_start}
        ORDER BY ci.date_from DESC
        LIMIT 1
    )""".format(
        key=key, employee_id=employee_id_expr,
        month_start=month_start_expr, month_end=month_end_expr,
    )


def build_accrual_balance_expr(type_id, key, employee_id_expr, month_start_expr, month_end_expr):
    """Scalar-subquery SQL text: the accrual-projected balance for one leave
    type, as of `month_end_expr`, for the employee identified by
    `employee_id_expr`. Picks the one accrual period whose [date_from,
    date_to] covers the target month (latest date_from wins on overlap -
    i.e. the newer plan, if two periods both nominally cover this month).

    Requires build_accrual_ctes(type_id, key) to already be included in the
    query's WITH clause.
    """
    return """(
        SELECT
            LEAST(
                ci.monthly_rate * (
                    (EXTRACT(YEAR FROM {month_end}) - EXTRACT(YEAR FROM ci.date_from)) * 12
                    + (EXTRACT(MONTH FROM {month_end}) - EXTRACT(MONTH FROM ci.date_from)) + 1
                ),
                ci.cap
            ) + ci.carryover_days
            - COALESCE((
                SELECT SUM(hl.number_of_days) FROM hr_leave hl
                WHERE hl.employee_id = {employee_id} AND hl.holiday_status_id = {type_id}
                  AND hl.state = 'validate'
                  AND hl.date_from::date >= ci.date_from AND hl.date_from::date <= {month_end}
            ), 0)
        FROM carryover_in_{key} ci
        WHERE ci.employee_id = {employee_id}
          AND ci.date_from <= {month_end} AND ci.date_to >= {month_start}
        ORDER BY ci.date_from DESC
        LIMIT 1
    )""".format(
        key=key, type_id=type_id, employee_id=employee_id_expr,
        month_start=month_start_expr, month_end=month_end_expr,
    )
