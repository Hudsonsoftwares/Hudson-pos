# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Visitor Management demo data (eh_hr_visitor).

Front-desk visitor log of the MG Road restaurant and the Central Kitchen goods gate. Created
idempotently (xmlids prefixed ``rc_vis_``), only for the main Resto Cafe company:

  * 4 extra visit purposes (food safety inspection, supplier tasting, event planning, equipment service)
  * 4 meeting rooms (private dining room, manager's office, tasting kitchen, rooftop lounge)
  * 2 front-desk stations (main reception with drinks, central kitchen goods gate)
  * 18 visitors in every status - checked out (incl. an auto check-out), checked in now, arrived and
    waiting, confirmed / invited / pending pre-registrations, a draft, a cancelled and an expired invite

Visitors are written straight into their final state (no kiosk flow), so no host e-mails are sent.
Photos, signatures and agreement PDFs are binaries and are not generated here; visitors whose purpose
needs an NDA are kept in the Pending state, where the agreement may still be open.
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
TZ = pytz.timezone('Asia/Kolkata')
CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_auto_subscribe_no_notify': True, 'mail_notify_noemail': True}

PURPOSES = [  # xid, name, code, sequence, nda, photo
    ('rc_vis_purpose_inspection', 'Safety & Licence Inspection', 'safety_inspection', 5, False, False),
    ('rc_vis_purpose_tasting', 'Supplier Tasting / Sampling', 'supplier_tasting', 6, False, False),
    ('rc_vis_purpose_event', 'Event & Catering Planning', 'event_planning', 7, False, False),
    ('rc_vis_purpose_service', 'Equipment Service Visit', 'equipment_service', 8, True, False),
]
ROOMS = [
    ('rc_vis_room_private', 'Backwater Private Dining Room'),
    ('rc_vis_room_office', "Manager's Office (1st floor)"),
    ('rc_vis_room_tasting', 'Tasting Kitchen'),
    ('rc_vis_room_rooftop', 'Rooftop Lounge'),
]
# standard purposes / drinks shipped by eh_hr_visitor, looked up by code / name
STD_PURPOSE = {'meeting': 'meeting', 'delivery': 'delivery', 'contractor': 'contractor', 'interview': 'interview'}

# day = offset from today, h = local start hour, dur = hours
VISITORS = [
    # ---- checked out (past)
    dict(xid='rc_vis_v01', name='Ravi Shankar', org='Commissionerate of Food Safety, Kerala', designation='Food Safety Officer',
         email='ravi.shankar@foodsafety.example.in', phone='+91 94470 11223', type='Government', purpose='rc_vis_purpose_inspection',
         host='Suresh Kumar', room='rc_vis_room_office', station='main', drink='Water', day=-12, h=10, dur=1.5,
         state='signed_out', reg='walk-in', city='Thiruvananthapuram', notes='Routine FSSAI licence inspection - kitchen hygiene rated "Excellent".'),
    dict(xid='rc_vis_v02', name='Meera Nair', org='Malabar Coffee Estates', designation='Key Account Manager',
         email='meera.nair@malabarcoffee.example.com', phone='+91 98950 44120', type='Vendor', purpose='rc_vis_purpose_tasting',
         host='Priya Menon', room='rc_vis_room_tasting', station='main', drink='Coffee', day=-9, h=15, dur=1.25,
         state='signed_out', reg='pre-registered', city='Wayanad', meeting='Single-estate Arabica cupping session',
         notes='Brought 3 new single-estate lots for the filter-coffee menu.'),
    dict(xid='rc_vis_v03', name='Joseph Kurian', org='Kerala Fresh Farms', designation='Delivery Supervisor',
         phone='+91 97450 30981', type='Delivery', purpose='delivery', host='Rahul Nair', station='kitchen',
         day=-7, h=7.5, dur=0.35, state='signed_out', reg='walk-in', city='Kochi',
         notes='Morning vegetable & herb delivery to the Central Kitchen cold room.'),
    dict(xid='rc_vis_v04', name='Biju Mathew', org='CoolTech Refrigeration Services', designation='Senior Technician',
         email='service@cooltech.example.in', phone='+91 90370 55812', type='Contractor', purpose='rc_vis_purpose_service',
         host='Thomas Mathew', station='kitchen', day=-6, h=9, dur=3.5, state='signed_out', reg='pre-registered',
         city='Kochi', meeting='Walk-in cold room compressor service',
         notes='Replaced the condenser fan motor; cold room back to 2 °C.'),
    dict(xid='rc_vis_v05', name='Aswathy Menon', org=False, designation='Barista candidate',
         email='aswathy.menon@example.com', phone='+91 81290 66340', type='Interview', purpose='meeting',
         host='Priya Menon', room='rc_vis_room_tasting', station='main', drink='Water', day=-5, h=11, dur=0.75,
         state='signed_out', reg='pre-registered', city='Kochi', meeting='Barista interview - latte art practical'),
    dict(xid='rc_vis_v06', name='Rohan Varghese', org='Wedding client (Marina Bay)', designation='Groom',
         email='rohan.varghese@example.com', phone='+91 99460 77125', type='Customer', purpose='rc_vis_purpose_event',
         host='Suresh Kumar', room='rc_vis_room_private', station='main', drink='Juice', day=-4, h=17, dur=1.2,
         state='signed_out', reg='pre-registered', vip=True, city='Kochi', meeting='Wedding reception menu tasting - 350 guests',
         notes='Finalised the Kerala sadya + live counter menu; family of 4 attended.'),
    dict(xid='rc_vis_v07', name='Prakash Menon', org='Hindustan Beverages Distributors', designation='Route Salesman',
         phone='+91 94950 21876', type='Delivery', purpose='delivery', host='Arun Varma', station='kitchen',
         day=-3, h=14, dur=0, state='signed_out', reg='walk-in', auto=True, city='Kochi',
         notes='Forgot to sign out - closed by the end-of-day auto check-out.'),
    dict(xid='rc_vis_v08', name='Divya Raghavan', org='BlueWave Technologies', designation='Admin & Facilities Head',
         email='divya.r@bluewave.example.com', phone='+91 98470 33019', type='Customer', purpose='rc_vis_purpose_event',
         host='Suresh Kumar', room='rc_vis_room_private', station='main', drink='Coffee', day=-2, h=12.5, dur=1,
         state='signed_out', reg='pre-registered', vip=True, city='Kochi', meeting='Corporate lunch-box contract renewal (220 meals/day)'),
    # ---- today
    dict(xid='rc_vis_v09', name='Harish Pai', org='Coastal Kitchen Equipments', designation='Field Engineer',
         email='harish.pai@coastalkitchen.example.in', phone='+91 90480 77311', type='Contractor', purpose='contractor',
         host='Thomas Mathew', station='kitchen', day=0, h=-2, dur=3, state='signed_in', reg='pre-registered', city='Kochi',
         meeting='Combi oven annual service', parking=True, nda=True),
    dict(xid='rc_vis_v10', name='Lekha Suresh', org='Nest Coworking Spaces', designation='Community Manager',
         email='lekha@nestcowork.example.com', phone='+91 97440 81236', type='Customer', purpose='meeting',
         host='Suresh Kumar', room='rc_vis_room_office', station='main', drink='Tea', day=0, h=-0.5, dur=1,
         state='signed_in', reg='pre-registered', city='Kochi', meeting='Coffee machine AMC & monthly catering review'),
    dict(xid='rc_vis_v11', name="Kevin D'Souza", org='Kochi Food Bloggers Club', designation='Food Blogger',
         email='kevin.dsouza@example.com', phone='+91 88910 45127', type='Guest', purpose='meeting',
         host='Ananya Sharma', station='main', drink='Coffee', day=0, h=-0.1, dur=1, state='arrived', reg='walk-in',
         city='Kochi', notes='Waiting at reception for the chef\'s table preview.'),
    dict(xid='rc_vis_v12', name='Nandana Pillai', org=False, designation='Server candidate',
         email='nandana.pillai@example.com', phone='+91 79070 12984', type='Interview', purpose='meeting',
         host='Thomas Mathew', room='rc_vis_room_office', station='main', day=0, h=4, dur=0.75,
         state='confirmed', reg='pre-registered', city='Aluva', meeting='Interview - Server (Service & Hospitality)'),
    # ---- upcoming
    dict(xid='rc_vis_v13', name='Sanjay Kurup', org='Spice Route Travels', designation='Operations Director',
         email='sanjay.kurup@spiceroute.example.com', phone='+91 98460 55408', type='Customer', purpose='rc_vis_purpose_event',
         host='Suresh Kumar', room='rc_vis_room_rooftop', station='main', day=1, h=11, dur=1,
         state='invitation_sent', reg='pre-registered', city='Kochi', meeting='Year-end team dinner for 80 - rooftop buy-out'),
    dict(xid='rc_vis_v14', name='Station Officer K. Rajan', org='Kerala Fire & Rescue Services', designation='Station Officer',
         phone='+91 484 2370 101', type='Government', purpose='rc_vis_purpose_inspection', host='Thomas Mathew',
         station='main', day=2, h=10, dur=1.5, state='confirmed', reg='pre-registered', city='Kochi',
         meeting='Annual fire-safety audit & NOC renewal'),
    dict(xid='rc_vis_v15', name='Arjun Babu', org=False, designation='Sous Chef candidate',
         email='arjun.babu@example.com', phone='+91 95620 44871', type='Interview', purpose='interview',
         host='Rahul Nair', room='rc_vis_room_tasting', station='main', day=3, h=15, dur=1.5, state='pending',
         reg='pre-registered', city='Thrissur', meeting='Sous Chef trial - live cooking round', nda=True),
    dict(xid='rc_vis_v16', name='Meera Nair', org='Malabar Coffee Estates', designation='Key Account Manager',
         email='meera.nair@malabarcoffee.example.com', phone='+91 98950 44120', type='Vendor', purpose='rc_vis_purpose_tasting',
         host='Priya Menon', room='rc_vis_room_tasting', station='main', day=6, h=15, dur=1, state='draft',
         reg='pre-registered', city='Wayanad', meeting='Follow-up cupping - winter blend'),
    # ---- cancelled / expired
    dict(xid='rc_vis_v17', name='Dr. Anitha Joseph', org='GreenLeaf Multispecialty Hospital', designation='Procurement Head',
         email='anitha.joseph@greenleaf.example.org', phone='+91 94470 90213', type='Customer', purpose='meeting',
         host='Lakshmi Iyer', room='rc_vis_room_office', station='main', day=-1, h=11, dur=1, state='cancelled',
         reg='pre-registered', city='Kochi', meeting='Cafeteria catering tender clarification',
         notes='Cancelled by the visitor - rescheduled to a video call.'),
    dict(xid='rc_vis_v18', name='Vinod Thampi', org='Kerala Tourism Promotion Council', designation='Deputy Manager',
         email='vinod.thampi@example.org', phone='+91 94460 31872', type='Government', purpose='rc_vis_purpose_event',
         host='Suresh Kumar', station='main', day=-8, h=16, dur=1, state='expired', reg='pre-registered',
         city='Thiruvananthapuram', meeting='Onam food festival partnership'),
]


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


def _dt(today, day, hour):
    """Local Kochi time -> naive UTC. A negative ``hour`` with day=0 means 'hours before now'."""
    if day == 0 and hour <= 0:
        return fields.Datetime.now().replace(microsecond=0) + timedelta(hours=hour)
    d = today + timedelta(days=day)
    local = TZ.localize(datetime.combine(d, time(int(hour), int(round((hour % 1) * 60)))))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def load_visitor_suite_demo_data(env):
    if 'eh.hr.visitor' not in env:
        _logger.info("Visitor Management (eh_hr_visitor) not installed - skipping visitor demo data")
        return
    company = env.company
    co_domain = [('company_id', 'in', (company.id, False))]
    Employee = env['hr.employee'].sudo()

    def emp(name):
        return Employee.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)

    purposes = {}
    for xid, name, code, seq, nda, photo in PURPOSES:
        purposes[xid] = _get_or_create(env, xid, 'eh.hr.visitor.purpose', {
            'name': name, 'code': code, 'sequence': seq, 'nda_required': nda, 'photo_required': photo,
            'company_id': company.id,
        }, search=[('code', '=', code)] + co_domain)
    for code in STD_PURPOSE.values():
        p = env['eh.hr.visitor.purpose'].sudo().search([('code', '=', code)] + co_domain, limit=1)
        if p:
            purposes[code] = p

    rooms = {xid: _get_or_create(env, xid, 'eh.hr.meeting.room', {'name': name, 'company_id': company.id},
                                 search=[('name', '=', name)] + co_domain) for xid, name in ROOMS}
    Drink = env['eh.hr.visitor.drink'].sudo()
    drinks = {d.name: d for d in Drink.search(co_domain)}

    reception = emp('Sneha Pillai')
    managers = emp('Suresh Kumar') | emp('Thomas Mathew')
    stations = {
        'main': _get_or_create(env, 'rc_vis_station_main', 'eh.hr.visitor.station', {
            'name': 'Main Reception - MG Road Restaurant',
            'company_id': company.id,
            'responsible_employee_ids': [Command.set((reception | managers).ids)],
            'host_selection': True,
            'field_email': 'optional', 'field_phone': 'required', 'field_organization': 'optional',
            'self_checkin': True,
            'offer_drinks': True,
            'drink_ids': [Command.set(Drink.search([('name', 'in', ['Coffee', 'Tea', 'Water', 'Juice'])] + co_domain).ids)],
            'notify_email': True, 'notify_discuss': True,
            'theme': 'light',
            'side_message': '<h3>Welcome to Resto Cafe Solutions</h3>'
                            '<p>Please sign in and we will let your host know you are here. '
                            'Enjoy a cup of our single-estate filter coffee while you wait.</p>',
        }),
        'kitchen': _get_or_create(env, 'rc_vis_station_kitchen', 'eh.hr.visitor.station', {
            'name': 'Central Kitchen - Goods & Service Gate',
            'company_id': company.id,
            'responsible_employee_ids': [Command.set((emp('Rahul Nair') | emp('Arun Varma') | emp('Thomas Mathew')).ids)],
            'allowed_host_employee_ids': [Command.set((emp('Rahul Nair') | emp('Arun Varma') | emp('Thomas Mathew')
                                                       | emp('Ananya Sharma')).ids)],
            'host_selection': True,
            'field_email': 'hidden', 'field_phone': 'required', 'field_organization': 'required',
            'offer_drinks': False,
            'notify_email': True, 'notify_discuss': True,
            'theme': 'dark',
            'side_message': '<h3>Central Kitchen - Food Safety Zone</h3>'
                            '<p>Hair nets and shoe covers are mandatory beyond this point. '
                            'Deliveries: please wait at the cold-room bay for the receiving chef.</p>',
        }),
    }

    company_texts = {
        'nda': company.eh_hr_visitor_nda_text or '',
    }
    today = fields.Date.context_today(env['res.users'].sudo().browse(env.uid))
    Visitor = env['eh.hr.visitor'].sudo().with_context(**CTX)
    created = 0
    for spec in VISITORS:
        if _ref(env, spec['xid']):
            continue
        host = emp(spec['host'])
        purpose = purposes.get(spec['purpose'])
        if not host or not purpose:
            _logger.warning("Visitor demo: missing host/purpose for %s", spec['xid'])
            continue
        start = _dt(today, spec['day'], spec['h'])
        end = start + timedelta(hours=spec['dur'] or 1)
        state = spec['state']
        vals = {
            'name': spec['name'],
            'visitor_company': spec.get('org') or False,
            'designation': spec.get('designation'),
            'visitor_email': spec.get('email'),
            'visitor_phone': spec.get('phone'),
            'visitor_city': spec.get('city'),
            'visitor_country': 'India',
            'visitor_type': spec['type'],
            'host_employee_id': host.id,
            'purpose_id': purpose.id,
            'company_id': company.id,
            'station_id': stations[spec['station']].id,
            'registration_type': spec['reg'],
            'meeting_title': spec.get('meeting'),
            'meeting_room_id': rooms[spec['room']].id if spec.get('room') else False,
            'drink_id': drinks[spec['drink']].id if spec.get('drink') in drinks else False,
            'is_vip': spec.get('vip', False),
            'parking_required': spec.get('parking', False),
            'notes': spec.get('notes'),
            'expected_arrival': start,
            'expected_departure': end,
            'identity_type': 'id_card',
        }
        # NDA only on records that may keep an open agreement (Pending); signed agreements need a signature image
        if spec.get('nda') and state == 'pending':
            vals.update({'nda_required': True, 'nda_text': company_texts['nda']})
        if state in ('signed_in', 'signed_out', 'arrived'):
            vals['arrived_on'] = start
        if state == 'signed_out':
            if spec.get('auto'):
                cutoff = TZ.localize(datetime.combine(today + timedelta(days=spec['day']), time(23, 0)))
                vals.update({'signed_out_on': cutoff.astimezone(pytz.utc).replace(tzinfo=None), 'auto_signed_out': True})
            else:
                vals['signed_out_on'] = end
        vals['state'] = state
        try:
            with env.cr.savepoint():
                rec = Visitor.create(vals)
                _bind(env, spec['xid'], rec)
                created += 1
        except Exception as e:
            _logger.warning("Visitor demo: could not create %s: %s", spec['xid'], e)
    _logger.info("Visitor demo: %s visitors created", created)
    return True
