# -*- coding: utf-8 -*-
from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def get_user_roots(self):
        """Hide the IT Helpdesk app from shared mailbox logins (hr@,
        accounts@, ...). Menu groups cannot express "every employee except
        shared accounts", so the root is dropped here instead; its submenus
        are only loaded under a visible root, so they go with it. The menu
        cache is per user, so a changed employee type shows after the next
        cache clear (module update or restart)."""
        roots = super().get_user_roots()
        if self.env['helpdesk.ticket']._xn_is_shared_account():
            root = self.env.ref('xn_it_helpdesk.menu_xn_it_helpdesk_root',
                                raise_if_not_found=False)
            if root:
                roots -= root
        return roots
