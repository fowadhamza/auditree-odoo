# -*- coding: utf-8 -*-
{
    'name': 'HR Leave Balance Report',
    'version': '17.0.2.1.0',
    'summary': 'Consolidated leave balance table for all employees (HR/Admin view)',
    'description': """
        Adds two menus under Leaves > Management:

        - Leave Balance Report: one row per employee, lifetime running
          Allocated/Taken/Balance per leave type. "How many days does this
          employee have left right now."
        - Leave Activity by Period: one row per employee per year/month,
          Allocated/Taken/Balance scoped to that period. "What happened in
          this period" - filterable by year and month. Allocated only
          reflects one-time/manual allocations - accrual-based allocations
          (Odoo tracks no per-month ledger for these) are intentionally
          excluded rather than misattributed to a single month.
    """,
    'category': 'Human Resources/Time Off',
    'author': 'Auditree',
    'website': 'https://www.auditree.com',
    'license': 'OPL-1',
    'depends': ['hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_leave_balance_report_views.xml',
        'views/hr_leave_period_report_views.xml',
        'views/hr_leave_balance_report_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
