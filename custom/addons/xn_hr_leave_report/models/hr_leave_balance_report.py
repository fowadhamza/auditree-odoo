# -*- coding: utf-8 -*-
from odoo import fields, models


class HrLeaveBalanceReport(models.Model):
    """
    Wide-format leave balance report ? one row per active employee.
    Each leave type has its own Allocated / Taken / Balance columns so HR
    can compare every employee side-by-side in a single scrollable table.

    Leave type IDs (live DB):
        7  = Casual Leave
        8  = Sick Leave
        9  = Earned Leave balance b/f
        12 = Maternity Leave
        13 = Comp-off

    The SQL view uses conditional aggregation (FILTER clause) to pivot the
    narrow allocation / leave tables into a single wide row per employee.
    """
    _name        = 'hr.leave.balance.report'
    _description = 'HR Leave Balance Report'
    _auto        = False          # backed by a SQL view, no ORM table
    _rec_name    = 'employee_id'
    _order       = 'employee_name'

    # ?? Identity ?????????????????????????????????????????????????????????????
    employee_id   = fields.Many2one('hr.employee',  string='Employee',   readonly=True)
    employee_name = fields.Char(string='Employee',  readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)

    # ?? Casual Leave (id=7) ???????????????????????????????????????????????????
    casual_allocated = fields.Float(string='Casual ? Allocated', readonly=True, digits=(16, 1))
    casual_taken     = fields.Float(string='Casual ? Taken',     readonly=True, digits=(16, 1))
    casual_balance   = fields.Float(string='Casual ? Balance',   readonly=True, digits=(16, 1))

    # ?? Sick Leave (id=8) ?????????????????????????????????????????????????????
    sick_allocated = fields.Float(string='Sick ? Allocated', readonly=True, digits=(16, 1))
    sick_taken     = fields.Float(string='Sick ? Taken',     readonly=True, digits=(16, 1))
    sick_balance   = fields.Float(string='Sick ? Balance',   readonly=True, digits=(16, 1))

    # ?? Earned Leave b/f (id=9) ???????????????????????????????????????????????
    earned_allocated = fields.Float(string='Earned b/f ? Allocated', readonly=True, digits=(16, 1))
    earned_taken     = fields.Float(string='Earned b/f ? Taken',     readonly=True, digits=(16, 1))
    earned_balance   = fields.Float(string='Earned b/f ? Balance',   readonly=True, digits=(16, 1))

    # ?? Maternity Leave (id=12) ???????????????????????????????????????????????
    maternity_allocated = fields.Float(string='Maternity ? Allocated', readonly=True, digits=(16, 1))
    maternity_taken     = fields.Float(string='Maternity ? Taken',     readonly=True, digits=(16, 1))
    maternity_balance   = fields.Float(string='Maternity ? Balance',   readonly=True, digits=(16, 1))

    # ?? Comp-off (id=13) ??????????????????????????????????????????????????????
    compoff_allocated = fields.Float(string='Comp-off ? Allocated', readonly=True, digits=(16, 1))
    compoff_taken     = fields.Float(string='Comp-off ? Taken',     readonly=True, digits=(16, 1))
    compoff_balance   = fields.Float(string='Comp-off ? Balance',   readonly=True, digits=(16, 1))

    # ?? Total row ?????????????????????????????????????????????????????????????
    total_allocated = fields.Float(string='Total Allocated', readonly=True, digits=(16, 1))
    total_taken     = fields.Float(string='Total Taken',     readonly=True, digits=(16, 1))
    total_balance   = fields.Float(string='Total Balance',   readonly=True, digits=(16, 1))

    # ?????????????????????????????????????????????????????????????????????????
    def init(self):
        """Drop and recreate the SQL view that backs this model."""
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_balance_report CASCADE")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hr_leave_balance_report AS (
                WITH alloc AS (
                    SELECT
                        employee_id,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 7)  AS casual_a,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 8)  AS sick_a,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 9)  AS earned_a,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 12) AS maternity_a,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 13) AS compoff_a
                    FROM hr_leave_allocation
                    WHERE state = 'validate'
                    GROUP BY employee_id
                ),
                taken AS (
                    SELECT
                        employee_id,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 7)  AS casual_t,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 8)  AS sick_t,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 9)  AS earned_t,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 12) AS maternity_t,
                        SUM(number_of_days) FILTER (WHERE holiday_status_id = 13) AS compoff_t
                    FROM hr_leave
                    WHERE state = 'validate'
                    GROUP BY employee_id
                )
                SELECT
                    e.id                                        AS id,
                    e.id                                        AS employee_id,
                    e.name                                      AS employee_name,
                    e.department_id                             AS department_id,

                    -- Casual Leave
                    COALESCE(a.casual_a, 0)                     AS casual_allocated,
                    COALESCE(t.casual_t, 0)                     AS casual_taken,
                    COALESCE(a.casual_a, 0) - COALESCE(t.casual_t, 0)  AS casual_balance,

                    -- Sick Leave
                    COALESCE(a.sick_a, 0)                       AS sick_allocated,
                    COALESCE(t.sick_t, 0)                       AS sick_taken,
                    COALESCE(a.sick_a, 0) - COALESCE(t.sick_t, 0)      AS sick_balance,

                    -- Earned Leave b/f
                    COALESCE(a.earned_a, 0)                     AS earned_allocated,
                    COALESCE(t.earned_t, 0)                     AS earned_taken,
                    COALESCE(a.earned_a, 0) - COALESCE(t.earned_t, 0)  AS earned_balance,

                    -- Maternity Leave
                    COALESCE(a.maternity_a, 0)                  AS maternity_allocated,
                    COALESCE(t.maternity_t, 0)                  AS maternity_taken,
                    COALESCE(a.maternity_a, 0) - COALESCE(t.maternity_t, 0) AS maternity_balance,

                    -- Comp-off
                    COALESCE(a.compoff_a, 0)                    AS compoff_allocated,
                    COALESCE(t.compoff_t, 0)                    AS compoff_taken,
                    COALESCE(a.compoff_a, 0) - COALESCE(t.compoff_t, 0) AS compoff_balance,

                    -- Totals
                    (
                        COALESCE(a.casual_a, 0) + COALESCE(a.sick_a, 0) +
                        COALESCE(a.earned_a, 0) + COALESCE(a.maternity_a, 0) +
                        COALESCE(a.compoff_a, 0)
                    )                                           AS total_allocated,
                    (
                        COALESCE(t.casual_t, 0) + COALESCE(t.sick_t, 0) +
                        COALESCE(t.earned_t, 0) + COALESCE(t.maternity_t, 0) +
                        COALESCE(t.compoff_t, 0)
                    )                                           AS total_taken,
                    (
                        COALESCE(a.casual_a, 0) + COALESCE(a.sick_a, 0) +
                        COALESCE(a.earned_a, 0) + COALESCE(a.maternity_a, 0) +
                        COALESCE(a.compoff_a, 0)
                    ) - (
                        COALESCE(t.casual_t, 0) + COALESCE(t.sick_t, 0) +
                        COALESCE(t.earned_t, 0) + COALESCE(t.maternity_t, 0) +
                        COALESCE(t.compoff_t, 0)
                    )                                           AS total_balance

                FROM hr_employee e
                LEFT JOIN alloc a ON a.employee_id = e.id
                LEFT JOIN taken t ON t.employee_id = e.id
                WHERE e.active = True
                  AND (
                        a.employee_id IS NOT NULL
                     OR t.employee_id IS NOT NULL
                  )
            )
        """)
