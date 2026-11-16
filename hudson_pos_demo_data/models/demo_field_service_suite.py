# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Field Service demo data (hudson_field_service), linked to Project,
Timesheets and Planning.

Resto Cafe sells and maintains coffee machines / hot-holding equipment for its corporate catering
clients (an AMC - annual maintenance contract) and sends technicians on site for event set-ups and
for its own outlet repairs. Created idempotently (xmlids prefixed ``rc_fs_``):

  * 2 field technicians (employee + internal user, Field Technician / Electrician planning roles)
  * A "Coffee Equipment AMC & Field Service" project (timesheets on) with one task per client
  * Customer equipment under contract, field service tags, materials (catering van, kits),
    spare-part products
  * 9 field service orders in every state, each linked to a project task:
      - AMC visits, a breakdown repair and a new installation (AMC project)
      - the live-counter set-up of the Marina Bay wedding (Marina Bay Wedding project / sale order)
      - rooftop lighting wiring (Rooftop Garden Lounge Renovation project)
      - KDS power adapter & patio Wi-Fi (Service Recovery & IT Fixes project, from Helpdesk)
  * Planning: every scheduled job is mirrored as a shift of its technicians (by the module itself)
  * Timesheets: the time of finished jobs is logged on the job AND on its project task, so the
    hours show in Project > Timesheets and on the task's effective hours
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
TZ = pytz.timezone('Asia/Kolkata')
CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_auto_subscribe_no_notify': True, 'no_reset_password': True, 'mail_notify_noemail': True}

TECHNICIANS = [
    # xid, name, job title, login, default role xid, other role xid
    ('rc_fs_tech_anil', 'Anil Raj', 'Coffee & Kitchen Equipment Technician', 'anil.raj',
     'hudson_planning.fs_planning_role_technician', 'hudson_planning.fs_planning_role_electrician'),
    ('rc_fs_tech_deepak', 'Deepak Menon', 'Maintenance Electrician', 'deepak.menon',
     'hudson_planning.fs_planning_role_electrician', 'hudson_planning.fs_planning_role_technician'),
]
TAGS = [('rc_fs_tag_amc', 'AMC Visit', 10), ('rc_fs_tag_breakdown', 'Breakdown', 1), ('rc_fs_tag_install', 'Installation', 4),
        ('rc_fs_tag_event', 'Event Set-up', 3), ('rc_fs_tag_electrical', 'Electrical', 2), ('rc_fs_tag_internal', 'Own Outlet', 7)]
MATERIALS = [('rc_fs_mat_van', 'Catering Van KL-07-CD-4521', 6), ('rc_fs_mat_counter_kit', 'Live Counter Kit (2 induction + 1 tawa)', 3),
             ('rc_fs_mat_service_kit', 'Coffee Machine Service Kit', 4), ('rc_fs_mat_ladder', 'Ladder & Electrical Tool Kit', 2)]
PARTS = [  # xid, name, price, cost, default code
    ('rc_fs_part_gasket', 'Group Head Gasket & Shower Screen Set', 1450.0, 820.0, 'FS-GASKET'),
    ('rc_fs_part_descaler', 'Espresso Machine Descaling Solution (1 L)', 650.0, 310.0, 'FS-DESCALE'),
    ('rc_fs_part_filter', 'Water Softener Filter Cartridge', 2200.0, 1350.0, 'FS-FILTER'),
    ('rc_fs_part_pump', 'Vibration Pump 230 V (bean-to-cup)', 3800.0, 2400.0, 'FS-PUMP'),
    ('rc_fs_part_thermostat', 'Bain-Marie Thermostat 30-110 °C', 1250.0, 700.0, 'FS-THERMO'),
]
# AMC project tasks: xid, name, customer, allocated hours, stage keyword
AMC_TASKS = [
    ('rc_fs_task_nest', 'Nest Coworking - espresso machine AMC (quarterly visits)', 'Nest Coworking Spaces', 10.0, 'progress'),
    ('rc_fs_task_bluewave', 'BlueWave Technologies - bean-to-cup machine AMC', 'BlueWave Technologies', 8.0, 'progress'),
    ('rc_fs_task_greenleaf', 'GreenLeaf Hospital - cafeteria hot-holding equipment checks', 'GreenLeaf Multispecialty Hospital', 6.0, 'to do'),
    ('rc_fs_task_spice', 'Spice Route Travels - new office coffee station installation', 'Spice Route Travels', 6.0, 'to do'),
]
EQUIPMENT = [
    # xid, name, customer, model, serial, location, contract ref, contract end (days from today)
    ('rc_fs_eq_nest_espresso', 'La Marzocco Linea PB 2-Group Espresso Machine', 'Nest Coworking Spaces', 'Linea PB AV 2GR',
     'LM-PB2-26-04417', '3rd floor pantry, Infopark Phase 2', 'AMC-2026-NEST-01', 140),
    ('rc_fs_eq_nest_grinder', 'Mazzer Super Jolly Coffee Grinder', 'Nest Coworking Spaces', 'Super Jolly V Pro',
     'MZ-SJ-88213', '3rd floor pantry, Infopark Phase 2', 'AMC-2026-NEST-01', 140),
    ('rc_fs_eq_bluewave_b2c', 'Jura GIGA X8 Bean-to-Cup Machine', 'BlueWave Technologies', 'GIGA X8c Professional',
     'JU-X8-552190', 'Cafeteria, Tower B ground floor', 'AMC-2026-BLUE-03', 60),
    ('rc_fs_eq_greenleaf_bain', '4-Well Electric Bain-Marie', 'GreenLeaf Multispecialty Hospital', 'BM-4W-SS304',
     'BM4-2024-0098', 'Staff cafeteria serving line', 'AMC-2025-GRN-02', -20),
    ('rc_fs_eq_spice_b2c', 'Jura WE8 Bean-to-Cup Machine (new)', 'Spice Route Travels', 'WE8 Professional',
     'JU-WE8-610447', 'Reception lounge, MG Road office', False, 0),
]
# Field service orders. day = offset from today, h = local start hour, dur = hours.
# state: new / scheduled / done ; time = list of (technician xid, hours, description) for done jobs
ORDERS = [
    dict(xid='rc_fs_job_nest_q3', title='Quarterly AMC visit - espresso machine & grinder', partner='Nest Coworking Spaces',
         task='rc_fs_task_nest', tech='rc_fs_tech_anil', day=-10, h=10, dur=3, state='done', tags=['rc_fs_tag_amc'],
         eq=['rc_fs_eq_nest_espresso', 'rc_fs_eq_nest_grinder'], mats=['rc_fs_mat_service_kit'], priority='0', role='technician',
         parts=[('rc_fs_part_gasket', 1), ('rc_fs_part_descaler', 2)], rating='5',
         rating_note='Machine pulls perfect shots again, technician was on time and explained the cleaning routine.',
         time=[('rc_fs_tech_anil', 2.5, 'Descaled boiler, replaced group gaskets, calibrated grinder (18 g / 28 s)')],
         ws={'intervention_type': 'maintenance', 'model': 'Linea PB AV 2GR', 'serial_number': 'LM-PB2-26-04417',
             'intervention_description': 'Quarterly preventive maintenance: descaling, gaskets & shower screens, grinder burr check.',
             'visual_inspection': True},
         notes='<p>Boiler descaled, both group gaskets and shower screens replaced. Grinder burrs at 60% life - replace next quarter.</p>'),
    dict(xid='rc_fs_job_bluewave_breakdown', title='URGENT - bean-to-cup machine not dispensing (error 8)', partner='BlueWave Technologies',
         task='rc_fs_task_bluewave', tech='rc_fs_tech_anil', day=-3, h=9, dur=3, state='done', tags=['rc_fs_tag_breakdown'],
         eq=['rc_fs_eq_bluewave_b2c'], mats=['rc_fs_mat_service_kit'], priority='3', role='technician',
         parts=[('rc_fs_part_pump', 1), ('rc_fs_part_filter', 1)], rating='4',
         rating_note='Fixed the same morning. Would like a spare machine during longer repairs.',
         time=[('rc_fs_tech_anil', 1.5, 'Diagnosis: failed vibration pump, blocked filter'),
               ('rc_fs_tech_anil', 1.25, 'Replaced pump & filter cartridge, test brews x10')],
         ws={'intervention_type': 'repair', 'model': 'GIGA X8c Professional', 'serial_number': 'JU-X8-552190',
             'intervention_description': 'Error 8 (no water flow). Pump replaced, new filter fitted, flow rate tested OK.',
             'visual_inspection': True},
         notes='<p>Vibration pump seized (scale). Pump and filter cartridge replaced. Advised monthly filter change - 1,800 cups/month.</p>'),
    dict(xid='rc_fs_job_roof_lights', title='Rooftop lounge - fairy lights & ambient lighting wiring', partner='__company__',
         task='rc_prj_t_roof_lighting', tech='rc_fs_tech_deepak', extra=['rc_fs_tech_anil'], day=-6, h=14, dur=5, state='done',
         tags=['rc_fs_tag_electrical', 'rc_fs_tag_internal'], mats=['rc_fs_mat_ladder'], priority='1', role='electrician',
         time=[('rc_fs_tech_deepak', 4.5, 'Ran 6 lighting circuits on pergola, weatherproof junction boxes'),
               ('rc_fs_tech_anil', 3.0, 'Fixed 40 m fairy lights & 12 warm spotlights, dimmer test')],
         notes='<p>6 circuits on separate MCBs, all outdoor sockets IP65. Dimmer scenes: Dinner 60%, Late night 30%.</p>'),
    dict(xid='rc_fs_job_kds_adapter', title='Replace KDS power adapter - Hot Kitchen screen', partner='__company__',
         task='rc_hd_t22_task', tech='rc_fs_tech_deepak', day=0, h=16, dur=1, state='scheduled',
         tags=['rc_fs_tag_electrical', 'rc_fs_tag_internal'], mats=['rc_fs_mat_ladder'], priority='2', role='electrician',
         notes='<p>From Helpdesk ticket: the Hot Kitchen KDS screen switches off during service. Bring a 12 V / 5 A adapter.</p>'),
    dict(xid='rc_fs_job_patio_wifi', title='Replace patio Wi-Fi access point', partner='__company__',
         task='rc_hd_t24_task', tech='rc_fs_tech_deepak', day=1, h=10, dur=2, state='scheduled',
         tags=['rc_fs_tag_electrical', 'rc_fs_tag_internal'], mats=['rc_fs_mat_ladder'], priority='1', role='electrician',
         notes='<p>Self-order QR tables on the patio lose connection. Mount new outdoor AP, same SSID, test 4 tables.</p>'),
    dict(xid='rc_fs_job_spice_install', title='Install & commission new bean-to-cup coffee station', partner='Spice Route Travels',
         task='rc_fs_task_spice', tech='rc_fs_tech_anil', extra=['rc_fs_tech_deepak'], day=2, h=11, dur=4, state='scheduled',
         tags=['rc_fs_tag_install'], eq=['rc_fs_eq_spice_b2c'], mats=['rc_fs_mat_van', 'rc_fs_mat_service_kit'], priority='2',
         role='technician', ws={'intervention_type': 'installation', 'model': 'WE8 Professional', 'serial_number': 'JU-WE8-610447'},
         notes='<p>Deepak: dedicated 16 A socket + water inlet. Anil: install, set recipes (filter kaapi, cappuccino), train 2 staff.</p>'),
    dict(xid='rc_fs_job_wedding_setup', title='Live-counter & buffet set-up at Marina Bay wedding venue', partner='Marina Bay Events & Weddings',
         task='rc_prj_t_wed_logistics', tech='rc_fs_tech_anil', extra=['rc_fs_tech_deepak'], day='wedding', h=9, dur=6, state='scheduled',
         tags=['rc_fs_tag_event', 'rc_fs_tag_electrical'], mats=['rc_fs_mat_van', 'rc_fs_mat_counter_kit'], priority='2', role='technician',
         notes='<p>Set up 3 live counters (dosa, appam, kebab), 2 buffet lines, power distribution for 6 induction tops. '
               'Test everything before 2 pm hand-over to the event captain.</p>'),
    dict(xid='rc_fs_job_greenleaf_check', title='Bain-marie inspection & thermostat check (contract expired)', partner='GreenLeaf Multispecialty Hospital',
         task='rc_fs_task_greenleaf', tech='rc_fs_tech_anil', day=6, h=15, dur=2, state='scheduled', tags=['rc_fs_tag_amc'],
         eq=['rc_fs_eq_greenleaf_bain'], mats=['rc_fs_mat_service_kit'], priority='0', role='technician',
         parts=[('rc_fs_part_thermostat', 1)],
         notes='<p>AMC ended last month: visit is chargeable. Quote AMC renewal on site.</p>'),
    dict(xid='rc_fs_job_nest_q4', title='Quarterly AMC visit - Q4 (to schedule)', partner='Nest Coworking Spaces',
         task='rc_fs_task_nest', tech=False, day=None, state='new', tags=['rc_fs_tag_amc'],
         eq=['rc_fs_eq_nest_espresso', 'rc_fs_eq_nest_grinder'], priority='0', role='technician',
         notes='<p>Replace grinder burrs (flagged in Q3 visit).</p>'),
]


ADDRESSES = {  # customer -> (street, city, zip); filled only when the customer has no address
    'Nest Coworking Spaces': ('Infopark Phase 2, Kakkanad', 'Kochi', '682042'),
    'BlueWave Technologies': ('Tower B, SmartCity, Kakkanad', 'Kochi', '682030'),
    'GreenLeaf Multispecialty Hospital': ('NH 66 Bypass, Palarivattom', 'Kochi', '682025'),
    'Spice Route Travels': ('MG Road, Ravipuram', 'Kochi', '682016'),
    'Marina Bay Events & Weddings': ('Bolgatty Island, Mulavukad', 'Kochi', '682504'),
}


def _ref(env, xid):
    return env.ref(xid if '.' in xid else f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals, search=None):
    rec = _ref(env, xid)
    if rec:
        return rec
    if search:
        rec = env[model].sudo().with_context(active_test=False).search(search, limit=1)
        if rec:
            return _bind(env, xid, rec)
    return _bind(env, xid, env[model].sudo().with_context(**CTX).create(vals))


def _utc(day, hour):
    local = TZ.localize(datetime.combine(day, time(int(hour), int(round((hour % 1) * 60)))))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def _partner(env, name):
    if name == '__company__':
        return env.company.partner_id
    return env['res.partner'].sudo().search([('name', '=', name)], limit=1)


def _technicians(env):
    group = env.ref('hudson_field_service.group_field_service_user', raise_if_not_found=False)
    techs = {}
    for xid, name, job, login, role_xid, role2_xid in TECHNICIANS:
        emp = _ref(env, xid)
        if not emp:
            email = f'{login}@restocafe.example.com'
            user = env['res.users'].sudo().with_context(active_test=False).search([('login', '=', email)], limit=1)
            if not user:
                groups = [env.ref('base.group_user').id] + ([group.id] if group else [])
                user = env['res.users'].sudo().with_context(**CTX).create({
                    'name': name, 'login': email, 'email': email, 'group_ids': [Command.set(groups)],
                    'tz': 'Asia/Kolkata',
                })
                _bind(env, f'{xid}_user', user)
            emp = env['hr.employee'].sudo().search([('name', '=', name)], limit=1)
            if emp:
                _bind(env, xid, emp)
            else:
                emp = _bind(env, xid, env['hr.employee'].sudo().with_context(**CTX).create({
                    'name': name, 'job_title': job, 'work_email': email, 'user_id': user.id,
                    'work_phone': '+91 484 400 1234', 'company_id': env.company.id,
                }))
        roles = (_ref(env, role_xid) | _ref(env, role2_xid)).filtered(bool)
        if 'planning_role_ids' in emp._fields and roles - emp.planning_role_ids:
            emp.planning_role_ids = [Command.link(r.id) for r in roles]
        if 'default_planning_role_id' in emp._fields and not emp.default_planning_role_id and _ref(env, role_xid):
            emp.default_planning_role_id = _ref(env, role_xid)
        techs[xid] = emp
    return techs


def _catalog(env):
    for xid, name, color in TAGS:
        _get_or_create(env, xid, 'field.service.tag', {'name': name, 'color': color}, [('name', '=', name)])
    for xid, name, color in MATERIALS:
        _get_or_create(env, xid, 'field.service.material', {'name': name, 'color': color, 'tz': 'Asia/Kolkata'},
                       [('name', '=', name)])
    categ = env['product.category'].sudo().search([('name', '=', 'Spare Parts')], limit=1) \
        or env['product.category'].sudo().create({'name': 'Spare Parts'})
    for xid, name, price, cost, code in PARTS:
        vals = {'name': name, 'list_price': price, 'standard_price': cost, 'default_code': code, 'type': 'consu',
                'categ_id': categ.id, 'sale_ok': True, 'purchase_ok': True}
        if 'is_storable' in env['product.template']._fields:
            vals['is_storable'] = False
        _get_or_create(env, xid, 'product.product', vals, [('default_code', '=', code)])


def _project(env):
    project = _get_or_create(env, 'rc_fs_project', 'project.project', {
        'name': 'Coffee Equipment AMC & Field Service', 'allow_timesheets': True,
        'description': '<p>Annual maintenance contracts and on-site interventions on the coffee & hot-holding '
                       'equipment Resto Cafe supplies to its corporate catering clients. Each field service job '
                       'is linked to the client task; technicians\' time is logged on the task.</p>',
        'company_id': env.company.id,
    }, [('name', '=', 'Coffee Equipment AMC & Field Service')])
    stages = env['project.task.type'].sudo().search([('project_ids', 'in', project.id)])
    if not stages:
        stages = env['project.task.type'].sudo().search([('project_ids', 'in', _ref(env, 'rc_prj_rooftop').ids)]) \
            if _ref(env, 'rc_prj_rooftop') else stages
        for st in stages:
            st.project_ids = [Command.link(project.id)]
    admin = env.ref('base.user_admin')
    for xid, name, partner_name, hours, stage_kw in AMC_TASKS:
        if _ref(env, xid):
            continue
        stage = stages.filtered(lambda s: stage_kw in s.name.lower())[:1] or stages[:1]
        _get_or_create(env, xid, 'project.task', {
            'name': name, 'project_id': project.id, 'partner_id': _partner(env, partner_name).id,
            'allocated_hours': hours, 'stage_id': stage.id, 'user_ids': [Command.set(admin.ids)],
        })
    return project


def _equipment(env):
    today = fields.Date.context_today(env['res.users'])
    manufacturers = {}
    for brand in ('La Marzocco', 'Mazzer', 'Jura', 'Prestige Commercial Kitchens'):
        manufacturers[brand] = env['res.partner'].sudo().search([('name', '=', brand)], limit=1) \
            or env['res.partner'].sudo().with_context(**CTX).create({'name': brand, 'is_company': True})
    for xid, name, partner_name, model, serial, loc, contract, end_days in EQUIPMENT:
        brand = next((b for b in manufacturers if name.startswith(b.split()[0])), 'Prestige Commercial Kitchens')
        vals = {'name': name, 'partner_id': _partner(env, partner_name).id, 'model': model, 'serial_number': serial,
                'location': loc, 'manufacturer_id': manufacturers[brand].id}
        if contract:
            vals.update(contract_reference=contract, contract_end_date=today + timedelta(days=end_days))
        _get_or_create(env, xid, 'fs.equipment', vals, [('serial_number', '=', serial)])


def _wedding_day(env):
    order = _ref(env, 'rc_so_wedding_welcome')
    if order and order.commitment_date:
        return pytz.utc.localize(order.commitment_date).astimezone(TZ).date()
    return fields.Date.context_today(env['res.users']) + timedelta(days=12)


def _orders(env, techs):
    Order = env['field.service.order'].sudo().with_context(**CTX)
    today = fields.Date.context_today(env['res.users'])
    worksheet = _ref(env, 'hudson_field_service.fs_worksheet_template_device')
    stage_by_state = {
        'new': _ref(env, 'hudson_field_service.field_service_stage_new'),
        'scheduled': _ref(env, 'hudson_field_service.field_service_stage_scheduled'),
        'done': _ref(env, 'hudson_field_service.field_service_stage_done'),
    }
    roles = {'technician': _ref(env, 'hudson_planning.fs_planning_role_technician'),
             'electrician': _ref(env, 'hudson_planning.fs_planning_role_electrician')}
    for spec in ORDERS:
        if _ref(env, spec['xid']):
            continue
        try:
            with env.cr.savepoint():
                _order(env, spec, techs, Order, today, worksheet, stage_by_state, roles)
                env.flush_all()
        except Exception as e:
            _logger.exception("Hudson POS: Field Service demo job %s failed: %s", spec['xid'], e)


def _order(env, spec, techs, Order, today, worksheet, stage_by_state, roles):
    if True:
        task = _ref(env, spec['task'])
        partner = _partner(env, spec['partner'])
        if not partner:
            return
        vals = {
            'title': spec['title'], 'partner_id': partner.id, 'priority': spec['priority'],
            'description': spec.get('notes'), 'employee_id': False,
            'tag_ids': [Command.set([_ref(env, t).id for t in spec.get('tags', []) if _ref(env, t)])],
            'material_ids': [Command.set([_ref(env, m).id for m in spec.get('mats', []) if _ref(env, m)])],
            'equipment_ids': [Command.set([_ref(env, e).id for e in spec.get('eq', []) if _ref(env, e)])],
            'role_id': roles[spec['role']].id if roles.get(spec['role']) else False,
            'company_id': env.company.id,
        }
        if not partner.street and spec['partner'] in ADDRESSES:
            street, city, zip_code = ADDRESSES[spec['partner']]
            kerala = env['res.country.state'].search([('code', '=', 'KL'), ('country_id.code', '=', 'IN')], limit=1)
            partner.sudo().write({'street': street, 'city': city, 'zip': zip_code,
                                  'state_id': kerala.id, 'country_id': env.ref('base.in').id})
        address = ', '.join(filter(None, [partner.street, partner.city, partner.zip]))
        vals['partner_address'] = address or 'Marine Drive, Kochi 682031'
        if task:
            vals.update(project_id=task.project_id.id, task_id=task.id)
            so = getattr(task, 'sale_line_id', False) and task.sale_line_id.order_id or task.project_id.sale_order_id
            if so:
                vals['sale_order_id'] = so.id
        if spec.get('ws') and worksheet:
            vals['worksheet_template_id'] = worksheet.id
        if spec['state'] != 'new':
            day = _wedding_day(env) if spec['day'] == 'wedding' else today + timedelta(days=spec['day'])
            start = _utc(day, spec['h'])
            vals.update(
                employee_id=techs[spec['tech']].id,
                extra_employee_ids=[Command.set([techs[x].id for x in spec.get('extra', [])])],
                date_planned=start, date_deadline=start + timedelta(hours=spec['dur']),
                is_published=True,
            )
        order = _bind(env, spec['xid'], Order.create(vals))
        if spec.get('ws') and worksheet:
            try:
                with env.cr.savepoint():
                    order.worksheet_properties = spec['ws']
            except Exception as e:  # noqa: BLE001 - properties are optional
                _logger.info("Field service demo: worksheet values skipped on %s (%s)", order.name, e)
        # spare parts used / quoted: billed through a quotation by the module
        for part_xid, qty in spec.get('parts', []):
            part = _ref(env, part_xid)
            if part:
                env['field.service.product.line'].sudo().create({
                    'order_id': order.id, 'product_id': part.id, 'quantity': qty, 'price_unit': part.lst_price,
                })
        state_vals = {'stage_id': stage_by_state[spec['state']].id if stage_by_state.get(spec['state']) else order.stage_id.id}
        if spec['state'] == 'done':
            state_vals.update(
                state='done', date_start=order.date_planned, date_end=order.date_deadline,
                worksheet_notes=spec.get('notes'), customer_rating=spec.get('rating') or False,
                rating_note=spec.get('rating_note') or False,
            )
        elif spec['state'] == 'scheduled':
            state_vals['state'] = 'scheduled'
        order.write(state_vals)
        _log_time(env, order, spec, techs)


def _log_time(env, order, spec, techs):
    """Finished jobs: time on the job (field service timesheet) and on its project task (Timesheets)."""
    if spec['state'] != 'done':
        return
    start = order.date_planned
    for n, (tech_xid, hours, desc) in enumerate(spec.get('time', []), start=1):
        emp = techs[tech_xid]
        end = start + timedelta(hours=hours)
        if emp.user_id:
            env['field.service.timesheet'].sudo().create({
                'order_id': order.id, 'user_id': emp.user_id.id, 'date': start.date(), 'description': desc,
                'duration': hours, 'start_time': start, 'end_time': end,
            })
        if order.project_id and 'project_id' in env['account.analytic.line']._fields:
            line = env['account.analytic.line'].sudo().create({
                'name': f'{order.name} - {desc}', 'project_id': order.project_id.id, 'task_id': order.task_id.id,
                'employee_id': emp.id, 'unit_amount': hours, 'date': start.date(),
            })
            _bind(env, f"{spec['xid']}_ts_{n}", line)
        start = end


def load_field_service_suite_demo_data(env):
    """Field service jobs linked to projects/tasks, with planning shifts and timesheets."""
    if 'field.service.order' not in env or 'fs.planning.slot' not in env:
        _logger.info("Hudson POS: Field Service demo skipped (hudson_field_service / hudson_planning not installed).")
        return False
    ICP = env['ir.config_parameter'].sudo()
    if not ICP.get_param('hudson_field_service.default_hourly_rate'):
        ICP.set_param('hudson_field_service.default_hourly_rate', '850')
    ctx = {}
    steps = [
        ('technicians', lambda: ctx.update(techs=_technicians(env))),
        ('catalog', lambda: _catalog(env)),
        ('project', lambda: _project(env)),
        ('equipment', lambda: _equipment(env)),
        ('orders', lambda: _orders(env, ctx['techs'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
                env.flush_all()
        except Exception as e:
            _logger.exception("Hudson POS: Field Service demo step '%s' failed: %s", name, e)
            if name == 'technicians':
                return False
    _logger.info("Hudson POS: Resto Cafe Field Service demo data loaded.")
    return True
