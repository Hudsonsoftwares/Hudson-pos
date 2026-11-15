# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'Hudson Subscriptions',
    'version': '20.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'sequence': 55,
    'summary': 'Manage recurring contracts, subscriptions, automated billing, renewals and MRR analytics',
    'description': """
Hudson Subscriptions Management
===============================

Complete enterprise-grade subscription and recurring billing management:

* **Subscription Lifecycle** - Seamless flow from Quotation -> In Progress -> To Renew -> Churned / Paused / Upsell.
* **Recurring Plans** - Configure daily, weekly, monthly, quarterly, semi-annual, and yearly billing plans.
* **Automated Recurring Invoicing** - Automated cron-driven recurring invoice generation with flexible billing dates.
* **Renewals & Upsells** - One-click renewal wizards and upsell order tracking with automatic delta MRR computation.
* **MRR & ARR Analytics** - Built-in reporting for Subscriptions, Retention cohorts, MRR Breakdown, and MRR Timeline.
* **Quotation Templates** - Pre-configured templates with recurring lines and plans.
* **Close Reasons** - Track and analyze churn reasons when customers cancel subscriptions.
* **Customer Portal** - Enable customers to view active subscriptions and invoice history online.
    """,
    'author': 'Hudson Community',
    'website': 'https://github.com/nandusaji2001/hudson-community',
    'depends': [
        'base',
        'web',
        'sale_management',
        'account',
        'product',
        'mail',
        'portal',
        'website_sale',
    ],
    'data': [
        # Security
        'security/subscription_security.xml',
        'security/ir.access.csv',

        # Data & Cron
        'data/subscription_sequence.xml',
        'data/subscription_data.xml',
        'data/portal_entry_data.xml',

        # Wizard Views (must be loaded before actions referencing them)
        'wizard/subscription_close_wizard_views.xml',
        'wizard/subscription_renew_wizard_views.xml',

        # Views
        'views/subscription_plan_views.xml',
        'views/subscription_close_reason_views.xml',
        'views/quotation_template_views.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/subscription_reporting_views.xml',
        'views/subscription_portal_templates.xml',
        'views/subscription_views.xml',
        'views/website_sale_templates.xml',

        # Menus (must be loaded after all views and actions)
        'views/subscription_menu.xml',
    ],
    'demo': [
        'data/subscription_demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_subscriptions/static/src/js/owl_compat.js',
            'hudson_subscriptions/static/src/css/subscription_backend.css',
            'hudson_subscriptions/static/src/css/retention_analysis.css',
            'hudson_subscriptions/static/src/js/retention_analysis.js',
            'hudson_subscriptions/static/src/xml/retention_analysis.xml',
        ],
        'web.assets_frontend': [
            'hudson_subscriptions/static/src/js/subscription_cart.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
