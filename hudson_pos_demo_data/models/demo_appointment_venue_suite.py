# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
#
# Appointment venues: party halls, banquet hall, garden lawn, private dining and
# tasting rooms as bookable appointment.resource records, a resource-based
# "Party Hall & Celebration Venue Booking" type and bookings in every status.
# Builds on the appointment demo of demo_business_suite (section 13).
# Idempotent: every record is looked up by name before being created.

import logging
from datetime import datetime, date, timedelta
from odoo import Command

_logger = logging.getLogger(__name__)

VENUE_SPECS = [
    # (name, capacity, description)
    ('Grand Celebration Party Hall (150 Pax)', 150,
     'Air-conditioned pillar-less hall with stage, LED wall, dance floor, bridal room and '
     'in-house sound system. Ideal for weddings, receptions and corporate galas.'),
    ('Royal Banquet Hall (80 Pax)', 80,
     'Elegant banquet hall with chandeliers, round-table seating and a dedicated live-counter '
     'buffet line. Suited to engagements, anniversaries and award nights.'),
    ("Kids' Birthday Party Room (30 Pax)", 30,
     'Colourful themed party room with play corner, balloon arch backdrop, cake table and '
     'kid-friendly furniture.'),
    ('Open-Air Garden Lawn (250 Pax)', 250,
     'Landscaped lawn with fairy-light canopy and a weatherproof marquee option for '
     'sangeet nights, mehendi and outdoor receptions.'),
    ('Private Dining Room (20 Pax)', 20,
     'Sound-insulated private dining room with a single long table, AV screen and dedicated '
     'service staff for family get-togethers and business dinners.'),
    ('Executive Conference & Tasting Room (10 Pax)', 10,
     'Boardroom-style room with tasting counter used for menu consultations, food tastings '
     'and client presentations.'),
]

VENUE_RESOURCE_NAMES = [spec[0] for spec in VENUE_SPECS]
VENUE_TYPE_NAMES = ['Party Hall & Celebration Venue Booking', 'Private Dining Room Reservation']

# Durations of the original appointment demo, in hours (were wrongly given in minutes)
_TYPE_DURATIONS = {
    "VIP Chef's Table 7-Course Degustation Experience": 2.0,
    'Banquets & Wedding Catering Consultation': 1.0,
    'Artisan Coffee Cupping & Barista Workshop': 0.75,
}


def _partner(env, name, email, is_company=True):
    Partner = env['res.partner'].sudo()
    partner = Partner.search([('name', '=', name)], limit=1)
    if not partner:
        partner = Partner.create({
            'name': name,
            'is_company': is_company,
            'email': email,
            'phone': '+91 98470 12345',
            'street': 'Marine Drive, Kochi',
            'city': 'Kochi',
            'zip': '682011',
        })
    return partner


def fix_appointment_demo_durations(env):
    """The first appointment demo passed minutes into hour fields (120 h sessions)."""
    AppType = env['appointment.type'].sudo()
    AppBooking = env['appointment.booking'].sudo()
    for name, hours in _TYPE_DURATIONS.items():
        apt = AppType.search([('name', '=', name)], limit=1)
        if not apt:
            continue
        if apt.appointment_duration > 24:
            apt.appointment_duration = hours
        for booking in AppBooking.search([('appointment_type_id', '=', apt.id)]):
            if booking.start_datetime and booking.duration > 24:
                booking.write({'end_datetime': booking.start_datetime + timedelta(hours=hours)})


def _assign_tables_to_celebration_type(env):
    """Give the 'Celebrate Your Life Events' type (hudson_pos_booking) the demo
    floor tables, so it has resources to book and can be published."""
    life = env.ref('hudson_pos_booking.appointment_type_event_other', raise_if_not_found=False)
    if not life or 'restaurant.table' not in env:
        return
    Table = env['restaurant.table'].sudo().with_context(active_test=False)
    if hasattr(Table, '_sync_appointment_resource'):
        Table.search([])._sync_appointment_resource()
    tables = env['restaurant.table'].sudo().search([
        ('floor_id.name', 'in', ['Main Floor', 'Patio']),
        ('appointment_resource_id', '!=', False),
    ])
    owned_elsewhere = env['appointment.type'].sudo().search([
        ('id', '!=', life.id),
        ('active', '=', True),
        ('booking_target', '=', 'resources'),
    ]).resource_ids
    free = tables.appointment_resource_id.filtered(lambda r: r.active) - owned_elsewhere - life.resource_ids
    try:
        with env.cr.savepoint():
            if free:
                life.resource_ids = [Command.link(r.id) for r in free]
            if life.resource_ids and not life.is_published and 'is_published' in life._fields:
                life.is_published = True
    except Exception as e:
        _logger.warning("Could not assign demo tables to %s: %s", life.name, e)


def load_appointment_venue_suite_demo_data(env):
    if 'appointment.resource' not in env or 'appointment.booking' not in env:
        return
    _logger.info("Hudson Appointment Venues: Setting up party hall & venue resources...")
    AppType = env['appointment.type'].sudo()
    AppBooking = env['appointment.booking'].sudo()
    AppResource = env['appointment.resource'].sudo()
    today = date.today()

    fix_appointment_demo_durations(env)

    venues = {}
    for v_name, v_cap, v_desc in VENUE_SPECS:
        venue = AppResource.search([('name', '=', v_name)], limit=1)
        if not venue:
            venue = AppResource.create({'name': v_name, 'capacity': v_cap, 'description': v_desc})
        venues[v_name] = venue

    grand_hall = venues['Grand Celebration Party Hall (150 Pax)']
    banquet_hall = venues['Royal Banquet Hall (80 Pax)']
    kids_room = venues["Kids' Birthday Party Room (30 Pax)"]
    garden_lawn = venues['Open-Air Garden Lawn (250 Pax)']
    private_dining = venues['Private Dining Room (20 Pax)']
    tasting_room = venues['Executive Conference & Tasting Room (10 Pax)']
    res_pergola = AppResource.search([('name', '=', 'Rooftop Pergola Garden Lounge (12 Pax)')], limit=1)
    res_chef_table = AppResource.search([('name', '=', "Chef's Table Suite (8 Pax)")], limit=1)

    # The banquet hall opens into the grand hall for very large parties
    if banquet_hall not in grand_hall.linked_resource_ids:
        grand_hall.linked_resource_ids = [Command.link(banquet_hall.id)]

    hall_resources = grand_hall | banquet_hall | kids_room | garden_lawn | res_pergola
    apt_party = AppType.search([('name', '=', 'Party Hall & Celebration Venue Booking')], limit=1)
    if not apt_party:
        apt_party = AppType.create({
            'name': 'Party Hall & Celebration Venue Booking',
            'appointment_duration': 4.0,
            'booking_target': 'resources',
            'assign_method': 'customer',
            'schedule_based_on': 'users',
            'location': 'custom',
            'location_details': 'Hudson Restaurant Event Venues',
            'max_schedule_days': 90,
            'min_schedule_hours': 48.0,
            'resource_ids': [Command.set(hall_resources.ids)],
        })
    elif apt_party.resource_ids != hall_resources:
        apt_party.resource_ids = [Command.set(hall_resources.ids)]

    apt_private = AppType.search([('name', '=', 'Private Dining Room Reservation')], limit=1)
    if not apt_private:
        apt_private = AppType.create({
            'name': 'Private Dining Room Reservation',
            'appointment_duration': 3.0,
            'booking_target': 'resources',
            'assign_method': 'customer',
            'location': 'custom',
            'location_details': 'Hudson Restaurant - First Floor',
            'resource_ids': [Command.set(private_dining.ids)],
        })
    elif apt_private.resource_ids != private_dining:
        apt_private.resource_ids = [Command.set(private_dining.ids)]

    _assign_tables_to_celebration_type(env)

    # The original sample appointment types become resource-based, each with its own room,
    # and their sample bookings are given that room.
    # (A resource may belong to only one resource-based type, see hudson_pos_booking.)
    res_lab = AppResource.search([('name', '=', 'Barista Cupping & Masterclass Lab (6 Pax)')], limit=1)
    sample_type_rooms = [
        ("VIP Chef's Table 7-Course Degustation Experience", res_chef_table),
        ('Banquets & Wedding Catering Consultation', tasting_room),
        ('Artisan Coffee Cupping & Barista Workshop', res_lab),
    ]
    for type_name, room in sample_type_rooms:
        apt = AppType.search([('name', '=', type_name)], limit=1)
        if not apt or not room:
            continue
        try:
            with env.cr.savepoint():
                vals = {}
                if apt.booking_target != 'resources':
                    vals['booking_target'] = 'resources'
                if apt.resource_ids != room:
                    vals['resource_ids'] = [Command.set(room.ids)]
                if vals:
                    apt.write(vals)
                for booking in AppBooking.search([('appointment_type_id', '=', apt.id)]):
                    if booking.resource_ids != room:
                        booking.resource_ids = [Command.set(room.ids)]
        except Exception as e:
            _logger.warning("Could not assign %s to '%s': %s", room.name, type_name, e)

    malabar = _partner(env, 'Malabar Corporate Club', 'events@malabarclub.in')
    ananya = _partner(env, 'Dr. Ananya Sharma', 'ananya.sharma@aims.org', is_company=False)
    royal = _partner(env, 'Royal Orchid Hospitality Ltd', 'catering@royalorchid.com')
    nair = _partner(env, 'Arjun & Meera Nair', 'arjun.meera.nair@example.com', is_company=False)
    techpark = _partner(env, 'Infopark Tech Solutions Pvt Ltd', 'hr@infopark-tech.example.com')
    joseph = _partner(env, "Joseph Family (Aarav's 7th Birthday)", 'joseph.family@example.com', is_company=False)
    menon = _partner(env, 'Lakshmi Menon', 'lakshmi.menon@example.com', is_company=False)
    rotary = _partner(env, 'Rotary Club of Kochi West', 'secretary@rotarykochiwest.example.com')

    def _dt(days, hour, minute=0):
        return datetime(today.year, today.month, today.day, hour, minute) + timedelta(days=days)

    venue_bookings = [
        # (type, partner, resources, start, hours, party size, state, description)
        (apt_party, nair, grand_hall, _dt(12, 18), 5.0, 140, 'confirmed',
         'Wedding reception: stage decor in ivory & gold, live Kerala sadya counter, DJ from 21:00, '
         'bridal room required from 16:00.'),
        (apt_party, techpark, banquet_hall, _dt(7, 19), 4.0, 75, 'confirmed',
         'Annual awards night: podium with mic, projector & LED wall, 3-course plated dinner, 10 round tables.'),
        (apt_party, joseph, kids_room, _dt(4, 16), 3.0, 25, 'confirmed',
         'Superhero-themed birthday party: balloon arch, magician at 17:00, kids menu + eggless chocolate cake.'),
        (apt_party, menon, garden_lawn, _dt(20, 17), 6.0, 220, 'draft',
         'Sangeet & mehendi night request: marquee required if rain forecast, folk music troupe, '
         'chaat counters. Awaiting advance payment.'),
        (apt_party, rotary, grand_hall | banquet_hall, _dt(-6, 19), 4.0, 210, 'checked_in',
         'Charity fundraiser gala using both halls combined; silent auction set-up in the banquet hall.'),
        (apt_party, malabar, res_pergola or garden_lawn, _dt(-10, 19, 30), 3.0, 12, 'no_show',
         'Rooftop cocktail evening for 12 - guests did not arrive; cancellation fee applicable.'),
        (apt_private, royal, private_dining, _dt(2, 20), 3.0, 16, 'confirmed',
         'Family dinner for Royal Orchid board members; Malabar seafood platter pre-ordered.'),
        (apt_private, ananya, private_dining, _dt(-3, 13), 2.0, 12, 'cancelled',
         'Department lunch cancelled by client due to schedule change.'),
    ]

    for apt, partner, resources, start, hours, size, state, desc in venue_bookings:
        if AppBooking.search([('appointment_type_id', '=', apt.id), ('partner_id', '=', partner.id)], limit=1):
            continue
        try:
            with env.cr.savepoint():
                AppBooking.create({
                    'appointment_type_id': apt.id,
                    'partner_id': partner.id,
                    'resource_ids': [Command.set(resources.ids)],
                    'start_datetime': start,
                    'end_datetime': start + timedelta(hours=hours),
                    'party_size': size,
                    'state': state,
                    'description': desc,
                })
        except Exception as e:
            _logger.warning("Could not create venue booking for %s: %s", partner.name, e)

    _logger.info("Hudson Appointment Venues: venue resources and bookings loaded.")
