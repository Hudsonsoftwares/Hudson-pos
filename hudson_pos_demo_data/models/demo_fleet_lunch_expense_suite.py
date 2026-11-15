# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Fleet, Lunch and Expenses demo data.

Idempotent: every created record is bound to an xmlid of this module (rc_flt_*, rc_lun_*, rc_exp_*)
and skipped when it already exists. Each app loads in its own savepoint.

  * Fleet:    catering vans, pickups, an Innova for events and electric delivery scooters (KL plates),
              drivers, odometer history, fuel/service logs, insurance & leasing contracts (one expiring soon)
  * Lunch:    3 Kochi lunch vendors with order days/deadlines, categories, 15 products, toppings,
              wallet top-ups, past (confirmed) and today (new/ordered) orders, a lunch alert
  * Expenses: expense categories, 15 expenses in every state (draft, submitted, approved, posted,
              paid, refused), one re-invoiced to a catering customer
"""
import logging
from datetime import date, timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(vals))


def _emp(env, name):
    return env['hr.employee'].sudo().search([('name', '=', name)], limit=1)


def _partner(env, xid, name, **vals):
    return _get_or_create(env, xid, 'res.partner', {
        'name': name, 'is_company': True, 'city': vals.pop('city', 'Kochi'),
        'country_id': env.ref('base.in').id, **vals})


# --------------------------------------------------------------------------- fleet
VEHICLE_MODELS = [
    # xid, brand, model, category, type, fuel, seats, doors, power(kW), range
    ('rc_flt_model_ace', 'Tata', 'Ace Gold Diesel', 'Light Commercial', 'car', 'diesel', 2, 2, 15, 0),
    ('rc_flt_model_eeco', 'Maruti Suzuki', 'Eeco Cargo CNG', 'Light Commercial', 'car', 'cng', 2, 5, 52, 0),
    ('rc_flt_model_bolero', 'Mahindra', 'Bolero Maxx Pik-Up', 'Light Commercial', 'car', 'diesel', 2, 2, 52, 0),
    ('rc_flt_model_innova', 'Toyota', 'Innova Crysta', 'MPV', 'car', 'diesel', 7, 5, 110, 0),
    ('rc_flt_model_ather', 'Ather', '450X', 'Electric Scooter', 'bike', 'electric', 2, 0, 6, 110),
    ('rc_flt_model_iqube', 'TVS', 'iQube S', 'Electric Scooter', 'bike', 'electric', 2, 0, 4, 100),
    ('rc_flt_model_ola', 'Ola Electric', 'S1 Air', 'Electric Scooter', 'bike', 'electric', 2, 0, 6, 150),
]
VEHICLES = [
    # xid, model xid, plate, driver employee, tags, state, year, acquired days ago, odometer readings, car value, location, colour
    ('rc_flt_van_1', 'rc_flt_model_ace', 'KL-07-CX-4521', 'Arun Varma', ['Catering', 'Refrigerated'], 'Registered', '2024', 640,
     [8200, 14650, 21340, 26875], 690000, 'Central Kitchen, Edappally', 'White'),
    ('rc_flt_van_2', 'rc_flt_model_eeco', 'KL-07-DA-1188', 'Mohammed Bilal', ['Catering'], 'Registered', '2025', 300,
     [3100, 7480, 11920], 560000, 'Central Kitchen, Edappally', 'Silver'),
    ('rc_flt_pickup', 'rc_flt_model_bolero', 'KL-43-H-7709', 'Vishnu Kumar', ['Market Run'], 'Registered', '2023', 900,
     [21000, 33800, 41260, 47515], 980000, 'Marine Drive Restaurant', 'White'),
    ('rc_flt_innova', 'rc_flt_model_innova', 'KL-07-CZ-9090', 'Suresh Kumar', ['Events', 'Management'], 'Registered', '2024', 520,
     [12500, 24100, 33980], 2350000, 'Marine Drive Restaurant', 'Pearl White'),
    ('rc_flt_scooter_1', 'rc_flt_model_ather', 'KL-07-DE-3344', 'Kevin Joseph', ['Delivery', 'EV'], 'Registered', '2025', 210,
     [1800, 4120, 6890], 165000, 'Marine Drive Restaurant', 'Space Grey'),
    ('rc_flt_scooter_2', 'rc_flt_model_iqube', 'KL-07-DE-3345', 'Rahul Nair', ['Delivery', 'EV'], 'Registered', '2025', 210,
     [1650, 3930, 6410], 158000, 'Marine Drive Restaurant', 'Titanium Grey'),
    ('rc_flt_scooter_3', 'rc_flt_model_ola', 'KL-07-DF-0021', False, ['Delivery', 'EV'], 'To Order', '2026', 0,
     [], 120000, 'Cafe, Panampilly Nagar', 'Coral Glam'),
]
SERVICES = [
    # vehicle xid, service type, days ago, amount, vendor xid, state, description
    ('rc_flt_van_1', 'Fuel', 3, 3200, 'rc_flt_vendor_fuel', 'done', 'Diesel full tank, BPCL Edappally'),
    ('rc_flt_van_1', 'Periodic Service', 40, 6850, 'rc_flt_vendor_tata', 'done', '25,000 km service: oil, filters, brake check'),
    ('rc_flt_van_1', 'Reefer Unit Check', 12, 2400, 'rc_flt_vendor_cool', 'done', 'Refrigeration unit gas top-up for catering runs'),
    ('rc_flt_van_2', 'Fuel', 2, 1150, 'rc_flt_vendor_fuel', 'done', 'CNG refill, Kalamassery'),
    ('rc_flt_van_2', 'Tyre Replacement', 0, 9800, 'rc_flt_vendor_tyre', 'running', 'Two rear tyres, MRF'),
    ('rc_flt_pickup', 'Fuel', 5, 3600, 'rc_flt_vendor_fuel', 'done', 'Diesel, market run to Ernakulam Market'),
    ('rc_flt_pickup', 'Periodic Service', -6, 7400, 'rc_flt_vendor_mahindra', 'new', 'Scheduled 50,000 km service'),
    ('rc_flt_innova', 'Fuel', 8, 4100, 'rc_flt_vendor_fuel', 'done', 'Diesel, wedding catering at Bolgatty'),
    ('rc_flt_innova', 'Body Repair', 25, 14500, 'rc_flt_vendor_toyota', 'done', 'Rear bumper scratch repair'),
    ('rc_flt_scooter_1', 'Battery Health Check', 15, 0, 'rc_flt_vendor_ev', 'done', 'Free battery check at Ather Space'),
    ('rc_flt_scooter_2', 'Periodic Service', 1, 950, 'rc_flt_vendor_ev', 'cancelled', 'Duplicate booking, cancelled'),
]
CONTRACTS = [
    # vehicle xid, type, start days ago, duration days, amount, recurring cost, frequency, insurer xid, ref
    ('rc_flt_van_1', 'Insurance', 340, 365, 18500, 0, 'no', 'rc_flt_vendor_insure', 'POL-KL-ACE-2025'),  # expires in ~25 days
    ('rc_flt_van_2', 'Insurance', 300, 365, 14200, 0, 'no', 'rc_flt_vendor_insure', 'POL-KL-EECO-2025'),
    ('rc_flt_pickup', 'Insurance', 380, 365, 21000, 0, 'no', 'rc_flt_vendor_insure', 'POL-KL-BOL-2024'),  # expired
    ('rc_flt_innova', 'Leasing', 520, 1095, 0, 42000, 'monthly', 'rc_flt_vendor_lease', 'LEASE-INN-0042'),
    ('rc_flt_scooter_1', 'Battery Subscription', 210, 365, 0, 1499, 'monthly', 'rc_flt_vendor_ev', 'BAAS-ATH-3344'),
    ('rc_flt_scooter_2', 'Insurance', 210, 365, 4200, 0, 'no', 'rc_flt_vendor_insure', 'POL-KL-IQ-2025'),
]


def _load_fleet(env):
    if 'fleet.vehicle' not in env:
        return
    vendors = {
        'rc_flt_vendor_fuel': 'Bharat Petroleum - Edappally Fuel Station',
        'rc_flt_vendor_tata': 'Concorde Motors (Tata) - Kochi',
        'rc_flt_vendor_mahindra': 'EVM Mahindra - Kalamassery',
        'rc_flt_vendor_toyota': 'Nippon Toyota - Maradu',
        'rc_flt_vendor_tyre': 'MRF T&S Tyres - Vyttila',
        'rc_flt_vendor_cool': 'Kerala Cool Tech Refrigeration',
        'rc_flt_vendor_ev': 'Ather Space / TVS EV Service - Kochi',
        'rc_flt_vendor_insure': 'New India Assurance - Kochi Branch',
        'rc_flt_vendor_lease': 'Muthoot Vehicle Leasing',
    }
    partners = {x: _partner(env, x, n) for x, n in vendors.items()}

    Brand = env['fleet.vehicle.model.brand'].sudo()
    cats = {}
    for name in ('Light Commercial', 'MPV', 'Electric Scooter'):
        cats[name] = env['fleet.vehicle.model.category'].sudo().search([('name', '=', name)], limit=1) or _get_or_create(
            env, 'rc_flt_cat_' + name.lower().replace(' ', '_'), 'fleet.vehicle.model.category', {'name': name})
    models = {}
    for xid, brand_name, name, cat, vtype, fuel, seats, doors, power, vrange in VEHICLE_MODELS:
        brand = Brand.search([('name', '=ilike', brand_name)], limit=1) or _get_or_create(
            env, 'rc_flt_brand_' + brand_name.lower().replace(' ', '_'), 'fleet.vehicle.model.brand', {'name': brand_name})
        vals = {'name': name, 'brand_id': brand.id, 'category_id': cats[cat].id, 'vehicle_type': vtype,
                'default_fuel_type': fuel, 'seats': seats, 'doors': doors, 'power': power, 'power_unit': 'power'}
        if vrange:
            vals.update({'vehicle_range': vrange, 'range_unit': 'km'})
        models[xid] = _get_or_create(env, xid, 'fleet.vehicle.model', vals)

    Tag = env['fleet.vehicle.tag'].sudo()
    tags = {}
    for i, name in enumerate(('Catering', 'Refrigerated', 'Market Run', 'Events', 'Management', 'Delivery', 'EV'), start=1):
        tags[name] = Tag.search([('name', '=', name)], limit=1) or _get_or_create(
            env, 'rc_flt_tag_' + name.lower().replace(' ', '_'), 'fleet.vehicle.tag', {'name': name, 'color': i})
    states = {s.name: s for s in env['fleet.vehicle.state'].sudo().search([])}
    manager = _ref(env, 'rc_user_arjun') or env.ref('base.user_admin')
    today = fields.Date.today()

    vehicles = {}
    for xid, model_xid, plate, driver, tag_names, state, year, acq, odos, value, location, colour in VEHICLES:
        if _ref(env, xid):
            vehicles[xid] = _ref(env, xid)
            continue
        model = models[model_xid]
        employee = _emp(env, driver) if driver else env['hr.employee']
        vals = {
            'model_id': model.id, 'license_plate': plate, 'tag_ids': [Command.set([tags[t].id for t in tag_names])],
            'model_year': year, 'car_value': value, 'location': location, 'color': colour, 'manager_id': manager.id,
            'fuel_type': model.default_fuel_type, 'odometer_unit': 'kilometers', 'country_id': env.ref('base.in').id,
            'acquisition_date': today - timedelta(days=acq) if acq else False,
            'vin_sn': 'MA1' + plate.replace('-', ''),
        }
        if state in states:
            vals['state_id'] = states[state].id
        if employee:
            if 'driver_employee_id' in env['fleet.vehicle']._fields:
                vals['driver_employee_id'] = employee.id
            vals['driver_id'] = employee.work_contact_id.id
        if not acq:
            vals['order_date'] = today - timedelta(days=5)
        vehicle = _get_or_create(env, xid, 'fleet.vehicle', vals)
        vehicles[xid] = vehicle
        # odometer history, spread evenly from acquisition to today
        for i, value_km in enumerate(odos):
            d = today - timedelta(days=int(acq * (len(odos) - 1 - i) / max(len(odos) - 1, 1)))
            env['fleet.vehicle.odometer'].sudo().create({
                'vehicle_id': vehicle.id, 'value': value_km, 'date': d,
                'driver_id': vehicle.driver_id.id,
            })

    stypes = {}
    SType = env['fleet.service.type'].sudo()
    for name, category in (('Fuel', 'service'), ('Periodic Service', 'service'), ('Tyre Replacement', 'service'),
                           ('Body Repair', 'service'), ('Reefer Unit Check', 'service'), ('Battery Health Check', 'service'),
                           ('Insurance', 'contract'), ('Leasing', 'contract'), ('Battery Subscription', 'contract')):
        stypes[name] = SType.search([('name', '=', name)], limit=1) or _get_or_create(
            env, 'rc_flt_stype_' + name.lower().replace(' ', '_'), 'fleet.service.type', {'name': name, 'category': category})

    for i, (vxid, stype, days, amount, vendor, state, desc) in enumerate(SERVICES, start=1):
        xid = f'rc_flt_service_{i}'
        if _ref(env, xid) or vxid not in vehicles:
            continue
        vehicle = vehicles[vxid]
        _get_or_create(env, xid, 'fleet.vehicle.log.services', {
            'vehicle_id': vehicle.id, 'service_type_id': stypes[stype].id,
            'date_from': today - timedelta(days=days), 'date_to': today - timedelta(days=days),
            'amount': amount, 'vendor_id': partners[vendor].id, 'description': desc, 'state': state,
            'purchaser_id': vehicle.driver_id.id, 'odometer': vehicle.odometer,
            'inv_ref': f'INV-{vendor[-4:].upper()}-{1000 + i}' if state == 'done' and amount else False,
        })

    for i, (vxid, ctype, start_ago, duration, amount, recurring, freq, insurer, ref) in enumerate(CONTRACTS, start=1):
        xid = f'rc_flt_contract_{i}'
        if _ref(env, xid) or vxid not in vehicles:
            continue
        vehicle = vehicles[vxid]
        start = today - timedelta(days=start_ago)
        end = start + timedelta(days=duration)
        contract = _get_or_create(env, xid, 'fleet.vehicle.log.contract', {
            'name': f'{ctype} - {vehicle.license_plate}', 'vehicle_id': vehicle.id, 'cost_subtype_id': stypes[ctype].id,
            'start_date': start, 'expiration_date': end, 'date': start, 'amount': amount,
            'cost_generated': recurring, 'cost_frequency': freq, 'insurer_id': partners[insurer].id, 'ins_ref': ref,
            'user_id': manager.id, 'purchaser_id': vehicle.driver_id.id,
            'notes': '<p>Renew 30 days before expiry. Copy of policy kept in the vehicle file.</p>',
        })
        contract.state = 'expired' if end < today else 'open'
    try:
        env['fleet.vehicle.log.contract'].sudo().scheduler_manage_contract_expiration()
    except Exception:
        pass

    # refrigeration unit of the catering van tracked as maintenance equipment (fleet_maintenance)
    if 'maintenance.equipment' in env and 'vehicle_id' in env['maintenance.equipment']._fields and 'rc_flt_van_1' in vehicles:
        try:
            with env.cr.savepoint():
                _get_or_create(env, 'rc_flt_equipment_reefer', 'maintenance.equipment', {
                    'name': 'Reefer Unit - Catering Van KL-07-CX-4521', 'equipment_assign_to': 'vehicle',
                    'vehicle_id': vehicles['rc_flt_van_1'].id, 'serial_no': 'KCT-RF-2024-118',
                    'model': 'Kerala Cool Tech RF-600', 'cost': 145000,
                })
        except Exception as e:
            _logger.info("Fleet maintenance equipment skipped: %s", e)


# --------------------------------------------------------------------------- lunch
LUNCH_VENDORS = [
    # xid, name, phone, street, days, deadline (automatic_email_time), send_by
    ('rc_lun_vendor_meals', 'Kerala Meals Corner', '+91 484 235 7781', 'MG Road, Ravipuram', 'mon tue wed thu fri sat', 11.0, 'phone'),
    ('rc_lun_vendor_biryani', 'Malabar Biryani House', '+91 484 238 1144', 'Broadway, Ernakulam', 'mon wed fri', 10.5, 'mail'),
    ('rc_lun_vendor_juice', 'Juice Junction', '+91 98470 66123', 'Panampilly Nagar Main Avenue', 'mon tue wed thu fri sat sun', 15.0, 'phone'),
]
LUNCH_PRODUCTS = [
    # xid, vendor, category, name, price, description
    ('rc_lun_p1', 'rc_lun_vendor_meals', 'Kerala Meals', 'Veg Kerala Meals (Matta Rice)', 90, 'Matta rice, sambar, avial, thoran, pickle, papadam'),
    ('rc_lun_p2', 'rc_lun_vendor_meals', 'Kerala Meals', 'Fish Curry Meals', 140, 'Meals with Kerala fish curry and fish fry'),
    ('rc_lun_p3', 'rc_lun_vendor_meals', 'Kerala Meals', 'Chicken Curry Meals', 130, 'Meals with nadan chicken curry'),
    ('rc_lun_p4', 'rc_lun_vendor_meals', 'Kerala Meals', 'Kappa & Meen Curry', 110, 'Tapioca with spicy fish curry'),
    ('rc_lun_p5', 'rc_lun_vendor_meals', 'Snacks', 'Parotta & Beef Fry', 120, '2 Kerala parottas with beef ularthiyathu'),
    ('rc_lun_p6', 'rc_lun_vendor_biryani', 'Biryani', 'Malabar Chicken Biryani', 160, 'Kaima rice dum biryani with raita and pickle'),
    ('rc_lun_p7', 'rc_lun_vendor_biryani', 'Biryani', 'Mutton Biryani', 220, 'Thalassery style mutton dum biryani'),
    ('rc_lun_p8', 'rc_lun_vendor_biryani', 'Biryani', 'Veg Biryani', 120, 'Vegetable dum biryani'),
    ('rc_lun_p9', 'rc_lun_vendor_biryani', 'Biryani', 'Egg Biryani', 130, 'Biryani with 2 boiled eggs'),
    ('rc_lun_p10', 'rc_lun_vendor_biryani', 'Snacks', 'Chicken 65 (Half)', 110, 'Spicy fried chicken starter'),
    ('rc_lun_p11', 'rc_lun_vendor_juice', 'Juices', 'Fresh Lime Soda', 40, 'Sweet, salt or mixed'),
    ('rc_lun_p12', 'rc_lun_vendor_juice', 'Juices', 'Tender Coconut Shake', 80, 'Tender coconut blended with ice cream'),
    ('rc_lun_p13', 'rc_lun_vendor_juice', 'Juices', 'Sharjah Shake', 90, 'Banana, milk, peanuts and Horlicks'),
    ('rc_lun_p14', 'rc_lun_vendor_juice', 'Juices', 'Mango Lassi', 70, 'Alphonso mango and curd'),
    ('rc_lun_p15', 'rc_lun_vendor_juice', 'Snacks', 'Fruit Salad Bowl', 60, 'Seasonal fruits with honey'),
]
LUNCH_TOPPINGS = [
    # xid, vendor, category (1-3), name, price
    ('rc_lun_t1', 'rc_lun_vendor_meals', 1, 'Extra Fish Fry', 60),
    ('rc_lun_t2', 'rc_lun_vendor_meals', 1, 'Omelette', 25),
    ('rc_lun_t3', 'rc_lun_vendor_meals', 2, 'Extra Papadam', 10),
    ('rc_lun_t4', 'rc_lun_vendor_biryani', 1, 'Extra Raita', 15),
    ('rc_lun_t5', 'rc_lun_vendor_biryani', 1, 'Boiled Egg', 15),
    ('rc_lun_t6', 'rc_lun_vendor_juice', 1, 'Extra Ice Cream Scoop', 30),
]


def _load_lunch(env):
    if 'lunch.order' not in env:
        return
    location = _get_or_create(env, 'rc_lun_location_kitchen', 'lunch.location', {
        'name': 'Resto Cafe - Staff Room (Marine Drive)', 'address': 'Marine Drive, Kochi 682031'})
    location_cafe = _get_or_create(env, 'rc_lun_location_cafe', 'lunch.location', {
        'name': 'Resto Cafe - Panampilly Nagar', 'address': 'Panampilly Nagar, Kochi 682036'})
    responsible = _ref(env, 'rc_user_arjun') or env.ref('base.user_admin')
    tz = 'Asia/Kolkata'
    vendors = {}
    for xid, name, phone, street, days, deadline, send_by in LUNCH_VENDORS:
        if _ref(env, xid):
            vendors[xid] = _ref(env, xid)
            continue
        partner = _partner(env, xid + '_partner', name, phone=phone, street=street)
        vals = {'partner_id': partner.id, 'responsible_id': responsible.id, 'send_by': send_by, 'tz': tz,
                'automatic_email_time': deadline,
                'available_location_ids': [Command.set([location.id, location_cafe.id])]}
        for d in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'):
            vals[d] = d in days.split()
        vendors[xid] = _get_or_create(env, xid, 'lunch.supplier', vals)

    Cat = env['lunch.product.category'].sudo()
    cats = {}
    for name in ('Kerala Meals', 'Biryani', 'Snacks', 'Juices'):
        cats[name] = Cat.search([('name', '=', name)], limit=1) or _get_or_create(
            env, 'rc_lun_cat_' + name.lower().replace(' ', '_'), 'lunch.product.category', {'name': name})
    products = {}
    for xid, vxid, cat, name, price, desc in LUNCH_PRODUCTS:
        products[xid] = _get_or_create(env, xid, 'lunch.product', {
            'name': name, 'supplier_id': vendors[vxid].id, 'category_id': cats[cat].id, 'price': price,
            'description': f'<p>{desc}</p>', 'new_until': fields.Date.today() + timedelta(days=7) if xid in ('rc_lun_p12', 'rc_lun_p4') else False,
        })
    for xid, vxid, tcat, name, price in LUNCH_TOPPINGS:
        _get_or_create(env, xid, 'lunch.topping', {'name': name, 'supplier_id': vendors[vxid].id, 'topping_category': tcat, 'price': price})

    users = [u for u in (env.ref('base.user_admin'), _ref(env, 'rc_user_arjun')) if u]
    # wallet top-ups (cash moves)
    for i, user in enumerate(users, start=1):
        for j, (days, amount) in enumerate(((20, 2000), (6, 1000)), start=1):
            _get_or_create(env, f'rc_lun_topup_{i}_{j}', 'lunch.cashmove', {
                'user_id': user.id, 'amount': amount, 'date': fields.Date.today() - timedelta(days=days),
                'description': 'Monthly staff meal allowance' if j == 1 else 'Wallet top-up (cash at counter)',
                'currency_id': env.company.currency_id.id})

    # past orders (confirmed) for the last working days + today's orders
    today = fields.Date.today()
    plan = [  # days ago, user index, product, qty, state, note
        (9, 0, 'rc_lun_p2', 1, 'confirmed', ''), (9, 1, 'rc_lun_p6', 1, 'confirmed', 'Less spicy'),
        (8, 0, 'rc_lun_p1', 1, 'confirmed', ''), (8, 1, 'rc_lun_p13', 2, 'confirmed', ''),
        (7, 0, 'rc_lun_p7', 1, 'confirmed', ''), (7, 1, 'rc_lun_p3', 1, 'confirmed', ''),
        (6, 0, 'rc_lun_p5', 1, 'confirmed', ''), (6, 1, 'rc_lun_p11', 1, 'confirmed', 'Salt'),
        (3, 0, 'rc_lun_p4', 1, 'confirmed', ''), (3, 1, 'rc_lun_p8', 1, 'cancelled', 'Out of office'),
        (2, 0, 'rc_lun_p6', 1, 'confirmed', ''), (2, 1, 'rc_lun_p2', 1, 'confirmed', ''),
        (1, 0, 'rc_lun_p12', 1, 'sent', ''), (1, 1, 'rc_lun_p1', 1, 'confirmed', ''),
        (0, 0, 'rc_lun_p2', 1, 'ordered', 'Extra fish fry please'), (0, 1, 'rc_lun_p14', 1, 'new', ''),
    ]
    for i, (days, uidx, pxid, qty, state, note) in enumerate(plan, start=1):
        if uidx >= len(users):
            continue
        product = products[pxid]
        _get_or_create(env, f'rc_lun_order_{i}', 'lunch.order', {
            'user_id': users[uidx].id, 'product_id': product.id, 'quantity': qty, 'date': today - timedelta(days=days),
            'state': state, 'note': note or False, 'lunch_location_id': location.id, 'price': product.price * qty,
        })

    _get_or_create(env, 'rc_lun_alert', 'lunch.alert', {
        'name': 'Order your lunch before 11 AM', 'mode': 'alert', 'recipients': 'everyone', 'tz': tz,
        'notification_time': 10.0, 'location_ids': [Command.set([location.id, location_cafe.id])],
        'message': '<p>Lunch orders for Kerala Meals Corner close at 11:00. Biryani House delivers Mon, Wed and Fri.</p>',
        'sun': False,
    })


# --------------------------------------------------------------------------- expenses
EXPENSE_CATEGORIES = [
    # xid, name, cost (0 = employee enters amount), reinvoice policy
    ('rc_exp_cat_ingredients', 'Emergency Ingredient Purchase', 0, 'cost'),
    ('rc_exp_cat_fuel', 'Fuel', 0, 'no'),
    ('rc_exp_cat_travel', 'Travel (Bus / Train / Auto)', 0, 'no'),
    ('rc_exp_cat_client', 'Client Entertainment', 0, 'sales_price'),
    ('rc_exp_cat_courier', 'Courier & Delivery', 0, 'cost'),
    ('rc_exp_cat_uniform', 'Uniform & Safety Wear', 450, 'no'),
]
EXPENSES = [
    # xid, employee, category xid, description, qty, unit price, days ago, payment mode, state, extra
    ('rc_exp_1', 'Vishnu Kumar', 'rc_exp_cat_ingredients', 'Shallots & curry leaves - Ernakulam Market (supplier short)', 1, 1850, 1, 'own_account', 'draft', {}),
    ('rc_exp_2', 'Arun Varma', 'rc_exp_cat_fuel', 'Diesel for catering van KL-07-CX-4521', 1, 3200, 3, 'own_account', 'submitted', {}),
    ('rc_exp_3', 'Mohammed Bilal', 'rc_exp_cat_fuel', 'CNG refill Eeco cargo', 1, 1150, 2, 'own_account', 'submitted', {}),
    ('rc_exp_4', 'Kevin Joseph', 'rc_exp_cat_courier', 'Courier - cake delivery to Kakkanad (Porter)', 1, 380, 4, 'own_account', 'approved', {}),
    ('rc_exp_5', 'Sneha Pillai', 'rc_exp_cat_client', 'Lunch with Marina Bay Events - wedding menu tasting', 1, 4600, 6, 'own_account', 'posted',
     {'sale_order': 'rc_so_wedding_welcome'}),
    ('rc_exp_6', 'Priya Menon', 'rc_exp_cat_travel', 'Train Kochi - Kozhikode, spice supplier visit', 1, 640, 15, 'own_account', 'paid', {}),
    ('rc_exp_7', 'Priya Menon', 'rc_exp_cat_travel', 'Hotel stay Kozhikode, 1 night', 1, 2800, 15, 'own_account', 'paid', {}),
    ('rc_exp_8', 'Ananya Sharma', 'rc_exp_cat_uniform', 'Chef coats (2 sets)', 2, 450, 20, 'own_account', 'paid', {}),
    ('rc_exp_9', 'Rahul Nair', 'rc_exp_cat_uniform', 'Anti-slip kitchen shoes', 1, 1290, 10, 'own_account', 'refused',
     {'reason': 'Shoes are issued from store; please collect from the Store Manager.'}),
    ('rc_exp_10', 'Suresh Kumar', 'rc_exp_cat_client', 'Dinner with Grand Residency F&B manager', 1, 7800, 9, 'company_account', 'paid', {}),
    ('rc_exp_11', 'Vishnu Kumar', 'rc_exp_cat_ingredients', 'Fresh karimeen for Onam Sadya order (vendor delay)', 1, 5400, 25, 'own_account', 'paid',
     {'sale_order': 'rc_so_onam_spice_route'}),
    ('rc_exp_12', 'Kevin Joseph', 'rc_exp_cat_fuel', 'EV charging - public charger, Vyttila hub', 1, 210, 7, 'own_account', 'approved', {}),
    ('rc_exp_13', 'Arun Varma', 'rc_exp_cat_travel', 'Auto fare - airport pickup of catering equipment', 1, 450, 12, 'own_account', 'posted', {}),
    ('rc_exp_14', 'Sneha Pillai', 'rc_exp_cat_courier', 'Speed post - signed contract to St. Teresa\'s School', 1, 120, 0, 'own_account', 'draft', {}),
    ('rc_exp_15', 'Mohammed Bilal', 'rc_exp_cat_ingredients', 'Ice blocks for outdoor BBQ', 6, 150, 5, 'own_account', 'refused',
     {'reason': 'Already billed by the ice vendor on the BBQ purchase order.'}),
]


def _load_expenses(env):
    if 'hr.expense' not in env:
        return
    tax = env.company.account_purchase_tax_id
    categ = env['product.category'].sudo().search([('name', '=', 'Expenses')], limit=1) or env.ref('product.product_category_all')
    products = {}
    for xid, name, cost, policy in EXPENSE_CATEGORIES:
        vals = {'name': name, 'type': 'service', 'can_be_expensed': True, 'sale_ok': policy != 'no', 'purchase_ok': True,
                'standard_price': cost, 'list_price': cost, 'categ_id': categ.id,
                'supplier_taxes_id': [Command.set(tax.ids if xid in ('rc_exp_cat_ingredients', 'rc_exp_cat_uniform') else [])],
                'taxes_id': [Command.clear()]}
        if 'available_in_pos' in env['product.template']._fields:
            vals['available_in_pos'] = False
        product = _get_or_create(env, xid, 'product.product', vals)
        if 'reinvoice_policy' in product._fields:
            product.product_tmpl_id.reinvoice_policy = policy
        products[xid] = product

    admin = env.ref('base.user_admin')
    today = fields.Date.today()
    Expense = env['hr.expense'].sudo().with_context(tracking_disable=True, mail_create_nosubscribe=True)
    for xid, emp_name, cat_xid, desc, qty, price, days, mode, state, extra in EXPENSES:
        if _ref(env, xid):
            continue
        employee = _emp(env, emp_name)
        if not employee:
            continue
        try:
            with env.cr.savepoint():
                vals = {
                    'name': desc, 'employee_id': employee.id, 'product_id': products[cat_xid].id,
                    'quantity': qty, 'price_unit': price, 'date': today - timedelta(days=days),
                    'payment_mode': mode, 'manager_id': admin.id,
                }
                expense = Expense.create(vals)
                if not products[cat_xid].standard_price:
                    expense.write({'price_unit': price, 'total_amount_currency': qty * price})
                so = _ref(env, extra.get('sale_order', '')) if extra.get('sale_order') else False
                if so and 'sale_order_id' in expense._fields and so.state == 'sale':
                    expense.sale_order_id = so
                _bind(env, xid, expense)
                relock = so if so and getattr(so, 'locked', False) else False
                if relock:
                    relock.action_unlock()  # confirmed orders are locked; re-invoicing an expense needs it open
                _advance_expense(env, expense, state, extra, today - timedelta(days=max(days - 2, 0)))
                if relock:
                    relock.action_lock()
        except Exception as e:
            _logger.exception("Hudson POS: expense %s failed: %s", xid, e)


def _advance_expense(env, expense, state, extra, when):
    if state == 'draft':
        return
    expense.approval_state = 'submitted'
    if state == 'submitted':
        expense.update_activities_and_mails()
        return
    if state == 'refused':
        expense._do_refuse(extra.get('reason', 'Not reimbursable.'))
        return
    expense._do_approve()  # creates the draft vendor bill (employee) or the posted entry (company-paid)
    move = expense.account_move_id
    if state == 'approved' or not move:
        return
    if move.state == 'draft':
        move.write({'invoice_date': when, 'date': when}) if move.is_invoice() else move.write({'date': when})
        move.action_post()
    if state == 'paid' and expense.payment_mode == 'own_account' and move.payment_state == 'not_paid':
        env['account.payment.register'].sudo().with_context(active_model='account.move', active_ids=move.ids).create(
            {'payment_date': when + timedelta(days=2)})._create_payments()


# --------------------------------------------------------------------------- entry point
def load_fleet_lunch_expense_suite_demo_data(env):
    for name, loader in (('Fleet', _load_fleet), ('Lunch', _load_lunch), ('Expenses', _load_expenses)):
        try:
            with env.cr.savepoint():
                loader(env)
            _logger.info("Hudson POS: Resto Cafe %s demo data loaded.", name)
        except Exception as e:
            _logger.exception("Hudson POS: %s demo data failed: %s", name, e)
