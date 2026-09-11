# -*- coding: utf-8 -*-
{
    'name': 'Auditree Forecast',
    'version': '17.0.1.0.0',
    'summary': 'Rolling 15-month FP&A forecast (revenue, salary, expenses, cash flow, P&L)',
    'description': """
        Auditree Rolling Forecast
        =========================
        Ports the standalone Auditree Forecast web app (Next.js/Prisma) into Odoo as a
        native module, restricted to firm partners via the "Forecast User" group.

        Phase 1 (this version) covers:
        - Employees, Clients, Revenue Assignments (+ overrides), Salary Plans,
          Expense Line Items, Other Cash Movements, Financial Adjustments
        - A rolling forecast window with an explicit "Advance Forecast Window" action
        - Generated monthly P&L lines and a Cash Flow summary
        - Excel export of the current forecast version

        Access is restricted to the "Forecast User" security group. By default this
        group is assigned (best-effort, via post_init_hook) to the users with logins
        sharook.mohamed@auditree.com, fowad.hamza@auditree.com, athif.azad@auditree.com
        and syed.faraz@auditree.com. Manage membership under Settings > Users & Companies
        > Groups > Forecast User.
    """,
    'category': 'Accounting/Accounting',
    'author': 'Auditree',
    'website': 'https://www.auditree.com',
    'license': 'OPL-1',
    'depends': ['base'],
    'data': [
        'security/forecast_security.xml',
        'security/ir.model.access.csv',
        'views/forecast_employee_views.xml',
        'views/forecast_client_views.xml',
        'views/forecast_revenue_assignment_views.xml',
        'views/forecast_salary_plan_views.xml',
        'views/forecast_expense_line_views.xml',
        'views/forecast_cash_movement_views.xml',
        'views/forecast_financial_adjustment_views.xml',
        'views/forecast_config_views.xml',
        'views/forecast_monthly_line_views.xml',
        'views/forecast_cash_flow_month_views.xml',
        'views/forecast_export_wizard_views.xml',
        'views/forecast_dashboard_views.xml',
        'views/forecast_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'xn_auditree_forecast/static/src/scss/forecast_dashboard.scss',
            'xn_auditree_forecast/static/src/js/forecast_dashboard.js',
            'xn_auditree_forecast/static/src/xml/forecast_dashboard.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
