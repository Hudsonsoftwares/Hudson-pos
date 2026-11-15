# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Manufacturing & Shop Floor demo data (central kitchen / bakery).

Creates, idempotently (records bound to xmlids of this module, prefix rc_mrp_):
  * 7 kitchen work centers (hot kitchen, grill, pizza oven, pastry, cold kitchen & sushi, beverage bar,
    packing & dispatch) with hourly costs, efficiency, OEE targets, setup/clean-up times
  * Operations (routings) on the 18 Resto Cafe bills of materials created by the Inventory suite
  * 14 manufacturing orders: draft, confirmed (ready and waiting for components), in progress with
    operators timing work orders live on the Shop Floor, paused, to close, done (with time logs,
    consumed components and backdated dates) and cancelled
  * A closed "Equipment Failure" downtime on the pizza oven, so OEE / losses reports show data
"""
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


# --------------------------------------------------------------------------- helpers
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


def _now():
    return fields.Datetime.now().replace(second=0, microsecond=0)


def _employee(env, name):
    return env['hr.employee'].sudo().search([('name', '=', name)], limit=1) if 'hr.employee' in env else False


# --------------------------------------------------------------------------- work centers
# xid slug, name, code, cost/h, efficiency %, OEE target, setup min, clean-up min, color
WORKCENTERS = [
    ('hot_kitchen', 'Hot Kitchen Line', 'HOT', 22.0, 100, 85, 10, 15, 1),
    ('grill', 'Grill & Burger Station', 'GRL', 18.0, 105, 85, 5, 10, 2),
    ('pizza_oven', 'Pizza Stone Oven', 'PZA', 20.0, 100, 80, 15, 10, 3),
    ('pastry', 'Pastry & Dessert Station', 'PST', 16.0, 95, 85, 10, 10, 4),
    ('cold_kitchen', 'Cold Kitchen & Sushi Bar', 'CLD', 17.0, 100, 85, 5, 10, 5),
    ('beverage', 'Beverage & Coffee Bar', 'BEV', 12.0, 110, 90, 2, 5, 6),
    ('packing', 'Packing & Dispatch', 'PCK', 10.0, 100, 90, 0, 5, 7),
]

# product name -> [(operation, workcenter slug, minutes per unit)]
ROUTINGS = {
    'Cheese Burger': [('Grill patties', 'grill', 6), ('Assemble burger', 'grill', 2), ('Box & label', 'packing', 1)],
    'Bacon Burger': [('Grill patties & bacon', 'grill', 7), ('Assemble burger', 'grill', 2), ('Box & label', 'packing', 1)],
    'Pizza Margherita': [('Stretch dough & top', 'pizza_oven', 3), ('Bake in stone oven', 'pizza_oven', 6), ('Cut & box', 'packing', 1)],
    'Pizza Vegetarian': [('Stretch dough & top', 'pizza_oven', 4), ('Bake in stone oven', 'pizza_oven', 6), ('Cut & box', 'packing', 1)],
    'Pasta Bolognese': [('Cook pasta & ragu', 'hot_kitchen', 8), ('Portion & pack', 'packing', 1)],
    'Pasta 4 Formaggi': [('Cook pasta & cheese sauce', 'hot_kitchen', 7), ('Portion & pack', 'packing', 1)],
    'Club Sandwich': [('Prepare fillings', 'cold_kitchen', 4), ('Assemble & toast', 'grill', 3), ('Wrap & label', 'packing', 1)],
    'Spicy Tuna Sandwich': [('Prepare tuna mix', 'cold_kitchen', 3), ('Assemble & toast', 'grill', 2), ('Wrap & label', 'packing', 1)],
    'Lunch Maki 18pc': [('Cook & season sushi rice', 'cold_kitchen', 4), ('Roll & cut maki', 'cold_kitchen', 6), ('Box & label', 'packing', 1)],
    'Salmon and Avocado': [('Cook & season sushi rice', 'cold_kitchen', 3), ('Roll & cut', 'cold_kitchen', 5), ('Box & label', 'packing', 1)],
    'Espresso': [('Grind & pull shot', 'beverage', 1)],
    'Green Tea': [('Steep tea', 'beverage', 2)],
    'Milkshake Banana': [('Blend milkshake', 'beverage', 2), ('Cap & label', 'packing', 1)],
    'Tiramisu': [('Whip mascarpone cream', 'pastry', 3), ('Layer & set', 'pastry', 4), ('Portion & pack', 'packing', 1)],
    'New York Cheesecake': [('Mix & bake cheesecake', 'pastry', 6), ('Chill & portion', 'pastry', 2), ('Pack', 'packing', 1)],
    'Chocolate Lava Cake': [('Mix batter & fill moulds', 'pastry', 3), ('Bake', 'pastry', 4), ('Pack', 'packing', 1)],
    'Warm Apple Pie': [('Make pastry & filling', 'pastry', 5), ('Bake pie', 'pastry', 6), ('Slice & pack', 'packing', 1)],
    'Vanilla Bean Ice Cream Sundae': [('Assemble sundae', 'pastry', 2)],
}


def _enable_routings(env):
    user_group = env.ref('base.group_user')
    group = env.ref('mrp.group_mrp_routings', raise_if_not_found=False)
    if group and group not in user_group.implied_ids:
        user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _workcenters(env):
    res = {}
    for seq, (slug, name, code, cost, eff, oee, setup, clean, color) in enumerate(WORKCENTERS, start=1):
        xid = f'rc_mrp_wc_{slug}'
        existing = _ref(env, xid) or env['mrp.workcenter'].sudo().search([('name', '=', name)], limit=1)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing)
        res[slug] = existing or _get_or_create(env, xid, 'mrp.workcenter', {
            'name': name, 'code': code, 'costs_hour': cost, 'time_efficiency': eff, 'oee_target': oee,
            'time_start': setup, 'time_stop': clean, 'color': color, 'sequence': seq,
        })
    # the grill can take over sandwiches when the hot kitchen is overloaded, and vice versa
    if not res['grill'].alternative_workcenter_ids:
        res['grill'].alternative_workcenter_ids = [Command.set(res['hot_kitchen'].ids)]
        res['hot_kitchen'].alternative_workcenter_ids = [Command.set(res['grill'].ids)]
    return res


def _routings(env, wcs):
    boms = {}
    for bom in env['mrp.bom'].sudo().search([('type', '=', 'normal')]):
        name = bom.product_tmpl_id.name
        if name not in ROUTINGS or name in boms:
            continue
        boms[name] = bom
        if bom.operation_ids:
            continue
        bom.write({'operation_ids': [Command.create({
            'name': op, 'workcenter_id': wcs[slug].id, 'time_cycle_manual': minutes, 'time_mode': 'manual', 'sequence': seq * 10,
        }) for seq, (op, slug, minutes) in enumerate(ROUTINGS[name], start=1)]})
        # consume each component at the first operation that uses the station preparing it
        first_op = bom.operation_ids.sorted('sequence')[:1]
        bom.bom_line_ids.filtered(lambda l: not l.operation_id).write({'operation_id': first_op.id})
    return boms


# --------------------------------------------------------------------------- manufacturing orders
# xid, product, qty, state, start offset in days (negative = past), origin, operator(s)
ORDERS = [
    ('rc_mrp_mo_tiramisu_done', 'Tiramisu', 30, 'done', -27, 'Weekend dessert counter', ['Ananya Sharma']),
    ('rc_mrp_mo_burger_done', 'Cheese Burger', 40, 'done', -21, 'BlueWave team lunch', ['Vishnu Kumar']),
    ('rc_mrp_mo_pizza_done', 'Pizza Margherita', 25, 'done', -14, 'Film Society screening night', ['Vishnu Kumar', 'Rahul Nair']),
    ('rc_mrp_mo_lava_done', 'Chocolate Lava Cake', 24, 'done', -7, 'POS restock - desserts', ['Ananya Sharma']),
    ('rc_mrp_mo_maki_done', 'Lunch Maki 18pc', 15, 'done', -3, 'Nest Coworking lunch boxes', ['Rahul Nair']),
    ('rc_mrp_mo_club_to_close', 'Club Sandwich', 30, 'to_close', -1, 'Harbour Point meeting platters', ['Vishnu Kumar']),
    ('rc_mrp_mo_bolognese_progress', 'Pasta Bolognese', 20, 'progress', 0, 'Corporate lunch run', ['Vishnu Kumar']),
    ('rc_mrp_mo_cheesecake_progress', 'New York Cheesecake', 16, 'progress', 0, 'POS restock - desserts', ['Ananya Sharma']),
    ('rc_mrp_mo_veg_pizza_paused', 'Pizza Vegetarian', 20, 'paused', 0, 'Evening takeaway prep', ['Rahul Nair']),
    ('rc_mrp_mo_bacon_ready', 'Bacon Burger', 35, 'confirmed', 1, 'Coastal Runners post-race meal', []),
    ('rc_mrp_mo_apple_pie_ready', 'Warm Apple Pie', 24, 'confirmed', 2, 'Weekend dessert counter', []),
    ('rc_mrp_mo_salmon_waiting', 'Salmon and Avocado', 40, 'waiting', 3, 'Marina Bay wedding canapes', []),
    ('rc_mrp_mo_milkshake_draft', 'Milkshake Banana', 50, 'draft', 5, "St. Teresa's annual day", []),
    ('rc_mrp_mo_green_tea_cancel', 'Green Tea', 30, 'cancel', -10, 'Yoga studio event (cancelled)', []),
]


def _top_up_components(env, mo, factor=1.5):
    """Make sure the MO's components are in stock (the kitchen received its morning delivery)."""
    location = mo.location_src_id
    Quant = env['stock.quant'].sudo()
    for move in mo.move_raw_ids:
        product = move.product_id
        if not product.is_storable:
            continue
        need = move.product_uom_qty * factor
        available = product.with_context(location=location.id).qty_available
        if available < need:
            Quant._update_available_quantity(product, location, need - available)


def _log_time(env, wo, start, minutes, employee, closed=True):
    vals = wo._prepare_timeline_vals(minutes, start, start + timedelta(minutes=minutes) if closed else False,
                                     employee_id=employee.id if employee else None)
    vals['user_id'] = env.ref('base.user_admin').id
    if employee:
        vals['employee_id'] = employee.id
    return env['mrp.workcenter.productivity'].sudo().create(vals)


def _create_mo(env, spec, boms):
    xid, product_name, qty, state, offset, origin, operators = spec
    if _ref(env, xid):
        return
    bom = boms.get(product_name)
    if not bom:
        return
    product = bom.product_tmpl_id.product_variant_ids[:1]
    start = (_now() + timedelta(days=offset)).replace(hour=7 if offset <= 0 else 8, minute=0)
    employees = [e for e in (_employee(env, n) for n in operators) if e]
    mo = env['mrp.production'].sudo().create({
        'product_id': product.id, 'bom_id': bom.id, 'product_qty': qty, 'origin': origin,
        'date_start': start, 'user_id': env.ref('base.user_admin').id,
        'priority': '1' if state in ('progress', 'waiting') else '0',
    })
    _bind(env, xid, mo)
    if state == 'draft':
        return
    if state != 'waiting':
        _top_up_components(env, mo)
    mo.action_confirm()
    if state == 'cancel':
        mo.action_cancel()
        return
    mo.action_assign()
    if state in ('confirmed', 'waiting'):
        return

    workorders = mo.workorder_ids.sorted('sequence')
    emp = employees[0] if employees else False
    if state in ('done', 'to_close'):
        mo.qty_producing = qty
        mo.set_qty_producing()
        cursor = start
        for i, wo in enumerate(workorders):
            operator = employees[i % len(employees)] if employees else False
            minutes = max(5, round(wo.duration_expected * (0.9 + 0.05 * i)))
            _log_time(env, wo, cursor, minutes, operator)
            wo.button_finish()
            wo.write({'date_start': cursor, 'date_finished': cursor + timedelta(minutes=minutes)})
            cursor += timedelta(minutes=minutes + 5)
        if state == 'done':
            mo.with_context(skip_consumption=True, skip_backorder=True).button_mark_done()
            mo.with_context(force_date=True).write({'date_start': start, 'date_finished': cursor})
            (mo.move_raw_ids | mo.move_finished_ids).filtered(lambda m: m.state == 'done').write({'date': cursor})
            (mo.move_raw_ids | mo.move_finished_ids).move_line_ids.write({'date': cursor})
        return

    # in progress / paused: first operation done earlier this morning, the next one is running
    first, rest = workorders[:1], workorders[1:]
    if rest:
        mo.qty_producing = qty
        mo.set_qty_producing()
        minutes = max(5, round(first.duration_expected))
        _log_time(env, first, start, minutes, emp)
        first.button_finish()
        first.write({'date_start': start, 'date_finished': start + timedelta(minutes=minutes)})
        current = rest[:1]
    else:
        current = first
    if state == 'progress':
        current.with_context(sf_employee_id=emp.id if emp else False).button_start()
        running = current.time_ids.filtered(lambda t: not t.date_end)
        running.write({'date_start': _now() - timedelta(minutes=25), 'employee_id': emp.id if emp else False,
                       'user_id': env.ref('base.user_admin').id})
    else:  # paused: operator logged 20 minutes then stopped for a break
        current.button_start()
        current.time_ids.filtered(lambda t: not t.date_end)._close()
        current.time_ids.write({'date_start': _now() - timedelta(minutes=60), 'date_end': _now() - timedelta(minutes=40),
                                'employee_id': emp.id if emp else False, 'user_id': env.ref('base.user_admin').id})


def _downtime(env, wcs):
    if _ref(env, 'rc_mrp_loss_pizza_oven'):
        return
    loss = env['mrp.workcenter.productivity.loss'].sudo().search([('loss_type', '=', 'availability'), ('name', 'ilike', 'Equipment')], limit=1)
    if not loss:
        return
    start = (_now() - timedelta(days=6)).replace(hour=11, minute=10)
    line = env['mrp.workcenter.productivity'].sudo().create({
        'workcenter_id': wcs['pizza_oven'].id, 'loss_id': loss.id, 'user_id': env.ref('base.user_admin').id,
        'description': 'Stone oven burner ignition failure - technician called',
        'date_start': start, 'date_end': start + timedelta(minutes=45),
    })
    _bind(env, 'rc_mrp_loss_pizza_oven', line)


# --------------------------------------------------------------------------- entry point
def load_mrp_suite_demo_data(env):
    if 'mrp.production' not in env:
        _logger.info("Hudson POS: Manufacturing not installed, skipping MRP demo data.")
        return
    ctx = {}
    for name, step in (
        ('routings group', lambda: _enable_routings(env)),
        ('work centers', lambda: ctx.update(wcs=_workcenters(env))),
        ('operations', lambda: ctx.update(boms=_routings(env, ctx['wcs']))),
        ('downtime', lambda: _downtime(env, ctx['wcs'])),
    ):
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: MRP demo step '%s' failed: %s", name, e)
            if name in ('work centers', 'operations'):
                return
    for spec in ORDERS:
        try:
            with env.cr.savepoint():
                _create_mo(env, spec, ctx['boms'])
        except Exception as e:
            _logger.exception("Hudson POS: MRP demo order %s failed: %s", spec[0], e)
    _logger.info("Hudson POS: Resto Cafe Manufacturing & Shop Floor demo data loaded.")
