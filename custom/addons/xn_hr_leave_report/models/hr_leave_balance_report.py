# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

# (column_prefix, leave type name, output label)
# Leave types are resolved by NAME at upgrade time in init() below - never by
# hardcoded database id. Auto-generated ids are not portable across
# environments (dev, staging, a fresh DR restore can all assign different
# ids to the same leave type), which was the cause of a real bug in an
# earlier version of this report: it silently showed zero balances outside
# of the one database it was written against.
#
# Adding a new leave type to this table means adding an entry here and
# running an -u upgrade. That one-line-of-code cost is a fundamental
# limitation of SQL-view-backed wide tables, not a shortcut: a SQL view
# requires a fixed, known-at-creation-time column list, so a per-type
# column can't appear automatically without a schema (and therefore code)
# change somewhere.
LEAVE_TYPE_COLUMNS = [
    ('casual', 'Casual Leave', 'Casual'),
    ('sick', 'Sick Leave', 'Sick'),
    ('earned', 'Earned Leave balance b/f', 'Earned b/f'),
    ('maternity', 'Maternity Leave', 'Maternity'),
    ('compoff', 'Comp-off', 'Comp-off'),
]


class HrLeaveBalanceReport(models.Model):
    """Wide-format leave balance report - one row per active employee.

    Each leave type gets its own Allocated / Taken / Balance columns so HR
    can compare every employee side-by-side in a single scrollable table.
    The SQL view uses conditional aggregation (FILTER clause) to pivot the
    narrow allocation / leave tables into a single wide row per employee.
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

    def _get_leave_type_id(self, name):
        """Resolve a leave type's database id by name.

        Returns None (with a warning logged) if the type is missing or
        inactive, so the view still builds - the affected columns just
        report zero instead of breaking the upgrade.
        """
        self.env.cr.execute(
            "SELECT id FROM hr_leave_type WHERE name->>'en_US' = %s AND active = True LIMIT 1",
            (name,),
        )
        row = self.env.cr.fetchone()
        if not row:
            _logger.warning(
                "hr.leave.balance.report: leave type '%s' not found (or inactive) in "
                "this database - its columns will show zero. Check Time Off > "
                "Configuration > Time Off Types.", name,
            )
            return None
        type_id = row[0]
        assert isinstance(type_id, int)
        return type_id

    def init(self):
        """Drop and recreate the SQL view that backs this model."""
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_balance_report CASCADE")

        type_ids = {key: self._get_leave_type_id(name) for key, name, _label in LEAVE_TYPE_COLUMNS}

        def sql_id(key):
            """SQL literal for a leave type id, or NULL if unresolved (a FILTER
            on `= NULL` never matches, so the aggregate safely comes out as 0)."""
            type_id = type_ids[key]
            return str(type_id) if type_id is not None else 'NULL'

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
            CREATE OR REPLACE VIEW hr_leave_balance_report AS (
                WITH alloc AS (
                    SELECT
                        employee_id,
                        %(alloc_cols)s
                    FROM hr_leave_allocation
                    WHERE state = 'validate'
                    GROUP BY employee_id
                ),
                taken AS (
                    SELECT
                        employee_id,
                        %(taken_cols)s
                    FROM hr_leave
                    WHERE state = 'validate'
                    GROUP BY employee_id
                )
                SELECT
                    e.id                             AS id,
                    e.id                             AS employee_id,
                    e.name                           AS employee_name,
                    e.department_id                  AS department_id,
                    e.company_id                     AS company_id,

                    %(select_cols)s,

                    (%(total_allocated_expr)s)                          AS total_allocated,
                    (%(total_taken_expr)s)                               AS total_taken,
                    (%(total_allocated_expr)s) - (%(total_taken_expr)s)  AS total_balance

                FROM hr_employee e
                LEFT JOIN alloc a ON a.employee_id = e.id
                LEFT JOIN taken t ON t.employee_id = e.id
                WHERE e.active = True
                  AND (
                        a.employee_id IS NOT NULL
                     OR t.employee_id IS NOT NULL
                  )
            )
        """ % {
            'alloc_cols': alloc_cols,
            'taken_cols': taken_cols,
            'select_cols': select_cols,
            'total_allocated_expr': total_allocated_expr,
            'total_taken_expr': total_taken_expr,
        })
