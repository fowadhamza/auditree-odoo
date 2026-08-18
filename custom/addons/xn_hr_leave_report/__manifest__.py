# -*- coding: utf-8 -*-
{
    'name': 'HR Leave Balance Report',
    'version': '17.0.1.0.0',
    'summary': 'Consolidated leave balance table for all employees (HR/Admin view)',
    'description': """
        Adds a "Leave Balance Report" menu under Leaves > Management.
        HR managers see every employee, every leave type, with columns:
        Allocated, Taken, and Balance — filterable and pivotable.
    """,
    'category': 'Human Resources/Time Off',
    'author': 'Auditree',
    'website': 'https://www.auditree.com',
    'license': 'OPL-1',
    'depends': ['hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_leave_balance_report_views.xml',
        'views/hr_leave_balance_report_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
