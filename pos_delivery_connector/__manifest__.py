# -*- coding: utf-8 -*-
{
    'name': 'POS Delivery Connector',
    'version': '20.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Standalone Food Delivery Connector for Point of Sale (Swiggy, Zomato, UrbanPiper, Uber Eats)',
    'description': """
POS Food Delivery Connector
===========================
Seamlessly integrates food delivery platforms and aggregators (UrbanPiper, Swiggy, Zomato, Radyes, Uber Eats, Talabat, Deliveroo) directly into Odoo Point of Sale and Kitchen Display System.

Key Features
------------
* **Direct Webhook Ingestion**: Receives incoming online orders via secure webhooks and automatically maps them to active POS sessions.
* **Platform Management**: Configure active delivery platforms with custom codes and color indicators.
* **Live POS Alerts**: Real-time navbar badge notifications with audio chime on incoming delivery orders.
* **Fulfillment & Rider Details**: Tracks external order reference, delivery customer address, rider name, rider phone, and cooking instructions.
* **Status Lifecycle**: Manage delivery stages (New, Accepted, Preparing, Ready for Pickup, Out for Delivery, Delivered, Cancelled).
* **Kitchen Display Integration**: Automatically routes online delivery tickets into the Kitchen Display System with 'Delivery' fulfillment tag.
* **Simulate & Test Tool**: Built-in test order generator to verify webhook workflows with one click.
    """,
    'author': 'Hudson Softwares',
    'website': 'https://www.hudsonsoftwares.com',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.access.csv',
        'data/delivery_platform_data.xml',
        'views/pos_delivery_platform_views.xml',
        'views/pos_order_views.xml',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_delivery_connector/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
