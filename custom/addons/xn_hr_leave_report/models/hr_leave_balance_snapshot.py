# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

from .accrual_balance import build_accrual_balance_expr, build_accrual_ctes
from .leave_type_columns import LEAVE_TYPE_COLUMNS, resolve_leave_type_ids

_logger = logging.getLogger(__name__)


class HrLeaveBalanceSnapshot(models.Model):
    """Projected running balance as of the end of each month - one row per
    employee per year/month, all five leave types as columns.

    This is the report neither hr.leave.balance.report (today only) nor
    hr.leave.period.report (period activity, accrual excluded) can answer:
    "what was this employee's balance as of March 2026".

    For REGULAR (one-time/manual) leave types - Earned Leave b/f, Maternity,
    Comp-off - this is exact: a cumulative sum of dated allocation and leave
    records as of the target month, continuous across months with no
    activity (the balance simply doesn't change until the next event).

    For ACCRUAL leave types - Casual, Sick in this org - this uses the same
    carry-over-aware projection as hr.leave.balance.report (see
    accrual_balance.py for the shared logic and its reasoning), evaluated as
    of each month's end instead of today.

    Known limitations of the projection:
    - Assumes a single accrual level per plan (true for every plan in this
      database at the time this was written - see hr_leave_accrual_level).
    - Carries over from at most one immediately preceding period; a chain
      of 3+ consecutive accrual periods for the same employee/type is not
      fully modeled.
    - Does NOT replicate Odoo's own cron exactly (e.g. exact day-of-month
      timing within a period) - it is accurate as of each month boundary,
      which is what this report shows.

    Validated by comparing "balance as of the current month" here against
    hr.leave.balance.report's live total for the same employee/leave type -
    they should match exactly (both use the same accrual_balance.py logic).
    """
    _name = 'hr.leave.balance.snapshot'
    _description = 'HR Leave Balance Snapshot (Projected, by Month)'
    _auto = False          # backed by a SQL view, no ORM table
    _rec_name = 'employee_id'
    _order = 'year desc, month desc, employee_name'

    # -- Identity / period --
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char(string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    year = fields.Integer('Year', readonly=True, group_operator=None)
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', readonly=True)

    _PROJECTED_HELP = ("Calculated projection (monthly accrual rate x months elapsed, "
                        "capped, plus carry-over) - Odoo keeps no ledger of accrual "
                        "history to read this from directly. See the model's help "
                        "for what this does and doesn't account for.")

    casual_balance = fields.Float(string='Casual Balance', readonly=True, digits=(16, 1), help=_PROJECTED_HELP)
    sick_balance = fields.Float(string='Sick Balance', readonly=True, digits=(16, 1), help=_PROJECTED_HELP)
    earned_balance = fields.Float(string='Earned b/f Balance', readonly=True, digits=(16, 1))
    maternity_balance = fields.Float(string='Maternity Balance', readonly=True, digits=(16, 1))
    compoff_balance = fields.Float(string='Comp-off Balance', readonly=True, digits=(16, 1))
    total_balance = fields.Float(string='Total Balance', readonly=True, digits=(16, 1))

    def _is_accrual_type(self, type_id):
        """True if this leave type has ANY accrual-type allocation on record
        (determined from data, not hardcoded, so this adapts if the org's
        leave-type configuration changes)."""
        if type_id is None:
            return False
        self.env.cr.execute(
            "SELECT 1 FROM hr_leave_allocation WHERE holiday_status_id = %s "
            "AND allocation_type = 'accrual' AND state = 'validate' LIMIT 1",
            (type_id,),
        )
        return self.env.cr.fetchone() is not None

    def init(self):
        """Drop and recreate the SQL view that backs this model."""
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_balance_snapshot CASCADE")

        type_ids = resolve_leave_type_ids(self.env.cr)
        accrual_type_ids = [key for key, _n, _l in LEAVE_TYPE_COLUMNS if self._is_accrual_type(type_ids[key])]
        _logger.info(
            "hr.leave.balance.snapshot: accrual-projected types=%s, regular-cumulative types=%s",
            accrual_type_ids, [k for k, _n, _l in LEAVE_TYPE_COLUMNS if k not in accrual_type_ids],
        )

        def sql_id(key):
            tid = type_ids[key]
            return str(tid) if tid is not None else 'NULL'

        month_start_expr = "make_date(grid.year, grid.month::int, 1)"
        # LEAST(..., CURRENT_DATE): for a fully-elapsed past month this is just that
        # month's last day (unchanged). For the current, still-in-progress month, this
        # caps the cutoff at today instead of projecting into not-yet-arrived days later
        # in the month - so a leave request dated later this month, that hasn't happened
        # yet, isn't counted as already taken. Without this, the current month's row
        # would disagree with hr.leave.balance.report's "balance right now" by counting
        # future-within-this-month leave that report correctly excludes.
        month_end_expr = (
            "LEAST((make_date(grid.year, grid.month::int, 1) + interval '1 month' "
            "- interval '1 day')::date, CURRENT_DATE)"
        )

        accrual_ctes = [build_accrual_ctes(sql_id(key), key) for key in accrual_type_ids]

        # -- One continuous monthly grid per employee, from their earliest leave-related
        #    record through the current month (independent of any single type's data) --
        grid_cte = """
            employee_range AS (
                SELECT employee_id, MIN(d) AS start_date FROM (
                    SELECT employee_id, MIN(date_from) AS d FROM hr_leave_allocation WHERE state = 'validate' GROUP BY employee_id
                    UNION ALL
                    SELECT employee_id, MIN(date_from) AS d FROM hr_leave WHERE state = 'validate' GROUP BY employee_id
                ) x
                GROUP BY employee_id
            ),
            grid AS (
                SELECT er.employee_id,
                       EXTRACT(YEAR FROM gs.month_start)::integer AS year,
                       EXTRACT(MONTH FROM gs.month_start)::integer::text AS month
                FROM employee_range er
                CROSS JOIN LATERAL generate_series(
                    date_trunc('month', er.start_date), date_trunc('month', CURRENT_DATE), interval '1 month'
                ) AS gs(month_start)
            )
        """
        cte_sql = ',\n'.join([grid_cte] + accrual_ctes)

        # -- Per-type balance expression: accrual types use the shared carry-over-aware
        #    projection; regular types are a plain cumulative sum. Both are correlated
        #    subqueries evaluated per grid row - no separate per-type month list needed,
        #    so gaps/overlaps can't cause missing or duplicate rows. --
        balance_exprs = []
        raw_exprs = {}
        for key, _name, _label in LEAVE_TYPE_COLUMNS:
            type_id = sql_id(key)
            if key in accrual_type_ids:
                expr = build_accrual_balance_expr(
                    type_id, key,
                    employee_id_expr='grid.employee_id',
                    month_start_expr=month_start_expr, month_end_expr=month_end_expr,
                )
            else:
                expr = """(
                    COALESCE((
                        SELECT SUM(a2.number_of_days) FROM hr_leave_allocation a2
                        WHERE a2.employee_id = grid.employee_id AND a2.holiday_status_id = {type_id}
                          AND a2.allocation_type != 'accrual' AND a2.state = 'validate'
                          AND a2.date_from::date <= {month_end}
                    ), 0)
                    - COALESCE((
                        SELECT SUM(l2.number_of_days) FROM hr_leave l2
                        WHERE l2.employee_id = grid.employee_id AND l2.holiday_status_id = {type_id}
                          AND l2.state = 'validate'
                          AND l2.date_from::date <= {month_end}
                    ), 0)
                )""".format(type_id=type_id, month_end=month_end_expr)
            raw_exprs[key] = expr
            balance_exprs.append("COALESCE(%s, 0) AS %s_balance" % (expr, key))

        balance_select = ',\n                    '.join(balance_exprs)
        total_expr = ' + '.join(
            "COALESCE(%s, 0)" % raw_exprs[key] for key, _n, _l in LEAVE_TYPE_COLUMNS
        )

        sql = """
            CREATE OR REPLACE VIEW hr_leave_balance_snapshot AS (
                WITH
                {cte_sql}
                SELECT
                    row_number() OVER (ORDER BY grid.employee_id, grid.year, grid.month) AS id,
                    e.id AS employee_id, e.name AS employee_name,
                    e.department_id AS department_id, e.company_id AS company_id,
                    grid.year AS year, grid.month AS month,
                    {balance_select},
                    ({total_expr}) AS total_balance
                FROM grid
                JOIN hr_employee e ON e.id = grid.employee_id
                WHERE e.active = True
            )
        """.format(cte_sql=cte_sql, balance_select=balance_select, total_expr=total_expr)
        self.env.cr.execute(sql)
