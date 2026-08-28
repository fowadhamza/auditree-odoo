# -*- coding: utf-8 -*-
{
    'name': 'Auditree Microsoft 365 Login',
    'version': '17.0.1.0.0',
    'summary': 'Sign in to Auditree with Microsoft 365 (Entra ID) accounts',
    'description': """
        Binds Microsoft 365 / Entra ID OAuth2 logins to existing Odoo users.

        Odoo core matches an OAuth identity on oauth_uid, which holds the
        provider's "sub" claim. Entra ID derives "sub" per application, so the
        value cannot be looked up in the Azure portal and cannot be filled in
        by hand ahead of the first login. This module closes that gap: on the
        first Microsoft sign-in it matches the email claim against an existing
        Odoo login, stores the "sub" for subsequent logins, and refuses any
        identity that has no Odoo user. Accounts are never auto-created.

        Also ships the Entra ID provider record pre-filled with the endpoints,
        scope and OIDC settings Odoo needs, so provisioning another server is
        a matter of pasting the tenant ID and client ID. See README.md for the
        Azure-side setup and the per-environment checklist.
    """,
    'category': 'Tools',
    'author': 'Auditree',
    'website': 'https://www.auditree.com',
    'license': 'OPL-1',
    'depends': ['auth_oauth'],
    'data': [
        'data/auth_oauth_provider_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
