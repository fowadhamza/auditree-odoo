# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Charity Forms',
    'version': '17.0.0.0',
    'category': 'Accounting',
    'description' :"""
    
    Charity Forms

   
    """,
    'author': 'shameem',
    'website': 'https://www.xetensolutions.com',
    'depends': ['base', 'account', 'mail'],
    'data': [
        'data/ir_sequence_data.xml',
        'security/ir.model.access.csv',
        'views/amity_charity_view.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'test': [],
    'license':'LGPL-3',
    'installable': True,
    'auto_install': False,
    'live_test_url':'https://youtu.be/P54ye8EZuEQ',
    "images":['static/description/Banner.gif'],
}
