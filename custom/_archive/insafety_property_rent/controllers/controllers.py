# -*- coding: utf-8 -*-
# from odoo import http


# class InsafetyPropertyRent(http.Controller):
#     @http.route('/insafety_property_rent/insafety_property_rent', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/insafety_property_rent/insafety_property_rent/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('insafety_property_rent.listing', {
#             'root': '/insafety_property_rent/insafety_property_rent',
#             'objects': http.request.env['insafety_property_rent.insafety_property_rent'].search([]),
#         })

#     @http.route('/insafety_property_rent/insafety_property_rent/objects/<model("insafety_property_rent.insafety_property_rent"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('insafety_property_rent.object', {
#             'object': obj
#         })
