# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Approvals & PLM demo data.

Approvals (custom module `approvals`):
  * 3 restaurant categories (Menu Price Change, Kitchen Equipment Purchase, Event Discount above 10%)
    next to the 9 standard ones, with Administrator / Arjun Nair as approvers
  * 15 requests in every status (To Submit, Submitted, Approved, Refused, Cancelled), INR amounts,
    product lines, dates and chatter notes - transitions use the module's own methods
PLM (custom module `hudson_plm`):
  * ECO types New Menu Item / Recipe Change / Packaging Change sharing the standard stages,
    stage approval roles (Head Chef, Food Safety Officer, Cost Controller), 4 tags
  * 8 ECOs on the restaurant BoMs in every stage: new, in progress, rejected, validated and
    effective (applied -> BoM V2 becomes the live recipe, V1 archived)
Idempotent: every record is bound to an xmlid of this module (rc_apr_ / rc_plm_).
"""
import logging
from datetime import timedelta

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


def _users(env):
    admin = env.ref('base.user_admin')
    arjun = _ref(env, 'rc_user_arjun') or admin
    return admin, arjun


def _ago(days, hour=10):
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)


def _product(env, *names, fallback=True):
    P = env['product.product'].with_context(active_test=False)
    for name in names:
        prod = P.search([('name', '=', name)], limit=1) or P.search([('name', 'ilike', name)], limit=1)
        if prod:
            return prod
    return P.search([('purchase_ok', '=', True)], limit=1) if fallback else P


# =========================================================================== APPROVALS
NEW_CATEGORIES = [
    ('rc_apr_cat_menu_price', 'Menu Price Change', 'Change the selling price of a dish or drink on the POS / website menu.', 'sequence', 2,
     {'amount': 'required', 'reference': 'optional', 'requirer_document': 'optional'}, 1),
    ('rc_apr_cat_kitchen_equipment', 'Kitchen Equipment Purchase', 'Buy or replace kitchen and cafe equipment above Rs 25,000.', 'or', 1,
     {'line_type': 'required', 'quantity': 'optional', 'amount': 'optional', 'has_partner': 'optional', 'create_rfq': True}, 2),
    ('rc_apr_cat_event_discount', 'Event Discount above 10%', 'Discounts above 10% on catering, banquet and party bookings.', 'or', 1,
     {'amount': 'required', 'has_partner': 'required', 'date': 'required', 'reference': 'optional'}, 3),
]


def _approval_categories(env, admin, arjun):
    cats = {}
    for xid, name, desc, atype, minimum, extra, color in NEW_CATEGORIES:
        approvers = [Command.create({'user_id': admin.id, 'required': True})]
        if arjun != admin:
            approvers.append(Command.create({'user_id': arjun.id, 'required': atype == 'sequence'}))
        cats[xid] = _get_or_create(env, xid, 'approval.category', {
            'name': name, 'description': desc, 'approval_type': atype, 'approval_minimum': minimum,
            'color': color, 'user_ids': approvers, **extra,
        })
    return cats


def _std_cat(env, name):
    return env['approval.category'].search([('name', '=', name)], limit=1)


EQUIPMENT = [
    ('rc_apr_prod_espresso_kit', 'Espresso Machine Service Kit (gaskets + burrs)', 18500),
    ('rc_apr_prod_blast_chiller', 'Blast Chiller 10-Tray (Central Kitchen)', 245000),
    ('rc_apr_prod_dishwasher', 'Commercial Glass & Dishwasher', 95000),
]


def _equipment_products(env):
    categ = env['product.category'].search([('name', '=', 'Kitchen Equipment & Spares')], limit=1) or _get_or_create(
        env, 'rc_apr_categ_equipment', 'product.category', {'name': 'Kitchen Equipment & Spares'})
    vals = {'type': 'consu', 'sale_ok': False, 'purchase_ok': True, 'categ_id': categ.id}
    if 'available_in_pos' in env['product.template']._fields:
        vals['available_in_pos'] = False
    return {xid: _get_or_create(env, xid, 'product.product', {**vals, 'name': name, 'standard_price': cost})
            for xid, name, cost in EQUIPMENT}


def _approval_requests(env):
    admin, arjun = _users(env)
    _equipment_products(env)
    cats = _approval_categories(env, admin, arjun)
    menu, equip, disc = cats['rc_apr_cat_menu_price'], cats['rc_apr_cat_kitchen_equipment'], cats['rc_apr_cat_event_discount']
    trip, procurement, payment = _std_cat(env, 'Business Trip'), _std_cat(env, 'Procurement'), _std_cat(env, 'Payment Application')
    contract, borrow, general = _std_cat(env, 'Contract Approval'), _std_cat(env, 'Borrow Items'), _std_cat(env, 'General Approval')
    marina = _ref(env, 'rc_partner_marina_events')
    bluewave = _ref(env, 'rc_partner_bluewave')
    harbour = _ref(env, 'rc_partner_harbour_park')
    vendor = env['res.partner'].search([('name', 'ilike', 'Wayanad Highland')], limit=1)

    # xid, category, title, owner, status, days ago, values, product lines [(names, qty, price)], approve-as, note
    specs = [
        ('rc_apr_req_01', menu, 'Raise Kerala Fish Curry Meals to Rs 320', arjun, 'approved', 21,
         {'amount': 320, 'reference': 'MENU-FISH-CURRY', 'description': '<p>Seer fish cost up 18% since August. Current price Rs 280.</p>'}, [], None,
         'Fish cost checked against the Vypeen Harbour invoices. Approved for the November menu.'),
        ('rc_apr_req_02', menu, 'Cardamom Cold Brew price Rs 180 to Rs 210', arjun, 'pending', 3,
         {'amount': 210, 'reference': 'MENU-COLD-BREW', 'description': '<p>New Wayanad estate beans; competitor cafes charge Rs 220-250.</p>'}, [], None, None),
        ('rc_apr_req_03', menu, 'Drop Pasta 4 Formaggi price to Rs 340', admin, 'refused', 15,
         {'amount': 340, 'reference': 'MENU-PASTA-4F', 'description': '<p>Slow seller; proposal to cut price by Rs 40.</p>'}, [], None,
         'Refused: margin would fall below 55%. Try a combo offer with a drink instead.'),
        ('rc_apr_req_04', menu, 'Onam Sadya menu price Rs 450 per leaf', admin, 'draft', 1,
         {'amount': 450, 'reference': 'MENU-ONAM-SADYA'}, [], None, None),
        ('rc_apr_req_05', equip, 'Replace La Marzocco group head gaskets and grinder burrs', arjun, 'approved', 26,
         {'description': '<p>Espresso shots running slow and grinder burrs worn after 14 months.</p>', 'partner_id': vendor.id or False},
         [(('Espresso Machine Service Kit (gaskets + burrs)',), 1, 18500)], admin, 'Approved - schedule with the maintenance team on Monday.'),
        ('rc_apr_req_06', equip, 'Second blast chiller for the Central Kitchen', admin, 'pending', 5,
         {'description': '<p>Catering volume doubled; one chiller cannot cool 40 kg biryani batches within 90 minutes.</p>'},
         [(('Blast Chiller 10-Tray (Central Kitchen)',), 1, 245000)], None, None),
        ('rc_apr_req_07', equip, 'Commercial dishwasher for the Patio bar', arjun, 'cancel', 12,
         {'description': '<p>Patio bar glassware washing.</p>'}, [(('Commercial Glass & Dishwasher',), 1, 95000)], None,
         'Cancelled - the Patio bar will share the main kitchen dishwasher this season.'),
        ('rc_apr_req_08', disc, '15% discount - Marina Bay wedding (450 guests)', arjun, 'approved', 8,
         {'amount': 76050, 'partner_id': marina.id if marina else False, 'date': _ago(-40), 'reference': 'MARINA-WED-450'}, [], admin,
         'Repeat client with 6 weddings this year. 15% approved, valid until 30 days before the event.'),
        ('rc_apr_req_09', disc, '20% discount - BlueWave Christmas party', admin, 'refused', 18,
         {'amount': 11077, 'partner_id': bluewave.id if bluewave else False, 'date': _ago(-38), 'reference': 'BW-XMAS'}, [], arjun,
         'Refused - December is peak season. Offer 10% plus free welcome drinks instead.'),
        ('rc_apr_req_10', disc, '12% discount - Harbour Point retreat BBQ', arjun, 'pending', 2,
         {'amount': 35100, 'partner_id': harbour.id if harbour else False, 'date': _ago(-30), 'reference': 'HPCP-RETREAT'}, [], None, None),
        ('rc_apr_req_11', trip, 'Wayanad coffee estate visit - bean sourcing', arjun, 'approved', 30,
         {'date_start': _ago(-6, 6), 'date_end': _ago(-8, 20), 'location': 'Wayanad Highland Coffee Estates, Kalpetta', 'amount': 14500}, [], admin,
         'Approved. Please bring back cupping notes for the Coffee Bean Club.'),
        ('rc_apr_req_12', procurement, 'Monthly spice stock - Idukki Spice Growers', admin, 'pending', 4,
         {'description': '<p>Pepper, cardamom and clove for December catering season.</p>'},
         [(('Malabar Black Pepper', 'Pepper'), 25, 720), (('Green Cardamom (8 mm bold)', 'Cardamom'), 8, 2800)], None, None),
        ('rc_apr_req_13', payment, 'Advance to Kochi PackRight for Onam packaging', arjun, 'approved', 40,
         {'amount': 60000, 'reference': 'PACK-ONAM-ADV', 'description': '<p>30% advance for 20,000 banana-leaf takeaway boxes.</p>'}, [], admin, None),
        ('rc_apr_req_14', contract, 'Annual fish supply contract - Vypeen Harbour Fresh Catch', admin, 'draft', 0,
         {'reference': 'CONTRACT-FISH-2027', 'description': '<p>12-month fixed-price contract for seer fish, karimeen and prawns.</p>'}, [], None, None),
        ('rc_apr_req_15', borrow, 'Borrow 2 chafing dishes for staff Onam lunch', arjun, 'cancel', 9,
         {'description': '<p>Staff celebration in the Party Hall.</p>'}, [], None, 'Cancelled - rental stock was free, used rental items instead.'),
    ]

    for xid, cat, title, owner, status, days, vals, lines, decider, note in specs:
        if _ref(env, xid) or not cat:
            continue
        approvers = [] if cat.user_ids else [Command.create({'user_id': admin.id, 'sequence': 1, 'required': True})]
        create_vals = {
            'name': title, 'category_id': cat.id, 'request_owner_id': owner.id,
            **{k: v for k, v in vals.items() if v not in (False, None)},
        }
        if approvers:
            create_vals['approver_ids'] = approvers
        if lines:
            create_vals['product_line_ids'] = []
            for names, qty, price in lines:
                prod = _product(env, *names)
                create_vals['product_line_ids'].append(Command.create({
                    'product_id': prod.id, 'product_uom_id': prod.uom_id.id, 'quantity': qty, 'price_unit': price,
                    'description': prod.display_name}))
        req = env['approval.request'].with_user(owner).with_context(mail_create_nosubscribe=True).sudo().create(create_vals)
        _bind(env, xid, req)
        if status == 'draft':
            continue
        req.action_confirm()
        req.date_confirmed = _ago(days)
        if status == 'approved':
            for _i in range(len(req.approver_ids)):  # sequential categories: each approver in turn
                current = req.approver_ids.filtered(lambda a: a.status == 'pending').sorted('sequence')[:1]
                if not current or req.request_status == 'approved':
                    break
                current.with_user(current.user_id).sudo().action_approve()
        elif status == 'refused':
            current = req.approver_ids.filtered(lambda a: a.status == 'pending').sorted('sequence')
            current = current.filtered(lambda a: a.user_id == decider)[:1] or current[:1]
            if current:
                current.with_user(current.user_id).sudo().action_refuse()
        elif status == 'cancel':
            req.action_cancel()
        req.approver_ids.filtered(lambda a: a.date).write({'date': _ago(max(days - 1, 0), 15)})
        if note:
            req.message_post(body=note, message_type='comment', subtype_xmlid='mail.mt_note', author_id=(decider or owner).partner_id.id)


# =========================================================================== PLM
ECO_TYPES = [
    ('rc_plm_type_new_item', 'New Menu Item', 2, 10),
    ('rc_plm_type_recipe', 'Recipe Change', 3, 4),
    ('rc_plm_type_packaging', 'Packaging Change', 4, 7),
]
TAGS = [('rc_plm_tag_cost', 'Cost Reduction', 3), ('rc_plm_tag_health', 'Healthier Recipe', 10),
        ('rc_plm_tag_allergen', 'Allergen / Label', 1), ('rc_plm_tag_supplier', 'Supplier Change', 5)]


def _plm_setup(env, admin, arjun):
    stages = {s: env.ref(f'hudson_plm.eco_stage_{s}', raise_if_not_found=False) for s in ('new', 'in_progress', 'validated', 'effective')}
    if not all(stages.values()):
        stages = dict(zip(('new', 'in_progress', 'validated', 'effective'), env['mrp.eco.stage'].search([], order='sequence, id')[:4]))
    types = {}
    for xid, name, seq, color in ECO_TYPES:
        types[xid] = _get_or_create(env, xid, 'mrp.eco.type', {'name': name, 'sequence': seq, 'color': color})
    for stage in stages.values():
        stage.type_ids = [Command.link(t.id) for t in types.values()]
    # approval roles per stage (only if the stage has none yet)
    Tmpl = env['mrp.eco.approval.template'].sudo()
    if not _ref(env, 'rc_plm_appr_head_chef'):
        _bind(env, 'rc_plm_appr_head_chef', Tmpl.create({'stage_id': stages['in_progress'].id, 'name': 'Head Chef',
                                                         'user_ids': [Command.set(admin.ids)], 'approval_type': 'mandatory'}))
    if not _ref(env, 'rc_plm_appr_food_safety'):
        _bind(env, 'rc_plm_appr_food_safety', Tmpl.create({'stage_id': stages['validated'].id, 'name': 'Food Safety Officer',
                                                           'user_ids': [Command.set(arjun.ids)], 'approval_type': 'mandatory'}))
    if not _ref(env, 'rc_plm_appr_cost'):
        _bind(env, 'rc_plm_appr_cost', Tmpl.create({'stage_id': stages['validated'].id, 'name': 'Cost Controller',
                                                    'user_ids': [Command.set(admin.ids)], 'approval_type': 'optional'}))
    tags = {xid: _get_or_create(env, xid, 'mrp.eco.tag', {'name': name, 'color': color}) for xid, name, color in TAGS}
    return stages, types, tags


def _bom(env, product_name):
    tmpl = env['product.template'].search([('name', '=', product_name)], limit=1)
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', tmpl.id)], order='version desc, id', limit=1) if tmpl else env['mrp.bom']
    return tmpl, bom


def _line(bom, component):
    return bom.bom_line_ids.filtered(lambda l: l.product_id.name == component)[:1]


# xid, title, type xid, product, kind(bom/product), target stage, outcome, tags, days ago, urgent, note, change(fn on new bom)
def _eco_specs(env):
    def scale(component, factor):
        def change(new_bom):
            line = _line(new_bom, component)
            if line:
                line.product_qty = round(line.product_qty * factor, 4)
        return change

    def several(*changes):
        def change(new_bom):
            for c in changes:
                c(new_bom)
        return change

    def add(component_names, qty):
        def change(new_bom):
            prod = _product(env, *component_names, fallback=False)
            if prod and not _line(new_bom, prod.name):
                new_bom.bom_line_ids = [Command.create({'product_id': prod.id, 'product_qty': qty, 'uom_id': prod.uom_id.id})]
        return change

    return [
        ('rc_plm_eco_tiramisu', 'Tiramisu - 25% less sugar', 'rc_plm_type_recipe', 'Tiramisu', 'bom', 'effective', 'approved',
         ['rc_plm_tag_health'], 34, False, 'Guests asked for a lighter dessert. Tasting panel approved 25% less sugar with no texture loss.',
         scale('Sugar', 0.75)),
        ('rc_plm_eco_apple_pie', 'Warm Apple Pie - more apple, less sugar', 'rc_plm_type_recipe', 'Warm Apple Pie', 'bom', 'effective', 'approved',
         ['rc_plm_tag_health'], 22, False, 'Fresh Himachal apples are sweeter this season: 20% more apple and 25% less sugar.',
         several(scale('Apples', 1.2), scale('Sugar', 0.75))),
        ('rc_plm_eco_burger_bun', 'Cheese Burger - double cheddar', 'rc_plm_type_recipe', 'Cheese Burger', 'bom', 'validated', 'approved',
         ['rc_plm_tag_allergen'], 9, False, 'Second cheddar slice after guest feedback. Head Chef approved; waiting for Food Safety sign-off on the dairy allergen label.',
         scale('Cheddar Slice', 2.0)),
        ('rc_plm_eco_pasta', 'Pasta Bolognese - reduce minced beef to 100 g', 'rc_plm_type_recipe', 'Pasta Bolognese', 'bom', 'in_progress', 'rejected',
         ['rc_plm_tag_cost'], 12, False, 'Cost reduction proposal: portion of beef from 120 g to 100 g.',
         scale('Minced Beef', 0.83)),
        ('rc_plm_eco_milkshake', 'Banana Milkshake Lite (half ice cream)', 'rc_plm_type_new_item', 'Milkshake Banana', 'bom', 'in_progress', 'pending',
         ['rc_plm_tag_health'], 4, True, 'Lighter version for the gym crowd from Nest Coworking: more banana, half the ice cream.',
         several(scale('Bananas', 1.3), scale('Vanilla Ice Cream', 0.5))),
        ('rc_plm_eco_pizza_kerala', 'New: Malabar Chicken Pizza (Kerala style)', 'rc_plm_type_new_item', 'Pizza Margherita', 'bom', 'new', 'pending',
         [], 2, False, 'Margherita base with Malabar chicken roast, curry leaves and shallots. Trial for the Onam special menu.',
         add(('Chicken Breast',), 0.12)),
        ('rc_plm_eco_lava_label', 'Chocolate Lava Cake - allergen label update', 'rc_plm_type_packaging', 'Chocolate Lava Cake', 'product', 'new', 'pending',
         ['rc_plm_tag_allergen'], 1, True, 'Add "Contains: egg, milk, gluten; may contain nuts" to the takeaway sticker (FSSAI labelling).', None),
        ('rc_plm_eco_club_box', 'Club Sandwich - compostable bagasse box', 'rc_plm_type_packaging', 'Club Sandwich', 'bom', 'effective', 'approved',
         ['rc_plm_tag_supplier'], 28, False, 'Replace plastic clamshell with a compostable bagasse box from Kochi PackRight.',
         add(('Takeaway Food Box',), 1.0)),
    ]


def _advance(eco, target_key, stages, admin, arjun):
    """Move an ECO stage by stage, granting the stage approvals on the way (as the real approvers)."""
    order = ['new', 'in_progress', 'validated', 'effective']
    for key in order[order.index(next(k for k, s in stages.items() if s == eco.stage_id)) + 1: order.index(target_key) + 1]:
        for approval in eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id and a.status == 'none'):
            user = approval.approval_template_id.user_ids[:1]
            approval.with_user(user).sudo().action_approve()
        eco.write({'stage_id': stages[key].id})


def _ecos(env):
    admin, arjun = _users(env)
    stages, types, tags = _plm_setup(env, admin, arjun)
    for xid, title, type_xid, product, kind, target, outcome, tag_xids, days, urgent, note, change in _eco_specs(env):
        if _ref(env, xid):
            continue
        tmpl, bom = _bom(env, product)
        if not tmpl or (kind == 'bom' and not bom):
            continue
        eco = env['mrp.eco'].with_context(mail_create_nosubscribe=True).create({
            'name': title, 'type_id': types[type_xid].id, 'type': kind, 'product_tmpl_id': tmpl.id,
            'bom_id': bom.id if kind == 'bom' else False, 'user_id': (arjun if days % 2 else admin).id,
            'priority': '1' if urgent else '0', 'tag_ids': [Command.set([tags[t].id for t in tag_xids])],
            'note': f'<p>{note}</p>', 'effectivity': 'asap' if target != 'validated' else 'date',
            **({'effectivity_date': _ago(-7)} if target == 'validated' else {}),
        })
        _bind(env, xid, eco)
        if kind == 'bom' and target != 'new':
            eco.action_start_revision()
            if change:
                change(eco.new_bom_id)
        if target != 'new':
            _advance(eco, target if outcome != 'rejected' else 'in_progress', stages, admin, arjun)
        if outcome == 'rejected':
            approval = eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id and a.status == 'none')[:1]
            if approval:
                approval.with_user(approval.approval_template_id.user_ids[:1]).sudo().action_reject()
                eco.message_post(body='Head Chef: 100 g looks too small on the plate. Keep 120 g and find savings elsewhere.',
                                 message_type='comment', subtype_xmlid='mail.mt_note', author_id=admin.partner_id.id)
        if eco.date_done:
            eco.date_done = _ago(max(days - 6, 0), 17)


# =========================================================================== entry point
def load_approvals_plm_suite_demo_data(env):
    if 'approval.request' in env:
        try:
            with env.cr.savepoint():
                _approval_requests(env)
        except Exception as e:
            _logger.exception("Hudson POS: Approvals demo data failed: %s", e)
    if 'mrp.eco' in env:
        try:
            with env.cr.savepoint():
                _ecos(env)
        except Exception as e:
            _logger.exception("Hudson POS: PLM demo data failed: %s", e)
    _logger.info("Hudson POS: Resto Cafe Approvals & PLM demo data loaded.")
