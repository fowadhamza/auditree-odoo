from odoo import models,fields,api


class ResPartnerBankDetails(models.Model):
    _inherit = 'res.partner.bank'

    iban = fields.Char('IBAN#')
    swift_code = fields.Char('Swift Code')
    branch = fields.Char('Branch')
    intl_acc_num=fields.Char(string="International Account Number")





