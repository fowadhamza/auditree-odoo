# -*- coding: utf-8 -*-

from odoo import fields, models

class PropertyType(models.Model):
    _name = 'insafety.property.rent.log'
    _description = 'Real Estate Property Rent Log'
    date_time = fields.Datetime(string="Date Time", required=True)
    year = fields.Integer(string="Year", required=True)
    month = fields.Integer(string="Month", required=True)
    status = fields.Selection([('ok','Processed'),('error','Already Processed')], required=True, default="ok")


    
    
   

