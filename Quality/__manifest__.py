# -*- coding: utf-8 -*-
{
    'name': 'Quality',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Quality',
    'summary': 'Quality Control Points, Quality Checks, Quality Alerts, Quality Teams '
               '- built for Odoo Community, integrated with Inventory & Manufacturing',
    'description': """
Custom Quality Management
==========================
A from-scratch recreation of the core Odoo Enterprise "Quality" app workflow,
built to run on Odoo 20 Community.

Implements:
-----------
* Quality Control Points (quality.point)   - the automation rule:
  "when this operation happens, create this kind of inspection"
* Quality Checks (quality.check)           - the actual inspection instance
* Quality Alerts (quality.alert)           - defect / problem records, Kanban stages
* Quality Teams / Tags / Reasons / Alert Stages - supporting configuration
* Automatic generation of Quality Checks from:
    - Inventory operations (Receipts, Deliveries, Internal Transfers)
    - Manufacturing Orders / Work Orders
* Check types: Instructions, Take a Picture, Register Consumed Materials,
  Register Production, Print Label, Pass-Fail, Measure, Worksheet, Spreadsheet
* Failure Locations (quarantine locations for failed quantity-controlled checks)
* Smart buttons on stock.picking and mrp.production showing pending/failed checks
* Automatic Quality Alert creation on check failure
""",
    'author': 'Hudson Software Solutions Private Limited',
    'website': '',
    'depends': ['base', 'mail', 'product', 'mrp', 'stock', 'spreadsheet', 'repair'],
    'data': [
        'security/quality_security.xml',
        'security/ir.access.csv',
        'data/quality_sequence.xml',
        'wizard/quality_check_fail_views.xml',
        'wizard/quality_check_wizard_views.xml',
        'views/quality_point_views.xml',
        'data/quality_data.xml',
        'views/quality_team_views.xml',
        'views/quality_tag_views.xml',
        'views/quality_spreadsheet_template_views.xml',
        'views/quality_alert_stage_views.xml',
        'views/quality_check_views.xml',
        'views/quality_alert_views.xml',
        'views/stock_picking_views.xml',
        'views/mrp_production_views.xml',
        'views/repair_order_views.xml',
        'views/quality_menus.xml',
    ],
    'application': True,
    'installable': True,
    'assets': {
        'spreadsheet.o_spreadsheet': [
            'Quality/static/src/spreadsheet_bundle/**/*.js',
        ],
        'web.assets_backend': [
            'Quality/static/src/assets_backend/**/*.js',
        ],
    },
    'license': 'LGPL-3',
}
