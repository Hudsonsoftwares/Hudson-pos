# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from datetime import datetime, date, timedelta
from odoo import fields, Command

_logger = logging.getLogger(__name__)


def load_business_suite_demo_data(env):
    """
    Populates comprehensive interconnected demo data across:
    1. CRM (Leads, Opportunities, Pipeline stages)
    2. Sales (Quotations, Confirmed Sales Orders)
    3. Inventory (Stock levels & Quantities on hand for kitchen/cafe)
    4. Purchase (Vendor RFQs, Confirmed Purchase Orders)
    5. Manufacturing (BOMs, Production Orders)
    6. Maintenance (Equipments, Maintenance Requests)
    7. Events (Food & Wine Masterclasses, Brunches, Registrations)
    8. Survey (Dining Experience & Customer Feedback Surveys)
    """
    _logger.info("Hudson Business Suite: Loading demo data across CRM, Sales, Inventory, Purchase, MRP, Maintenance, Events & Survey...")

    today = date.today()
    company = env.company

    # Helper to get or create demo partners
    def get_or_create_partner(name, is_company=True, email=None, phone=None, supplier=False):
        Partner = env['res.partner'].sudo()
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': is_company,
                'email': email or f"{name.lower().replace(' ', '.')}@example.com",
                'phone': phone or '+91 98470 12345',
                'street': 'Marine Drive, Kochi',
                'city': 'Kochi',
                'zip': '682011',
            })
        return partner

    # -------------------------------------------------------------------------
    # 1. CRM Opportunities & Pipeline
    # -------------------------------------------------------------------------
    if 'crm.lead' in env:
        _logger.info("Hudson Business Suite: Setting up CRM demo leads...")
        Lead = env['crm.lead'].sudo()
        Stage = env['crm.stage'].sudo()

        stage_new = Stage.search([('name', '=', 'New')], limit=1)
        stage_qual = Stage.search([('name', '=', 'Qualified')], limit=1)
        stage_prop = Stage.search([('name', '=', 'Proposition')], limit=1)
        stage_won = Stage.search([('name', '=', 'Won')], limit=1)

        crm_specs = [
            {
                'name': 'TechCorp Annual Gala Banquet (150 Pax)',
                'partner_name': 'TechCorp Systems Pvt Ltd',
                'contact_name': 'Anand Verma',
                'email_from': 'anand.verma@techcorp.in',
                'phone': '+91 98471 22334',
                'expected_revenue': 185000.0,
                'probability': 100.0,
                'stage_id': stage_won.id if stage_won else False,
                'priority': '3',
            },
            {
                'name': 'Wedding Reception Catering & Live Mocktail Bar',
                'partner_name': 'Menon Family Celebrations',
                'contact_name': 'Dr. Priya Menon',
                'email_from': 'priya.menon@hospital.org',
                'phone': '+91 97450 99887',
                'expected_revenue': 340000.0,
                'probability': 70.0,
                'stage_id': stage_prop.id if stage_prop else False,
                'priority': '2',
            },
            {
                'name': 'Executive Daily Lunch Subscription (Infopark Hub)',
                'partner_name': 'Infopark Software Solutions',
                'contact_name': 'Ramesh Krishnan',
                'email_from': 'hr@infoparksoft.com',
                'phone': '+91 94471 55667',
                'expected_revenue': 78000.0,
                'probability': 40.0,
                'stage_id': stage_qual.id if stage_qual else False,
                'priority': '2',
            },
            {
                'name': 'Private Rooftop Birthday & Live Acoustic Night (40 Pax)',
                'partner_name': 'Kavya Rajesh',
                'contact_name': 'Kavya Rajesh',
                'email_from': 'kavya.rajesh@gmail.com',
                'phone': '+91 99950 11223',
                'expected_revenue': 42000.0,
                'probability': 15.0,
                'stage_id': stage_new.id if stage_new else False,
                'priority': '1',
            },
        ]

        for cspec in crm_specs:
            lead = Lead.search([('name', '=', cspec['name'])], limit=1)
            if not lead:
                Lead.create(cspec)

    # -------------------------------------------------------------------------
    # 2. Sales Orders & Quotations
    # -------------------------------------------------------------------------
    if 'sale.order' in env:
        _logger.info("Hudson Business Suite: Setting up Sales demo orders...")
        SaleOrder = env['sale.order'].sudo()
        Product = env['product.product'].sudo()

        cust_malabar = get_or_create_partner('Malabar Corporate Club', is_company=True, email='banquets@malabarclub.org')
        cust_emerald = get_or_create_partner('Emerald Luxury Living', is_company=True, email='concierge@emeraldluxury.com')
        cust_cyber = get_or_create_partner('Cyberpark Innovations', is_company=True, email='admin@cyberparkhub.com')

        # Find or create catering service products
        prod_catering = Product.search([('name', '=', 'Banquets & Buffet Catering Service')], limit=1)
        if not prod_catering:
            prod_catering = Product.create({
                'name': 'Banquets & Buffet Catering Service',
                'type': 'service',
                'list_price': 1500.0,
                'invoice_policy': 'order',
            })

        prod_dining = Product.search([('name', '=', 'Chef Degustation Tasting Pass')], limit=1)
        if not prod_dining:
            prod_dining = Product.create({
                'name': 'Chef Degustation Tasting Pass',
                'type': 'service',
                'list_price': 2200.0,
                'invoice_policy': 'order',
            })

        sale_specs = [
            {
                'partner_id': cust_malabar.id,
                'client_order_ref': 'MALABAR-GALA-2026',
                'state': 'sale',
                'lines': [
                    {'product_id': prod_catering.id, 'name': 'Grand Malabar Buffet Feast (60 Pax)', 'product_uom_qty': 60, 'price_unit': 1400.0},
                ]
            },
            {
                'partner_id': cust_emerald.id,
                'client_order_ref': 'EMERALD-CHEF-PASS',
                'state': 'sale',
                'lines': [
                    {'product_id': prod_dining.id, 'name': 'VIP Wine & Dine Tasting Experience (15 Pax)', 'product_uom_qty': 15, 'price_unit': 2200.0},
                ]
            },
            {
                'partner_id': cust_cyber.id,
                'client_order_ref': 'CYBER-LUNCH-RFQ',
                'state': 'draft',
                'lines': [
                    {'product_id': prod_catering.id, 'name': 'Corporate Weekly Lunch Buffet Trial (30 Pax)', 'product_uom_qty': 30, 'price_unit': 1200.0},
                ]
            },
        ]

        for sspec in sale_specs:
            so = SaleOrder.search([('partner_id', '=', sspec['partner_id']), ('client_order_ref', '=', sspec['client_order_ref'])], limit=1)
            if not so:
                so = SaleOrder.create({
                    'partner_id': sspec['partner_id'],
                    'client_order_ref': sspec['client_order_ref'],
                    'date_order': fields.Datetime.now() - timedelta(days=2),
                })
                for l in sspec['lines']:
                    env['sale.order.line'].sudo().create({
                        'order_id': so.id,
                        'product_id': l['product_id'],
                        'name': l['name'],
                        'product_uom_qty': l['product_uom_qty'],
                        'price_unit': l['price_unit'],
                    })
                if sspec['state'] == 'sale':
                    try:
                        so.action_confirm()
                    except Exception as e:
                        _logger.warning("Could not confirm demo sale order %s: %s", so.name, e)

    # -------------------------------------------------------------------------
    # 3. Inventory Stock Levels (Kitchen & Cafe Ingredients)
    # -------------------------------------------------------------------------
    if 'stock.quant' in env:
        _logger.info("Hudson Business Suite: Setting up Inventory stock levels...")
        Product = env['product.product'].sudo()
        Location = env['stock.location'].sudo()
        Quant = env['stock.quant'].sudo()

        stock_loc = Location.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', company.id)
        ], limit=1)
        if not stock_loc:
            stock_loc = Location.search([('usage', '=', 'internal')], limit=1)

        raw_materials = [
            ('Basmati Biryani Aged Rice (Premium)', 50.0, 110.0),
            ('Cold Pressed Organic Coconut Oil', 30.0, 240.0),
            ('Highland Malabar Garam Masala Blend', 18.0, 450.0),
            ('Single Origin Arabica Roasted Beans', 25.0, 850.0),
            ('Farm Fresh Whole Dairy Milk & Cream', 40.0, 65.0),
            ('Eco-Friendly Takeout Kraft Boxes', 400.0, 12.0),
        ]

        for p_name, qty, cost in raw_materials:
            prod = Product.search([('name', '=', p_name)], limit=1)
            if not prod:
                prod = Product.create({
                    'name': p_name,
                    'type': 'consu',
                    'is_storable': True,
                    'standard_price': cost,
                    'list_price': cost * 1.4,
                })
            else:
                if 'is_storable' in prod._fields and not prod.is_storable:
                    prod.write({'is_storable': True})
            if stock_loc:
                try:
                    quant = Quant.search([
                        ('product_id', '=', prod.id),
                        ('location_id', '=', stock_loc.id)
                    ], limit=1)
                    if not quant or quant.quantity <= 0:
                        Quant.with_context(inventory_mode=True).create({
                            'product_id': prod.id,
                            'location_id': stock_loc.id,
                            'inventory_quantity': qty,
                        }).action_apply_inventory()
                except Exception as e:
                    _logger.warning("Could not set inventory for %s: %s", p_name, e)

    # -------------------------------------------------------------------------
    # 4. Purchase Orders (Vendors & Suppliers)
    # -------------------------------------------------------------------------
    if 'purchase.order' in env:
        _logger.info("Hudson Business Suite: Setting up Purchase demo orders...")
        PurchaseOrder = env['purchase.order'].sudo()
        Product = env['product.product'].sudo()

        v_dairy = get_or_create_partner('Kerala Organic Dairy & Farm Co.', is_company=True, email='orders@keraladairy.org')
        v_spices = get_or_create_partner('Highland Spice Merchants Ltd', is_company=True, email='sales@highlandspices.in')
        v_coffee = get_or_create_partner('Wayanad Coffee Planters Co-op', is_company=True, email='info@wayanadcoffeecoop.org')

        p_rice = Product.search([('name', '=', 'Basmati Biryani Aged Rice (Premium)')], limit=1)
        p_oil = Product.search([('name', '=', 'Cold Pressed Organic Coconut Oil')], limit=1)
        p_spices = Product.search([('name', '=', 'Highland Malabar Garam Masala Blend')], limit=1)
        p_coffee = Product.search([('name', '=', 'Single Origin Arabica Roasted Beans')], limit=1)

        po_specs = [
            {
                'partner_id': v_dairy.id,
                'partner_ref': 'KODF-INV-2026-88',
                'state': 'purchase',
                'lines': [
                    {'product_id': p_rice.id if p_rice else False, 'name': 'Basmati Biryani Aged Rice (Premium)', 'qty': 50, 'price': 95.0},
                    {'product_id': p_oil.id if p_oil else False, 'name': 'Cold Pressed Organic Coconut Oil', 'qty': 20, 'price': 210.0},
                ]
            },
            {
                'partner_id': v_spices.id,
                'partner_ref': 'HSM-DELIVERY-014',
                'state': 'purchase',
                'lines': [
                    {'product_id': p_spices.id if p_spices else False, 'name': 'Highland Malabar Garam Masala Blend', 'qty': 15, 'price': 390.0},
                ]
            },
            {
                'partner_id': v_coffee.id,
                'partner_ref': 'WCC-RFQ-FEB',
                'state': 'draft',
                'lines': [
                    {'product_id': p_coffee.id if p_coffee else False, 'name': 'Single Origin Arabica Roasted Beans', 'qty': 30, 'price': 780.0},
                ]
            },
        ]

        for pspec in po_specs:
            valid_lines = [l for l in pspec['lines'] if l['product_id']]
            if not valid_lines:
                continue
            po = PurchaseOrder.search([('partner_id', '=', pspec['partner_id']), ('partner_ref', '=', pspec['partner_ref'])], limit=1)
            if not po:
                po = PurchaseOrder.create({
                    'partner_id': pspec['partner_id'],
                    'partner_ref': pspec['partner_ref'],
                    'date_order': fields.Datetime.now() - timedelta(days=3),
                })
                for l in valid_lines:
                    env['purchase.order.line'].sudo().create({
                        'order_id': po.id,
                        'product_id': l['product_id'],
                        'name': l['name'],
                        'product_qty': l['qty'],
                        'price_unit': l['price'],
                        'date_planned': fields.Datetime.now() + timedelta(days=2),
                    })
                if pspec['state'] == 'purchase':
                    try:
                        po.button_confirm()
                    except Exception as e:
                        _logger.warning("Could not confirm demo purchase order %s: %s", po.name, e)

    # -------------------------------------------------------------------------
    # 5. Manufacturing (BOM & Production Orders)
    # -------------------------------------------------------------------------
    if 'mrp.bom' in env and 'mrp.production' in env:
        _logger.info("Hudson Business Suite: Setting up MRP Bills of Materials & Production...")
        Bom = env['mrp.bom'].sudo()
        Production = env['mrp.production'].sudo()
        Product = env['product.product'].sudo()

        # Finished good 1: Signature Kerala Dum Biryani Feast Box
        p_finished_biryani = Product.search([('name', '=', 'Signature Kerala Dum Biryani Feast Box (5 Pax)')], limit=1)
        if not p_finished_biryani:
            p_finished_biryani = Product.create({
                'name': 'Signature Kerala Dum Biryani Feast Box (5 Pax)',
                'list_price': 1850.0,
                'standard_price': 750.0,
            })

        # Finished good 2: Cold Brew Bottled Coffee Reserve
        p_finished_coffee = Product.search([('name', '=', 'Artisan Cold Brew Bottle Reserve (Batch of 10)')], limit=1)
        if not p_finished_coffee:
            p_finished_coffee = Product.create({
                'name': 'Artisan Cold Brew Bottle Reserve (Batch of 10)',
                'list_price': 1200.0,
                'standard_price': 420.0,
            })

        p_rice = Product.search([('name', '=', 'Basmati Biryani Aged Rice (Premium)')], limit=1)
        p_oil = Product.search([('name', '=', 'Cold Pressed Organic Coconut Oil')], limit=1)
        p_spices = Product.search([('name', '=', 'Highland Malabar Garam Masala Blend')], limit=1)
        p_coffee = Product.search([('name', '=', 'Single Origin Arabica Roasted Beans')], limit=1)
        p_box = Product.search([('name', '=', 'Eco-Friendly Takeout Kraft Boxes')], limit=1)

        # BOM for Biryani Feast Box
        bom_biryani = Bom.search([('product_tmpl_id', '=', p_finished_biryani.product_tmpl_id.id)], limit=1)
        if not bom_biryani and p_rice and p_oil and p_spices:
            bom_biryani = Bom.create({
                'product_tmpl_id': p_finished_biryani.product_tmpl_id.id,
                'product_qty': 1.0,
                'type': 'normal',
                'bom_line_ids': [
                    (0, 0, {'product_id': p_rice.id, 'product_qty': 2.5}),
                    (0, 0, {'product_id': p_oil.id, 'product_qty': 0.5}),
                    (0, 0, {'product_id': p_spices.id, 'product_qty': 0.3}),
                    (0, 0, {'product_id': p_box.id, 'product_qty': 5.0}) if p_box else False,
                ]
            })

        # BOM for Cold Brew Reserve
        bom_coffee = Bom.search([('product_tmpl_id', '=', p_finished_coffee.product_tmpl_id.id)], limit=1)
        if not bom_coffee and p_coffee:
            bom_coffee = Bom.create({
                'product_tmpl_id': p_finished_coffee.product_tmpl_id.id,
                'product_qty': 1.0,
                'type': 'normal',
                'bom_line_ids': [
                    (0, 0, {'product_id': p_coffee.id, 'product_qty': 1.0}),
                ]
            })

        # Create Manufacturing Orders
        if bom_biryani:
            mo_biryani = Production.search([('product_id', '=', p_finished_biryani.id)], limit=1)
            if not mo_biryani:
                try:
                    mo_biryani = Production.create({
                        'product_id': p_finished_biryani.id,
                        'product_qty': 10.0,
                        'bom_id': bom_biryani.id,
                    })
                    mo_biryani.action_confirm()
                except Exception as e:
                    _logger.warning("Could not create demo MO for Biryani: %s", e)

        if bom_coffee:
            mo_coffee = Production.search([('product_id', '=', p_finished_coffee.id)], limit=1)
            if not mo_coffee:
                try:
                    mo_coffee = Production.create({
                        'product_id': p_finished_coffee.id,
                        'product_qty': 15.0,
                        'bom_id': bom_coffee.id,
                    })
                    mo_coffee.action_confirm()
                except Exception as e:
                    _logger.warning("Could not create demo MO for Coffee: %s", e)

    # -------------------------------------------------------------------------
    # 6. Maintenance (Equipments & Work Requests)
    # -------------------------------------------------------------------------
    if 'maintenance.equipment' in env and 'maintenance.request' in env:
        _logger.info("Hudson Business Suite: Setting up Kitchen & Cafe Maintenance demo data...")
        Equipment = env['maintenance.equipment'].sudo()
        Request = env['maintenance.request'].sudo()
        Stage = env['maintenance.stage'].sudo()

        stage_new = Stage.search([('name', '=', 'New Request')], limit=1)
        stage_prog = Stage.search([('name', '=', 'In Progress')], limit=1)
        stage_done = Stage.search([('name', '=', 'Repaired')], limit=1)

        equipments_spec = [
            {'name': 'Commercial Deck Bakery Oven (Kitchen Line 1)', 'serial_no': 'OVN-2026-PRO', 'model': 'Zanolli Teorema'},
            {'name': 'La Marzocco Linea PB Espresso Machine (Cafe Counter)', 'serial_no': 'ESP-LM-880', 'model': 'Linea PB 2-Group'},
            {'name': 'Industrial Twin Tank Deep Fryer (Hot Line)', 'serial_no': 'FRY-PITCO-99', 'model': 'Pitco Frialator'},
            {'name': 'Walk-in Cold Storage Blast Freezer & Chiller', 'serial_no': 'CHL-FOSTER-500', 'model': 'Foster EcoPro G2'},
        ]

        equip_objs = {}
        for espec in equipments_spec:
            eq = Equipment.search([('serial_no', '=', espec['serial_no'])], limit=1)
            if not eq:
                eq = Equipment.create(espec)
            equip_objs[espec['name']] = eq

        requests_spec = [
            {
                'name': 'Espresso Machine Group Head De-scale & Steam Pressure Calibration',
                'equipment_id': equip_objs.get('La Marzocco Linea PB Espresso Machine (Cafe Counter)').id,
                'maintenance_type': 'corrective',
                'stage_id': stage_prog.id if stage_prog else False,
                'priority': '3',
            },
            {
                'name': 'Deck Oven Heating Element & Thermocouple Annual Inspection',
                'equipment_id': equip_objs.get('Commercial Deck Bakery Oven (Kitchen Line 1)').id,
                'maintenance_type': 'preventive',
                'stage_id': stage_new.id if stage_new else False,
                'priority': '2',
            },
            {
                'name': 'Deep Fryer Thermostat Diagnostic & Oil Filter Pump Check',
                'equipment_id': equip_objs.get('Industrial Twin Tank Deep Fryer (Hot Line)').id,
                'maintenance_type': 'preventive',
                'stage_id': stage_done.id if stage_done else False,
                'priority': '1',
            },
        ]

        for rspec in requests_spec:
            if not rspec.get('equipment_id'):
                continue
            req = Request.search([('name', '=', rspec['name']), ('equipment_id', '=', rspec['equipment_id'])], limit=1)
            if not req:
                Request.create(rspec)

    # -------------------------------------------------------------------------
    # 7. Events & Registrations
    # -------------------------------------------------------------------------
    if 'event.event' in env:
        _logger.info("Hudson Business Suite: Setting up Events demo data...")
        Event = env['event.event'].sudo()
        Registration = env['event.registration'].sudo()

        events_spec = [
            {
                'name': 'Artisan Coffee Brewing & Cupping Masterclass',
                'date_begin': datetime.combine(today + timedelta(days=5), datetime.min.time()).replace(hour=10),
                'date_end': datetime.combine(today + timedelta(days=5), datetime.min.time()).replace(hour=13),
                'seats_max': 25,
                'seats_limited': True,
            },
            {
                'name': "Chef's Table: 7-Course Malabar Degustation Night",
                'date_begin': datetime.combine(today + timedelta(days=7), datetime.min.time()).replace(hour=19),
                'date_end': datetime.combine(today + timedelta(days=7), datetime.min.time()).replace(hour=22),
                'seats_max': 20,
                'seats_limited': True,
            },
            {
                'name': 'Sunday Live Jazz & Rooftop Garden Brunch Gala',
                'date_begin': datetime.combine(today + timedelta(days=6), datetime.min.time()).replace(hour=11),
                'date_end': datetime.combine(today + timedelta(days=6), datetime.min.time()).replace(hour=16),
                'seats_max': 80,
                'seats_limited': True,
            },
        ]

        for espec in events_spec:
            ev = Event.search([('name', '=', espec['name'])], limit=1)
            if not ev:
                ev = Event.create(espec)
                # Add sample attendee registrations
                attendees = [
                    ('Vivek Nambiar', 'vivek.nambiar@gmail.com', '+91 98470 11223'),
                    ('Deepa Chandran', 'deepa.chandran@outlook.com', '+91 97451 44556'),
                    ('Arjun Pillai', 'arjun.pillai@yahoo.com', '+91 99950 77889'),
                ]
                for aname, amail, aphone in attendees:
                    Registration.create({
                        'event_id': ev.id,
                        'name': aname,
                        'email': amail,
                        'phone': aphone,
                    })

    # -------------------------------------------------------------------------
    # 8. Survey & Customer Feedback
    # -------------------------------------------------------------------------
    if 'survey.survey' in env:
        _logger.info("Hudson Business Suite: Setting up Survey demo data...")
        Survey = env['survey.survey'].sudo()
        Question = env['survey.question'].sudo()

        survey_name = 'Hudson Restaurant & Cafe Dining Experience Survey'
        srv = Survey.search([('title', '=', survey_name)], limit=1)
        if not srv:
            srv = Survey.create({
                'title': survey_name,
                'access_mode': 'public',
            })
            # Add Questions
            questions = [
                {'title': 'How was the culinary taste and presentation of your meal today?', 'question_type': 'scale_simple' if 'scale_simple' in Question._fields.get('question_type').selection else 'simple_choice', 'sequence': 1},
                {'title': 'How would you rate the speed, courteousness, and knowledge of our service team?', 'question_type': 'simple_choice', 'sequence': 2},
                {'title': 'How satisfied were you with the ambience, music volume, and cleanliness?', 'question_type': 'simple_choice', 'sequence': 3},
                {'title': 'What dishes or culinary experiences would you love to see on our next seasonal menu?', 'question_type': 'text_box', 'sequence': 4},
            ]
            for q in questions:
                try:
                    Question.create({
                        'survey_id': srv.id,
                        'title': q['title'],
                        'question_type': q['question_type'],
                        'sequence': q['sequence'],
                    })
                except Exception as e:
                    _logger.warning("Could not create survey question %s: %s", q['title'], e)

    # -------------------------------------------------------------------------
    # 9. Projects & Timesheets (project.project, project.task, account.analytic.line)
    # -------------------------------------------------------------------------
    if 'project.project' in env:
        _logger.info("Hudson Business Suite: Setting up Projects & Timesheets demo data...")
        Project = env['project.project'].sudo()
        Task = env['project.task'].sudo()
        AnalyticLine = env['account.analytic.line'].sudo() if 'account.analytic.line' in env else None

        employees = {}
        if 'hr.employee' in env:
            for emp in env['hr.employee'].sudo().search([('name', 'in', [
                'Rahul Nair', 'Vishnu Kumar', 'Kevin Joseph', 'Ananya Sharma', 'Priya Menon', 'Sneha Pillai'
            ])]):
                employees[emp.name] = emp

        # Project 1: Rooftop Dining & Garden Expansion
        p1 = Project.search([('name', '=', 'Hudson Rooftop Dining & Garden Lounge Expansion')], limit=1)
        if not p1:
            malabar_partner = get_or_create_partner('Malabar Corporate Club', email='events@malabarclub.in')
            p1 = Project.create({
                'name': 'Hudson Rooftop Dining & Garden Lounge Expansion',
                'allow_timesheets': True,
                'partner_id': malabar_partner.id,
            })
        p1_tasks_data = [
            ('Acoustic Insulation & Weatherproof Pergola Installation', 32.0, 'Rahul Nair', [
                ('Structural alignment and seal testing on pergola glass roof', 6.0, '2026-11-03', 'Rahul Nair'),
                ('Installed acoustic vibration dampers and weather strips', 4.5, '2026-11-04', 'Rahul Nair'),
            ]),
            ('Rooftop Hydroponic Herb Garden & Ambient Lighting Setup', 24.0, 'Vishnu Kumar', [
                ('Installed automated drip-irrigation tubes and planter racks', 5.0, '2026-11-04', 'Vishnu Kumar'),
                ('Planted fresh organic mint, rosemary, and Thai basil seedlings', 4.0, '2026-11-05', 'Vishnu Kumar'),
            ]),
            ('POS Terminal & Network Infrastructure Cabling', 16.0, 'Kevin Joseph', [
                ('Ran CAT6 Ethernet drops to rooftop POS terminal 2 and tested latency', 4.0, '2026-11-05', 'Kevin Joseph'),
                ('Configured wireless mesh access point and kitchen receipt printer link', 3.5, '2026-11-06', 'Kevin Joseph'),
            ]),
            ('Food Safety & Fire Safety Compliance Certification', 12.0, 'Ananya Sharma', [
                ('Conducted mock fire evacuation drill & completed municipal kitchen safety audit documentation', 4.0, '2026-11-06', 'Ananya Sharma'),
            ]),
        ]
        for tname, alloc, emp_name, tlines in p1_tasks_data:
            t = Task.search([('project_id', '=', p1.id), ('name', '=', tname)], limit=1)
            if not t:
                assigned_emp = employees.get(emp_name)
                tvals = {
                    'name': tname,
                    'project_id': p1.id,
                    'allocated_hours': alloc,
                }
                if assigned_emp and assigned_emp.user_id:
                    tvals['user_ids'] = [Command.link(assigned_emp.user_id.id)]
                t = Task.create(tvals)
            if AnalyticLine:
                for ts_name, ts_hrs, ts_date, ts_emp_name in tlines:
                    if not AnalyticLine.search_count([('task_id', '=', t.id), ('name', '=', ts_name)]):
                        ts_emp = employees.get(ts_emp_name)
                        AnalyticLine.create({
                            'name': ts_name,
                            'project_id': p1.id,
                            'task_id': t.id,
                            'employee_id': ts_emp.id if ts_emp else False,
                            'unit_amount': ts_hrs,
                            'date': ts_date,
                            'user_id': ts_emp.user_id.id if (ts_emp and ts_emp.user_id) else False,
                        })

        # Project 2: Autumn 2026 Seasonal Menu Launch & Marketing Campaign
        p2 = Project.search([('name', '=', 'Autumn 2026 Seasonal Menu Launch & Marketing Campaign')], limit=1)
        if not p2:
            p2 = Project.create({
                'name': 'Autumn 2026 Seasonal Menu Launch & Marketing Campaign',
                'allow_timesheets': True,
            })
        p2_tasks_data = [
            ('Recipe Testing & Costing Analysis with Head Chef', 20.0, 'Priya Menon', [
                ('Standardized Malabar spice blend proportions for signature slow-cooked lamb shank', 5.5, '2026-11-02', 'Priya Menon'),
                ('Calculated food cost margins and vendor ingredient pricing benchmarks', 4.0, '2026-11-03', 'Priya Menon'),
            ]),
            ('Food Photography & Digital Menu Display Asset Design', 18.0, 'Sneha Pillai', [
                ('Shot 4K food hero photos of signature cold brews and mocktails', 4.5, '2026-11-04', 'Sneha Pillai'),
                ('Designed visual layout templates for digital kiosk menu boards', 4.0, '2026-11-05', 'Sneha Pillai'),
            ]),
            ('Staff Training on Wine Pairings & Allergen Protocols', 14.0, 'Rahul Nair', [
                ('Conducted 2-hour front-of-house tasting session and service sequence briefing', 3.5, '2026-11-06', 'Rahul Nair'),
            ]),
        ]
        for tname, alloc, emp_name, tlines in p2_tasks_data:
            t = Task.search([('project_id', '=', p2.id), ('name', '=', tname)], limit=1)
            if not t:
                assigned_emp = employees.get(emp_name)
                tvals = {
                    'name': tname,
                    'project_id': p2.id,
                    'allocated_hours': alloc,
                }
                if assigned_emp and assigned_emp.user_id:
                    tvals['user_ids'] = [Command.link(assigned_emp.user_id.id)]
                t = Task.create(tvals)
            if AnalyticLine:
                for ts_name, ts_hrs, ts_date, ts_emp_name in tlines:
                    if not AnalyticLine.search_count([('task_id', '=', t.id), ('name', '=', ts_name)]):
                        ts_emp = employees.get(ts_emp_name)
                        AnalyticLine.create({
                            'name': ts_name,
                            'project_id': p2.id,
                            'task_id': t.id,
                            'employee_id': ts_emp.id if ts_emp else False,
                            'unit_amount': ts_hrs,
                            'date': ts_date,
                            'user_id': ts_emp.user_id.id if (ts_emp and ts_emp.user_id) else False,
                        })

    # -------------------------------------------------------------------------
    # 10. Repairs (repair.order)
    # -------------------------------------------------------------------------
    if 'repair.order' in env:
        _logger.info("Hudson Business Suite: Setting up Repairs demo data...")
        Repair = env['repair.order'].sudo()
        Product = env['product.product'].sudo()

        repairs_info = [
            (
                'Espresso Machine',
                'Replaced faulty boiler temperature sensor and recalibrated dual group head pressure relief valve.',
                'confirmed'
            ),
            (
                'Deep Fryer',
                'Cleaned thermopile, replaced high-limit safety cut-out switch, and performed burn temperature test.',
                'done'
            ),
            (
                'Blast Freezer',
                'Replaced magnetic door gasket and serviced condenser cooling fan motor.',
                'confirmed'
            ),
        ]

        repair_partner = get_or_create_partner('Hudson Kitchen Equipment Service Hub', email='service@hudsonkitchen.in')

        for prod_kw, notes, state in repairs_info:
            existing = Repair.search([('internal_notes', '=', notes)], limit=1)
            if not existing:
                prod = Product.search([('name', 'ilike', prod_kw)], limit=1)
                if not prod:
                    prod = Product.search([], limit=1)
                if prod:
                    try:
                        ro = Repair.create({
                            'product_id': prod.id,
                            'product_qty': 1.0,
                            'partner_id': repair_partner.id,
                            'internal_notes': notes,
                        })
                        if state in ('confirmed', 'done') and hasattr(ro, 'action_validate'):
                            ro.action_validate()
                        if state == 'done' and hasattr(ro, 'action_repair_done'):
                            ro.action_repair_done()
                    except Exception as e:
                        _logger.warning("Could not setup repair order for %s: %s", prod_kw, e)

    # -------------------------------------------------------------------------
    # 11. Quality Management (quality.team, quality.point, quality.check, quality.alert)
    # -------------------------------------------------------------------------
    if 'quality.team' in env:
        _logger.info("Hudson Business Suite: Setting up Quality Control demo data...")
        QTeam = env['quality.team'].sudo()
        QPoint = env['quality.point'].sudo()
        QCheck = env['quality.check'].sudo()
        QAlert = env['quality.alert'].sudo()
        QAlertStage = env['quality.alert.stage'].sudo() if 'quality.alert.stage' in env else None
        QTag = env['quality.tag'].sudo() if 'quality.tag' in env else None
        QReason = env['quality.reason'].sudo() if 'quality.reason' in env else None
        Product = env['product.product'].sudo()

        # Quality Teams
        qteam_haccp = QTeam.search([('name', '=', 'Hudson Food Safety & HACCP Team')], limit=1)
        if not qteam_haccp:
            qteam_haccp = QTeam.create({'name': 'Hudson Food Safety & HACCP Team'})

        qteam_inbound = QTeam.search([('name', '=', 'Inbound Receiving & Cold Chain QC')], limit=1)
        if not qteam_inbound:
            qteam_inbound = QTeam.create({'name': 'Inbound Receiving & Cold Chain QC'})

        # Quality Tags
        tag_temp = QTag.search([('name', '=', 'Temperature Control')], limit=1) if QTag else None
        if QTag and not tag_temp:
            tag_temp = QTag.create({'name': 'Temperature Control', 'color': 1})

        tag_haccp = QTag.search([('name', '=', 'HACCP Critical Limit')], limit=1) if QTag else None
        if QTag and not tag_haccp:
            tag_haccp = QTag.create({'name': 'HACCP Critical Limit', 'color': 2})

        tag_pack = QTag.search([('name', '=', 'Packaging Integrity')], limit=1) if QTag else None
        if QTag and not tag_pack:
            tag_pack = QTag.create({'name': 'Packaging Integrity', 'color': 3})

        # Quality Reasons
        reason_temp = QReason.search([('name', '=', 'Temperature Above Safe Threshold')], limit=1) if QReason else None
        if QReason and not reason_temp:
            reason_temp = QReason.create({'name': 'Temperature Above Safe Threshold'})

        reason_pkg = QReason.search([('name', '=', 'Transit Damage & Seal Tamper')], limit=1) if QReason else None
        if QReason and not reason_pkg:
            reason_pkg = QReason.create({'name': 'Transit Damage & Seal Tamper'})

        # Quality Control Points (QCP)
        p_milk = Product.search([('name', 'ilike', 'Milk')], limit=1)
        if p_milk and not QPoint.search([('name', '=', 'Chilled Dairy Receiving Temperature Check')], limit=1):
            QPoint.create({
                'name': 'Chilled Dairy Receiving Temperature Check',
                'title': 'Core Temp Under 4.0°C Check',
                'team_id': qteam_inbound.id,
                'product_ids': [Command.link(p_milk.id)],
                'test_type': 'measure',
                'norm': 3.5,
                'tolerance_min': 0.5,
                'tolerance_max': 4.0,
                'norm_unit': '°C',
                'instructions': 'Insert calibrated probe thermometer between dairy cartons. Reject delivery if temperature exceeds 4.0°C.',
            })

        p_burger = Product.search([('name', 'ilike', 'Burger')], limit=1)
        if p_burger and not QPoint.search([('name', '=', 'Gourmet Angus Beef Patty Core Temp Verification')], limit=1):
            QPoint.create({
                'name': 'Gourmet Angus Beef Patty Core Temp Verification',
                'title': 'Core Cook Temp > 75°C Check',
                'team_id': qteam_haccp.id,
                'product_ids': [Command.link(p_burger.id)],
                'test_type': 'measure',
                'norm': 77.0,
                'tolerance_min': 75.0,
                'tolerance_max': 85.0,
                'norm_unit': '°C',
                'instructions': 'Verify internal burger core cooking temperature reaches minimum 75°C to eliminate pathogens before plating.',
            })

        p_salmon = Product.search([('name', 'ilike', 'Salmon')], limit=1)
        if not p_salmon:
            p_salmon = Product.search([('name', 'ilike', 'Pizza')], limit=1)
        if p_salmon and not QPoint.search([('name', '=', 'Raw Protein Vacuum Packaging & Sensory Audit')], limit=1):
            QPoint.create({
                'name': 'Raw Protein Vacuum Packaging & Sensory Audit',
                'title': 'Vacuum Seal & Color Freshness',
                'team_id': qteam_haccp.id,
                'product_ids': [Command.link(p_salmon.id)],
                'test_type': 'passfail',
                'instructions': 'Inspect for tight vacuum seal, absence of discoloration, and natural fresh aroma.',
            })

        # Quality Checks
        if not QCheck.search([('name', 'ilike', 'QC-DAIRY-PASS')], limit=1):
            QCheck.create({
                'name': 'QC-DAIRY-PASS-001',
                'title': 'Morning Inbound Milk Batch Receiving QC',
                'team_id': qteam_inbound.id,
                'product_id': p_milk.id if p_milk else False,
                'test_type': 'measure',
                'measure': 3.2,
                'norm': 3.5,
                'tolerance_min': 0.5,
                'tolerance_max': 4.0,
                'norm_unit': '°C',
                'quality_state': 'pass',
                'additional_note': 'Refrigerated van temperature logged at 2.8°C. Carton seals intact and fresh.',
            })

        if p_burger and not QCheck.search([('name', 'ilike', 'QC-BURGER-PASS')], limit=1):
            QCheck.create({
                'name': 'QC-BURGER-PASS-002',
                'title': 'Lunch Rush Gourmet Burger Core Cook Audit',
                'team_id': qteam_haccp.id,
                'product_id': p_burger.id,
                'test_type': 'measure',
                'measure': 77.8,
                'norm': 77.0,
                'tolerance_min': 75.0,
                'tolerance_max': 85.0,
                'norm_unit': '°C',
                'quality_state': 'pass',
                'additional_note': 'Digital thermocouple probe confirmed 77.8°C core temperature after 4.5 mins grill searing.',
            })

        p_oil = Product.search([('name', 'ilike', 'Olive Oil')], limit=1)
        if not p_oil:
            p_oil = Product.search([], limit=1)
        if not QCheck.search([('name', 'ilike', 'QC-OIL-FAIL')], limit=1):
            QCheck.create({
                'name': 'QC-OIL-FAIL-003',
                'title': 'Imported Olive Oil Pallet Packaging Inspection',
                'team_id': qteam_inbound.id,
                'product_id': p_oil.id if p_oil else False,
                'test_type': 'passfail',
                'quality_state': 'fail',
                'additional_note': 'Damaged shipping carton; 3 metal tins leaked into outer protective wrap during transit.',
            })

        # Quality Alerts
        if QAlertStage:
            stages = {s.name: s.id for s in QAlertStage.search([])}
            stage_action = stages.get('Action Proposed', stages.get('Confirmed', False))
            stage_solved = stages.get('Solved', False)
            stage_confirmed = stages.get('Confirmed', False)

            alerts_data = [
                (
                    'Damaged Olive Oil Cans on Delivery from Malabar Agro',
                    p_oil.id if p_oil else False,
                    qteam_inbound.id,
                    stage_action,
                    '2',
                    reason_pkg.id if reason_pkg else False,
                    [Command.link(tag_pack.id)] if tag_pack else [],
                    'Morning pallet delivery arrived with visible corner denting on 3 olive oil tins causing minor seepage in freight compartment.',
                    'Immediate quarantine of damaged tins in Bay B; credit note initiated with Malabar Agro delivery representative.',
                    'Requested vendor use reinforced heavy-gauge corner guards and shrink-wrap securing on pallets.'
                ),
                (
                    'Walk-in Chiller Temperature Excursion Warning (+5.8°C)',
                    p_milk.id if p_milk else False,
                    qteam_haccp.id,
                    stage_confirmed,
                    '3',
                    reason_temp.id if reason_temp else False,
                    [Command.link(tag_temp.id), Command.link(tag_haccp.id)] if (tag_temp and tag_haccp) else [],
                    'Overnight data logger indicated temperature rose to 5.8°C for 45 minutes during defrost cycle.',
                    'Items checked with core probe - core temperatures remained safely at 3.5°C.',
                    'Maintenance scheduled defrost cycle optimization and condenser fan motor cleaning.'
                ),
                (
                    'Espresso Machine Group Head Gasket Steam Leak',
                    False,
                    qteam_haccp.id,
                    stage_solved,
                    '1',
                    False,
                    [],
                    'Slight steam leakage observed around portafilter collar during high-pressure espresso extraction.',
                    'Gasket and shower screen replaced with high-durability silicon replacement.',
                    'Updated barista weekly preventative checklist to inspect portafilter seals.'
                ),
            ]

            for atitle, prod_id, tid, stg_id, prio, r_id, t_ids, desc, corr, prev in alerts_data:
                if not QAlert.search([('title', '=', atitle)], limit=1):
                    QAlert.create({
                        'title': atitle,
                        'product_id': prod_id,
                        'team_id': tid,
                        'stage_id': stg_id,
                        'priority': prio,
                        'reason_id': r_id,
                        'tag_ids': t_ids,
                        'description': desc,
                        'corrective_action': corr,
                        'preventive_action': prev,
                    })

    # -------------------------------------------------------------------------
    # 12. Approvals (approval.category, approval.request)
    # -------------------------------------------------------------------------
    if 'approval.category' in env:
        _logger.info("Hudson Business Suite: Setting up Approvals demo data...")
        ApprCat = env['approval.category'].sudo()
        ApprReq = env['approval.request'].sudo()
        user = env.user
        metro_partner = get_or_create_partner('Metro Hospitality Equipment Mart', email='sales@metroequip.in')
        malabar_partner = get_or_create_partner('Malabar Corporate Club', email='events@malabarclub.in')

        cat_equip = ApprCat.search([('name', '=', 'Kitchen Equipment Capital Expenditure')], limit=1)
        if not cat_equip:
            cat_equip = ApprCat.create({
                'name': 'Kitchen Equipment Capital Expenditure',
                'description': 'Approval for purchasing heavy commercial kitchen appliances, ovens, blast chillers, or coffee bar machinery.',
                'amount': 'required',
                'has_partner': 'optional',
                'user_ids': [Command.create({'user_id': user.id})],
            })

        cat_event = ApprCat.search([('name', '=', 'Special Event & Catering Budget Allocation')], limit=1)
        if not cat_event:
            cat_event = ApprCat.create({
                'name': 'Special Event & Catering Budget Allocation',
                'description': 'Budget authorizations for banquets, floral staging, outdoor catering equipment, and guest entertainment.',
                'amount': 'required',
                'date': 'required',
                'has_partner': 'required',
                'user_ids': [Command.create({'user_id': user.id})],
            })

        cat_ot = ApprCat.search([('name', '=', 'Peak Shift & Banquet Staff Overtime')], limit=1)
        if not cat_ot:
            cat_ot = ApprCat.create({
                'name': 'Peak Shift & Banquet Staff Overtime',
                'description': 'Pre-authorization for front-of-house and kitchen staff working extra shifts during peak holiday weekends.',
                'date': 'required',
                'user_ids': [Command.create({'user_id': user.id})],
            })

        cat_menu = ApprCat.search([('name', '=', 'Seasonal Recipe & Menu Introduction')], limit=1)
        if not cat_menu:
            cat_menu = ApprCat.create({
                'name': 'Seasonal Recipe & Menu Introduction',
                'description': 'Executive Chef sign-off on new recipe cost benchmarks, ingredient standardization, and plating aesthetics.',
                'user_ids': [Command.create({'user_id': user.id})],
            })

        requests_data = [
            (
                'Commercial Sous-Vide Immersion Cooker & Chamber Vacuum Sealer',
                cat_equip.id,
                1850.0,
                metro_partner.id,
                today + timedelta(days=5),
                'approved',
                'Required to replace aging sous-vide unit for low-temperature cooking of signature slow-cooked short ribs and confit duck.'
            ),
            (
                'Diwali Festive Rooftop Garden Canopy Lighting & Floral Staging',
                cat_event.id,
                3400.0,
                malabar_partner.id,
                today + timedelta(days=12),
                'approved',
                'Full ambient warm fairy light canopy, natural floral entryway, and acoustic live sitar background setup for rooftop Diwali gala.'
            ),
            (
                'Weekend Banquet Extra Shift: 4 Service Waiters & 2 Prep Cooks',
                cat_ot.id,
                480.0,
                False,
                today + timedelta(days=3),
                'pending',
                'Overtime authorization required for 220-cover corporate networking banquet dinner scheduled for upcoming Saturday evening.'
            ),
            (
                'Slow-Braised Malabar Spiced Lamb Shank Recipe Introduction',
                cat_menu.id,
                0.0,
                False,
                today + timedelta(days=7),
                'pending',
                'Cost margin validated at 28.5%. Plating guidelines, storage specs, and allergen disclosure sheet attached for menu launch.'
            ),
        ]

        for rname, cid, amt, pid, rdate, status, rdesc in requests_data:
            if not ApprReq.search([('name', '=', rname)], limit=1):
                ApprReq.create({
                    'name': rname,
                    'category_id': cid,
                    'request_owner_id': user.id,
                    'amount': amt,
                    'partner_id': pid,
                    'date': rdate,
                    'request_status': status,
                    'description': rdesc,
                })

    # -------------------------------------------------------------------------
    # 13. Appointments & VIP Table Bookings (appointment.type, appointment.booking, appointment.resource)
    # -------------------------------------------------------------------------
    if 'appointment.type' in env:
        _logger.info("Hudson Business Suite: Setting up Appointment demo data...")
        AppType = env['appointment.type'].sudo()
        AppBooking = env['appointment.booking'].sudo()
        AppResource = env['appointment.resource'].sudo() if 'appointment.resource' in env else None

        res_chef_table = None
        res_pergola = None
        res_lab = None
        if AppResource:
            res_chef_table = AppResource.search([('name', '=', "Chef's Table Suite (8 Pax)")], limit=1)
            if not res_chef_table:
                res_chef_table = AppResource.create({
                    'name': "Chef's Table Suite (8 Pax)",
                    'capacity': 8,
                    'description': 'Exclusive front-row glass counter dining table overlooking the executive pastry and pass line.',
                })

            res_pergola = AppResource.search([('name', '=', 'Rooftop Pergola Garden Lounge (12 Pax)')], limit=1)
            if not res_pergola:
                res_pergola = AppResource.create({
                    'name': 'Rooftop Pergola Garden Lounge (12 Pax)',
                    'capacity': 12,
                    'description': 'Private semi-outdoor weatherproof pergola with panoramic skyline views and ambient fireplace.',
                })

            res_lab = AppResource.search([('name', '=', 'Barista Cupping & Masterclass Lab (6 Pax)')], limit=1)
            if not res_lab:
                res_lab = AppResource.create({
                    'name': 'Barista Cupping & Masterclass Lab (6 Pax)',
                    'capacity': 6,
                    'description': 'Professional specialty coffee laboratory with commercial grinders, manual brew bars, and sensory cups.',
                })

        apt_degustation = AppType.search([('name', '=', "VIP Chef's Table 7-Course Degustation Experience")], limit=1)
        if not apt_degustation:
            apt_vals = {
                'name': "VIP Chef's Table 7-Course Degustation Experience",
                'appointment_duration': 120,
                'location': 'custom',
                'location_details': "Chef's Table Suite - Hudson Restaurant Main Kitchen",
            }
            if res_chef_table:
                apt_vals['resource_ids'] = [Command.link(res_chef_table.id)]
            apt_degustation = AppType.create(apt_vals)

        apt_catering = AppType.search([('name', '=', 'Banquets & Wedding Catering Consultation')], limit=1)
        if not apt_catering:
            apt_catering = AppType.create({
                'name': 'Banquets & Wedding Catering Consultation',
                'appointment_duration': 60,
                'location': 'custom',
                'location_details': 'Hudson Executive Conference Lounge & Tasting Room',
            })

        apt_coffee = AppType.search([('name', '=', 'Artisan Coffee Cupping & Barista Workshop')], limit=1)
        if not apt_coffee:
            apt_vals = {
                'name': 'Artisan Coffee Cupping & Barista Workshop',
                'appointment_duration': 45,
                'location': 'custom',
                'location_details': 'Hudson Specialty Coffee Lab',
            }
            if res_lab:
                apt_vals['resource_ids'] = [Command.link(res_lab.id)]
            apt_coffee = AppType.create(apt_vals)

        malabar_partner = get_or_create_partner('Malabar Corporate Club', email='events@malabarclub.in')
        ananya_partner = get_or_create_partner('Dr. Ananya Sharma', email='ananya.sharma@aims.org')
        royal_partner = get_or_create_partner('Royal Orchid Hospitality Ltd', email='catering@royalorchid.com')

        bookings_data = [
            (
                apt_degustation.id,
                malabar_partner.id,
                datetime(today.year, today.month, today.day, 19, 30, 0) + timedelta(days=5),
                datetime(today.year, today.month, today.day, 21, 30, 0) + timedelta(days=5),
                120,
                8,
                'confirmed',
                'Leadership dinner for Malabar Corporate Club board. Special 7-course menu paired with organic boutique wines; 2 pescatarian guests.'
            ),
            (
                apt_catering.id,
                ananya_partner.id,
                datetime(today.year, today.month, today.day, 15, 0, 0) + timedelta(days=3),
                datetime(today.year, today.month, today.day, 16, 0, 0) + timedelta(days=3),
                60,
                4,
                'confirmed',
                'Consultation regarding 25th Wedding Anniversary banquet (120 Pax). Tasting samples of dessert shooters and live tandoori appetizers.'
            ),
            (
                apt_coffee.id,
                royal_partner.id,
                datetime(today.year, today.month, today.day, 11, 0, 0) - timedelta(days=2),
                datetime(today.year, today.month, today.day, 11, 45, 0) - timedelta(days=2),
                45,
                6,
                'checked_in',
                'Hands-on cupping session evaluating single-origin beans: Ethiopian Yirgacheffe washed and Colombian Geisha honey-processed.'
            ),
        ]

        for atid, pid, s_dt, e_dt, dur, size, st, desc in bookings_data:
            if not AppBooking.search([('appointment_type_id', '=', atid), ('partner_id', '=', pid)], limit=1):
                AppBooking.create({
                    'appointment_type_id': atid,
                    'partner_id': pid,
                    'start_datetime': s_dt,
                    'end_datetime': e_dt,
                    'duration': dur,
                    'party_size': size,
                    'state': st,
                    'description': desc,
                })

    _logger.info("Hudson Business Suite: All demo data loaded successfully!")


def clear_business_suite_demo_data(env):
    """
    Cleans up Business Suite demo data across CRM, Sales, Purchase, MRP, Maintenance, Events, Survey, Repairs, Projects.
    """
    _logger.info("Hudson Business Suite: Cleaning up demo data...")

    # 1. Unlink Survey
    if 'survey.survey' in env:
        try:
            with env.cr.savepoint():
                srvs = env['survey.survey'].sudo().search([('title', '=', 'Hudson Restaurant & Cafe Dining Experience Survey')])
                if srvs:
                    if 'survey.question' in env:
                        env['survey.question'].sudo().search([('survey_id', 'in', srvs.ids)]).unlink()
                    srvs.unlink()
        except Exception as e:
            _logger.warning("Could not unlink survey: %s", e)

    # 2. Unlink Events & Registrations
    if 'event.event' in env:
        try:
            with env.cr.savepoint():
                event_names = [
                    'Artisan Coffee Brewing & Cupping Masterclass',
                    "Chef's Table: 7-Course Malabar Degustation Night",
                    'Sunday Live Jazz & Rooftop Garden Brunch Gala'
                ]
                evs = env['event.event'].sudo().search([('name', 'in', event_names)])
                if evs:
                    if 'event.registration' in env:
                        env['event.registration'].sudo().search([('event_id', 'in', evs.ids)]).unlink()
                    evs.unlink()
        except Exception as e:
            _logger.warning("Could not unlink events: %s", e)

    # 3. Unlink Maintenance Requests & Equipments
    if 'maintenance.equipment' in env:
        try:
            with env.cr.savepoint():
                req_names = [
                    'Espresso Machine Group Head De-scale & Steam Pressure Calibration',
                    'Deck Oven Heating Element & Thermocouple Annual Inspection',
                    'Deep Fryer Thermostat Diagnostic & Oil Filter Pump Check'
                ]
                if 'maintenance.request' in env:
                    env['maintenance.request'].sudo().search([('name', 'in', req_names)]).unlink()
                env['maintenance.equipment'].sudo().search([('serial_no', 'in', ['OVN-2026-PRO', 'ESP-LM-880', 'FRY-PITCO-99', 'CHL-FOSTER-500'])]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink maintenance: %s", e)

    # 4. Unlink MRP Orders & BOMs
    if 'mrp.production' in env:
        try:
            with env.cr.savepoint():
                mos = env['mrp.production'].sudo().search([
                    ('product_id.name', 'in', [
                        'Signature Kerala Dum Biryani Feast Box (5 Pax)',
                        'Artisan Cold Brew Bottle Reserve (Batch of 10)'
                    ])
                ])
                if mos:
                    for mo in mos:
                        try:
                            mo.action_cancel()
                        except Exception:
                            pass
                    mos.unlink()
        except Exception as e:
            _logger.warning("Could not unlink MOs: %s", e)

    if 'mrp.bom' in env:
        try:
            with env.cr.savepoint():
                env['mrp.bom'].sudo().search([
                    ('product_tmpl_id.name', 'in', [
                        'Signature Kerala Dum Biryani Feast Box (5 Pax)',
                        'Artisan Cold Brew Bottle Reserve (Batch of 10)'
                    ])
                ]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink BOMs: %s", e)

    # 5. Unlink Purchase Orders
    if 'purchase.order' in env:
        try:
            with env.cr.savepoint():
                pos = env['purchase.order'].sudo().search([('partner_ref', 'in', ['KODF-INV-2026-88', 'HSM-DELIVERY-014', 'WCC-RFQ-FEB'])])
                if pos:
                    for po in pos:
                        try:
                            po.button_cancel()
                        except Exception:
                            pass
                    if 'purchase.order.line' in env:
                        env['purchase.order.line'].sudo().search([('order_id', 'in', pos.ids)]).unlink()
                    pos.unlink()
        except Exception as e:
            _logger.warning("Could not unlink purchase orders: %s", e)

    # 6. Unlink Sales Orders
    if 'sale.order' in env:
        try:
            with env.cr.savepoint():
                sos = env['sale.order'].sudo().search([('client_order_ref', 'in', ['MALABAR-GALA-2026', 'EMERALD-CHEF-PASS', 'CYBER-LUNCH-RFQ'])])
                if sos:
                    for so in sos:
                        try:
                            so.action_cancel()
                        except Exception:
                            pass
                    if 'sale.order.line' in env:
                        env['sale.order.line'].sudo().search([('order_id', 'in', sos.ids)]).unlink()
                    sos.unlink()
        except Exception as e:
            _logger.warning("Could not unlink sales orders: %s", e)

    # 7. Unlink CRM Leads
    if 'crm.lead' in env:
        try:
            with env.cr.savepoint():
                lead_names = [
                    'TechCorp Annual Gala Banquet (150 Pax)',
                    'Wedding Reception Catering & Live Mocktail Bar',
                    'Executive Daily Lunch Subscription (Infopark Hub)',
                    'Private Rooftop Birthday & Live Acoustic Night (40 Pax)',
                ]
                env['crm.lead'].sudo().search([('name', 'in', lead_names)]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink CRM leads: %s", e)

    # 8. Unlink Repairs
    if 'repair.order' in env:
        try:
            with env.cr.savepoint():
                ro_notes = [
                    'Replaced faulty boiler temperature sensor and recalibrated dual group head pressure relief valve.',
                    'Cleaned thermopile, replaced high-limit safety cut-out switch, and performed burn temperature test.',
                    'Replaced magnetic door gasket and serviced condenser cooling fan motor.',
                ]
                ros = env['repair.order'].sudo().search([('internal_notes', 'in', ro_notes)])
                if ros:
                    for r in ros:
                        try:
                            if hasattr(r, 'action_repair_cancel'):
                                r.action_repair_cancel()
                        except Exception:
                            pass
                    ros.unlink()
        except Exception as e:
            _logger.warning("Could not unlink repairs: %s", e)

    # 9. Unlink Timesheets & Projects
    if 'project.project' in env:
        try:
            with env.cr.savepoint():
                pnames = [
                    'Hudson Rooftop Dining & Garden Lounge Expansion',
                    'Autumn 2026 Seasonal Menu Launch & Marketing Campaign'
                ]
                projs = env['project.project'].sudo().search([('name', 'in', pnames)])
                if projs:
                    if 'account.analytic.line' in env:
                        env['account.analytic.line'].sudo().search([('project_id', 'in', projs.ids)]).unlink()
                    if 'project.task' in env:
                        env['project.task'].sudo().search([('project_id', 'in', projs.ids)]).unlink()
                    projs.unlink()
        except Exception as e:
            _logger.warning("Could not unlink projects: %s", e)

    # 10. Unlink Appointments
    if 'appointment.type' in env:
        try:
            with env.cr.savepoint():
                at_names = [
                    "VIP Chef's Table 7-Course Degustation Experience",
                    'Banquets & Wedding Catering Consultation',
                    'Artisan Coffee Cupping & Barista Workshop'
                ]
                ats = env['appointment.type'].sudo().search([('name', 'in', at_names)])
                if ats:
                    if 'appointment.booking' in env:
                        env['appointment.booking'].sudo().search([('appointment_type_id', 'in', ats.ids)]).unlink()
                    ats.unlink()
                if 'appointment.resource' in env:
                    env['appointment.resource'].sudo().search([('name', 'in', [
                        "Chef's Table Suite (8 Pax)",
                        'Rooftop Pergola Garden Lounge (12 Pax)',
                        'Barista Cupping & Masterclass Lab (6 Pax)'
                    ])]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink appointments: %s", e)

    # 11. Unlink Approvals
    if 'approval.category' in env:
        try:
            with env.cr.savepoint():
                cat_names = [
                    'Kitchen Equipment Capital Expenditure',
                    'Special Event & Catering Budget Allocation',
                    'Peak Shift & Banquet Staff Overtime',
                    'Seasonal Recipe & Menu Introduction'
                ]
                cats = env['approval.category'].sudo().search([('name', 'in', cat_names)])
                if cats:
                    if 'approval.request' in env:
                        env['approval.request'].sudo().search([('category_id', 'in', cats.ids)]).unlink()
                    cats.unlink()
        except Exception as e:
            _logger.warning("Could not unlink approvals: %s", e)

    # 12. Unlink Quality
    if 'quality.team' in env:
        try:
            with env.cr.savepoint():
                alert_names = [
                    'Damaged Olive Oil Cans on Delivery from Malabar Agro',
                    'Walk-in Chiller Temperature Excursion Warning (+5.8°C)',
                    'Espresso Machine Group Head Gasket Steam Leak'
                ]
                if 'quality.alert' in env:
                    env['quality.alert'].sudo().search([('title', 'in', alert_names)]).unlink()
                if 'quality.check' in env:
                    env['quality.check'].sudo().search([('name', 'in', ['QC-DAIRY-PASS-001', 'QC-BURGER-PASS-002', 'QC-OIL-FAIL-003'])]).unlink()
                if 'quality.point' in env:
                    env['quality.point'].sudo().search([('name', 'in', [
                        'Chilled Dairy Receiving Temperature Check',
                        'Gourmet Angus Beef Patty Core Temp Verification',
                        'Raw Protein Vacuum Packaging & Sensory Audit'
                    ])]).unlink()
                if 'quality.tag' in env:
                    env['quality.tag'].sudo().search([('name', 'in', ['Temperature Control', 'HACCP Critical Limit', 'Packaging Integrity'])]).unlink()
                if 'quality.reason' in env:
                    env['quality.reason'].sudo().search([('name', 'in', ['Temperature Above Safe Threshold', 'Transit Damage & Seal Tamper'])]).unlink()
                env['quality.team'].sudo().search([('name', 'in', ['Hudson Food Safety & HACCP Team', 'Inbound Receiving & Cold Chain QC'])]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink quality: %s", e)

    _logger.info("Hudson Business Suite: Cleanup complete.")
