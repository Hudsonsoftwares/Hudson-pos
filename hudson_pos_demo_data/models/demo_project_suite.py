# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Project & Timesheet demo data.

Idempotent: every record is bound to an xmlid of this module (prefix ``rc_prj_``).
  * 5 projects (renovation, Onam menu launch, Marina Bay wedding execution, central kitchen
    expansion, website revamp) with their own stages, tags, milestones, sub-tasks, dependencies,
    priorities, deadlines, assignees and project status updates
  * The wedding project is billed on timesheets: a "Event Coordination (hours)" service line on the
    Sales suite's confirmed Marina Bay order; logged hours become billable/delivered quantity
  * ~60 timesheet lines over the last 4 weeks for the Resto Cafe employees
  * Personal to-dos (project_todo)
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


TAGS = [('rc_prj_tag_kitchen', 'Kitchen', 1), ('rc_prj_tag_marketing', 'Marketing', 2), ('rc_prj_tag_event', 'Event', 3),
        ('rc_prj_tag_urgent', 'Urgent', 4), ('rc_prj_tag_vendor', 'Vendor', 5), ('rc_prj_tag_it', 'IT', 6),
        ('rc_prj_tag_compliance', 'Compliance', 7), ('rc_prj_tag_design', 'Design', 8)]

STAGES = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done']

# project: xid, name, manager ('admin'|'arjun'), partner xid, color, tags, start offset, end offset, stage name,
#          description, employees (timesheets), billable (sale order xid), status update
PROJECTS = [
    ('rc_prj_rooftop', 'Rooftop Garden Lounge Renovation', 'admin', None, 2, ['rc_prj_tag_design', 'rc_prj_tag_vendor'], -40, 35,
     'In Progress', 'Convert the rooftop into a 40-seat garden lounge with pergola, lighting and a live-music corner.',
     ['Suresh Kumar', 'Mohammed Bilal', 'Kevin Joseph'], None,
     ('at_risk', 55, 'Pergola steel delivery slipped by 6 days; electrical work re-sequenced. Opening may move by one week.')),
    ('rc_prj_onam', 'Onam Festival Menu Launch', 'arjun', None, 10, ['rc_prj_tag_kitchen', 'rc_prj_tag_marketing'], -30, 10,
     'In Progress', 'Design, cost and launch the 26-dish Onam Sadya menu for dine-in, takeaway and corporate catering.',
     ['Rahul Nair', 'Ananya Sharma', 'Vishnu Kumar', 'Priya Menon'], None,
     ('on_track', 70, 'Tasting done, final menu approved. Photoshoot and online listing this week.')),
    ('rc_prj_wedding', 'Marina Bay Wedding – Event Execution', 'arjun', 'rc_partner_marina_events', 4, ['rc_prj_tag_event'], -20, 15,
     'In Progress', 'End-to-end execution of the Marina Bay destination wedding welcome dinner: menu, staffing, logistics and setup.',
     ['Suresh Kumar', 'Mohammed Bilal', 'Rahul Nair', 'Arun Varma'], 'rc_so_wedding_welcome',
     ('on_track', 45, 'Menu and guest count confirmed (120). Staffing roster and transport planned.')),
    ('rc_prj_central_kitchen', 'Central Kitchen Expansion', 'admin', None, 7, ['rc_prj_tag_kitchen', 'rc_prj_tag_compliance'], -60, 60,
     'To Do', 'Add a second hot line, blast chiller and FSSAI-compliant cold room to support catering volumes.',
     ['Rahul Nair', 'Vishnu Kumar', 'Suresh Kumar'], None,
     ('off_track', 30, 'FSSAI licence modification pending; equipment order on hold until approval.')),
    ('rc_prj_website', 'Website & Online Ordering Revamp', 'admin', None, 9, ['rc_prj_tag_it', 'rc_prj_tag_marketing'], -25, 20,
     'In Progress', 'New website design, table QR ordering and packaged-food webshop integration.',
     ['Sneha Pillai', 'Priya Menon', 'Suresh Kumar'], None,
     ('on_track', 60, 'Home, Shop and Events pages live; appointment booking redesign in review.')),
]

# milestones: project xid, name, deadline offset, reached
MILESTONES = [
    ('rc_prj_rooftop', 'Design approved', -25, True), ('rc_prj_rooftop', 'Civil & electrical complete', 10, False),
    ('rc_prj_rooftop', 'Soft opening', 35, False),
    ('rc_prj_onam', 'Menu finalised', -10, True), ('rc_prj_onam', 'Launch day', 10, False),
    ('rc_prj_wedding', 'Menu & headcount confirmed', -8, True), ('rc_prj_wedding', 'Event day', 12, False),
    ('rc_prj_central_kitchen', 'FSSAI approval', 15, False), ('rc_prj_central_kitchen', 'Equipment installed', 50, False),
    ('rc_prj_website', 'Pages redesigned', -5, True), ('rc_prj_website', 'Online ordering go-live', 20, False),
]

# tasks: xid, project, name, stage, assignees, priority, deadline offset, tags, milestone index (name), hours, parent xid, depends on xids
TASKS = [
    # Rooftop
    ('rc_prj_t_roof_design', 'rc_prj_rooftop', 'Finalize lounge layout with architect', 'Done', ['admin'], '0', -26, [], 'Design approved', 12, None, []),
    ('rc_prj_t_roof_quotes', 'rc_prj_rooftop', 'Collect 3 vendor quotes for pergola', 'Done', ['arjun'], '0', -18, ['rc_prj_tag_vendor'], 'Civil & electrical complete', 6, None, []),
    ('rc_prj_t_roof_pergola', 'rc_prj_rooftop', 'Install pergola and shade sails', 'In Progress', ['admin'], '1', 6, ['rc_prj_tag_urgent'], 'Civil & electrical complete', 30, None, ['rc_prj_t_roof_quotes']),
    ('rc_prj_t_roof_lighting', 'rc_prj_rooftop', 'Fairy lights & ambient lighting wiring', 'To Do', ['arjun'], '0', 9, [], 'Civil & electrical complete', 16, None, ['rc_prj_t_roof_pergola']),
    ('rc_prj_t_roof_furniture', 'rc_prj_rooftop', 'Order outdoor furniture (40 seats)', 'Review', ['admin'], '0', 14, ['rc_prj_tag_vendor'], 'Soft opening', 8, None, []),
    ('rc_prj_t_roof_licence', 'rc_prj_rooftop', 'Fire NOC & music licence', 'Backlog', ['admin'], '1', 25, ['rc_prj_tag_compliance'], 'Soft opening', 6, None, []),
    # Onam
    ('rc_prj_t_onam_menu', 'rc_prj_onam', 'Draft 26-dish Sadya menu', 'Done', ['arjun'], '0', -14, ['rc_prj_tag_kitchen'], 'Menu finalised', 10, None, []),
    ('rc_prj_t_onam_costing', 'rc_prj_onam', 'Recipe costing & pricing', 'Done', ['admin'], '0', -11, [], 'Menu finalised', 8, None, ['rc_prj_t_onam_menu']),
    ('rc_prj_t_onam_tasting', 'rc_prj_onam', 'Tasting session with management', 'Done', ['arjun'], '0', -9, [], 'Menu finalised', 4, None, ['rc_prj_t_onam_costing']),
    ('rc_prj_t_onam_photo', 'rc_prj_onam', 'Food photoshoot for website & social', 'In Progress', ['arjun'], '1', 3, ['rc_prj_tag_marketing'], 'Launch day', 6, None, ['rc_prj_t_onam_tasting']),
    ('rc_prj_t_onam_listing', 'rc_prj_onam', 'Publish Onam menu on website & POS', 'To Do', ['admin'], '0', 6, ['rc_prj_tag_marketing'], 'Launch day', 4, None, ['rc_prj_t_onam_photo']),
    ('rc_prj_t_onam_banana', 'rc_prj_onam', 'Book banana-leaf & vegetable supply', 'Review', ['admin'], '1', 5, ['rc_prj_tag_vendor', 'rc_prj_tag_urgent'], 'Launch day', 3, None, []),
    # Wedding (billable)
    ('rc_prj_t_wed_menu', 'rc_prj_wedding', 'Confirm menu & dietary list with the couple', 'Done', ['arjun'], '0', -9, [], 'Menu & headcount confirmed', 5, None, []),
    ('rc_prj_t_wed_staff', 'rc_prj_wedding', 'Staffing roster (12 waiters, 3 chefs)', 'In Progress', ['arjun'], '0', 5, [], 'Event day', 6, None, ['rc_prj_t_wed_menu']),
    ('rc_prj_t_wed_logistics', 'rc_prj_wedding', 'Transport & venue setup plan', 'In Progress', ['admin'], '1', 8, ['rc_prj_tag_urgent'], 'Event day', 8, None, []),
    ('rc_prj_t_wed_vans', 'rc_prj_wedding', 'Book 2 catering vans', 'To Do', ['admin'], '0', 7, [], 'Event day', 2, 'rc_prj_t_wed_logistics', []),
    ('rc_prj_t_wed_layout', 'rc_prj_wedding', 'Buffet & live-counter layout drawing', 'To Do', ['arjun'], '0', 9, [], 'Event day', 3, 'rc_prj_t_wed_logistics', []),
    ('rc_prj_t_wed_decor', 'rc_prj_wedding', 'Decor sign-off with Marina Bay', 'Backlog', ['arjun'], '0', 10, [], 'Event day', 2, None, []),
    # Central kitchen
    ('rc_prj_t_ck_fssai', 'rc_prj_central_kitchen', 'FSSAI licence modification application', 'In Progress', ['admin'], '1', -3, ['rc_prj_tag_compliance', 'rc_prj_tag_urgent'], 'FSSAI approval', 10, None, []),
    ('rc_prj_t_ck_layout', 'rc_prj_central_kitchen', 'Hot line & cold room layout', 'Done', ['admin'], '0', -20, ['rc_prj_tag_kitchen'], 'FSSAI approval', 14, None, []),
    ('rc_prj_t_ck_chiller', 'rc_prj_central_kitchen', 'Blast chiller purchase', 'Backlog', ['admin'], '0', 30, ['rc_prj_tag_vendor'], 'Equipment installed', 4, None, ['rc_prj_t_ck_fssai']),
    ('rc_prj_t_ck_training', 'rc_prj_central_kitchen', 'Train staff on new HACCP flow', 'To Do', ['arjun'], '0', 55, ['rc_prj_tag_compliance'], 'Equipment installed', 12, None, ['rc_prj_t_ck_chiller']),
    # Website
    ('rc_prj_t_web_pages', 'rc_prj_website', 'Redesign Home, Shop, Events, Blog pages', 'Done', ['admin'], '0', -6, ['rc_prj_tag_design'], 'Pages redesigned', 24, None, []),
    ('rc_prj_t_web_appt', 'rc_prj_website', 'Table booking & appointment pages', 'Review', ['admin'], '1', 2, ['rc_prj_tag_design'], 'Online ordering go-live', 10, None, ['rc_prj_t_web_pages']),
    ('rc_prj_t_web_qr', 'rc_prj_website', 'Table QR self-ordering rollout', 'In Progress', ['arjun'], '1', 10, ['rc_prj_tag_it'], 'Online ordering go-live', 16, None, []),
    ('rc_prj_t_web_seo', 'rc_prj_website', 'SEO & Google Business profile', 'To Do', ['admin'], '0', 18, ['rc_prj_tag_marketing'], 'Online ordering go-live', 6, None, ['rc_prj_t_web_pages']),
]

TODOS = [
    ('rc_prj_todo_1', 'Call Federal Bank about POS card settlement', 'admin', 1),
    ('rc_prj_todo_2', 'Renew FSSAI registration certificate', 'admin', 12),
    ('rc_prj_todo_3', 'Review Onam staff overtime', 'admin', 4),
    ('rc_prj_todo_4', 'Send Marina Bay revised floor plan', 'arjun', 2),
    ('rc_prj_todo_5', 'Follow up BlueWave lunch subscription renewal', 'arjun', 5),
]

TIMESHEET_TEXTS = ['Site visit & coordination', 'Vendor call', 'Planning meeting', 'Recipe trials', 'Documentation',
                   'Client meeting', 'Setup & testing', 'Review & sign-off', 'Procurement follow-up', 'Team briefing']


def _users(env):
    return {'admin': env.ref('base.user_admin'), 'arjun': _ref(env, 'rc_user_arjun') or env.ref('base.user_admin')}


def _enable_features(env):
    user_group = env.ref('base.group_user')
    for xid in ('project.group_project_milestone', 'project.group_project_task_dependencies', 'project.group_project_stages'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _billing_line(env, so_xid):
    """Add an hours-based 'Event Coordination' service line to the confirmed Sales demo order."""
    order = _ref(env, so_xid) if so_xid else None
    if not order or order.state != 'sale':
        return env['sale.order.line']
    line = _ref(env, 'rc_prj_so_line_coordination')
    if line:
        return line
    product = _get_or_create(env, 'rc_prj_prod_coordination', 'product.product', {
        'name': 'Event Coordination (hours)', 'type': 'service', 'list_price': 1500, 'standard_price': 600,
        'uom_id': env.ref('uom.product_uom_hour').id, 'invoice_policy': 'delivery', 'service_type': 'timesheet',
        'service_tracking': 'no', 'sale_ok': True, 'purchase_ok': False, 'available_in_pos': False,
        'taxes_id': [Command.set(env.company.account_sale_tax_id.ids)],
        'description_sale': 'Event manager and coordinator time, billed on timesheets.',
    })
    line = env['sale.order.line'].sudo().create({
        'order_id': order.id, 'product_id': product.id, 'product_uom_qty': 40, 'name': 'Event Coordination (hours) – billed on timesheets',
    })
    return _bind(env, 'rc_prj_so_line_coordination', line)


def _projects(env):
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    tags = {xid: _get_or_create(env, xid, 'project.tags', {'name': name, 'color': color}) for xid, name, color in TAGS}
    pstages = {s.name: s for s in env['project.project.stage'].search([])} if 'project.project.stage' in env else {}
    projects = {}
    for (xid, name, mgr, partner_xid, color, tag_xids, start, end, pstage, desc, _emps, so_xid, _upd) in PROJECTS:
        if _ref(env, xid):
            projects[xid] = _ref(env, xid)
            continue
        partner = _ref(env, partner_xid) if partner_xid else None
        stage_ids = []
        for seq, sname in enumerate(STAGES, start=1):
            stage_ids.append(Command.create({'name': sname, 'sequence': seq, 'fold': sname == 'Done'}))
        vals = {
            'name': name, 'user_id': users[mgr].id, 'color': color, 'description': f'<p>{desc}</p>',
            'tag_ids': [Command.set([tags[t].id for t in tag_xids])],
            'date_start': today + timedelta(days=start), 'date': today + timedelta(days=end),
            'allow_timesheets': True, 'allow_milestones': True, 'allow_task_dependencies': True,
            'privacy_visibility': 'portal' if partner else 'employees', 'label_tasks': 'Tasks',
            'type_ids': stage_ids,
            'favorite_user_ids': [Command.link(users['admin'].id)],
        }
        if partner:
            vals['partner_id'] = partner.id
        if pstage in pstages:
            vals['stage_id'] = pstages[pstage].id
        project = _bind(env, xid, env['project.project'].sudo().with_context(mail_create_nosubscribe=True).create(vals))
        line = _billing_line(env, so_xid)
        if line:
            project.write({'allow_billable': True, 'sale_line_id': line.id, 'partner_id': line.order_id.partner_id.id})
        projects[xid] = project
    return projects


def _milestones(env, projects):
    today = fields.Date.context_today(env['res.users'])
    res = {}
    for i, (pxid, name, offset, reached) in enumerate(MILESTONES, start=1):
        xid = f'rc_prj_ms_{i}'
        res[(pxid, name)] = _get_or_create(env, xid, 'project.milestone', {
            'name': name, 'project_id': projects[pxid].id, 'deadline': today + timedelta(days=offset), 'is_reached': reached,
        })
    return res


def _tasks(env, projects, milestones):
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    tags = {xid: _ref(env, xid) for xid, _n, _c in TAGS}
    tasks = {}
    for (xid, pxid, name, stage_name, assignees, prio, dl, tag_xids, ms_name, hours, parent, depends) in TASKS:
        if _ref(env, xid):
            tasks[xid] = _ref(env, xid)
            continue
        project = projects[pxid]
        stage = project.type_ids.filtered(lambda s: s.name == stage_name)[:1]
        vals = {
            'name': name, 'project_id': project.id, 'stage_id': stage.id, 'priority': prio,
            'user_ids': [Command.set([users[u].id for u in assignees])],
            'date_deadline': fields.Datetime.to_datetime(today + timedelta(days=dl)).replace(hour=12),
            'tag_ids': [Command.set([tags[t].id for t in tag_xids if tags.get(t)])],
            'allocated_hours': hours,
        }
        ms = milestones.get((pxid, ms_name))
        if ms:
            vals['milestone_id'] = ms.id
        if parent and parent in tasks:
            vals['parent_id'] = tasks[parent].id
        if depends:
            vals['depend_on_ids'] = [Command.set([tasks[d].id for d in depends if d in tasks])]
        if project.sale_line_id:
            vals['sale_line_id'] = project.sale_line_id.id
            vals['partner_id'] = project.partner_id.id
        task = _bind(env, xid, env['project.task'].sudo().with_context(mail_create_nosubscribe=True).create(vals))
        if stage_name == 'Done':
            task.state = '1_done'
        elif stage_name == 'Review':
            task.state = '03_approved' if prio == '0' else '02_changes_requested'
        tasks[xid] = task
    return tasks


def _updates(env, projects):
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    for (xid, name, mgr, *_rest) in PROJECTS:
        status, progress, text = _rest[-1]
        _get_or_create(env, f'{xid}_update', 'project.update', {
            'name': f'Weekly update – {name}', 'project_id': projects[xid].id, 'status': status, 'progress': progress,
            'date': today - timedelta(days=2), 'user_id': users[mgr].id, 'description': f'<p>{text}</p>',
        })


def _timesheets(env, projects, tasks):
    if _ref(env, 'rc_prj_ts_1'):
        return
    today = fields.Date.context_today(env['res.users'])
    Employee = env['hr.employee'].sudo()
    by_project = {}
    for (xid, *_r) in TASKS:
        pxid = _r[0]
        if xid in tasks:
            by_project.setdefault(pxid, []).append(tasks[xid])
    n = 0
    for p_idx, (pxid, name, _m, _p, _c, _t, start, _e, _s, _d, emp_names, _so, _u) in enumerate(PROJECTS):
        emps = Employee.search([('name', 'in', emp_names)])
        ptasks = [t for t in by_project.get(pxid, []) if t.stage_id.name != 'Backlog']
        if not emps or not ptasks:
            continue
        for k in range(12):
            day = today - timedelta(days=(k * 2 + p_idx) % 27 + 1)
            if day.weekday() == 6:
                day -= timedelta(days=1)
            emp = emps[(k + p_idx) % len(emps)]
            task = ptasks[(k * 3 + p_idx) % len(ptasks)]
            hours = [1.5, 2.0, 3.0, 4.0, 2.5, 6.0, 1.0, 3.5][(k + p_idx) % 8]
            n += 1
            line = env['account.analytic.line'].sudo().create({
                'name': TIMESHEET_TEXTS[(k + p_idx) % len(TIMESHEET_TEXTS)], 'project_id': projects[pxid].id, 'task_id': task.id,
                'employee_id': emp.id, 'unit_amount': hours, 'date': day,
            })
            _bind(env, f'rc_prj_ts_{n}', line)


def _todos(env):
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    for xid, name, user, dl in TODOS:
        if _ref(env, xid):
            continue
        task = env['project.task'].sudo().with_user(users[user]).with_context(mail_create_nosubscribe=True).create({
            'name': name, 'user_ids': [Command.set(users[user].ids)],
            'date_deadline': fields.Datetime.to_datetime(today + timedelta(days=dl)).replace(hour=12),
        })
        _bind(env, xid, task.sudo())


def load_project_suite_demo_data(env):
    if 'project.project' not in env:
        _logger.info("Hudson POS: Project not installed, skipping Project demo data.")
        return
    ctx = {}
    steps = [
        ('features', lambda: _enable_features(env)),
        ('projects', lambda: ctx.update(projects=_projects(env))),
        ('milestones', lambda: ctx.update(milestones=_milestones(env, ctx['projects']))),
        ('tasks', lambda: ctx.update(tasks=_tasks(env, ctx['projects'], ctx['milestones']))),
        ('updates', lambda: _updates(env, ctx['projects'])),
        ('timesheets', lambda: 'account.analytic.line' in env and 'project_id' in env['account.analytic.line']._fields
         and _timesheets(env, ctx['projects'], ctx['tasks'])),
        ('to-dos', lambda: _todos(env)),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Project demo step '%s' failed: %s", name, e)
            if name in ('projects', 'milestones', 'tasks'):
                return
    _logger.info("Hudson POS: Resto Cafe Project & Timesheet demo data loaded.")
