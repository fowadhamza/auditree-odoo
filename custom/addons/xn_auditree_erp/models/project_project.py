from odoo import models, fields, api


class LeadService(models.Model):
    _inherit = "project.project"

    actual_start_date=fields.Date(string="Actual Start Date")

class ResUsers(models.Model):
    _inherit = "res.users"

    #is_freelancer=fields.Boolean(string="Is Consultants and Freelancers ",store=True)








