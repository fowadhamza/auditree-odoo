# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
import os
import secrets
from datetime import timedelta

import requests

_logger = logging.getLogger(__name__)

GRAPH_SCOPES = "offline_access Files.Read.All Sites.Read.All"
AUTHORITY = "https://login.microsoftonline.com"
CLIENT_SECRET_ENV_VAR = "AUDITREE_GRAPH_CLIENT_SECRET"

# Refresh this far before the token actually expires, so a call that starts
# just inside the window does not finish just outside it.
EXPIRY_MARGIN_SECONDS = 300


class XnGraphToken(models.Model):
    """One row per user who has connected their Microsoft documents.

    Never created or read through the UI by an ordinary user: the record rule
    scopes rows to their owner, and the machinery below uses sudo() with an
    explicit user filter rather than relying on the caller's environment. Both
    are deliberate -- a bug that widened the search here would hand one
    person's SharePoint to another.
    """

    _name = 'xn.graph.token'
    _description = 'Microsoft Graph Token'
    _rec_name = 'user_id'

    user_id = fields.Many2one(
        'res.users', string='User', required=True, ondelete='cascade',
        index=True)
    refresh_token = fields.Char(string='Refresh Token', groups='xn_ai_core.group_ai_administrator')
    access_token = fields.Char(string='Access Token', groups='xn_ai_core.group_ai_administrator')
    expires_at = fields.Datetime(string='Access Token Expires')
    scopes = fields.Char(string='Scopes', readonly=True)
    connected_on = fields.Datetime(string='Connected On', readonly=True)
    last_error = fields.Char(string='Last Error', readonly=True)

    _sql_constraints = [
        ('user_uniq', 'unique (user_id)',
         'A user can only have one Microsoft Graph connection.'),
    ]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @api.model
    def _config(self, key, default=None):
        value = self.env['ir.config_parameter'].sudo().get_param('xn_ai_graph.' + key)
        return value if value else default

    @api.model
    def _client_secret(self):
        """Environment only. No config-parameter fallback, unlike xn_ai_core.

        The AI key buys a read-only model call. This secret, combined with a
        stored refresh token, reaches a person's documents and mail, so it
        does not get a convenience path that ends with it in a database dump.
        """
        secret = os.environ.get(CLIENT_SECRET_ENV_VAR)
        if not secret:
            raise UserError(_(
                "Microsoft Graph is not configured on this server: the %s "
                "environment variable is not set.", CLIENT_SECRET_ENV_VAR))
        return secret

    @api.model
    def _tenant_id(self):
        tenant = self._config('tenant_id')
        if not tenant:
            raise UserError(_("The Microsoft tenant ID is not configured."))
        return tenant

    @api.model
    def _client_id(self):
        client = self._config('client_id')
        if not client:
            raise UserError(_("The Microsoft client ID is not configured."))
        return client

    @api.model
    def _redirect_uri(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return "%s/xn_ai/graph/callback" % (base or '').rstrip('/')

    # ------------------------------------------------------------------
    # The flow
    # ------------------------------------------------------------------

    @api.model
    def authorize_url(self, state):
        return (
            "%s/%s/oauth2/v2.0/authorize"
            "?client_id=%s&response_type=code&redirect_uri=%s"
            "&response_mode=query&scope=%s&state=%s"
        ) % (
            AUTHORITY, self._tenant_id(), self._client_id(),
            requests.utils.quote(self._redirect_uri(), safe=''),
            requests.utils.quote(GRAPH_SCOPES, safe=''),
            state,
        )

    @api.model
    def _token_endpoint(self):
        return "%s/%s/oauth2/v2.0/token" % (AUTHORITY, self._tenant_id())

    @api.model
    def _post_token_request(self, data):
        data.update({
            'client_id': self._client_id(),
            'client_secret': self._client_secret(),
        })
        response = requests.post(
            self._token_endpoint(), data=data,
            timeout=int(self._config('timeout_seconds', 30)))
        if response.status_code >= 400:
            # Entra puts the useful part in error_description. Log it, but
            # never hand it back to the browser: it can name the tenant, the
            # app and the exact policy that refused.
            try:
                detail = response.json()
            except ValueError:
                detail = {'raw': response.text[:500]}
            _logger.warning("xn_ai_graph: token request failed: %s", detail)
            raise UserError(_(
                "Microsoft refused the request. Please try connecting again, "
                "and tell your administrator if it keeps happening."))
        return response.json()

    @api.model
    def exchange_code(self, code, user=None):
        """Trade an authorization code for tokens and store them."""
        user = user or self.env.user
        payload = self._post_token_request({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self._redirect_uri(),
            'scope': GRAPH_SCOPES,
        })
        return self._store(user, payload)

    @api.model
    def _store(self, user, payload):
        values = {
            'user_id': user.id,
            'access_token': payload.get('access_token'),
            'expires_at': fields.Datetime.now() + timedelta(
                seconds=int(payload.get('expires_in') or 3600)),
            'scopes': payload.get('scope'),
            'last_error': False,
        }
        # Entra does not always return a new refresh token on refresh. Keeping
        # the old one is correct; overwriting it with None would disconnect
        # the user on their next call.
        if payload.get('refresh_token'):
            values['refresh_token'] = payload['refresh_token']

        existing = self.sudo().search([('user_id', '=', user.id)], limit=1)
        if existing:
            existing.write(values)
            return existing
        values['connected_on'] = fields.Datetime.now()
        return self.sudo().create(values)

    @api.model
    def get_valid_token(self, user=None):
        """A usable access token for `user`, refreshing if needed.

        Returns None when the user has not connected, which callers should
        treat as "offer to connect", not as an error.
        """
        user = user or self.env.user
        record = self.sudo().search([('user_id', '=', user.id)], limit=1)
        if not record or not record.refresh_token:
            return None

        fresh_enough = (
            record.access_token
            and record.expires_at
            and record.expires_at > fields.Datetime.now() + timedelta(
                seconds=EXPIRY_MARGIN_SECONDS)
        )
        if fresh_enough:
            return record.access_token

        try:
            payload = self._post_token_request({
                'grant_type': 'refresh_token',
                'refresh_token': record.refresh_token,
                'scope': GRAPH_SCOPES,
            })
        except UserError:
            # A refresh that fails is usually revoked consent or a changed
            # password. Clear the dead credential so the user is offered a
            # reconnect rather than silently getting nothing forever.
            record.write({
                'refresh_token': False,
                'access_token': False,
                'last_error': 'refresh_failed',
            })
            _logger.info(
                "xn_ai_graph: cleared dead Graph connection for %s", user.login)
            return None

        return self._store(user, payload).access_token

    def action_disconnect(self):
        """Forget the stored credential. Does not revoke it at Microsoft."""
        for record in self:
            record.sudo().write({
                'refresh_token': False,
                'access_token': False,
                'expires_at': False,
                'last_error': 'disconnected',
            })
        return True

    @api.model
    def new_state(self):
        """CSRF token for the authorize round trip, kept in the session."""
        state = secrets.token_urlsafe(24)
        return state
