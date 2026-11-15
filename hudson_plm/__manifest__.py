# -*- coding: utf-8 -*-
{
    'name': 'Hudson PLM',
    'version': '20.0.1.1.1',
    'category': 'Manufacturing/Product Lifecycle Management',
    'summary': 'Manage Engineering Change Orders and Product Versions',
    'description': """
Hudson PLM
==========
Integrates with the Manufacturing module so that product versions can be managed effectively through Engineering Change Orders (ECOs).
    """,
    'depends': ['mrp', 'mail'],
    'data': [
        'security/plm_security.xml',
        'security/ir.access.csv',
        'data/mrp_eco_data.xml',
        'views/mrp_eco_bom_change_views.xml',
        'views/plm_menus.xml',
        'views/mrp_eco_views.xml',
        'views/plm_report_views.xml',
        'views/mrp_eco_type_views.xml',
        'views/mrp_eco_stage_views.xml',
        'views/mrp_eco_tag_views.xml',
        'views/mrp_bom_views.xml',
        'views/plm_master_data_views.xml',
        'report/mrp_eco_report.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
