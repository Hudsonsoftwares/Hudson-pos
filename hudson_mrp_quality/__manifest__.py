# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'MRP Quality Bridge',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Unified BoM Operation Instructions & Quality Control Points (Hybrid Mode)',
    'description': """
MRP Quality Bridge (Hybrid Mode)
================================
- Adds an Instructions tab to BoM Operations (mrp.routing.workcenter) and Work Orders (mrp.workorder)
- Works standalone on MRP: provides recipe instructions, Register Production, Register Consumed Materials, and Register By-products
- Automatically bridges to the Quality app when Quality is installed, unlocking full Quality Control Points (Take a Picture, Pass-Fail, Measure, Spreadsheet) and automatic Quality Check generation
- Zero duplication: synchronized with quality.point when Quality is present
    """,
    'author': 'Hudson',
    'depends': ['mrp'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/mrp_routing_views.xml',
        'views/mrp_workorder_views.xml',
        'views/mrp_production_views.xml',
    ],
    'auto_install': ['mrp'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
