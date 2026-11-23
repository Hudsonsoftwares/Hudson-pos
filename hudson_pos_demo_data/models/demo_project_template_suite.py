# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Project Templates & project-generating service products.

Idempotent: every record is bound to an xmlid of this module (prefix ``rc_pt_``).
  * 6 project templates (Project > Configuration > Project Templates) with stages, milestones,
    tasks, sub-tasks, priorities, tags and allocated hours:
      Wedding & Banquet Catering, Corporate Lunch Contract Onboarding, Kitchen Setup Consultancy,
      Birthday & Private Party, Coffee Machine Installation & AMC, Cooking Masterclass
  * 6 service products (Sales > Products) whose "Create on Order" is Project or Project & Task
    and whose "Project Template" is one of the templates above: confirming a sales order with
    one of them creates a new project from that template, linked to the order line
  * 7 sales orders: 5 confirmed (each one generated its project(s) from the template - one order
    holds two template products and produced two projects), 1 sent quotation and 1 draft
    quotation (no project yet: it is created when the quotation is confirmed)
  * The generated projects are moved forward: first tasks done, a milestone reached (the Kitchen
    Setup product is invoiced on milestones, so reaching it makes 30% of the line deliverable)
Requires Sales + Project (sale_project); fields the installed apps do not provide are skipped.
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


def _clean(env, model, vals):
    fields_ = env[model]._fields
    return {k: v for k, v in vals.items() if k in fields_}


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(_clean(env, model, vals)))


def _users(env):
    admin = env.ref('base.user_admin')
    return {'admin': admin, 'arjun': _ref(env, 'rc_user_arjun') or admin}


# --------------------------------------------------------------------------- templates
TAGS = [('rc_pt_tag_catering', 'Catering', 2), ('rc_pt_tag_onsite', 'On-site', 4),
        ('rc_pt_tag_client', 'Client Approval', 3), ('rc_pt_tag_recurring', 'Recurring', 10),
        ('rc_pt_tag_equipment', 'Equipment', 6), ('rc_pt_tag_learning', 'Workshop', 11)]

# Template: xid, name, manager, colour, tags, duration (days), description,
#           stages, milestones [(name, day offset, invoice %)],
#           tasks [(name, stage, hours, milestone, priority, tags, sub-tasks)]
TEMPLATES = [
    ('rc_pt_tmpl_wedding', 'Wedding & Banquet Catering', 'arjun', 4, ['rc_pt_tag_catering', 'rc_pt_tag_onsite'], 30,
     'Standard plan for a wedding or banquet: menu tasting, headcount, staffing, procurement, '
     'event-day execution and wrap-up.',
     ['Confirmed', 'Planning', 'Procurement', 'Event Day', 'Wrap-up'],
     [('Menu & headcount confirmed', 10, 0), ('Event day', 28, 0), ('Feedback & closure', 30, 0)],
     [('Kick-off call with the client', 'Confirmed', 1, 'Menu & headcount confirmed', '1', ['rc_pt_tag_client'], []),
      ('Menu tasting session', 'Planning', 4, 'Menu & headcount confirmed', '1', ['rc_pt_tag_client'],
       ['Shortlist 3 menu options', 'Book tasting table for 6']),
      ('Final headcount & dietary list', 'Planning', 2, 'Menu & headcount confirmed', '0', ['rc_pt_tag_client'], []),
      ('Venue recce & buffet layout', 'Planning', 6, 'Event day', '0', ['rc_pt_tag_onsite'],
       ['Measure buffet and live-counter area', 'Check power points for chafing dishes', 'Draw layout plan']),
      ('Staffing roster (waiters, chefs, supervisors)', 'Planning', 3, 'Event day', '0', [], []),
      ('Procure ingredients & hire crockery', 'Procurement', 8, 'Event day', '1', [], []),
      ('Catering vans & transport plan', 'Procurement', 2, 'Event day', '0', [], []),
      ('Event-day execution', 'Event Day', 16, 'Event day', '2', ['rc_pt_tag_onsite'],
       ['Load-in and setup', 'Service', 'Pack-up and venue hand-back']),
      ('Client feedback & final invoice', 'Wrap-up', 1, 'Feedback & closure', '0', ['rc_pt_tag_client'], [])]),
    ('rc_pt_tmpl_corporate', 'Corporate Lunch Contract Onboarding', 'admin', 10, ['rc_pt_tag_catering', 'rc_pt_tag_recurring'], 45,
     'Onboard a new corporate lunch client: menu cycle, delivery schedule, trial week and monthly reviews.',
     ['Onboarding', 'Trial Week', 'Live', 'Monthly Review'],
     [('Trial week completed', 14, 0), ('First monthly review', 45, 0)],
     [('Agree 4-week menu cycle', 'Onboarding', 4, 'Trial week completed', '1', ['rc_pt_tag_client'], []),
      ('Collect headcount & dietary preferences', 'Onboarding', 2, 'Trial week completed', '0', [], []),
      ('Delivery slots & drop point setup', 'Onboarding', 2, 'Trial week completed', '0', ['rc_pt_tag_onsite'], []),
      ('Run trial week & collect feedback', 'Trial Week', 10, 'Trial week completed', '2', ['rc_pt_tag_client'],
       ['Day 1-2 feedback forms', 'Adjust spice levels and portions']),
      ('Go live with daily deliveries', 'Live', 6, 'First monthly review', '1', ['rc_pt_tag_recurring'], []),
      ('Monthly hygiene & quality audit', 'Monthly Review', 3, 'First monthly review', '0', [], []),
      ('Monthly review meeting with the client', 'Monthly Review', 2, 'First monthly review', '0', ['rc_pt_tag_client'], [])]),
    ('rc_pt_tmpl_kitchen', 'Kitchen Setup Consultancy', 'admin', 7, ['rc_pt_tag_equipment', 'rc_pt_tag_onsite'], 60,
     'Consultancy for a new restaurant or cloud kitchen: assessment, layout, equipment, FSSAI, '
     'installation, staff training and handover. Invoiced on milestones.',
     ['Assessment', 'Design', 'Installation', 'Training', 'Handover'],
     [('Layout approved', 15, 0.3), ('Equipment installed', 45, 0.4), ('Handover', 60, 0.3)],
     [('Site assessment & requirements', 'Assessment', 6, 'Layout approved', '1', ['rc_pt_tag_onsite'], []),
      ('Kitchen layout & workflow design', 'Design', 12, 'Layout approved', '2', ['rc_pt_tag_client'],
       ['Hot line and cold line zoning', 'Wash area and waste flow']),
      ('Equipment list & vendor quotations', 'Design', 6, 'Equipment installed', '0', ['rc_pt_tag_equipment'], []),
      ('FSSAI licence documentation', 'Design', 4, 'Equipment installed', '1', [], []),
      ('Installation supervision', 'Installation', 16, 'Equipment installed', '0', ['rc_pt_tag_equipment', 'rc_pt_tag_onsite'], []),
      ('Staff training on HACCP & recipes', 'Training', 12, 'Handover', '0', [], []),
      ('Handover & sign-off', 'Handover', 2, 'Handover', '0', ['rc_pt_tag_client'], [])]),
    ('rc_pt_tmpl_birthday', 'Birthday & Private Party', 'arjun', 9, ['rc_pt_tag_catering'], 14,
     'Small private party: theme, cake, menu, entertainment, setup and clean-up.',
     ['Booked', 'Preparation', 'Party Day', 'Done'],
     [('Party day', 14, 0)],
     [('Theme & decor plan', 'Booked', 2, 'Party day', '0', ['rc_pt_tag_client'], []),
      ('Order the cake', 'Preparation', 1, 'Party day', '1', [], []),
      ('Kids & adults menu', 'Preparation', 2, 'Party day', '0', ['rc_pt_tag_client'], []),
      ('Book entertainer / magician', 'Preparation', 1, 'Party day', '0', [], []),
      ('Setup, party service & clean-up', 'Party Day', 8, 'Party day', '1', ['rc_pt_tag_onsite'],
       ['Balloon and table setup', 'Cake cutting', 'Clean-up'])]),
    ('rc_pt_tmpl_amc', 'Coffee Machine Installation & AMC', 'admin', 6, ['rc_pt_tag_equipment', 'rc_pt_tag_recurring'], 365,
     'Install an espresso machine and grinder at the client site, train baristas and run a '
     'one-year annual maintenance contract with quarterly preventive visits.',
     ['Scheduled', 'Installation', 'Preventive Visits', 'Closed'],
     [('Machine installed', 7, 0), ('Contract year completed', 365, 0)],
     [('Delivery & installation', 'Installation', 4, 'Machine installed', '1', ['rc_pt_tag_equipment', 'rc_pt_tag_onsite'], []),
      ('Barista training (2 sessions)', 'Installation', 4, 'Machine installed', '0', [], []),
      ('Quarterly preventive maintenance', 'Preventive Visits', 8, 'Contract year completed', '0', ['rc_pt_tag_recurring'],
       ['Q1 visit - descaling & gasket check', 'Q2 visit - grinder burr check', 'Q3 visit - descaling', 'Q4 visit - full service']),
      ('Annual contract renewal call', 'Preventive Visits', 1, 'Contract year completed', '0', ['rc_pt_tag_client'], [])]),
    ('rc_pt_tmpl_masterclass', 'Cooking Masterclass', 'arjun', 3, ['rc_pt_tag_learning'], 21,
     'Plan and run a hands-on cooking masterclass: recipes, ingredients kits, promotion, session and follow-up.',
     ['Planning', 'Promotion', 'Session', 'Follow-up'],
     [('Session day', 18, 0)],
     [('Pick recipes & write handouts', 'Planning', 6, 'Session day', '1', ['rc_pt_tag_learning'], []),
      ('Ingredient kits per participant', 'Planning', 3, 'Session day', '0', [], []),
      ('Promote on website & social media', 'Promotion', 3, 'Session day', '0', [], []),
      ('Run the masterclass', 'Session', 4, 'Session day', '2', ['rc_pt_tag_learning', 'rc_pt_tag_onsite'], []),
      ('Send recipes & feedback survey', 'Follow-up', 1, 'Session day', '0', [], [])]),
]

# Service product: xid, name, price, uom ('unit'|'hour'), create on order, template xid, invoicing policy, description
PRODUCTS = [
    ('rc_pt_prod_wedding', 'Wedding Catering Management', 75000, 'unit', 'project_only', 'rc_pt_tmpl_wedding', 'ordered_prepaid',
     'End-to-end planning and execution of your wedding catering by our events team.'),
    ('rc_pt_prod_corporate', 'Corporate Lunch Contract Onboarding', 25000, 'unit', 'project_only', 'rc_pt_tmpl_corporate', 'ordered_prepaid',
     'Menu cycle design, delivery setup, trial week and monthly quality reviews.'),
    ('rc_pt_prod_kitchen', 'Kitchen Setup Consultancy', 150000, 'unit', 'task_in_project', 'rc_pt_tmpl_kitchen', 'delivered_milestones',
     'Restaurant / cloud-kitchen setup consultancy, invoiced on milestones (30% / 40% / 30%).'),
    ('rc_pt_prod_birthday', 'Birthday Party Planning', 15000, 'unit', 'project_only', 'rc_pt_tmpl_birthday', 'ordered_prepaid',
     'Theme, cake, menu, entertainment, setup and clean-up for your private party.'),
    ('rc_pt_prod_amc', 'Coffee Machine Installation & AMC (1 year)', 36000, 'unit', 'task_in_project', 'rc_pt_tmpl_amc', 'ordered_prepaid',
     'Installation, barista training and 4 preventive maintenance visits over 12 months.'),
    ('rc_pt_prod_masterclass', 'Cooking Masterclass (hours)', 2500, 'hour', 'task_in_project', 'rc_pt_tmpl_masterclass', 'delivered_timesheet',
     'Chef-led hands-on masterclass, billed on the hours logged by our chefs.'),
]

# Orders: xid, partner (xid, fallback name), lines [(product xid, qty)], state, client ref, tasks to mark done per project
ORDERS = [
    ('rc_pt_so_wedding', ('rc_partner_marina_events', 'Marina Bay Events'), [('rc_pt_prod_wedding', 1)], 'sale', 'MARINA-WED-PRJ', 3),
    ('rc_pt_so_corporate', ('rc_partner_harbour_park', 'Harbour Park Corporate'), [('rc_pt_prod_corporate', 1)], 'sale', 'HPCP-LUNCH-PRJ', 2),
    ('rc_pt_so_kitchen', ('rc_pt_partner_malabar', 'Malabar Cloud Kitchen'), [('rc_pt_prod_kitchen', 1), ('rc_pt_prod_amc', 1)],
     'sale', 'MCK-SETUP-2026', 2),
    ('rc_pt_so_birthday', ('rc_sale_partner_priya', 'Priya Raghavan'), [('rc_pt_prod_birthday', 1)], 'sale', 'BDAY-PRJ', 1),
    ('rc_pt_so_amc', ('rc_partner_nest_cowork', 'Nest Co-working'), [('rc_pt_prod_amc', 1)], 'sale', 'NEST-AMC-2026', 1),
    ('rc_pt_so_masterclass', ('rc_partner_film_society', 'Kochi Film Society'), [('rc_pt_prod_masterclass', 6)], 'sent', 'KFS-MASTERCLASS', 0),
    ('rc_pt_so_wedding_draft', ('rc_partner_grand_residency', 'Grand Residency Hotel'), [('rc_pt_prod_wedding', 1)], 'draft', 'GRH-WED-Q', 0),
]


def _enable_features(env):
    user_group = env.ref('base.group_user')
    for xid in ('project.group_project_milestone', 'project.group_project_stages'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _templates(env):
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    tags = {xid: _get_or_create(env, xid, 'project.tags', {'name': name, 'color': color}) for xid, name, color in TAGS}
    templates = {}
    for (xid, name, mgr, color, tag_xids, duration, desc, stages, milestones, tasks) in TEMPLATES:
        existing = _ref(env, xid)
        if existing:
            templates[xid] = existing
            continue
        vals = {
            'name': name, 'is_template': True, 'user_id': users[mgr].id, 'color': color,
            'description': f'<p>{desc}</p>', 'tag_ids': [Command.set([tags[t].id for t in tag_xids])],
            'date_start': today, 'date': today + timedelta(days=duration),
            'allow_milestones': True, 'allow_billable': True, 'allow_timesheets': True,
            'privacy_visibility': 'portal', 'label_tasks': 'Tasks',
            'type_ids': [Command.create({'name': s, 'sequence': i, 'fold': i == len(stages)})
                         for i, s in enumerate(stages, start=1)],
        }
        project = _bind(env, xid, env['project.project'].sudo().with_context(mail_create_nosubscribe=True).create(
            _clean(env, 'project.project', vals)))
        ms_by_name = {}
        for i, (ms_name, offset, pct) in enumerate(milestones, start=1):
            ms_by_name[ms_name] = _get_or_create(env, f'{xid}_ms_{i}', 'project.milestone', {
                'name': ms_name, 'project_id': project.id, 'deadline': today + timedelta(days=offset),
                'quantity_percentage': pct,
            })
        for i, (t_name, stage_name, hours, ms_name, prio, t_tags, subtasks) in enumerate(tasks, start=1):
            stage = project.type_ids.filtered(lambda s: s.name == stage_name)[:1]
            task = _get_or_create(env, f'{xid}_task_{i}', 'project.task', {
                'name': t_name, 'project_id': project.id, 'stage_id': stage.id, 'allocated_hours': hours,
                'milestone_id': ms_by_name[ms_name].id if ms_name in ms_by_name else False,
                'priority': prio, 'tag_ids': [Command.set([tags[t].id for t in t_tags])],
                'user_ids': [Command.set([])],
            })
            for j, sub_name in enumerate(subtasks, start=1):
                _get_or_create(env, f'{xid}_task_{i}_sub_{j}', 'project.task', {
                    'name': sub_name, 'project_id': project.id, 'parent_id': task.id, 'stage_id': stage.id,
                    'user_ids': [Command.set([])],
                })
        templates[xid] = project
    return templates


def _products(env, templates):
    Template = env['product.template']
    policies = dict(Template._fields['service_policy']._description_selection(env)) \
        if 'service_policy' in Template._fields else {}
    sale_tax = env.company.account_sale_tax_id
    categ = _ref(env, 'rc_sale_categ_catering') or _get_or_create(
        env, 'rc_pt_categ_services', 'product.category', {'name': 'Services & Projects'})
    uoms = {'unit': env.ref('uom.product_uom_unit'), 'hour': env.ref('uom.product_uom_hour')}
    prods = {}
    for (xid, name, price, uom, tracking, tmpl_xid, policy, desc) in PRODUCTS:
        if policy not in policies:  # e.g. milestones disabled or Timesheets not installed
            policy = 'ordered_prepaid'
        vals = {
            'name': name, 'type': 'service', 'list_price': price, 'standard_price': round(price * 0.55),
            'uom_id': uoms[uom].id, 'categ_id': categ.id, 'sale_ok': True, 'purchase_ok': False,
            'service_tracking': tracking, 'project_template_id': templates[tmpl_xid].id,
            'description_sale': desc, 'available_in_pos': False,
            'taxes_id': [Command.set(sale_tax.ids)],
        }
        prod = _get_or_create(env, xid, 'product.template', vals)
        if prod.service_policy != policy and 'service_policy' in prod._fields:
            prod.service_policy = policy
        prods[xid] = prod
    return prods


def _partner(env, xid, name):
    partner = _ref(env, xid)
    if partner:
        return partner
    own_xid = xid if xid.startswith('rc_pt_') else f'rc_pt_{xid}'
    return _get_or_create(env, own_xid, 'res.partner', {
        'name': name, 'is_company': True, 'city': 'Kochi', 'country_id': env.ref('base.in').id,
        'email': f"{name.lower().replace(' ', '.')}@example.com",
    })


TEMPLATE_TASK_NAMES = {t[0]: [task[0] for task in t[9]] for t in TEMPLATES}


def _complete_tasks(project, template_xid, count):
    """Mark the first ``count`` tasks of the template (in template order) done, then reach the
    milestones whose tasks are all done (copies do not keep the template's task order)."""
    names = TEMPLATE_TASK_NAMES.get(template_xid, [])[:count]
    tasks = project.tasks.filtered(lambda t: not t.parent_id and t.milestone_id)
    done = tasks.filtered(lambda t: t.name in names)
    if done:
        done.write({'state': '1_done'})
        done.child_ids.write({'state': '1_done'})
    for ms in project.milestone_ids:
        ms_tasks = tasks.filtered(lambda t: t.milestone_id == ms)
        if ms_tasks and all(t.state == '1_done' for t in ms_tasks):
            ms.is_reached = True


def _orders(env, prods):
    users = _users(env)
    team = _ref(env, 'rc_team_catering_events') or env.ref('sales_team.team_sales_department', raise_if_not_found=False)
    tmpl_by_id = {_ref(env, t[0]).id: t[0] for t in TEMPLATES if _ref(env, t[0])}
    for i, (xid, (pxid, pname), lines, state, ref, done_count) in enumerate(ORDERS):
        if _ref(env, xid):
            continue
        partner = _partner(env, pxid, pname)
        vals = {
            'partner_id': partner.id, 'user_id': users['arjun' if i % 2 == 0 else 'admin'].id,
            'client_order_ref': ref,
            # "<product>\n<description>": the task created for a "Project & Task" product is named after the product
            'order_line': [Command.create({'product_id': prods[p].product_variant_id.id, 'product_uom_qty': q,
                                           'name': f'{prods[p].name}\n{prods[p].description_sale or ""}'.strip()})
                           for p, q in lines],
        }
        if team:
            vals['team_id'] = team.id
        order = _bind(env, xid, env['sale.order'].sudo().with_context(
            mail_create_nosubscribe=True, tracking_disable=True).create(vals))
        if state == 'sent':
            order.action_quotation_sent()
        elif state == 'sale':
            order.with_context(send_email=False).action_confirm()
            for n, line in enumerate(order.order_line.filtered('project_id'), start=1):
                _bind(env, f'{xid}_project_{n}', line.project_id)
                _complete_tasks(line.project_id, tmpl_by_id.get(line.product_id.project_template_id.id), done_count)


def load_project_template_suite_demo_data(env):
    if 'project.project' not in env or 'project_template_id' not in env['product.template']._fields:
        _logger.info("Hudson POS: Sales/Project link (sale_project) not installed, skipping project templates demo.")
        return
    ctx = {}
    steps = [
        ('features', lambda: _enable_features(env)),
        ('templates', lambda: ctx.update(templates=_templates(env))),
        ('products', lambda: ctx.update(prods=_products(env, ctx['templates']))),
        ('orders', lambda: _orders(env, ctx['prods'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Project template demo step '%s' failed: %s", name, e)
            return
    _logger.info("Hudson POS: Resto Cafe project templates, service products and sales orders loaded.")
