# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Demo Data (Restaurant, Cafe, Loyalty & Inventory)',
    'version': '20.0.1.0.17',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Declarative XML & Python Demo Data for POS (Restaurant, Cafe, Loyalty & Inventory) loaded on manual module activation',
    'description': """
        Declarative Standard Odoo Demo Data for Point of Sale:
        - Does NOT auto-install; install/activate this module manually when demo data is needed.
        - Categories: Food, Drinks, Desserts, Chocolates & Sweets
        - Products: 40+ Restaurant & Cafe POS products with product images and combos
        - Floors & Tables: Main Floor (12 Tables) & Patio (12 Tables)
        - Courses: Starter, Main Course, Dessert, Drinks
        - Notes: Preparation Note Models (Extra Spicy, Less Sugar, No Ice, etc.)
        - Pricelists: Happy Hour (20% off), VIP Member (15% off)
        - Loyalty: Gift Cards, eWallet, and Promotional Programs
        - Inventory: Restaurant ingredients, packaging, vendors, Cold/Dry/Kitchen locations, reordering rules, BoMs, and move history
        - CRM (when CRM is installed): Resto Cafe Solutions CRM - catering, banquet, wedding & corporate lunch leads, opportunities in every stage,
          won/lost deals, activities, activity plans, email history, tags, UTM campaigns, Catering & Events team, Kochi client companies
        - Blog (when installed): recipe, coffee & festival posts in two blogs - published, scheduled and draft
        - Events (when installed): masterclasses, Christmas Food & Wine Festival with agenda, kids' party, past & draft events,
          ticket types, registrations and website pages
        - Email Marketing (when installed): mailing lists, subscribers, sent campaigns with open/click/reply/bounce stats,
          scheduled & draft mailings and an SMS campaign
        - eCommerce (when installed): 25 published packaged-food products (snacks, spices, ready-to-eat meals, pickles,
          sweets, coffee & tea, breakfast mixes) with images, pack-size variants, sale prices, ribbons, tags and stock
        - eLearning (when installed): Kerala cuisine, barista, food safety, service and recipe-library courses with sections,
          articles, infographics, videos, quizzes, karma, enrolled learners, a scored certification and a paid baking course
        - Sales: catering & events products (buffets, live counters, staff, hall, decoration, lunch-box variants),
          quotation templates with optional products, online signature and prepayment, PDF headers/footers,
          14 quotations and orders (draft, sent, expired, cancelled, delivered, down payment, invoiced, paid),
          promotions, coupons, promo code, corporate pricelist and a catering-van delivery method
        - Purchase & Inventory: Kerala suppliers, vendor prices, RFQs and purchase orders in every stage, receipts, bills, stock counts
        - Manufacturing & Shop Floor: kitchen work centres, routings, manufacturing orders in every state with live work-order timers
        - Quality & Maintenance: control points, checks, alerts; kitchen equipment, maintenance teams and requests
        - Inventory features: lot-tracked dairy, Central Kitchen Warehouse (3-step), storage locations, packages, packaging UoMs,
          FIFO/LIFO removal, reordering rules, receipt quality checks and vendor returns
        - Rental & Subscriptions: event-equipment rentals in every status; coffee/lunch/membership subscriptions with MRR
        - Planning: roles, shift templates, a 2-week staff rota and event-staff shifts linked to catering orders
        - Project & Timesheets: 5 Resto Cafe projects, tasks, milestones, updates, 60 timesheets, billable event coordination
        - Fleet, Lunch & Expenses: KL-registered vans and EV scooters with services/contracts; staff lunch vendors and orders;
          expenses in every state incl. re-invoicing to catering orders
        - Approvals & PLM: price-change, equipment and discount approvals; recipe change orders with BoM versions
        - Helpdesk: customer care, catering, webshop and IT/POS teams, SLAs, 25 tickets with ratings, refunds and coupons
        - HR: 22 staff, contracts, skills & FSSAI certificates, leave types/allocations/requests, Kerala holidays, attendance
        - Recruitment & Payroll: published website jobs, applicants in every stage, interviews; Indian payroll runs with PF/ESI
        - Collaboration: DMS licences/contracts/SOPs, live chat history & canned replies, Discuss channels, calendar,
          feedback surveys with responses, staff challenges & badges
        - Company setup: Resto Cafe Solutions branding, GSTIN/HSN (e-invoice sandbox), EAN barcodes, data recycle rules,
          wire transfer / COD providers and a UPI QR payment method in POS
        - Field Service: coffee-equipment AMC jobs, a breakdown repair, an installation, wedding venue set-up and outlet
          repairs, each linked to a project task, with technicians' planning shifts, timesheets and spare-part quotations
        - Automatically loads demo data on module activation via post_init_hook and cleans up on uninstall.
    """,
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_loyalty', 'stock'],
    'auto_install': False,
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_demo_data/static/src/overrides/control_buttons.js',
        ],
    },
    'demo': [],
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}
