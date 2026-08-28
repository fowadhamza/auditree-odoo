# -*- coding: utf-8 -*-
import logging

from odoo import api, models
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        """Link an OAuth identity to an existing Odoo user on first sign-in.

        Core Odoo matches an OAuth login on oauth_uid (the provider's "sub"
        claim) and, when that misses, falls through to signup - creating a
        brand new user. Entra ID derives "sub" per application, so the value
        cannot be read from the Azure portal and cannot be loaded into
        oauth_uid ahead of time, which means every first login would take the
        signup path.

        Instead: run core's oauth_uid match with user creation switched off,
        and on a miss fall back to the email claim. A match binds "sub" to
        that user so later logins go through core's fast path; no match is an
        AccessDenied. Nothing is ever created, so the Odoo user list stays the
        authority on who has access and Entra only proves who is signing in.
        """
        login = super(
            ResUsers, self.with_context(no_user_creation=True)
        )._auth_oauth_signin(provider, validation, params)
        if login:
            return login

        user = self._auth_oauth_find_user(validation)
        if not user:
            _logger.info(
                "OAuth sign-in refused (provider %s): no active Odoo user "
                "matches the identity claims", provider,
            )
            raise AccessDenied()

        if user.oauth_uid and user.oauth_uid != validation['user_id']:
            _logger.warning(
                "Re-binding OAuth identity of user %s: provider subject "
                "changed, which normally means the app registration was "
                "recreated", user.login,
            )

        user.write({
            'oauth_provider_id': provider,
            'oauth_uid': validation['user_id'],
            'oauth_access_token': params['access_token'],
        })
        _logger.info(
            "Bound OAuth identity from provider %s to existing user %s",
            provider, user.login,
        )
        return user.login

    @api.model
    def _auth_oauth_find_user(self, validation):
        """Return the active user whose login matches an identity claim.

        Entra ID only emits "email" when the account has a mail attribute or
        the optional claim is configured, so the UPN claims are accepted as a
        fallback. Matching is on res.users.login only - deliberately not on
        partner emails, which are neither unique nor a credential.

        Security note: this trusts the provider's email claim, which is only
        sound because the app registration is single-tenant. A multi-tenant
        registration would let anyone create a tenant asserting any address.
        """
        for key in ('email', 'preferred_username', 'upn'):
            claim = (validation.get(key) or '').strip()
            if not claim:
                continue
            # Exact match only, mirroring res.users._get_login_domain. Not
            # =ilike: LIKE reads "_" as a wildcard and underscores are common
            # in addresses, so one claim could match a different user's login.
            logins = list({claim, claim.lower()})
            user = self.sudo().search([('login', 'in', logins)], limit=1)
            if user:
                return user
        return self.browse()
