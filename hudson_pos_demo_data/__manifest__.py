# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Demo Data (Restaurant, Cafe, Loyalty & Inventory)',
    'version': '20.0.1.0.37',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Declarative XML & Python Demo Data for POS (Restaurant, Cafe, Loyalty & Inventory), auto-installed and loaded per app as apps get installed',
    'description': """
        Declarative Standard Odoo Demo Data for Point of Sale:
        - Auto-installs with every new database (depends only on base), whatever apps are installed.
        - Loads the demo data of each app as soon as that app is installed, also when it is installed later:
          e.g. install Point of Sale later and the POS restaurant/cafe data loads automatically, install
          Appraisals later and the appraisal demo loads automatically. No manual action or configuration needed.
        - Never resets existing data: records that existed before an install/upgrade (possibly modified by the
          user) are not changed or deleted; only new demo records and fields added by the new module are written,
          and demo records deleted by the user are not recreated from the XML files.
        - Categories: Food, Drinks, Desserts, Chocolates & Sweets
        - Products: 40+ Restaurant & Cafe POS products with product images and combos
        - Floors & Tables: decorated floor plans - Main Dining (12 tables) with walls, entrance, reception desk,
          waiting lounge, open kitchen, dessert display, coffee & mocktail bar with stools, booths, family area,
          chef's table, restrooms and plants; Garden Patio (12 tables) with hedges, fountain, parasols, fairy
          lights, live grill and fire-pit lounge; chairs drawn around every table
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
        - Purchase Agreements & Alternatives (when installed): Café Food Supplies, Restaurant Kitchen Supplies and
          Beverage & Packaging Supplies purchase templates; 4 calls for tender (café dairy, espresso beans & tea,
          sushi/grill fish, salad produce) built from the existing demo vendors and products - a main RFQ and an
          alternative RFQ each, priced from the vendors' existing prices and lead times, to compare product lines
          and choose a vendor per line; a confirmed
          Basmati Rice blanket order (100 kg at Rs 120/kg) with a confirmed 40 kg release, a 30 kg RFQ and 30 kg open
        - Manufacturing & Shop Floor: kitchen work centres, routings, manufacturing orders in every state with live work-order timers
        - Quality & Maintenance: control points, checks, alerts; kitchen equipment, maintenance teams and requests
        - FEFO (First Expiry First Out): Perishables (FEFO) category & Perishables Chiller location, 6 products with
          expiration/best-before/removal/alert times, lots received out of expiry order (incl. expired & alert lots),
          a validated and a reserved delivery showing FEFO lot selection
          and (with Purchase) lot-wise expiration dates on purchases: Greek Yogurt, Fresh Cream and Paneer bought
          from a dairy vendor in several lots with different expiration dates (received POs, a receipt ready to
          validate, an RFQ), scrap of an expired lot and a FEFO delivery across the purchased lots
        - Inventory features: lot-tracked dairy, Central Kitchen Warehouse (3-step), storage locations, packages, packaging UoMs,
          FIFO/LIFO removal, reordering rules, receipt quality checks and vendor returns
        - Inventory rules: inter-warehouse replenishment Distribution Center (DC) -> Transit -> Store 1 (S1) / Store 2 (S2):
          warehouse supply routes, a cold-chain pull route through per-store reefer-van transit locations,
          push rules putting store receipts away into the walk-in chillers, min/max replenishment rules per store
          (and Buy rules at the DC) and the internal transfers they generated in every stage
        - Rental & Subscriptions: event-equipment rentals in every status; coffee/lunch/membership subscriptions with MRR
        - Planning: roles, shift templates, a 2-week staff rota and event-staff shifts linked to catering orders
        - Project & Timesheets: 5 Resto Cafe projects, tasks, milestones, updates, 60 timesheets, billable event coordination
        - Project Templates (with Sales): Wedding & Banquet Catering, Corporate Lunch Onboarding, Kitchen Setup
          Consultancy (invoiced on milestones), Birthday Party, Coffee Machine AMC and Cooking Masterclass templates
          with stages, milestones, tasks and sub-tasks; 6 service products that create a project from their
          template when a sales order is confirmed; confirmed orders with their generated projects and quotations
        - Sign (when installed): Employee Employment, Vendor Supply, Customer Catering and Recipe Confidentiality
          (NDA) templates in Sign > Templates, each with its agreement PDF, 2-3 signer roles in signing order and
          Signature, Initials, Name, Date, Text, Checkbox, Company, Email, Selection and Multiline fields
        - Knowledge (when installed): Restaurant Operations, Employee Onboarding, Food Safety & Hygiene and Kitchen
          SOP articles with nested sub-articles, headings, lists, check lists, tables, images, banners, columns,
          cover images, properties and embedded Item Kanban / List / Calendar views with their items
        - Fleet, Lunch & Expenses: KL-registered vans and EV scooters with services/contracts; staff lunch vendors and orders;
          expenses in every state incl. re-invoicing to catering orders
        - Batch Transfers & fleet delivery: 5 delivery routes combining 15 orders - several orders of one customer
          (Harbour Park Hotel, BlueWave) and orders of different customers - done, in progress and draft, stops
          sorted by PIN code, plus open deliveries to add to a batch; with Stock Transport (stock_fleet) each
          batch gets its fleet vehicle, driver and payload weight/volume load %
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
        - Visitor Management (when installed): MG Road reception & Central Kitchen gate front desks, meeting rooms,
          18 visitors (inspectors, suppliers, wedding & corporate clients, candidates) in every status
        - Employee Referral (when installed): staff referrals for kitchen, bar, service & delivery jobs with points, rewards and alerts
        - Appraisals (when installed): review cycles in every state with goals, ratings and manager/employee feedback
        - Appointments (when installed): party halls, banquet hall, garden lawn, kids' party room, private dining &
          tasting room as bookable resources, a Party Hall booking type and venue bookings in every status
        - Automatically loads demo data for the installed apps, and for every app installed afterwards; cleans up on uninstall.
    """,
    # Only `base`: every other app is optional. Demo data of each app is loaded when that app is
    # installed (now or later) by models/demo_autoloader.py.
    'depends': ['base'],
    'auto_install': True,
    'data': ['data/ir_cron.xml'],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_demo_data/static/src/overrides/control_buttons.js',
            'hudson_pos_demo_data/static/src/overrides/combo_configurator.js',
        ],
    },
    'demo': [],
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}
