# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Flag the first web client load of each login.

        Login and logout both start a session without our key, while reloads
        and new tabs reuse the session, so the welcome shows once per login.
        """
        result = super().session_info()
        if (request and request.session.uid
                and not request.session.get('xn_welcome_shown')):
            request.session['xn_welcome_shown'] = True
            result['xn_show_welcome'] = True
            # Without a logo /web/image serves a camera placeholder; the
            # client shows the company initial instead.
            result['xn_welcome_has_logo'] = bool(self.env.company.sudo().logo)
        return result
