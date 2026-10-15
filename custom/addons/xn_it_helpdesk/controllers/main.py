# -*- coding: utf-8 -*-
"""Switch off helpdesk_mgmt's website (portal) ticket pages.

Tickets are raised and followed only in the backend IT Helpdesk app. The
portal pages would be a second, less controlled way in: their form skips the
employee fields and category rules, and the portal ticket page has its own
close button. Each route is redefined here to send the user to the backend
instead.
"""
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.helpdesk_mgmt.controllers.main import HelpdeskTicketController
from odoo.addons.helpdesk_mgmt.controllers.myaccount import CustomerPortalHelpdesk

MY_TICKETS_URL = '/web#action=xn_it_helpdesk.action_xn_helpdesk_my_tickets'


class XnHelpdeskTicketController(HelpdeskTicketController):

    @http.route("/ticket/close", type="http", auth="user")
    def support_ticket_close(self, **kw):
        raise NotFound()

    @http.route("/new/ticket", type="http", auth="user", website=True)
    def create_new_ticket(self, **kw):
        return request.redirect(MY_TICKETS_URL)

    @http.route("/submitted/ticket", type="http", auth="user", website=True, csrf=True)
    def submit_ticket(self, **kw):
        raise NotFound()


class XnCustomerPortalHelpdesk(CustomerPortalHelpdesk):

    def _prepare_home_portal_values(self, counters):
        # No "Tickets" tile on /my.
        counters = [c for c in counters if c != 'ticket_count']
        return super()._prepare_home_portal_values(counters)

    @http.route(["/my/tickets", "/my/tickets/page/<int:page>"],
                type="http", auth="user", website=True)
    def portal_my_tickets(self, **kw):
        return request.redirect(MY_TICKETS_URL)

    @http.route(["/my/ticket/<int:ticket_id>"], type="http", auth="public", website=True)
    def portal_my_ticket(self, ticket_id, access_token=None, **kw):
        # /mail/view checks access and opens the backend form.
        return request.redirect('/mail/view?model=helpdesk.ticket&res_id=%s' % int(ticket_id))
