# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS - Accounting Journal Connector',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Post the POS session closing journal entry in the Point of Sale Journal',
    'description': """
        When a POS session is closed, Odoo 20 posts the session's journal
        entries (sales receipt and refund receipt) in the separate
        "Point of Sale Closing" journal. This connector posts them in the
        POS configuration's "Point of Sale Journal" instead, so the closing
        entry shows up in Accounting > Journals > Point of Sale.

        Installs automatically together with Point of Sale.
    """,
    'depends': ['point_of_sale', 'account'],
    'data': [],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
