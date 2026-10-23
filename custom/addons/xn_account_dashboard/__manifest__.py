# -*- coding: utf-8 -*-
{
    "name": "Auditree Accounting Overview",
    "summary": "A one-page accounting overview: cash, receivables, payables "
               "and profit for the financial year.",
    "description": """
A basic accounting dashboard, added next to Odoo's journal dashboard
under Accounting > Overview.

* Cash in each bank and cash journal, with bank lines still to be matched.
* Receivables and payables, aged, with the largest balances.
* Income, expenses and profit by month for the current financial year,
  taken from the company's fiscal year end (31 March), not the calendar year.
* What needs attention: overdue balances, unmatched bank lines, draft entries.

Posted entries only, read with the user's own access rights. Every figure
opens the list it was counted from.
    """,
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "data/xn_account_dashboard_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "xn_account_dashboard/static/src/scss/xn_account_dashboard.scss",
            "xn_account_dashboard/static/src/js/xn_account_dashboard.js",
            "xn_account_dashboard/static/src/xml/xn_account_dashboard.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
