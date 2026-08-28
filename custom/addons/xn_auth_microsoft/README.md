# xn_auth_microsoft

Microsoft 365 (Entra ID) sign-in for Auditree, on top of core `auth_oauth`.

Core Odoo matches an OAuth login on `oauth_uid`, which stores the provider's
`sub` claim. Entra ID derives `sub` per application, so it cannot be read from
the Azure portal and cannot be pre-loaded by hand -- meaning every first login
would fall through to signup and create a duplicate user.

This module makes the first login bind instead of create: it matches the email
claim against an existing `res.users.login`, stores the `sub`, and refuses any
identity with no Odoo user. **No account is ever auto-created**, so the Odoo
user list stays the authority on who has access and Entra only authenticates.

## Azure setup (once per tenant)

Entra ID > App registrations > New registration:

- **Single tenant.** The email-claim fallback is only sound because of this --
  a multi-tenant app would let anyone create a tenant asserting any address.
- Platform **Web** (not SPA -- SPA rejects implicit token responses).
- Redirect URIs, one per environment, all on this one registration:
  - `http://localhost:8069/auth_oauth/signin` (dev)
  - `https://<gcp-host>/auth_oauth/signin`
  - `https://<prod-host>/auth_oauth/signin`
- Authentication > Implicit grant and hybrid flows > tick **Access tokens**.
  `auth_oauth` uses `response_type=token` (see its `controllers/main.py`).
- API permissions > Microsoft Graph > Delegated: `openid`, `profile`, `email`,
  then Grant admin consent.
- Enterprise applications > this app > Properties > **Assignment required =
  Yes**, then assign only staff who should reach the ERP.

There is no client secret -- the implicit flow uses a public client ID only.
Nothing here belongs in `deploy/secrets/prod.env`.

Keep **one registration across all environments**. `sub` is unique per (user,
application), so a second registration invalidates every stored `oauth_uid`
and forces every user to re-link.

## Odoo setup (once per database)

Install, then Settings > Users and Companies > OAuth Providers > Microsoft 365:

1. Client ID <- Application (client) ID
2. Authorization URL: replace `YOUR_TENANT_ID` with the Directory (tenant) ID
3. Tick **Allowed**

Everything else ships pre-filled. Installing also sets the
`auth_oauth.authorization_header` system parameter (Graph rejects the token as
a query parameter and answers 401 without it) and disables the "Log in with
Odoo.com" provider that `auth_oauth` enables by default.

Password login stays available alongside Microsoft sign-in.

## Moving to another server

Code and the provider record travel (the record lives in the database, which
moves with the dump). Per environment you need:

- [ ] TLS + a real domain. Entra rejects non-HTTPS redirect URIs except
      `http://localhost`. `deploy/07_nginx_http_only.sh` is HTTP-only today.
- [ ] The new `https://<host>/auth_oauth/signin` added to the same Azure app
      registration.
- [ ] `proxy_mode = True` in the Odoo config, and nginx sending
      `X-Forwarded-Proto https`. If Odoo computes an `http://` origin the
      redirect URI will not match and Entra answers AADSTS50011.
- [ ] `web.base.url` updated to the new host. It travels with the dump
      pointing at the old one, and `web.base.url.freeze` stops it
      self-correcting.

The redirect URI itself is never stored -- `auth_oauth` rebuilds it from the
live request host on every page load, so no code or record needs editing.

Note: `odoo-bin neutralize` disables all OAuth providers
(`auth_oauth/data/neutralize.sql`). If a cloned database shows no login
button, that is why.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `AADSTS700051` | "Access tokens" not ticked under Implicit grant |
| `AADSTS50011` | Redirect URI mismatch -- check scheme, host, trailing path |
| Access denied after consent | No Odoo user with that login; check the log |
| 401 from the UserInfo call | `auth_oauth.authorization_header` missing |
