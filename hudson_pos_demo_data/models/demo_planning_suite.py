# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Planning demo data (hudson_planning: fs.planning.*).

Creates, idempotently (every record is bound to an xmlid of this module, prefix ``rc_plan_``):
  * Restaurant roles (Chef, Sous Chef, Barista, Waiter, Cashier, Delivery Rider, Kitchen Helper,
    Event Staff) with colours and the employees able to do them
  * Shift templates: Morning, Evening, Lunch / Dinner split peaks, Event shift
  * ~55 shifts for the restaurant team over last week, this week and next week
    (published past/current weeks, draft shifts next week, open shifts without employee)
  * Event-staff shifts on the confirmed / quoted catering orders of the Sales demo
    (rc_so_* records, used only when they exist)
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
TZ = pytz.timezone('Asia/Kolkata')

ROLES = [
    # xid, name, color, employees (by name)
    ('rc_plan_role_chef', 'Chef', 1, ['Rahul Nair', 'Ananya Sharma']),
    ('rc_plan_role_sous_chef', 'Sous Chef', 2, ['Ananya Sharma', 'Vishnu Kumar']),
    ('rc_plan_role_barista', 'Barista', 3, ['Priya Menon']),
    ('rc_plan_role_waiter', 'Waiter', 4, ['Mohammed Bilal', 'Sneha Pillai']),
    ('rc_plan_role_cashier', 'Cashier', 5, ['Sneha Pillai']),
    ('rc_plan_role_rider', 'Delivery Rider', 6, ['Arun Varma', 'Kevin Joseph']),
    ('rc_plan_role_helper', 'Kitchen Helper', 7, ['Vishnu Kumar']),
    ('rc_plan_role_event', 'Event Staff', 10, ['Mohammed Bilal', 'Kevin Joseph', 'Suresh Kumar']),
]
DEFAULT_ROLE = {
    'Rahul Nair': 'rc_plan_role_chef', 'Ananya Sharma': 'rc_plan_role_sous_chef', 'Vishnu Kumar': 'rc_plan_role_helper',
    'Priya Menon': 'rc_plan_role_barista', 'Mohammed Bilal': 'rc_plan_role_waiter', 'Sneha Pillai': 'rc_plan_role_cashier',
    'Arun Varma': 'rc_plan_role_rider', 'Kevin Joseph': 'rc_plan_role_rider', 'Suresh Kumar': 'rc_plan_role_event',
}
TEMPLATES = [
    # xid, name, start, end, role xid
    ('rc_plan_tmpl_morning', 'Morning Shift', 7.0, 15.0, False),
    ('rc_plan_tmpl_evening', 'Evening Shift', 15.0, 23.0, False),
    ('rc_plan_tmpl_lunch', 'Split - Lunch Peak', 11.0, 15.0, False),
    ('rc_plan_tmpl_dinner', 'Split - Dinner Peak', 18.0, 22.0, False),
    ('rc_plan_tmpl_event', 'Event Shift', 16.0, 23.0, 'rc_plan_role_event'),
]
# shift kind -> (start hour, end hour, break hours, template xid)
KINDS = {
    'morning': (7, 15, 1.0, 'rc_plan_tmpl_morning'),
    'evening': (15, 23, 1.0, 'rc_plan_tmpl_evening'),
    'lunch': (11, 15, 0.0, 'rc_plan_tmpl_lunch'),
    'dinner': (18, 22, 0.0, 'rc_plan_tmpl_dinner'),
    'event': (16, 23, 0.5, 'rc_plan_tmpl_event'),
}
# daily rotation: (employee, role xid, kind), cycled by day index
KITCHEN = [('Rahul Nair', 'rc_plan_role_chef', 'morning'), ('Ananya Sharma', 'rc_plan_role_sous_chef', 'evening')]
FRONT = [('Priya Menon', 'rc_plan_role_barista', 'morning'), ('Mohammed Bilal', 'rc_plan_role_waiter', 'evening'),
         ('Sneha Pillai', 'rc_plan_role_cashier', 'morning')]
SUPPORT = [('Arun Varma', 'rc_plan_role_rider', 'evening'), ('Vishnu Kumar', 'rc_plan_role_helper', 'lunch'),
           ('Kevin Joseph', 'rc_plan_role_rider', 'dinner')]
# open shifts next week: (day offset from next Monday, role xid, kind, note)
OPEN_SHIFTS = [
    (4, 'rc_plan_role_waiter', 'dinner', 'Friday dinner rush - extra waiter needed.'),
    (5, 'rc_plan_role_event', 'event', 'Saturday Party Hall booking - event staff needed.'),
    (5, 'rc_plan_role_barista', 'lunch', 'Weekend brunch - second barista.'),
]
# catering orders of the Sales demo: (order xid, staff employees, open slots)
EVENT_ORDERS = [
    ('rc_so_wedding_welcome', ['Mohammed Bilal', 'Kevin Joseph'], 1),
    ('rc_so_birthday_priya', ['Mohammed Bilal'], 0),
    ('rc_so_wedding_marina', [], 2),
    ('rc_so_retreat_bbq', [], 1),
]


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
    return _bind(env, xid, env[model].sudo().with_context(tracking_disable=True).create(vals))


def _utc(day, hour):
    """Local Kochi date + hour -> naive UTC datetime (how Odoo stores datetimes)."""
    local = TZ.localize(datetime.combine(day, time(int(hour), int(round((hour % 1) * 60)))))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def _employees(env):
    names = {n for _x, _n, _c, emps in ROLES for n in emps}
    return {e.name: e for e in env['hr.employee'].sudo().search([('name', 'in', list(names))])}


def _roles(env, employees):
    roles = {}
    for xid, name, color, emp_names in ROLES:
        role = _ref(env, xid) or env['fs.planning.role'].sudo().search([('name', '=', name)], limit=1)
        if role and not _ref(env, xid):
            _bind(env, xid, role)
        role = role or _get_or_create(env, xid, 'fs.planning.role', {'name': name, 'color': color, 'sequence': color})
        staff = [employees[n].id for n in emp_names if n in employees]
        if staff:
            role.resource_ids = [Command.link(i) for i in staff]
        roles[xid] = role
    for emp_name, role_xid in DEFAULT_ROLE.items():
        emp = employees.get(emp_name)
        if emp and not emp.default_planning_role_id:
            emp.default_planning_role_id = roles[role_xid]
    return roles


def _templates(env, roles):
    res = {}
    for seq, (xid, name, start, end, role_xid) in enumerate(TEMPLATES, start=1):
        vals = {'name': name, 'start_time': start, 'end_time': end, 'sequence': seq}
        if role_xid:
            vals['role_id'] = roles[role_xid].id
        res[xid] = _get_or_create(env, xid, 'fs.shift.template', vals)
    return res


def _slot_vals(day, kind, role, templates, employee=None, name=None, state='published'):
    start, end, brk, tmpl_xid = KINDS[kind]
    vals = {
        'date_start': _utc(day, start), 'date_end': _utc(day, end), 'break_hours': brk,
        'role_id': role.id, 'shift_template_id': templates[tmpl_xid].id, 'state': state,
    }
    if employee:
        vals['resource_id'] = employee.id
    if name:
        vals['name'] = name
    return vals


def _shifts(env, employees, roles, templates):
    today = fields.Date.context_today(env['fs.planning.slot'].with_context(tz=TZ.zone))
    this_monday = today - timedelta(days=today.weekday())
    first = this_monday - timedelta(days=7)
    created = 0
    for i in range(21):
        day = first + timedelta(days=i)
        if day.weekday() == 6:  # Sunday: restaurant runs the weekend crew below
            continue
        week = i // 7  # 0 last week, 1 this week, 2 next week
        state = 'draft' if week == 2 and day.weekday() >= 3 else 'published'
        for slot_no, (emp_name, role_xid, kind) in enumerate(
                (KITCHEN[i % len(KITCHEN)], FRONT[i % len(FRONT)], SUPPORT[i % len(SUPPORT)]), start=1):
            xid = f'rc_plan_slot_{i:02d}_{slot_no}'
            if _ref(env, xid) or emp_name not in employees:
                continue
            _get_or_create(env, xid, 'fs.planning.slot',
                           _slot_vals(day, kind, roles[role_xid], templates, employees[emp_name], state=state))
            created += 1
    next_monday = this_monday + timedelta(days=7)
    for n, (offset, role_xid, kind, note) in enumerate(OPEN_SHIFTS, start=1):
        xid = f'rc_plan_open_{n}'
        if not _ref(env, xid):
            vals = _slot_vals(next_monday + timedelta(days=offset), kind, roles[role_xid], templates, state='published')
            vals['note'] = note
            _get_or_create(env, xid, 'fs.planning.slot', vals)
            created += 1
    return created


def _event_shifts(env, employees, roles, templates):
    created = 0
    for order_xid, staff, open_count in EVENT_ORDERS:
        order = _ref(env, order_xid)
        if not order or order.state == 'cancel':
            continue
        event_dt = order.commitment_date or order.date_order
        local_day = pytz.utc.localize(event_dt).astimezone(TZ).date()
        confirmed = order.state == 'sale'
        people = [employees[n] for n in staff if n in employees] + [None] * open_count
        for n, emp in enumerate(people, start=1):
            xid = f'rc_plan_event_{order_xid[3:]}_{n}'
            if _ref(env, xid):
                continue
            vals = _slot_vals(local_day, 'event', roles['rc_plan_role_event'], templates, emp,
                              name=f'Catering: {order.client_order_ref or order.name}',
                              state='published' if confirmed else 'draft')
            vals.update({'sale_order_id': order.id, 'partner_id': order.partner_id.id,
                         'note': 'Tentative - quotation not confirmed yet.' if not confirmed else
                         'Load the catering van 2 hours before; uniform: black with gold apron.'})
            _get_or_create(env, xid, 'fs.planning.slot', vals)
            created += 1
    return created


def load_planning_suite_demo_data(env):
    if 'fs.planning.slot' not in env:
        _logger.info("Hudson POS: Planning (hudson_planning) not installed, skipping Planning demo data.")
        return
    ctx = {}
    steps = [
        ('employees', lambda: ctx.update(employees=_employees(env))),
        ('roles', lambda: ctx.update(roles=_roles(env, ctx['employees']))),
        ('templates', lambda: ctx.update(templates=_templates(env, ctx['roles']))),
        ('shifts', lambda: _shifts(env, ctx['employees'], ctx['roles'], ctx['templates'])),
        ('event shifts', lambda: _event_shifts(env, ctx['employees'], ctx['roles'], ctx['templates'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Planning demo step '%s' failed: %s", name, e)
            if name in ('employees', 'roles', 'templates'):
                return
    _logger.info("Hudson POS: Resto Cafe Planning demo data loaded.")
