from odoo import models, fields, api




class ResUsers(models.Model):
    _inherit = "res.users"

    is_freelancer=fields.Boolean(string="Is Consultants and Freelancers ",store=True)








