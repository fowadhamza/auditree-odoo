# -*- coding: utf-8 -*-
{
    "name": "Auditree Microsoft Graph Access",
    "summary": "Per-user Microsoft Graph tokens, so the assistant can search "
               "SharePoint as the person asking.",
    "description": """
Obtains and refreshes a Microsoft Graph token for each user who opts in.

Why this is separate from xn_auth_microsoft
-------------------------------------------
That module handles sign-in and works in production. It is not touched here,
deliberately: breaking login to add document search would be a poor trade.

It also cannot be reused. Odoo's auth_oauth drives the implicit flow
(enableAccessTokenIssuance is true on the app registration), which by design
never issues a refresh token, and the login scope is openid/profile/email --
no Graph permissions at all. The token stored at login therefore cannot call
Graph, and would be dead an hour later even if it could.

So this module runs its own authorization-code flow purely for Graph, leaving
authentication alone. A user signs in as they always have, and separately
clicks Connect if they want the assistant to search their documents.

Opt-in, per user, delegated
---------------------------
Nobody's documents become searchable until they connect. The token obtained
is delegated: it can reach exactly what that person can already open in
SharePoint, enforced by SharePoint, not by anything written here.

Application permissions were rejected for this. An app-only token reads every
site in the tenant, including HR and board material, and would answer from
them for whoever asked. The whole design exists to avoid that.

What is stored, and the risk it carries
---------------------------------------
A refresh token grants standing access to that person's SharePoint and
OneDrive. Odoo stores such fields in plain columns and they travel in
database dumps, exactly as auth_oauth's own oauth_access_token does today.
The model is restricted and row-scoped, but that is access control, not
encryption. Treat a database dump accordingly.
    """,
    "version": "17.0.1.0.0",
    "category": "Technical",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "base",
        "xn_ai_core",
        "xn_ai_assistant",
    ],
    "data": [
        "security/xn_ai_graph_security.xml",
        "security/ir.model.access.csv",
        "views/xn_graph_token_views.xml",
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
