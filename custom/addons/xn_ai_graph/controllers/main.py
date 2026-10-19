# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request

import logging
import werkzeug

_logger = logging.getLogger(__name__)

SESSION_STATE_KEY = 'xn_ai_graph_state'


class GraphConnectController(http.Controller):
    """The consent round trip for Microsoft Graph.

    Separate from login on purpose. auth_oauth owns authentication and works
    in production; this only ever grants document access, and a user who
    never clicks Connect is unaffected by any of it.
    """

    @http.route('/xn_ai/graph/connect', type='http', auth='user', website=False)
    def connect(self, **kwargs):
        token_model = request.env['xn.graph.token'].sudo()

        state = token_model.new_state()
        # Held in the session, compared on the way back. Without this, a
        # third party could hand a signed-in user a crafted callback URL and
        # bind their Odoo account to a Microsoft account they do not own.
        request.session[SESSION_STATE_KEY] = state

        try:
            url = token_model.authorize_url(state)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("xn_ai_graph: cannot build authorize URL")
            return request.render('xn_ai_graph.connect_result', {
                'ok': False,
                'message': str(exc),
            })
        return request.redirect(url, local=False)

    @http.route('/xn_ai/graph/callback', type='http', auth='user', website=False)
    def callback(self, **kwargs):
        expected = request.session.pop(SESSION_STATE_KEY, None)
        supplied = kwargs.get('state')

        if not expected or not supplied or expected != supplied:
            _logger.warning(
                "xn_ai_graph: state mismatch on callback for %s",
                request.env.user.login)
            return request.render('xn_ai_graph.connect_result', {
                'ok': False,
                'message': _("That link has expired or did not come from "
                             "here. Please start again."),
            })

        if kwargs.get('error'):
            # The user declined, or a policy blocked it. error_description is
            # logged but not shown: it can name tenant policies.
            _logger.info(
                "xn_ai_graph: consent refused for %s: %s",
                request.env.user.login, kwargs.get('error'))
            return request.render('xn_ai_graph.connect_result', {
                'ok': False,
                'message': _("Microsoft did not grant access. Nothing has "
                             "been connected."),
            })

        code = kwargs.get('code')
        if not code:
            return request.render('xn_ai_graph.connect_result', {
                'ok': False,
                'message': _("No authorization code was returned."),
            })

        try:
            request.env['xn.graph.token'].sudo().exchange_code(
                code, user=request.env.user)
        except Exception as exc:  # noqa: BLE001
            _logger.exception(
                "xn_ai_graph: code exchange failed for %s",
                request.env.user.login)
            return request.render('xn_ai_graph.connect_result', {
                'ok': False,
                'message': _("Could not complete the connection. Please try "
                             "again."),
            })

        return request.render('xn_ai_graph.connect_result', {
            'ok': True,
            'message': _("Your Microsoft documents are now connected. The "
                         "assistant can search what you can already open."),
        })

    @http.route('/xn_ai/graph/disconnect', type='http', auth='user', website=False)
    def disconnect(self, **kwargs):
        record = request.env['xn.graph.token'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1)
        if record:
            record.action_disconnect()
        return request.render('xn_ai_graph.connect_result', {
            'ok': True,
            'message': _("Disconnected. Note this forgets the credential "
                         "here; to revoke it at Microsoft as well, remove "
                         "the app from your account at "
                         "myaccount.microsoft.com."),
        })
