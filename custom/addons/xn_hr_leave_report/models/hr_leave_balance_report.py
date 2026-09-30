# -*- coding: utf-8 -*-
from odoo import fields, models

from .accrual_balance import (
    build_accrual_allocated_expr, build_accrual_balance_expr, build_accrual_ctes,
    build_regular_allocated_expr, build_regular_taken_expr,
)
from .leave_type_columns import LEAVE_TYPE_COLUMNS, resolve_leave_type_ids, sql_id_literal


class HrLeaveBalanceReport(models.Model):
    """Wide-format leave balance report - one row per active employee.

    Each leave type gets its own Allocated / Taken / Balance columns so HR
    can compare every employee side-by-side in a single scrollable table.

    This is the balance right now - it does not accept a date/period
    filter. See hr.leave.period.report for the period-scoped activity view,
    and hr.leave.balance.snapshot for balance as of a specific past month.

    Balance equals the "available" figure on Odoo's Time Off dashboard, for
    every leave type (see accrual_balance.py for the shared rules):
    - Allocated: allocations valid today only. For accrual types this is
      what Odoo's accrual cron has actually granted so far.
    - Taken: approved AND waiting-for-approval requests inside those
      allocations, including requests booked for a future date - the
      dashboard subtracts both.
    - Nothing carries over from an expired or superseded allocation.
    """
    _name = 'hr.leave.balance.report'
    _description = 'HR Leave Balance Report'
    _auto = False          # backed by a SQL view, no ORM table
    _rec_name = 'employee_id'
    _order = 'employee_name'

    # -- Identity --
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char(string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    # -- Casual Leave --
    casual_allocated = fields.Float(string='Casual - Allocated', readonly=True, digits=(16, 1))
    casual_taken = fields.Float(string='Casual - Taken', readonly=True, digits=(16, 1))
    casual_balance = fields.Float(string='Casual - Balance', readonly=True, digits=(16, 1))

    # -- Sick Leave --
    sick_allocated = fields.Float(string='Sick - Allocated', readonly=True, digits=(16, 1))
    sick_taken = fields.Float(string='Sick - Taken', readonly=True, digits=(16, 1))
    sick_balance = fields.Float(string='Sick - Balance', readonly=True, digits=(16, 1))

    # -- Earned Leave b/f --
    earned_allocated = fields.Float(string='Earned b/f - Allocated', readonly=True, digits=(16, 1))
    earned_taken = fields.Float(string='Earned b/f - Taken', readonly=True, digits=(16, 1))
    earned_balance = fields.Float(string='Earned b/f - Balance', readonly=True, digits=(16, 1))

    # -- Maternity Leave --
    maternity_allocated = fields.Float(string='Maternity - Allocated', readonly=True, digits=(16, 1))
    maternity_taken = fields.Float(string='Maternity - Taken', readonly=True, digits=(16, 1))
    maternity_balance = fields.Float(string='Maternity - Balance', readonly=True, digits=(16, 1))

    # -- Comp-off --
    compoff_allocated = fields.Float(string='Comp-off - Allocated', readonly=True, digits=(16, 1))
    compoff_taken = fields.Float(string='Comp-off - Taken', readonly=True, digits=(16, 1))
    compoff_balance = fields.Float(string='Comp-off - Balance', readonly=True, digits=(16, 1))

    # -- Total row --
    total_allocated = fields.Float(string='Total Allocated', readonly=True, digits=(16, 1))
    total_taken = fields.Float(string='Total Taken', readonly=True, digits=(16, 1))
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
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_balance_report CASCADE")

        type_ids = resolve_leave_type_ids(self.env.cr)
        accrual_type_ids = [key for key, _n, _l in LEAVE_TYPE_COLUMNS if self._is_accrual_type(type_ids[key])]
        regular_type_ids = [key for key, _n, _l in LEAVE_TYPE_COLUMNS if key not in accrual_type_ids]

        def sql_id(key):
            return sql_id_literal(type_ids, key)

        month_start_expr = "date_trunc('month', CURRENT_DATE)::date"
        month_end_expr = "CURRENT_DATE"

        accrual_ctes = [build_accrual_ctes(sql_id(key), key) for key in accrual_type_ids]
        cte_sql = ',\n'.join(accrual_ctes)

        # -- Regular types: allocations valid today, approved + pending leave inside them --
        regular_alloc = {
            key: build_regular_allocated_expr(sql_id(key), 'e.id', month_end_expr)
            for key in regular_type_ids
        }
        regular_taken = {
            key: build_regular_taken_expr(sql_id(key), 'e.id', month_end_expr)
            for key in regular_type_ids
        }

        # -- Per-type Allocated/Taken/Balance select fragments --
        select_fragments = []
        allocated_exprs = {}
        for key, _name, label in LEAVE_TYPE_COLUMNS:
            if key in accrual_type_ids:
                allocated_expr = build_accrual_allocated_expr(
                    sql_id(key), key, employee_id_expr='e.id',
                    month_start_expr=month_start_expr, month_end_expr=month_end_expr,
                )
                balance_expr = build_accrual_balance_expr(
                    sql_id(key), key, employee_id_expr='e.id',
                    month_start_expr=month_start_expr, month_end_expr=month_end_expr,
                )
                allocated_exprs[key] = allocated_expr
                select_fragments.append(
                    "-- %s (accrual, carry-over-aware)\n"
                    "                    COALESCE(%s, 0) AS %s_allocated,\n"
                    "                    COALESCE(%s, 0) - COALESCE(%s, 0) AS %s_taken,\n"
                    "                    COALESCE(%s, 0) AS %s_balance"
                    % (label, allocated_expr, key, allocated_expr, balance_expr, key, balance_expr, key)
                )
            else:
                allocated_exprs[key] = regular_alloc[key]
                select_fragments.append(
                    "-- %s\n"
                    "                    COALESCE(%s, 0) AS %s_allocated,\n"
                    "                    COALESCE(%s, 0) AS %s_taken,\n"
                    "                    COALESCE(%s, 0) - COALESCE(%s, 0) AS %s_balance"
                    % (label, regular_alloc[key], key, regular_taken[key], key,
                       regular_alloc[key], regular_taken[key], key)
                )
        select_cols = ',\n\n                    '.join(select_fragments)

        # -- Totals: sum each type's own Allocated/Balance (Taken derived as Alloc-Balance,
        #    consistent with how each type's own Taken column above is computed) --
        total_allocated_terms = []
        total_balance_terms = []
        for key, _name, _label in LEAVE_TYPE_COLUMNS:
            if key in accrual_type_ids:
                total_allocated_terms.append("COALESCE(%s, 0)" % allocated_exprs[key])
                total_balance_terms.append("COALESCE(%s, 0)" % build_accrual_balance_expr(
                    sql_id(key), key, employee_id_expr='e.id',
                    month_start_expr=month_start_expr, month_end_expr=month_end_expr,
                ))
            else:
                total_allocated_terms.append("COALESCE(%s, 0)" % regular_alloc[key])
                total_balance_terms.append(
                    "(COALESCE(%s, 0) - COALESCE(%s, 0))" % (regular_alloc[key], regular_taken[key])
                )
        total_allocated_expr = ' + '.join(total_allocated_terms)
        total_balance_expr = ' + '.join(total_balance_terms)

        sql = """
            CREATE OR REPLACE VIEW hr_leave_balance_report AS (
                {with_sql}
                SELECT
                    e.id                             AS id,
                    e.id                             AS employee_id,
                    e.name                           AS employee_name,
                    e.department_id                  AS department_id,
                    e.company_id                     AS company_id,

                    {select_cols},

                    ({total_allocated_expr})                              AS total_allocated,
                    ({total_allocated_expr}) - ({total_balance_expr})      AS total_taken,
                    ({total_balance_expr})                                AS total_balance

                FROM hr_employee e
                WHERE e.active = True
            )
        """.format(
            with_sql=('WITH ' + cte_sql) if cte_sql else '',
            select_cols=select_cols,
            total_allocated_expr=total_allocated_expr,
            total_balance_expr=total_balance_expr,
        )
        self.env.cr.execute(sql)
