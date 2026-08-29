from odoo import api, fields, models


class BaseDocumentLayout(models.TransientModel):
    _inherit = "base.document.layout"

    header_image = fields.Binary(related="company_id.header_image", readonly=False)
    footer_image = fields.Binary(related="company_id.footer_image", readonly=False)
    water_mark_log = fields.Binary(related="company_id.water_mark_log", readonly=False)
    signature = fields.Binary(related="company_id.signature", readonly=False)
    stamp = fields.Binary(related="company_id.stamp", readonly=False)

    @api.depends(
        "report_layout_id",
        "logo",
        "font",
        "primary_color",
        "secondary_color",
        "report_header",
        "report_footer",
        "layout_background",
        "layout_background_image",
        "company_details",
        "header_image",
        "footer_image",
    )
    def _compute_preview(self):
        """Override to add header_image and footer_image to the preview"""
        return super()._compute_preview()
