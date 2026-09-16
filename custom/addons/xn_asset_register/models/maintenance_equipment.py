# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MaintenanceEquipment(models.Model):
    """Company equipment, extended with the two things the Auditree asset
    register needs and core maintenance does not provide: our own asset tag,
    and the physical condition of the item."""

    _inherit = 'maintenance.equipment'

    xn_asset_code = fields.Char(
        string='Asset Code',
        index=True,
        copy=False,
        tracking=True,
        help="Auditree's own asset tag, for example AT-LT-002. This is the "
             "identifier the asset master sheet is keyed on, and the one that "
             "will reconcile a physical item against the accounting records "
             "later. It is not the same as Serial Number, which is the "
             "manufacturer's identifier.")

    # No default. A blank condition means nobody has recorded one yet, which is
    # true of a handful of rows in the master sheet. Defaulting to 'good' would
    # turn that gap into a claim, and would quietly relabel a broken item as
    # working on any import where the column is empty.
    xn_condition = fields.Selection(
        selection=[
            ('very_good', 'Very Good'),
            ('good', 'Good'),
            ('average', 'Average'),
            ('bad', 'Bad'),
            ('not_working', 'Not Working'),
        ],
        string='Condition',
        tracking=True,
        help="Physical condition as at the last handover or audit. Recorded on "
             "the chatter when it changes, so the history of an item survives "
             "without anyone maintaining a comments column by hand.")

    _sql_constraints = [
        # Company-wide rather than per-company: Auditree runs a single company,
        # and the codes in the master sheet are unique across the whole estate.
        # Postgres permits repeated NULLs, so items with no tag are unaffected.
        ('xn_asset_code_uniq', 'unique (xn_asset_code)',
         'That asset code is already in use. Asset codes must be unique.'),
    ]

    @api.constrains('xn_asset_code')
    def _check_xn_asset_code(self):
        """Reject a code that is only whitespace.

        Odoo stores an empty Char as NULL, which the unique constraint allows
        any number of. A code of "   " is not empty, so it would survive as a
        real value and collide with the next one on import.
        """
        for equipment in self:
            code = equipment.xn_asset_code
            if code is not False and not code.strip():
                raise ValidationError(
                    _("Asset Code cannot be blank spaces. Leave it empty "
                      "instead if the item has no tag."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._xn_clean_asset_code(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._xn_clean_asset_code(vals)
        return super().write(vals)

    @api.model
    def _xn_clean_asset_code(self, vals):
        """Trim the asset code, and store a now-empty one as NULL.

        Spreadsheet imports arrive with trailing spaces often enough that
        'AT-LT-002' and 'AT-LT-002 ' would otherwise become two distinct codes
        that the unique constraint happily accepts.
        """
        if 'xn_asset_code' in vals and vals['xn_asset_code']:
            vals['xn_asset_code'] = vals['xn_asset_code'].strip() or False
