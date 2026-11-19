# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Project & Timesheet demo data.

Idempotent: every record is bound to an xmlid of this module (prefix ``rc_prj_``).
  * 8 colourful projects (renovation, Onam menu launch, Marina Bay wedding execution, central
    kitchen expansion, website revamp, monsoon food festival, staff training academy, zero-waste
    kitchen) with their own stages, 13 coloured tags, milestones, sub-tasks, dependencies,
    1-3 star priorities, deadlines, assignees, colour-coded tasks, kanban cover pictures and a
    history of On Track / At Risk / Off Track / On Hold / Complete status updates
  * The wedding project is billed on timesheets: a "Event Coordination (hours)" service line on the
    Sales suite's confirmed Marina Bay order; logged hours become billable/delivered quantity
  * ~6 weeks of daily timesheets (Mon-Sat, up to today) for every project team, Administrator included
  * Personal to-dos (project_todo)
Fields that the installed apps do not provide (e.g. ``allow_timesheets`` without Timesheets) are
skipped, so the projects and tasks load with or without Timesheets.
"""
import logging
from datetime import timedelta

from odoo import Command, fields
from odoo.tools import file_open

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
    """Drop values for fields the installed apps do not provide (e.g. ``allow_timesheets`` only
    exists with Timesheets): one missing field must not abort the whole Project demo."""
    fields_ = env[model]._fields
    return {k: v for k, v in vals.items() if k in fields_}


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(_clean(env, model, vals)))


TAGS = [('rc_prj_tag_kitchen', 'Kitchen', 1), ('rc_prj_tag_marketing', 'Marketing', 2), ('rc_prj_tag_event', 'Event', 3),
        ('rc_prj_tag_urgent', 'Urgent', 4), ('rc_prj_tag_vendor', 'Vendor', 5), ('rc_prj_tag_it', 'IT', 6),
        ('rc_prj_tag_compliance', 'Compliance', 7), ('rc_prj_tag_design', 'Design', 8),
        ('rc_prj_tag_festival', 'Festival', 9), ('rc_prj_tag_training', 'Training', 11), ('rc_prj_tag_hr', 'HR', 6),
        ('rc_prj_tag_sustain', 'Sustainability', 10), ('rc_prj_tag_finance', 'Finance', 3)]

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
    ('rc_prj_monsoon', 'Monsoon Food Festival 2026', 'admin', None, 3, ['rc_prj_tag_festival', 'rc_prj_tag_kitchen', 'rc_prj_tag_marketing'], -15, 25,
     'In Progress', 'A two-week rainy-season festival: kappa & karimeen, hot pazhampori, rain-themed decor and live music.',
     ['Lakshmi Iyer', 'Gokul Krishna', 'Anjali Das', 'Faisal Ahmed', 'Administrator'], None,
     ('on_track', 40, 'Menu locked and tasted; decor and promotion running on schedule.')),
    ('rc_prj_academy', 'Staff Training Academy', 'arjun', None, 5, ['rc_prj_tag_training', 'rc_prj_tag_hr'], -35, 45,
     'In Progress', 'In-house academy for baristas, servers and cooks: curriculum, micro-videos, hygiene certification and mentoring.',
     ['Deepa Krishnan', 'Manoj Pillai', 'Reshma Babu', 'Nikhil Raj'], None,
     ('at_risk', 50, 'Video recording is behind: two trainers on leave. Hygiene batch 1 still on track.')),
    ('rc_prj_green', 'Zero-Waste Green Kitchen', 'admin', None, 10, ['rc_prj_tag_sustain', 'rc_prj_tag_kitchen', 'rc_prj_tag_compliance'], -50, 30,
     'In Progress', 'Cut food waste by 40% and remove single-use plastic: waste audit, composting, leaf packaging and solar hot water.',
     ['Sabu Thomas', 'Thomas Mathew', 'Ajay Menon', 'Fathima Rasheed', 'Administrator'], None,
     ('on_track', 75, 'Composter running; food waste already down 28% against the baseline.')),
]

# milestones: project xid, name, deadline offset, reached
MILESTONES = [
    ('rc_prj_rooftop', 'Design approved', -25, True), ('rc_prj_rooftop', 'Civil & electrical complete', 10, False),
    ('rc_prj_rooftop', 'Soft opening', 35, False),
    ('rc_prj_onam', 'Menu finalised', -10, True), ('rc_prj_onam', 'Launch day', 10, False),
    ('rc_prj_wedding', 'Menu & headcount confirmed', -8, True), ('rc_prj_wedding', 'Event day', 12, False),
    ('rc_prj_central_kitchen', 'FSSAI approval', 15, False), ('rc_prj_central_kitchen', 'Equipment installed', 50, False),
    ('rc_prj_website', 'Pages redesigned', -5, True), ('rc_prj_website', 'Online ordering go-live', 20, False),
    ('rc_prj_monsoon', 'Menu locked', -6, True), ('rc_prj_monsoon', 'Festival opening', 12, False),
    ('rc_prj_academy', 'Curriculum ready', -18, True), ('rc_prj_academy', 'First batch certified', 20, False),
    ('rc_prj_green', 'Waste baseline', -28, True), ('rc_prj_green', 'Plastic-free kitchen', 15, False),
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
    # Monsoon festival
    ('rc_prj_t_mon_menu', 'rc_prj_monsoon', 'Curate 12-dish monsoon menu (kappa, karimeen, pazhampori)', 'Done', ['admin'], '2', -8, ['rc_prj_tag_kitchen'], 'Menu locked', 10, None, []),
    ('rc_prj_t_mon_decor', 'rc_prj_monsoon', 'Rain-themed decor & lighting', 'In Progress', ['arjun'], '1', 5, ['rc_prj_tag_design'], 'Festival opening', 14, None, []),
    ('rc_prj_t_mon_promo', 'rc_prj_monsoon', 'Instagram reels & influencer tasting', 'In Progress', ['admin'], '2', 4, ['rc_prj_tag_marketing'], 'Festival opening', 8, None, ['rc_prj_t_mon_menu']),
    ('rc_prj_t_mon_pos', 'rc_prj_monsoon', 'Festival combo pricing in POS', 'Review', ['admin'], '1', 6, ['rc_prj_tag_it'], 'Festival opening', 5, None, ['rc_prj_t_mon_menu']),
    ('rc_prj_t_mon_fish', 'rc_prj_monsoon', 'Confirm fresh-fish supplier (daily 6 a.m.)', 'To Do', ['arjun'], '3', 3, ['rc_prj_tag_vendor', 'rc_prj_tag_urgent'], 'Festival opening', 3, None, []),
    ('rc_prj_t_mon_music', 'rc_prj_monsoon', 'Book live chenda & fusion band', 'Backlog', ['arjun'], '0', 15, ['rc_prj_tag_event'], 'Festival opening', 2, None, []),
    # Training academy
    ('rc_prj_t_aca_curriculum', 'rc_prj_academy', 'Design barista & service curriculum', 'Done', ['arjun'], '1', -20, ['rc_prj_tag_training'], 'Curriculum ready', 16, None, []),
    ('rc_prj_t_aca_videos', 'rc_prj_academy', 'Record 10 micro-learning videos', 'In Progress', ['admin'], '2', 7, ['rc_prj_tag_training', 'rc_prj_tag_design'], 'First batch certified', 20, None, ['rc_prj_t_aca_curriculum']),
    ('rc_prj_t_aca_hygiene', 'rc_prj_academy', 'Food hygiene certification - batch 1', 'In Progress', ['arjun'], '3', 2, ['rc_prj_tag_compliance', 'rc_prj_tag_urgent'], 'First batch certified', 12, None, []),
    ('rc_prj_t_aca_quiz', 'rc_prj_academy', 'Online quizzes in eLearning', 'Review', ['admin'], '0', 10, ['rc_prj_tag_it'], 'First batch certified', 6, None, ['rc_prj_t_aca_curriculum']),
    ('rc_prj_t_aca_mentors', 'rc_prj_academy', 'Assign mentors to new joiners', 'To Do', ['arjun'], '1', 14, ['rc_prj_tag_hr'], 'First batch certified', 4, None, ['rc_prj_t_aca_videos']),
    ('rc_prj_t_aca_feedback', 'rc_prj_academy', 'Trainee feedback survey', 'Backlog', ['admin'], '0', 30, ['rc_prj_tag_hr'], 'First batch certified', 3, None, []),
    # Zero-waste kitchen
    ('rc_prj_t_grn_audit', 'rc_prj_green', 'Food-waste audit (2 weeks of weighing)', 'Done', ['admin'], '1', -30, ['rc_prj_tag_sustain'], 'Waste baseline', 18, None, []),
    ('rc_prj_t_grn_compost', 'rc_prj_green', 'Install on-site composter', 'Done', ['arjun'], '2', -12, ['rc_prj_tag_sustain', 'rc_prj_tag_vendor'], 'Plastic-free kitchen', 10, None, ['rc_prj_t_grn_audit']),
    ('rc_prj_t_grn_packaging', 'rc_prj_green', 'Switch to areca-leaf takeaway packaging', 'In Progress', ['admin'], '2', 6, ['rc_prj_tag_sustain', 'rc_prj_tag_vendor'], 'Plastic-free kitchen', 8, None, []),
    ('rc_prj_t_grn_solar', 'rc_prj_green', 'Solar water heater quotation', 'Review', ['admin'], '0', 12, ['rc_prj_tag_finance'], 'Plastic-free kitchen', 4, None, []),
    ('rc_prj_t_grn_menu', 'rc_prj_green', 'Zero-waste specials (peel & stem recipes)', 'To Do', ['arjun'], '1', 18, ['rc_prj_tag_kitchen', 'rc_prj_tag_sustain'], 'Plastic-free kitchen', 6, None, ['rc_prj_t_grn_packaging']),
    ('rc_prj_t_grn_report', 'rc_prj_green', 'Monthly sustainability report', 'Backlog', ['admin'], '0', 28, ['rc_prj_tag_finance'], 'Plastic-free kitchen', 3, None, []),
]

# Kanban colour stripe per task: urgent = red, done = green, review = yellow, in progress = light blue,
# to do = dark blue, backlog = salmon (Odoo colour indexes)
def _task_color(stage_name, tag_xids):
    if 'rc_prj_tag_urgent' in tag_xids:
        return 1
    return {'Done': 10, 'Review': 3, 'In Progress': 4, 'To Do': 8}.get(stage_name, 6)


# In-progress tasks shown with the orange "Changes Requested" state
CHANGES_REQUESTED = {'rc_prj_t_wed_logistics', 'rc_prj_t_aca_videos', 'rc_prj_t_mon_decor'}

# Cover pictures on kanban cards (public images shipped with Odoo)
COVERS = {
    'rc_prj_t_onam_menu': 'pos_restaurant/static/img/food_category.jpg',
    'rc_prj_t_onam_photo': 'pos_restaurant/static/img/th-pasta-4f.png',
    'rc_prj_t_roof_furniture': 'mass_mailing_themes/static/src/img/theme_coffeebreak/s_default_image_block_banner.jpg',
    'rc_prj_t_wed_layout': 'pos_restaurant/static/img/floor_main.jpeg',
    'rc_prj_t_mon_menu': 'pos_restaurant/static/img/th-burger.png',
    'rc_prj_t_mon_promo': 'pos_restaurant/static/img/product_mojito.png',
    'rc_prj_t_mon_pos': 'pos_restaurant/static/img/th-pizza-fu.png',
    'rc_prj_t_aca_curriculum': 'pos_restaurant/static/img/th-espresso.png',
    'rc_prj_t_grn_menu': 'pos_restaurant/static/img/drink_category.jpg',
}

# Earlier status updates (days ago, status, progress %, text): a coloured history on each project
UPDATE_HISTORY = {
    'rc_prj_rooftop': [(23, 'on_track', 20, 'Design approved by management; vendor shortlist ready.'),
                       (12, 'on_track', 40, 'Pergola order placed; civil work started.')],
    'rc_prj_onam': [(20, 'on_track', 30, 'Draft menu of 26 dishes ready for costing.'),
                    (9, 'at_risk', 55, 'Banana-leaf supplier short on volume; backup vendor being onboarded.')],
    'rc_prj_wedding': [(14, 'on_track', 20, 'Contract signed and advance received.'),
                       (7, 'on_track', 35, 'Menu tasting with the couple went well.')],
    'rc_prj_central_kitchen': [(40, 'on_track', 15, 'Layout drawings approved.'),
                               (16, 'at_risk', 25, 'FSSAI asked for revised drainage drawings.')],
    'rc_prj_website': [(18, 'on_hold', 30, 'Paused one week for the Onam campaign.'),
                       (8, 'on_track', 50, 'Design system done; pages being rebuilt.')],
    'rc_prj_monsoon': [(10, 'on_track', 20, 'Festival concept approved; menu tasting scheduled.')],
    'rc_prj_academy': [(25, 'on_track', 25, 'Curriculum signed off by the head chef.'),
                       (11, 'on_track', 40, 'First 4 videos recorded.')],
    'rc_prj_green': [(35, 'on_track', 30, 'Two-week waste audit completed: 42 kg/day baseline.'),
                     (14, 'done', 60, 'Composter installed and running - milestone complete.')],
}

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
    valid_service_type = 'timesheet' if 'timesheet' in dict(env['product.template']._fields['service_type'].selection) else 'manual'
    product = _get_or_create(env, 'rc_prj_prod_coordination', 'product.product', {
        'name': 'Event Coordination (hours)', 'type': 'service', 'list_price': 1500, 'standard_price': 600,
        'uom_id': env.ref('uom.product_uom_hour').id, 'invoice_policy': 'delivery', 'service_type': valid_service_type,
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
            'allow_milestones': True, 'allow_task_dependencies': True,
            'privacy_visibility': 'portal' if partner else 'employees', 'label_tasks': 'Tasks',
            'type_ids': stage_ids,
            'favorite_user_ids': [Command.link(users['admin'].id)],
        }
        if 'allow_timesheets' in env['project.project']._fields:
            vals['allow_timesheets'] = True
        if partner:
            vals['partner_id'] = partner.id
        if pstage in pstages:
            vals['stage_id'] = pstages[pstage].id
        project = _bind(env, xid, env['project.project'].sudo().with_context(mail_create_nosubscribe=True).create(
            _clean(env, 'project.project', vals)))
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
        vals['color'] = _task_color(stage_name, tag_xids)
        task = _bind(env, xid, env['project.task'].sudo().with_context(mail_create_nosubscribe=True).create(
            _clean(env, 'project.task', vals)))
        if stage_name == 'Done':
            task.state = '1_done'
        elif stage_name == 'Review':
            task.state = '03_approved' if prio == '0' else '02_changes_requested'
        elif xid in CHANGES_REQUESTED:
            task.state = '02_changes_requested'
        _set_cover(env, task, xid, COVERS.get(xid))
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


def _set_cover(env, task, task_xid, path):
    """Attach a public Odoo image to the task and show it as the kanban card cover."""
    if not path or 'displayed_image_id' not in task._fields or task.displayed_image_id:
        return
    xid = f'{task_xid}_cover'
    if _ref(env, xid):
        return
    try:
        with file_open(path, 'rb') as f:
            data = f.read()
    except (OSError, ValueError):
        return  # the app providing the picture is not installed
    mimetype = 'image/png' if path.endswith('.png') else 'image/jpeg'
    attachment = _bind(env, xid, env['ir.attachment'].sudo().create({
        'name': path.rsplit('/', 1)[-1], 'raw': data, 'mimetype': mimetype,
        'res_model': 'project.task', 'res_id': task.id,
    }))
    task.displayed_image_id = attachment


def _update_history(env, projects):
    """Older status updates, so each project shows a coloured status timeline."""
    users = _users(env)
    today = fields.Date.context_today(env['res.users'])
    managers = {p[0]: p[2] for p in PROJECTS}
    for pxid, entries in UPDATE_HISTORY.items():
        if pxid not in projects:
            continue
        for i, (days_ago, status, progress, text) in enumerate(entries, start=1):
            _get_or_create(env, f'{pxid}_update_h{i}', 'project.update', {
                'name': f'Status update - week of {(today - timedelta(days=days_ago)).strftime("%d %b")}',
                'project_id': projects[pxid].id, 'status': status, 'progress': progress,
                'date': today - timedelta(days=days_ago), 'user_id': users[managers[pxid]].id,
                'description': f'<p>{text}</p>',
            })
    # the latest update (created by _updates) must stay the project's current status
    for pxid, project in projects.items():
        latest = _ref(env, f'{pxid}_update')
        if latest and 'last_update_id' in project._fields and project.last_update_id != latest:
            project.sudo().last_update_id = latest


# Activity texts per kind of work, used to describe timesheet lines
TIMESHEET_TEXTS_BY_TAG = {
    'rc_prj_tag_kitchen': ['Recipe trials', 'Tasting with chefs', 'Prep-line rehearsal', 'Plating photos'],
    'rc_prj_tag_marketing': ['Content shoot', 'Social media planning', 'Copywriting', 'Campaign review'],
    'rc_prj_tag_vendor': ['Vendor call', 'Quote comparison', 'Procurement follow-up', 'Delivery check'],
    'rc_prj_tag_it': ['Configuration', 'Testing on tablets', 'Bug fixing', 'User walkthrough'],
    'rc_prj_tag_design': ['Design review', 'Mood board', 'Layout drawing', 'Site measurement'],
    'rc_prj_tag_compliance': ['Documentation', 'Inspection prep', 'SOP writing', 'Licence follow-up'],
    'rc_prj_tag_training': ['Trainer session', 'Video recording', 'Assessment', 'Coaching on the floor'],
    'rc_prj_tag_hr': ['One-to-one', 'Onboarding', 'Survey design', 'Roster planning'],
    'rc_prj_tag_sustain': ['Waste weighing', 'Composter check', 'Supplier sampling', 'Data entry'],
    'rc_prj_tag_finance': ['Cost analysis', 'Budget review', 'Report preparation'],
    'rc_prj_tag_event': ['Event planning', 'Client meeting', 'Site visit & coordination'],
}
TIMESHEET_HOURS = [2.0, 1.5, 3.0, 0.5, 4.0, 2.5, 1.0, 3.5, 2.0, 1.5]


def _timesheets(env, projects, tasks):
    """~6 weeks of daily timesheets (Mon-Sat) for every project team, including today, so the
    Timesheets grid, 'My Timesheets' (Administrator) and the project/task reports are well filled.
    Deterministic, at most 8 h per employee and day."""
    if _ref(env, 'rc_prj_tsx_1'):
        return
    today = fields.Date.context_today(env['res.users'])
    Employee = env['hr.employee'].sudo()
    by_project = {}
    for (xid, pxid, *_r) in TASKS:
        task = tasks.get(xid)
        if task and task.stage_id.name != 'Backlog':
            by_project.setdefault(pxid, []).append((xid, task))
    task_tags = {t[0]: t[7] for t in TASKS}
    booked = {}
    vals_list = []
    for p_idx, (pxid, _n, _m, _p, _c, _t, start, _e, _s, _d, emp_names, _so, _u) in enumerate(PROJECTS):
        project = projects.get(pxid)
        ptasks = by_project.get(pxid, [])
        if not project or not ptasks:
            continue
        emps = Employee.browse()
        for name in emp_names:  # one employee per name (names can repeat)
            emps |= Employee.search([('name', '=', name)], limit=1)
        first_day = max(start, -41)
        for d in range(0, -first_day + 1):
            day = today - timedelta(days=d)
            if day.weekday() == 6:  # closed on Sundays
                continue
            for e_idx, emp in enumerate(emps):
                if (d * 7 + e_idx * 3 + p_idx) % 5 == 0:  # ~1 day in 5 off this project
                    continue
                hours = TIMESHEET_HOURS[(d + e_idx * 2 + p_idx) % len(TIMESHEET_HOURS)]
                used = booked.get((emp.id, day), 0.0)
                hours = min(hours, 8.0 - used)
                if hours <= 0:
                    continue
                booked[(emp.id, day)] = used + hours
                txid, task = ptasks[(d + e_idx) % len(ptasks)]
                texts = next((TIMESHEET_TEXTS_BY_TAG[t] for t in task_tags.get(txid, []) if t in TIMESHEET_TEXTS_BY_TAG),
                             TIMESHEET_TEXTS)
                vals_list.append({
                    'name': texts[(d + e_idx) % len(texts)], 'project_id': project.id, 'task_id': task.id,
                    'employee_id': emp.id, 'unit_amount': hours, 'date': day,
                })
    lines = env['account.analytic.line'].sudo().create(vals_list)
    env['ir.model.data'].sudo().create([{
        'module': MODULE, 'name': f'rc_prj_tsx_{n}', 'model': 'account.analytic.line', 'res_id': line.id, 'noupdate': True,
    } for n, line in enumerate(lines, start=1)])
    _logger.info("Hudson POS: %s demo timesheet lines created.", len(lines))


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
        ('update history', lambda: _update_history(env, ctx['projects'])),
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
