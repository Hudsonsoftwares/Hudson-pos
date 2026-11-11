# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - After Sales',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Refunds, Coupons, Returns, Replacements and Repairs on Tickets',
    'description': """
        Integrates Helpdesk Management Pro with After-Sales services:
        - Invoicing refunds / credit notes
        - Loyalty gift cards & coupons
        - Stock delivery replacements & returns
        - Manufacturing / Repair orders
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'sale_management', 'account', 'stock', 'loyalty', 'repair'],
    'data': [
        'security/ir.access.csv',
        'wizard/ticket_after_sales_wizard_views.xml',
        'views/helpdesk_ticket_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}

