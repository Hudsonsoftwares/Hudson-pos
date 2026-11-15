# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

{
    'name': 'Field Service',
    'version': '20.0.4.5.0',
    'category': 'Services/Field Service',
    'sequence': 55,
    'summary': 'Plan onsite interventions in Planning, invoice time and materials, complete worksheets, and track customer satisfaction',
    'description': """
Field Service Management
========================

A comprehensive field service management module for Odoo 19 that provides:

* **Service Order Management** — Create, schedule, and track field service orders
* **Timer-based Time Tracking** — Start/pause/stop timer to automatically record time
* **Product Tracking** — Track products and parts used during service visits
* **Project Integration** — Link service orders to projects and tasks; inherit the project's
  originating Sale Order for seamless billing
* **Sales Order Billing Flow** — Products added to a FS order are automatically synced to the
  linked (or auto-created) Sale Order and invoiced via standard Odoo SO invoicing
* **Invoice Generation** — Create customer invoices from time and product charges
* **Employee Dashboard** — Overview of all technicians with their assigned work and time
* **PDF Reports** — Detailed service reports with time, products, and customer signature
* **Analysis Reports** — Pivot and graph views for service analytics
* **Customer Signature** — Capture customer sign-off on completed work
* **Worksheet** — Document work performed during service visits; set on a service product,
  its Sales Orders generate the field service jobs
* **Customer Satisfaction Survey** — Automatically send a satisfaction survey on order completion
* **Customer Ratings** — Store and display customer ratings directly on the order
* **Live Technician Map** — Real-time map showing all active technicians' GPS locations
* **Geolocation Tracking** — Track technician location when timer starts/resumes
    """,
    'website': 'https://github.com/nandusaji2001/hudson-community',
    'author': 'Hudson Community',
    'depends': [
        'mail',
        'project',
        'hr',
        'hr_timesheet',
        'product',
        'sale',
        'account',
        'uom',
        'survey',           # Required: Customer satisfaction survey feature
        'hudson_planning',
        'stock',            # Required: Inventory deductions
        'base_geolocalize', # Required: customer locations on the job maps
    ],
    'data': [
        # Security (must be loaded first)
        'security/field_service_security.xml',
        'security/ir.access.csv',
        'data/field_service_sequence_data.xml',
        'data/field_service_stage_data.xml',
        'data/field_service_mail_template.xml',
        'data/field_service_survey_data.xml',
        'data/field_service_rating_mail_template.xml',
        'data/field_service_publish_mail_template.xml',
        'data/mail_template_data.xml',
        'data/fs_worksheet_template_data.xml',
        'data/fs_settings_data.xml',
        'wizard/field_service_stop_wizard_views.xml',
        'wizard/field_service_create_invoice_wizard_views.xml',
        'wizard/fs_order_publish_wizard_views.xml',
        'views/field_service_order_views.xml',
        'views/fs_worksheet_template_views.xml',
        'views/fs_equipment_views.xml',
        'views/fs_request_form_templates.xml',
        'views/fs_planning_slot_views.xml',
        'views/product_template_views.xml',
        'views/field_service_material_views.xml',
        'views/field_service_dashboard_views.xml',
        'views/field_service_stage_views.xml',
        'views/field_service_tag_views.xml',
        'views/field_service_live_map_views.xml',
        'views/res_config_settings_views.xml',
        'report/field_service_report_views.xml',
        'report/field_service_report_templates.xml',
        'views/field_service_menus.xml',
        'views/field_service_portal_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Existing assets
            'hudson_field_service/static/src/js/geolocation_action.js',
            'hudson_field_service/static/src/xml/geolocation_action.xml',
            'hudson_field_service/static/src/js/fs_photo_upload.js',
            'hudson_field_service/static/src/xml/fs_photo_upload.xml',
            'hudson_field_service/static/src/js/fs_worksheet_definition.js',
            'hudson_field_service/static/src/xml/fs_worksheet_definition.xml',
            'hudson_field_service/static/src/scss/fs_worksheet_definition.scss',
            # Live Map (new)
            'hudson_field_service/static/src/css/fs_live_map.css',
            'hudson_field_service/static/src/js/fs_live_map.js',
            'hudson_field_service/static/src/xml/fs_live_map.xml',
            # Job maps (Maps > By Resource / Timeline, Planning > My > Map)
            'hudson_field_service/static/src/css/fs_job_map.css',
            'hudson_field_service/static/src/js/fs_job_map.js',
            'hudson_field_service/static/src/xml/fs_job_map.xml',
            # Field Service Board
            'hudson_field_service/static/src/css/fs_board.css',
            'hudson_field_service/static/src/js/fs_board.js',
            'hudson_field_service/static/src/xml/fs_board.xml',
        ],
    },
    'installable': True,
    # Field service jobs are part of the Planning app (shifts with a customer).
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_install_hook',
    'post_upgrade_hook': 'post_upgrade_hook',
    'license': 'LGPL-3',
}
