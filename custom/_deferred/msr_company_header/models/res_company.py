from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    header_image = fields.Image(string="Header Image")
    footer_image = fields.Image(string="Footer Image")
    water_mark_log = fields.Image(string="Watermark Logo")
    signature=fields.Image(string="Signature")
    stamp=fields.Image(string="Stamp")


