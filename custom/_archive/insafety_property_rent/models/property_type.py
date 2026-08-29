# -*- coding: utf-8 -*-

from odoo import fields, models

class PropertyType(models.Model):
    _name = 'insafety.property.type'
    _description = 'Real Estate Property Types'
    name = fields.Char(string="Name", required=True)

    _sql_constraints = [('name_uniq', 'unique(name)', 'Property type already exists')] 
    
   

