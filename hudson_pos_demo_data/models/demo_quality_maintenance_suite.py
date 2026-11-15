# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Quality & Maintenance demo data (kitchen context).

Quality (custom ``Quality`` module):
  * quality teams, tags and root causes for a restaurant kitchen
  * control points on Receipts (dairy / meat / frozen temperature measures, egg & packaging pass-fail,
    coffee freshness) and on Manufacturing (patty core temperature, allergen label photo, hygiene instructions)
  * quality checks in every state (to do / passed / failed) with measured values
  * quality alerts in every stage with priorities, tags, root causes and corrective / preventive actions

Maintenance:
  * teams (Kitchen Equipment, Cafe Equipment, Facilities), equipment categories, equipment vendors
  * 12 pieces of kitchen / cafe / IT / facility equipment with model, serial, cost, warranty and assignment
  * corrective and preventive requests in every stage, past and future dates, durations, priorities and
    recurring preventive maintenance

Every record is bound to an xmlid of this module (prefixes ``rc_qc_`` / ``rc_mnt_``), so it is idempotent.
"""
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    return env.ref(xid if '.' in xid else f'{MODULE}.{xid}', raise_if_not_found=False)


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


def _now(days=0, hour=10):
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)


def _product(env, *names):
    Product = env['product.product'].sudo()
    for name in names:
        product = Product.search([('name', '=', name)], limit=1) or Product.search([('name', 'ilike', name)], limit=1)
        if product:
            return product
    return Product


def _users(env):
    admin = env.ref('base.user_admin')
    arjun = _ref(env, 'rc_user_arjun') or admin
    return admin, arjun


def _html(*paras):
    return ''.join(f'<p>{p}</p>' for p in paras)


# =========================================================================== QUALITY
QC_TEAMS = [
    ('rc_qc_team_kitchen', 'Kitchen Food Safety Team', 1),
    ('rc_qc_team_receiving', 'Receiving & Cold Chain Team', 2),
]
QC_TAGS = [('rc_qc_tag_cold', 'Cold Chain', 4), ('rc_qc_tag_allergen', 'Allergen', 1), ('rc_qc_tag_hygiene', 'Hygiene', 10),
           ('rc_qc_tag_supplier', 'Supplier Issue', 3), ('rc_qc_tag_packaging', 'Packaging Damage', 2)]
QC_REASONS = [('rc_qc_reason_temp', 'Supplier Temperature Breach'), ('rc_qc_reason_shelf', 'Expired / Short Shelf Life'),
              ('rc_qc_reason_cooking', 'Under-cooking on the Line')]

# xid, title, test type, where (receipt|mrp), products (names), team, extra vals
QC_POINTS = [
    ('rc_qc_point_dairy', 'Dairy Receiving Temperature', 'measure', 'receipt', ['Milk', 'Heavy Cream', 'Butter', 'Cream Cheese'],
     'rc_qc_team_receiving', {'norm': 4.0, 'norm_unit': '°C', 'tolerance_min': 0.0, 'tolerance_max': 5.0,
                              'instructions': _html('Probe one unit per crate in the centre of the pallet.',
                                                    'Record the reading before the goods leave the loading bay.'),
                              'failure_message': _html('Reject the crate, move it to Quarantine and call the supplier.')}),
    ('rc_qc_point_meat', 'Meat & Poultry Core Temperature on Receipt', 'measure', 'receipt', ['Chicken Breast', 'Minced Beef', 'Beef Patty'],
     'rc_qc_team_receiving', {'norm': 2.0, 'norm_unit': '°C', 'tolerance_min': 0.0, 'tolerance_max': 4.0,
                              'instructions': _html('Insert the sanitised probe between two packs. Never pierce the vacuum pack.'),
                              'failure_message': _html('Above 4 °C: reject the delivery and raise a quality alert.')}),
    ('rc_qc_point_frozen', 'Frozen Goods Receipt', 'measure', 'receipt', ['Vanilla Ice Cream'],
     'rc_qc_team_receiving', {'norm': -18.0, 'norm_unit': '°C', 'tolerance_min': -25.0, 'tolerance_max': -15.0,
                              'instructions': _html('Check for ice crystals and soft edges; they mean the cold chain was broken.')}),
    ('rc_qc_point_eggs', 'Egg Shell Integrity', 'passfail', 'receipt', ['Eggs'],
     'rc_qc_team_receiving', {'instructions': _html('Open 2 trays per delivery. More than 2 cracked or dirty eggs per tray = fail.'),
                              'control_per': 'product'}),
    ('rc_qc_point_packaging', 'Packaging, Label & Shelf-Life Inspection', 'passfail', 'receipt', [],
     'rc_qc_team_receiving', {'control_per': 'operation',
                              'instructions': _html('Seals intact, labels readable, at least 70% of shelf life remaining.')}),
    ('rc_qc_point_coffee', 'Weekly Coffee Bean Freshness', 'passfail', 'receipt', ['Espresso Coffee Beans'],
     'rc_qc_team_kitchen', {'control_frequency': 'periodical', 'periodic_qty': 1, 'periodic_uom': 'week',
                            'instructions': _html('Roast date within 21 days, valve bag sealed, no stale aroma.')}),
    ('rc_qc_point_patty', 'Burger Patty Core Temperature', 'measure', 'mrp', ['Beef Patty'],
     'rc_qc_team_kitchen', {'norm': 75.0, 'norm_unit': '°C', 'tolerance_min': 72.0, 'tolerance_max': 85.0,
                            'instructions': _html('Probe the thickest patty of the batch after resting 1 minute.'),
                            'failure_message': _html('Return the batch to the grill and re-probe after 2 minutes.')}),
    ('rc_qc_point_allergen', 'Allergen Label Photo', 'picture', 'mrp', [],
     'rc_qc_team_kitchen', {'instructions': _html('Take a photo of the allergen label on the packed batch (nuts, dairy, gluten).')}),
    ('rc_qc_point_hygiene', 'Pre-production Hygiene Checklist', 'instructions', 'mrp', [],
     'rc_qc_team_kitchen', {'instructions': _html('Hands washed, hair net and gloves on, colour-coded boards in place, '
                                                  'sanitiser at 200 ppm, probe thermometer calibrated.')}),
]

# xid, point, product, state, measure, days ago, note
QC_CHECKS = [
    ('rc_qc_check_1', 'rc_qc_point_dairy', 'Milk', 'pass', 3.6, 9, 'GoldenCrumb delivery, all crates within limit.'),
    ('rc_qc_check_2', 'rc_qc_point_dairy', 'Heavy Cream', 'pass', 4.2, 9, False),
    ('rc_qc_check_3', 'rc_qc_point_dairy', 'Butter', 'fail', 8.4, 6, 'Truck chiller unit faulty; 6 cases rejected.'),
    ('rc_qc_check_4', 'rc_qc_point_meat', 'Chicken Breast', 'pass', 1.8, 5, False),
    ('rc_qc_check_5', 'rc_qc_point_meat', 'Minced Beef', 'fail', 6.1, 4, 'Delivered 2 hours late, packs warm to touch.'),
    ('rc_qc_check_6', 'rc_qc_point_frozen', 'Vanilla Ice Cream', 'pass', -19.5, 3, False),
    ('rc_qc_check_7', 'rc_qc_point_eggs', 'Eggs', 'fail', 0, 2, '5 cracked eggs in tray 2.'),
    ('rc_qc_check_8', 'rc_qc_point_coffee', 'Espresso Coffee Beans', 'pass', 0, 7, 'Roasted 6 days ago.'),
    ('rc_qc_check_9', 'rc_qc_point_patty', 'Beef Patty', 'pass', 78.0, 1, False),
    ('rc_qc_check_10', 'rc_qc_point_patty', 'Beef Patty', 'fail', 68.5, 1, 'Grill 2 running cold; batch re-cooked.'),
    ('rc_qc_check_11', 'rc_qc_point_meat', 'Beef Patty', 'none', 0, 0, False),
    ('rc_qc_check_12', 'rc_qc_point_dairy', 'Cream Cheese', 'none', 0, 0, False),
    ('rc_qc_check_13', 'rc_qc_point_hygiene', False, 'pass', 0, 0, 'Morning shift checklist completed by the sous chef.'),
]

# xid, title, stage xmlid, priority, team, tags, reason, product, check, days ago, description, corrective, preventive
QC_ALERTS = [
    ('rc_qc_alert_butter', 'Butter delivered at 8.4 °C', 'Quality.quality_alert_stage_resolved', '2', 'rc_qc_team_receiving',
     ['rc_qc_tag_cold', 'rc_qc_tag_supplier'], 'rc_qc_reason_temp', 'Butter', 'rc_qc_check_3', 6,
     'Six cases of butter rejected at the loading bay; supplier truck chiller faulty.',
     'Cases returned, credit note received from GoldenCrumb.', 'Supplier must share the truck temperature log with every delivery.'),
    ('rc_qc_alert_beef', 'Minced beef above 4 °C on arrival', 'Quality.quality_alert_stage_corrective', '3', 'rc_qc_team_receiving',
     ['rc_qc_tag_cold', 'rc_qc_tag_supplier'], 'rc_qc_reason_temp', 'Minced Beef', 'rc_qc_check_5', 4,
     'Delivery arrived 2 hours late and the core temperature was 6.1 °C.',
     'Whole delivery rejected; emergency order placed with backup butcher.', 'Delivery window moved to 7 AM, before the heat of the day.'),
    ('rc_qc_alert_eggs', 'Cracked eggs in morning delivery', 'Quality.quality_alert_stage_investigation', '1', 'rc_qc_team_receiving',
     ['rc_qc_tag_packaging'], 'Quality.reason_parts_quality', 'Eggs', 'rc_qc_check_7', 2,
     '5 cracked eggs found in one tray.', False, False),
    ('rc_qc_alert_grill', 'Grill 2 under-cooking burger patties', 'Quality.quality_alert_stage_investigation', '3', 'rc_qc_team_kitchen',
     ['rc_qc_tag_hygiene'], 'rc_qc_reason_cooking', 'Beef Patty', 'rc_qc_check_10', 1,
     'Batch measured 68.5 °C core temperature. Grill 2 thermostat suspected.',
     'Batch re-cooked; grill 2 taken off the line until maintenance checks the thermostat.', False),
    ('rc_qc_alert_allergen', 'Missing nut warning on cookie boxes', 'Quality.quality_alert_stage_new', '2', 'rc_qc_team_kitchen',
     ['rc_qc_tag_allergen'], 'Quality.reason_work_operation', 'Cardamom Butter Cookies', False, 0,
     'A customer reported that a takeaway box had no allergen sticker.', False, False),
    ('rc_qc_alert_shelf', 'Cream cheese with 5 days of shelf life left', 'Quality.quality_alert_stage_new', '0', 'rc_qc_team_receiving',
     ['rc_qc_tag_supplier'], 'rc_qc_reason_shelf', 'Cream Cheese', False, 0,
     'Received stock is below our 70% shelf-life rule.', False, False),
]


def _quality(env):
    if 'quality.point' not in env:
        return
    admin, arjun = _users(env)
    for xid, name, color in QC_TEAMS:
        _get_or_create(env, xid, 'quality.team', {'name': name, 'color': color, 'user_id': admin.id,
                                                  'member_ids': [Command.set((admin | arjun).ids)]}
                       if 'member_ids' in env['quality.team']._fields else {'name': name, 'color': color})
    for xid, name, color in QC_TAGS:
        if 'quality.tag' in env:
            _get_or_create(env, xid, 'quality.tag', {'name': name, 'color': color})
    for xid, name in QC_REASONS:
        if 'quality.reason' in env:
            _get_or_create(env, xid, 'quality.reason', {'name': name})

    receipts = env.ref('stock.picking_type_in', raise_if_not_found=False) or env['stock.picking.type'].search(
        [('code', '=', 'incoming')], limit=1)
    cooking_op = env['mrp.routing.workcenter'].sudo().search(
        ['|', '|', ('name', 'ilike', 'grill'), ('name', 'ilike', 'cook'), ('name', 'ilike', 'patty')], limit=1) \
        if 'mrp.routing.workcenter' in env else False
    for xid, title, ttype, where, products, team, extra in QC_POINTS:
        if _ref(env, xid):
            continue
        vals = {'title': title, 'test_type': ttype, 'team_id': _ref(env, team).id, 'user_id': admin.id,
                'control_per': 'product' if products else 'operation', **extra}
        if where == 'receipt':
            vals['picking_type_ids'] = [Command.set(receipts.ids)]
        else:
            vals['applies_to_manufacturing'] = True
            if xid == 'rc_qc_point_patty' and cooking_op:
                vals['workorder_operation_id'] = cooking_op.id
        product_ids = [p.id for p in (_product(env, n) for n in products) if p]
        if product_ids:
            vals.update(apply_to='products', product_ids=[Command.set(product_ids)])
        elif xid == 'rc_qc_point_packaging':
            categ = env['product.category'].search([('name', '=', 'Ingredients')], limit=1)
            if categ:
                vals.update(apply_to='categories', product_category_id=categ.id)
        _get_or_create(env, xid, 'quality.point', vals)

    Picking = env['stock.picking'].sudo()
    for xid, point_xid, pname, state, measure, days, note in QC_CHECKS:
        if _ref(env, xid):
            continue
        point = _ref(env, point_xid)
        product = _product(env, pname) if pname else env['product.product']
        vals = {
            'point_id': point.id, 'title': point.title + (f' - {product.name}' if product else ''),
            'test_type': point.test_type, 'team_id': point.team_id.id, 'user_id': (arjun if days % 2 else admin).id,
            'control_per': point.control_per, 'product_id': product.id or False,
            'instructions': point.instructions, 'failure_message': point.failure_message,
            'norm': point.norm, 'norm_unit': point.norm_unit, 'tolerance_min': point.tolerance_min,
            'tolerance_max': point.tolerance_max, 'date_create': _now(-days, 8),
        }
        if point.test_type == 'measure' and state != 'none':
            vals['measure'] = measure
        if note:
            vals['additional_note'] = note
        if product and point.picking_type_ids:
            picking = Picking.search([('picking_type_id', 'in', point.picking_type_ids.ids),
                                      ('move_ids.product_id', '=', product.id)], order='id desc', limit=1)
            if picking:
                vals['picking_id'] = picking.id
        check = _get_or_create(env, xid, 'quality.check', vals)
        if state != 'none':
            # written directly: do_fail() would re-route stock moves to a quarantine location
            check.write({'quality_state': state, 'date_done': _now(-days, 9)})

    stage_new = _ref(env, 'Quality.quality_alert_stage_new')
    for (xid, title, stage_xid, priority, team, tags, reason, pname, check_xid, days,
         desc, corrective, preventive) in QC_ALERTS:
        if _ref(env, xid):
            continue
        check = _ref(env, check_xid) if check_xid else False
        product = _product(env, pname)
        vals = {
            'title': title, 'priority': priority, 'team_id': _ref(env, team).id, 'user_id': admin.id,
            'product_id': product.id or False, 'description': _html(desc), 'date_assign': _now(-days, 9),
            'stage_id': (stage_new or _ref(env, stage_xid)).id,
        }
        if 'quality.tag' in env:
            vals['tag_ids'] = [Command.set([_ref(env, t).id for t in tags if _ref(env, t)])]
        if _ref(env, reason):
            vals['reason_id'] = _ref(env, reason).id
        if check:
            vals.update(check_id=check.id, picking_id=check.picking_id.id or False)
        if corrective:
            vals['corrective_action'] = _html(corrective)
        if preventive:
            vals['preventive_action'] = _html(preventive)
        alert = _get_or_create(env, xid, 'quality.alert', vals)
        stage = _ref(env, stage_xid)
        if stage and stage != alert.stage_id:
            alert.write({'stage_id': stage.id})
        if stage and stage.done:
            alert.date_close = _now(-max(days - 2, 0), 17)


# =========================================================================== MAINTENANCE
MNT_TEAMS = [('rc_mnt_team_kitchen', 'Kitchen Equipment', 1), ('rc_mnt_team_cafe', 'Cafe Equipment', 4),
             ('rc_mnt_team_facilities', 'Facilities', 10)]
MNT_CATEGORIES = [('rc_mnt_cat_cooking', 'Cooking Equipment', 1), ('rc_mnt_cat_refrigeration', 'Refrigeration', 4),
                  ('rc_mnt_cat_beverage', 'Beverage Equipment', 3), ('rc_mnt_cat_dishwashing', 'Dishwashing', 7),
                  ('rc_mnt_cat_it', 'POS & Kitchen Display Hardware', 9), ('rc_mnt_cat_hvac', 'HVAC & Power', 10)]
MNT_VENDORS = [('rc_mnt_vendor_kke', 'Kerala Kitchen Equipments Pvt Ltd', 'service@keralakitchen.example'),
               ('rc_mnt_vendor_coffee', 'Brewline Coffee Machines India', 'support@brewline.example'),
               ('rc_mnt_vendor_cold', 'ColdStar Refrigeration Systems', 'care@coldstar.example'),
               ('rc_mnt_vendor_tech', 'Kochi POS & Display Solutions', 'help@kochipos.example'),
               ('rc_mnt_vendor_power', 'Malabar Power & Cooling', 'service@malabarpower.example')]

# xid, name, category, vendor, model, serial, cost, warranty (days from today), team, employee, location, age (days), mtbf
MNT_EQUIPMENT = [
    ('rc_mnt_eq_espresso', 'Espresso Machine - La Marzocco Linea 3-Group', 'rc_mnt_cat_beverage', 'rc_mnt_vendor_coffee',
     'Linea Classic S 3AV', 'RC-ESP-22031', 850000, 240, 'rc_mnt_team_cafe', 'Ananya Sharma', 'Cafe counter', 520, 90),
    ('rc_mnt_eq_grinder', 'Coffee Grinder - Mazzer Super Jolly', 'rc_mnt_cat_beverage', 'rc_mnt_vendor_coffee',
     'Super Jolly V Pro', 'RC-GRD-11872', 145000, 120, 'rc_mnt_team_cafe', 'Ananya Sharma', 'Cafe counter', 520, 180),
    ('rc_mnt_eq_deck_oven', 'Deck Oven - 3 Deck Electric', 'rc_mnt_cat_cooking', 'rc_mnt_vendor_kke',
     'KKE-DO3-E', 'RC-OVN-30417', 420000, 400, 'rc_mnt_team_kitchen', 'Kevin Joseph', 'Bakery section', 700, 120),
    ('rc_mnt_eq_combi', 'Combi Oven - Rational iCombi Pro 10-1/1', 'rc_mnt_cat_cooking', 'rc_mnt_vendor_kke',
     'iCombi Pro 10-1/1', 'RC-CMB-88210', 1250000, 900, 'rc_mnt_team_kitchen', 'Mohammed Bilal', 'Hot line', 300, 150),
    ('rc_mnt_eq_fryer', 'Twin Tank Deep Fryer', 'rc_mnt_cat_cooking', 'rc_mnt_vendor_kke',
     'KKE-FRY-2T', 'RC-FRY-55120', 95000, -30, 'rc_mnt_team_kitchen', 'Mohammed Bilal', 'Hot line', 800, 60),
    ('rc_mnt_eq_blast', 'Blast Chiller - 10 Tray', 'rc_mnt_cat_refrigeration', 'rc_mnt_vendor_cold',
     'ColdStar BC-10', 'RC-BLC-70031', 380000, 600, 'rc_mnt_team_kitchen', 'Rahul Nair', 'Cold kitchen', 400, 200),
    ('rc_mnt_eq_freezer', 'Walk-in Freezer (-20 °C)', 'rc_mnt_cat_refrigeration', 'rc_mnt_vendor_cold',
     'ColdStar WIF-12', 'RC-WIF-12009', 980000, 1100, 'rc_mnt_team_facilities', 'Suresh Kumar', 'Back store', 650, 240),
    ('rc_mnt_eq_dishwasher', 'Hood-type Dishwasher', 'rc_mnt_cat_dishwashing', 'rc_mnt_vendor_kke',
     'KKE-HD-60', 'RC-DSW-40552', 310000, 60, 'rc_mnt_team_kitchen', 'Vishnu Kumar', 'Dish area', 760, 90),
    ('rc_mnt_eq_pos', 'POS Terminal - Front Counter', 'rc_mnt_cat_it', 'rc_mnt_vendor_tech',
     'TouchPOS 15.6" i5', 'RC-POS-00117', 68000, 365, 'rc_mnt_team_facilities', 'Priya Menon', 'Front counter', 200, 365),
    ('rc_mnt_eq_kds', 'Kitchen Display Screen - Hot Line', 'rc_mnt_cat_it', 'rc_mnt_vendor_tech',
     'KDS 22" IP65', 'RC-KDS-00342', 42000, 365, 'rc_mnt_team_facilities', 'Mohammed Bilal', 'Hot line pass', 200, 365),
    ('rc_mnt_eq_ac', 'Dining Hall AC - 2 x 5.5 TR Ductable', 'rc_mnt_cat_hvac', 'rc_mnt_vendor_power',
     'Blue Star DSA-55', 'RC-HVC-90876', 560000, 180, 'rc_mnt_team_facilities', 'Suresh Kumar', 'Main dining hall', 900, 120),
    ('rc_mnt_eq_generator', 'Diesel Generator 62.5 kVA', 'rc_mnt_cat_hvac', 'rc_mnt_vendor_power',
     'Kirloskar KG1-62.5', 'RC-GEN-62514', 780000, 30, 'rc_mnt_team_facilities', 'Suresh Kumar', 'Generator room', 1100, 300),
]

# xid, title, equipment, type, stage, priority, days (schedule from today), duration h, recurring (interval, unit), description
MNT_REQUESTS = [
    ('rc_mnt_req_espresso_descale', 'Monthly descale & group head service', 'rc_mnt_eq_espresso', 'preventive', 'maintenance.stage_0', '2', 6, 2.0,
     (1, 'month'), 'Descale boilers, replace group gaskets and shower screens, check brew pressure (9 bar).'),
    ('rc_mnt_req_espresso_leak', 'Steam wand leaking on group 2', 'rc_mnt_eq_espresso', 'corrective', 'maintenance.stage_3', '3', -12, 1.5,
     None, 'Barista reported water dripping from the steam wand valve during rush hour.'),
    ('rc_mnt_req_grinder_burrs', 'Replace grinder burrs', 'rc_mnt_eq_grinder', 'preventive', 'maintenance.stage_1', '2', 0, 1.0,
     (6, 'month'), 'Burrs reached 500 kg of coffee; grind is no longer consistent.'),
    ('rc_mnt_req_oven_thermo', 'Deck 2 not reaching 220 °C', 'rc_mnt_eq_deck_oven', 'corrective', 'maintenance.stage_1', '3', -1, 3.0,
     None, 'Bread on deck 2 is pale. Suspect heating element or thermocouple.'),
    ('rc_mnt_req_oven_pm', 'Quarterly oven inspection', 'rc_mnt_eq_deck_oven', 'preventive', 'maintenance.stage_0', '1', 21, 2.0,
     (3, 'month'), 'Check door seals, elements, steam injection and calibrate thermostats.'),
    ('rc_mnt_req_combi_care', 'Combi oven CareControl cleaning check', 'rc_mnt_eq_combi', 'preventive', 'maintenance.stage_3', '1', -20, 1.0,
     (1, 'month'), 'Verify cleaning tablets, descaling and the water filter cartridge.'),
    ('rc_mnt_req_fryer_thermostat', 'Fryer left tank overheating', 'rc_mnt_eq_fryer', 'corrective', 'maintenance.stage_0', '3', 1, 2.0,
     None, 'Oil smoking at the 180 °C setting. Fryer off the line until fixed.'),
    ('rc_mnt_req_fryer_old', 'Fryer burner replaced', 'rc_mnt_eq_fryer', 'corrective', 'maintenance.stage_3', '2', -45, 4.0,
     None, 'Left burner cracked; replaced under the annual service contract.'),
    ('rc_mnt_req_blast_gas', 'Blast chiller slow to pull down', 'rc_mnt_eq_blast', 'corrective', 'maintenance.stage_1', '2', -2, 3.5,
     None, 'Takes 140 minutes to reach 3 °C instead of 90. Check refrigerant charge.'),
    ('rc_mnt_req_freezer_coils', 'Walk-in freezer coil cleaning & door gasket check', 'rc_mnt_eq_freezer', 'preventive', 'maintenance.stage_0', '2', 10, 3.0,
     (3, 'month'), 'Clean evaporator and condenser coils, test the door alarm and heater strips.'),
    ('rc_mnt_req_dish_pump', 'Dishwasher rinse pump noisy', 'rc_mnt_eq_dishwasher', 'corrective', 'maintenance.stage_0', '1', 3, 1.5,
     None, 'Grinding noise from the rinse pump. Rinse temperature still at 82 °C.'),
    ('rc_mnt_req_pos_printer', 'Receipt printer not cutting paper', 'rc_mnt_eq_pos', 'corrective', 'maintenance.stage_3', '2', -7, 0.5,
     None, 'Auto-cutter jammed; blade cleaned and realigned.'),
    ('rc_mnt_req_kds_touch', 'KDS touchscreen unresponsive', 'rc_mnt_eq_kds', 'corrective', 'maintenance.stage_4', '3', -30, 1.0,
     None, 'Touch layer damaged by steam. Screen scrapped and replaced with an IP65 unit.'),
    ('rc_mnt_req_ac_service', 'AC filter cleaning & gas check', 'rc_mnt_eq_ac', 'preventive', 'maintenance.stage_0', '1', 14, 4.0,
     (1, 'month'), 'Clean filters and drain trays, check gas pressure before the weekend rush.'),
    ('rc_mnt_req_genset', 'Generator load test & oil change', 'rc_mnt_eq_generator', 'preventive', 'maintenance.stage_0', '2', 4, 3.0,
     (6, 'month'), 'Run on load for 30 minutes, change engine oil and filters, top up coolant.'),
]


def _employee(env, name):
    if 'hr.employee' not in env:
        return env['res.users']
    return env['hr.employee'].sudo().search([('name', '=', name)], limit=1)


def _maintenance(env):
    if 'maintenance.equipment' not in env:
        return
    admin, arjun = _users(env)
    for xid, name, color in MNT_TEAMS:
        _get_or_create(env, xid, 'maintenance.team', {'name': name, 'color': color,
                                                      'member_ids': [Command.set((admin | arjun).ids)]})
    for xid, name, color in MNT_CATEGORIES:
        _get_or_create(env, xid, 'maintenance.equipment.category', {'name': name, 'color': color,
                                                                     'technician_user_id': arjun.id})
    for xid, name, email in MNT_VENDORS:
        _get_or_create(env, xid, 'res.partner', {'name': name, 'email': email, 'is_company': True,
                                                 'city': 'Kochi', 'country_id': env.ref('base.in').id})

    Equipment = env['maintenance.equipment']
    location_field = Equipment._fields.get('location_id')
    for (xid, name, cat, vendor, model, serial, cost, warranty, team, emp_name, location, age, mtbf) in MNT_EQUIPMENT:
        if _ref(env, xid):
            continue
        employee = _employee(env, emp_name)
        vals = {
            'name': name, 'category_id': _ref(env, cat).id, 'partner_id': _ref(env, vendor).id,
            'partner_ref': f'AMC-{serial[-5:]}', 'model': model, 'serial_no': serial, 'cost': cost,
            'warranty_date': fields.Date.today() + timedelta(days=warranty),
            'effective_date': fields.Date.today() - timedelta(days=age),
            'maintenance_team_id': _ref(env, team).id, 'technician_user_id': arjun.id, 'owner_user_id': admin.id,
            'note': _html(f'Installed at: {location}.'),
        }
        if 'expected_mtbf' in Equipment._fields:
            vals['expected_mtbf'] = mtbf
        if employee and 'employee_id' in Equipment._fields:
            vals.update(equipment_assign_to='employee', employee_id=employee.id,
                        assign_date=fields.Date.today() - timedelta(days=age))
        if location_field is not None and location_field.type == 'char':
            vals['location_id'] = location
        _get_or_create(env, xid, 'maintenance.equipment', vals)

    for (xid, title, eq_xid, mtype, stage_xid, priority, days, duration, recurring, desc) in MNT_REQUESTS:
        if _ref(env, xid):
            continue
        equipment = _ref(env, eq_xid)
        schedule = _now(days, 15 if mtype == 'preventive' else 11)
        vals = {
            'name': title, 'equipment_id': equipment.id, 'maintenance_type': mtype, 'priority': priority,
            'maintenance_team_id': equipment.maintenance_team_id.id, 'description': _html(desc),
            'schedule_date': schedule, 'duration': duration,
            'owner_user_id': admin.id, 'category_id': equipment.category_id.id,
        }
        if 'user_ids' in env['maintenance.request']._fields:
            vals['user_ids'] = [Command.set(arjun.ids)]
        if 'schedule_end' in env['maintenance.request']._fields:
            vals['schedule_end'] = schedule + timedelta(hours=duration)
        if recurring:
            vals.update(recurring_maintenance=True, repeat_interval=recurring[0], repeat_unit=recurring[1], repeat_type='forever')
        request = _get_or_create(env, xid, 'maintenance.request', vals)
        stage = env.ref(stage_xid, raise_if_not_found=False)
        if stage and stage != request.stage_id:
            request.write({'stage_id': stage.id})
        if stage_xid in ('maintenance.stage_3', 'maintenance.stage_4'):
            closed = {'close_date': (schedule + timedelta(hours=duration)).date()}
            state_field = request._fields.get('state')
            if state_field is not None and state_field.type == 'selection':
                options = dict(state_field._description_selection(env))
                state = 'done' if stage_xid == 'maintenance.stage_3' else 'cancelled'
                if state in options:
                    closed['state'] = state
            request.write({k: v for k, v in closed.items() if k in request._fields})
    # the KDS replaced after the scrapped request is still in service; the old unit is not modelled separately


# =========================================================================== entry point
def load_quality_maintenance_suite_demo_data(env):
    for name, step in (('quality', _quality), ('maintenance', _maintenance)):
        try:
            with env.cr.savepoint():
                step(env)
        except Exception as e:
            _logger.exception("Hudson POS: %s demo data failed: %s", name, e)
    _logger.info("Hudson POS: Resto Cafe Quality & Maintenance demo data loaded.")
