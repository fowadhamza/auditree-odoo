# -*- coding: utf-8 -*-
from odoo import fields, models

from .leave_type_columns import LEAVE_TYPE_COLUMNS, resolve_leave_type_ids, sql_id_literal


class HrLeavePeriodReport(models.Model):
    """Wide-format leave ACTIVITY report - one row per employee per year/month.

    Unlike hr.leave.balance.report (a lifetime running balance), every
    number here is scoped to the row's own year/month: Allocated is what
    was granted in that period, Taken is what was used in that period, and
    Balance is simply their difference - so the three numbers always add up
    on screen for the period you're looking at. This intentionally does NOT
    answer "how many days does this employee have left today" (that's what
    hr.leave.balance.report is for); it answers "what happened in this
    period".

    Period is derived from each allocation/leave request's date_from, same
    as hr_holidays' own hr.leave.employee.type.report.
    """
    _name = 'hr.leave.period.report'
    _description = 'HR Leave Activity by Period'
    _auto = False          # backed by a SQL view, no ORM table
    _rec_name = 'employee_id'
    _order = 'year desc, month desc, employee_name'

    # -- Identity --
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char(string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    # -- Period --
    year = fields.Integer('Year', readonly=True, group_operator=None)
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', readonly=True)

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

    def init(self):
        """Drop and recreate the SQL view that backs this model."""
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_period_report CASCADE")

        type_ids = resolve_leave_type_ids(self.env.cr)

        def sql_id(key):
            return sql_id_literal(type_ids, key)

        alloc_cols = ',\n                        '.join(
            "SUM(number_of_days) FILTER (WHERE holiday_status_id = %s) AS %s_a" % (sql_id(key), key)
            for key, _name, _label in LEAVE_TYPE_COLUMNS
        )
        taken_cols = ',\n                        '.join(
            "SUM(number_of_days) FILTER (WHERE holiday_status_id = %s) AS %s_t" % (sql_id(key), key)
            for key, _name, _label in LEAVE_TYPE_COLUMNS
        )
        select_cols = ',\n\n                    '.join(
            "-- %s\n"
            "                    COALESCE(a.%s_a, 0) AS %s_allocated,\n"
            "                    COALESCE(t.%s_t, 0) AS %s_taken,\n"
            "                    COALESCE(a.%s_a, 0) - COALESCE(t.%s_t, 0) AS %s_balance"
            % (label, key, key, key, key, key, key, key)
            for key, _name, label in LEAVE_TYPE_COLUMNS
        )
        total_allocated_expr = ' + '.join(
            "COALESCE(a.%s_a, 0)" % key for key, _name, _label in LEAVE_TYPE_COLUMNS
        )
        total_taken_expr = ' + '.join(
            "COALESCE(t.%s_t, 0)" % key for key, _name, _label in LEAVE_TYPE_COLUMNS
        )

        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hr_leave_period_report AS (
                WITH alloc AS (
                    SELECT
                        employee_id,
                        EXTRACT(YEAR FROM date_from)::integer AS year,
                        EXTRACT(MONTH FROM date_from)::integer::text AS month,
                        %(alloc_cols)s
                    FROM hr_leave_allocation
                    WHERE state = 'validate' AND date_from IS NOT NULL
                    GROUP BY employee_id, year, month
                ),
                taken AS (
                    SELECT
                        employee_id,
                        EXTRACT(YEAR FROM date_from)::integer AS year,
                        EXTRACT(MONTH FROM date_from)::integer::text AS month,
                        %(taken_cols)s
                    FROM hr_leave
                    WHERE state = 'validate' AND date_from IS NOT NULL
                    GROUP BY employee_id, year, month
                ),
                periods AS (
                    SELECT employee_id, year, month FROM alloc
                    UNION
                    SELECT employee_id, year, month FROM taken
                )
                SELECT
                    row_number() OVER (ORDER BY p.employee_id, p.year, p.month) AS id,
                    e.id                             AS employee_id,
                    e.name                           AS employee_name,
                    e.department_id                  AS department_id,
                    e.company_id                     AS company_id,
                    p.year                           AS year,
                    p.month                          AS month,

                    %(select_cols)s,

                    (%(total_allocated_expr)s)                          AS total_allocated,
                    (%(total_taken_expr)s)                               AS total_taken,
                    (%(total_allocated_expr)s) - (%(total_taken_expr)s)  AS total_balance

                FROM periods p
                JOIN hr_employee e ON e.id = p.employee_id
                LEFT JOIN alloc a ON a.employee_id = p.employee_id AND a.year = p.year AND a.month = p.month
                LEFT JOIN taken t ON t.employee_id = p.employee_id AND t.year = p.year AND t.month = p.month
                WHERE e.active = True
            )
        """ % {
            'alloc_cols': alloc_cols,
            'taken_cols': taken_cols,
            'select_cols': select_cols,
            'total_allocated_expr': total_allocated_expr,
            'total_taken_expr': total_taken_expr,
        })
