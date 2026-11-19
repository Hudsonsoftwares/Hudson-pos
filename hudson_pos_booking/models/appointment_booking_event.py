# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Celebration / guest-contact / notification features of appointment.booking.

These features used to be patched directly into the customised ``appointment``
module. They now live in the POS Table Booking Bridge so the stock
``appointment`` module can be installed and upgraded without modification.
Field names are unchanged, so databases that ran the old customised module
keep all their data (the bridge takes over ownership of the columns).
"""

import calendar
import logging
import re
import uuid
from datetime import date, timedelta
from urllib.parse import urlencode

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

# Only these states occupy a table / staff slot. A no-show, a completed
# (checked-out) or a draft booking must never block a new reservation.
BLOCKING_BOOKING_STATES = ('confirmed', 'checked_in')
NON_BLOCKING_BOOKING_STATES = ('cancelled', 'no_show', 'checked_out', 'draft')

# Life events offered by the single "Celebrate Your Life Events" appointment type.
CELEBRATION_TYPE_SELECTION = [
    ('birthday', 'Birthday'),
    ('anniversary', 'Anniversary'),
    ('engagement', 'Engagement'),
    ('wedding', 'Wedding'),
    ('other', 'Other'),
]
CELEBRATION_TYPE_EMOJI = {
    'birthday': '🎂',
    'anniversary': '💍',
    'engagement': '💖',
    'wedding': '💒',
    'other': '🎉',
}


class AppointmentBookingEvent(models.Model):
    _inherit = 'appointment.booking'

    celebrant_name = fields.Char('Celebrant / Honoree Name', tracking=True)
    occasion_title = fields.Char('Occasion / Celebration Details', tracking=True)
    occasion_date = fields.Date('Special Day / Occasion Date', tracking=True, index=True)
    event_category = fields.Selection(
        related='appointment_type_id.event_category', store=True, readonly=True)
    celebration_type = fields.Selection(
        CELEBRATION_TYPE_SELECTION, string='Celebration Event Type', tracking=True, index=True,
        help="Life event chosen by the guest on the 'Celebrate Your Life Events' booking form.")
    celebration_event_name = fields.Char(
        'Celebration Event Name', compute='_compute_celebration_event_display')
    celebration_event_emoji = fields.Char(
        'Celebration Event Emoji', compute='_compute_celebration_event_display')
    confirmation_sent = fields.Boolean('Confirmation Sent', copy=False, default=False)
    wish_last_advance_year = fields.Integer('Last Advance Wish Year', copy=False, default=0)
    wish_last_day_year = fields.Integer('Last Special Day Wish Year', copy=False, default=0)

    # ------------------------------------------------------------------
    # Table occupancy: no-show / checked-out bookings release the slot
    # ------------------------------------------------------------------

    @api.model
    def _search(self, domain, *args, **kwargs):
        if self.env.context.get('hudson_blocking_bookings_only'):
            domain = Domain(domain) & Domain('state', 'in', BLOCKING_BOOKING_STATES)
        return super()._search(domain, *args, **kwargs)

    @api.constrains('staff_user_id', 'resource_ids', 'start_datetime', 'end_datetime', 'state', 'party_size')
    def _check_overlapping_appointments(self):
        to_check = self.filtered(lambda b: b.state not in NON_BLOCKING_BOOKING_STATES)
        return super(AppointmentBookingEvent, to_check.with_context(
            hudson_blocking_bookings_only=True))._check_overlapping_appointments()

    @api.depends('appointment_type_id', 'staff_user_id', 'resource_ids', 'start_datetime', 'end_datetime',
                 'party_size', 'state')
    def _compute_unavailable_targets(self):
        idle = self.filtered(lambda b: b.state in NON_BLOCKING_BOOKING_STATES)
        idle.unavailable_user_ids = False
        idle.unavailable_resource_ids = False
        return super(AppointmentBookingEvent, (self - idle).with_context(
            hudson_blocking_bookings_only=True))._compute_unavailable_targets()

    # ------------------------------------------------------------------
    # Guest contact helpers
    # ------------------------------------------------------------------

    def _compute_display_name(self):
        for booking in self:
            booking.display_name = booking._get_guest_display_name() or booking.name

    @api.depends('customer_name', 'partner_id', 'partner_id.name', 'appointment_type_id',
                 'appointment_type_id.name', 'appointment_type_id.is_event_booking', 'celebrant_name', 'name')
    def _compute_subject(self):
        for booking in self:
            guest_name = booking._get_guest_display_name() or booking.name
            type_name = booking.appointment_type_id.name if booking.appointment_type_id else ''
            if booking.celebrant_name and booking.appointment_type_id.is_event_booking:
                booking.subject = f"{booking.celebrant_name} - {type_name}" if type_name else booking.celebrant_name
            else:
                booking.subject = f"{guest_name} - {type_name}" if guest_name and type_name else (guest_name or type_name or '')

    @api.model
    def _phone_get_number_fields(self):
        return ['customer_phone']

    @api.model
    def _normalize_phone_digits(self, phone):
        return re.sub(r'\D+', '', str(phone or ''))

    def _get_guest_display_name(self):
        self.ensure_one()
        if self.customer_name and self.customer_name.strip():
            return self.customer_name.strip()
        partner = self.partner_id
        company = self.company_id or self.appointment_type_id.company_id or self.env.company
        if partner and partner.id != 1 and not partner.is_company and (not company or partner.id != company.partner_id.id):
            if partner.name and (not company or partner.name != company.name):
                return partner.name.strip()
        return ''

    def _get_recipient_email(self):
        self.ensure_one()
        email = (self.customer_email or '').strip()
        if not email and self.partner_id:
            email = (self.partner_id.email or '').strip()
        return email if ('@' in email and '.' in email.split('@', 1)[-1]) else False

    def _get_recipient_phone(self):
        self.ensure_one()
        phone = (self.customer_phone or '').strip()
        if not phone and self.partner_id:
            phone = (self.partner_id.phone or (self.partner_id.mobile if 'mobile' in self.partner_id._fields else '') or '').strip()
        return phone or False

    @api.depends('customer_name', 'customer_phone', 'customer_email', 'partner_id', 'partner_id.name',
                 'partner_id.email', 'partner_id.phone', 'guest_details', 'celebrant_name',
                 'occasion_title', 'occasion_date', 'appointment_type_id.name')
    def _compute_calendar_contact_details(self):
        for booking in self:
            details = ""
            guest_name = booking._get_guest_display_name()
            guest_email = booking._get_recipient_email()
            guest_phone = booking._get_recipient_phone()
            if guest_name:
                details += f"<b>{guest_name}</b><br/>"
            if guest_email:
                details += f"<span style='color: #28a745;'>{guest_email}</span><br/>"
            if guest_phone:
                details += f"<span style='color: #28a745;'>{guest_phone}</span><br/>"
            if booking.celebrant_name:
                details += f"<span><b>Celebrant:</b> {booking.celebrant_name}</span><br/>"
            if booking.occasion_title:
                details += f"<span><b>Occasion:</b> {booking.occasion_title}</span><br/>"
            if booking.occasion_date:
                details += f"<span><b>Special Day:</b> {booking.occasion_date.strftime('%d %b %Y')}</span><br/>"
            if booking.guest_details:
                details += f"<br/>{booking.guest_details.replace(chr(10), '<br/>')}"
            booking.calendar_contact_details = details

    def action_send_sms(self):
        action = super().action_send_sms()
        if isinstance(action, dict) and isinstance(action.get('context'), dict):
            action['context'] = dict(action['context'], default_recipient_single_number_itf=self._get_recipient_phone() or False)
        return action

    # ------------------------------------------------------------------
    # Answers -> structured celebration fields
    # ------------------------------------------------------------------

    def _sync_event_fields_from_answers(self):
        Answer = self.env['appointment.answer']
        for booking in self.sudo():
            vals = {}
            for answer in booking.answer_ids:
                q = answer.question_id
                if not q:
                    continue
                role = q.question_role or 'none'
                if q.is_occasion_date or role == 'occasion_date':
                    parsed = answer.value_date or Answer._parse_date_value(answer.value_text)
                    if parsed:
                        vals['occasion_date'] = parsed
                        if not answer.value_date:
                            answer.with_context(skip_event_sync=True).write({'value_date': parsed})
                elif role == 'celebrant_name':
                    text = (answer.value_text or '').strip()
                    if text:
                        vals['celebrant_name'] = text
                elif role == 'occasion_title':
                    text = (answer.value_text or '').strip()
                    if text:
                        vals['occasion_title'] = text
                elif role == 'celebration_type':
                    raw = (answer.value_answer_ids[:1].name or answer.value_text or '').strip().lower()
                    key = next((k for k, label in CELEBRATION_TYPE_SELECTION
                                if raw in (k, label.lower())), False)
                    if raw and not key:
                        key = 'other'
                    if key and booking.celebration_type != key:
                        vals['celebration_type'] = key
                elif role == 'special_requests':
                    text = (answer.value_text or '').strip()
                    if text:
                        details = booking.guest_details or ''
                        if text not in details:
                            line = f"Special Requests: {text}"
                            vals['guest_details'] = f"{details}\n{line}".strip() if details else line
                        if not booking.notes:
                            vals['notes'] = text
            if vals:
                booking.with_context(skip_event_sync=True).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        bookings = super().create(vals_list)
        bookings._sync_event_fields_from_answers()
        return bookings

    def _create_calendar_event(self):
        without_event = self.filtered(lambda b: not b.calendar_event_id)
        res = super()._create_calendar_event()
        for booking in without_event.filtered('calendar_event_id'):
            extra = []
            if not booking.partner_id or booking.customer_name:
                guest_name = booking._get_guest_display_name()
                guest_phone = booking._get_recipient_phone()
                if guest_name or guest_phone:
                    extra.append("<b>Guest</b>")
                    if guest_name:
                        extra.append(guest_name)
                    if guest_phone:
                        extra.append(f"<a href='tel:{guest_phone}'>{guest_phone}</a>")
            if booking.celebrant_name:
                extra.append(f"<b>Celebrant / Honoree:</b> {booking.celebrant_name}")
            if booking.occasion_title:
                extra.append(f"<b>Occasion:</b> {booking.occasion_title}")
            if booking.occasion_date:
                extra.append(f"<b>Special Day:</b> {booking.occasion_date.strftime('%Y-%m-%d')}")
            if extra:
                event = booking.calendar_event_id.sudo()
                event.write({
                    'name': booking.subject or event.name,
                    'description': (event.description or '') + "<br/><br/>" + "<br/>".join(extra),
                })
        return res

    # ------------------------------------------------------------------
    # Confirmation notifications (Email + SMS)
    # ------------------------------------------------------------------

    def _format_booking_confirmation_sms(self):
        self.ensure_one()
        guest_name = self._get_guest_display_name() or _("Guest")
        appt = self.appointment_type_id
        company = self.company_id or appt.company_id or self.env.company
        tz = self._hudson_booking_tz()
        start_local = ''
        if self.start_datetime:
            utc_dt = pytz.UTC.localize(self.start_datetime) if not self.start_datetime.tzinfo else self.start_datetime.astimezone(pytz.UTC)
            start_local = utc_dt.astimezone(tz).strftime('%d %b %Y, %I:%M %p')
        emoji = f"{appt.event_emoji} " if appt.event_emoji else ""
        manage_url = f"{self.get_base_url()}/appointment/manage/{self.id}?token={self.access_token}"
        parts = [
            f"Hi {guest_name}, your {emoji}{appt.name} at {company.name} is confirmed for {start_local} ({self.party_size or 1} guests)."
        ]
        if self.celebrant_name:
            parts.append(f"Celebrant: {self.celebrant_name}.")
        if self.occasion_title:
            parts.append(f"Occasion: {self.occasion_title}.")
        parts.append(f"Manage booking: {manage_url}")
        return " ".join(parts)

    def _hudson_booking_tz(self):
        self.ensure_one()
        appt = self.appointment_type_id
        company = self.company_id or appt.company_id or self.env.company
        tz_name = appt.appointment_tz or company.partner_id.tz or self.env.user.tz or 'Asia/Calcutta'
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.UTC

    def _hudson_queue_sms(self, body):
        """Queue an SMS to the guest phone. Never raises."""
        self.ensure_one()
        phone = self._get_recipient_phone()
        if not phone:
            return False
        try:
            with self.env.cr.savepoint():
                self.sudo()._message_sms(
                    body,
                    partner_ids=[],
                    sms_numbers=[phone],
                    sms_content=body,
                    put_in_queue=True,
                    sms_type='alert',
                )
            return True
        except Exception:
            _logger.exception("SMS failed for booking %s", self.id)
            return False

    def _send_booking_confirmation_notifications(self, send_email=True):
        """Send the confirmation Email (if the guest has an email) and SMS (if
        the guest has a phone) once per booking.

        :param send_email: False when the stock appointment flow already queued
            its own confirmation email (e.g. on sale order confirmation).
        """
        mail_template_fallback = self.env.ref('appointment.email_template_booking_confirmation', raise_if_not_found=False)
        for booking in self.sudo():
            if booking.confirmation_sent or booking.state not in ('confirmed', 'checked_in'):
                continue
            if not booking.access_token:
                booking.with_context(skip_event_sync=True).write({'access_token': str(uuid.uuid4())})
            if send_email:
                template = booking.appointment_type_id.booking_template_id or mail_template_fallback
                if template and booking._get_recipient_email():
                    try:
                        with self.env.cr.savepoint():
                            template.sudo().send_mail(booking.id, force_send=False)
                    except Exception:
                        _logger.exception("Booking confirmation email failed for booking %s", booking.id)
            booking._hudson_queue_sms(booking._format_booking_confirmation_sms())
            booking.with_context(skip_event_sync=True).write({'confirmation_sent': True})

    def _send_booking_cancellation_sms(self):
        for booking in self.sudo():
            guest_label = booking._get_guest_display_name() or _("Guest")
            booking._hudson_queue_sms(
                f"Hi {guest_label}, your booking for {booking.appointment_type_id.name} ({booking.name}) has been cancelled."
            )

    # ------------------------------------------------------------------
    # Next-Year Celebration Wishes
    # ------------------------------------------------------------------

    def _get_celebration_wish_booking_url(self):
        self.ensure_one()
        if not self.access_token:
            self.with_context(skip_event_sync=True).write({'access_token': str(uuid.uuid4())})
        query = urlencode({
            'wish_ref': self.id,
            'wish_token': self.access_token,
        })
        return f"{self.get_base_url()}/appointment/{self.appointment_type_id.id}?{query}"

    @api.model
    @api.depends('celebration_type', 'appointment_type_id.name', 'appointment_type_id.event_emoji',
                 'appointment_type_id.event_category')
    def _compute_celebration_event_display(self):
        """Name/emoji used by wishes (Email & SMS): the guest's chosen life
        event when set, otherwise the appointment type itself (legacy types)."""
        labels = dict(CELEBRATION_TYPE_SELECTION)
        for booking in self:
            appt = booking.appointment_type_id
            if booking.celebration_type:
                booking.celebration_event_name = labels[booking.celebration_type]
                booking.celebration_event_emoji = CELEBRATION_TYPE_EMOJI.get(booking.celebration_type, '')
            elif appt.is_event_booking and appt.event_category == 'other':
                booking.celebration_event_name = _("Special Day")
                booking.celebration_event_emoji = appt.event_emoji or ''
            else:
                booking.celebration_event_name = appt.name or ''
                booking.celebration_event_emoji = appt.event_emoji or ''

    def _get_anniversary_date_for_year(self, occ_date, year):
        if not occ_date or not year:
            return False
        max_day = calendar.monthrange(year, occ_date.month)[1]
        return date(year, occ_date.month, min(occ_date.day, max_day))

    def _format_celebration_wish_message(self, kind='day', target_year=None):
        self.ensure_one()
        appt = self.appointment_type_id
        company = self.company_id or appt.company_id or self.env.company
        guest_name = self._get_guest_display_name() or _("Guest")
        celebrant_name = (self.celebrant_name or '').strip() or guest_name
        occasion_title = (self.occasion_title or '').strip() or appt.name
        special_day_str = ''
        if self.occasion_date:
            anniv = self._get_anniversary_date_for_year(self.occasion_date, target_year or self.occasion_date.year)
            special_day_str = anniv.strftime('%d %b %Y') if anniv else ''
        emoji_prefix = f"{self.celebration_event_emoji} " if self.celebration_event_emoji else ""

        if kind == 'advance':
            raw_tpl = (appt.wish_advance_sms_text or '').strip() or (
                "Hi {guest_name}! {celebrant_name}'s {event_name} celebration is coming up on {special_day}. "
                "Reserve a table with us at {company_name}! Grab a party here: {booking_url}"
            )
        else:
            raw_tpl = (appt.wish_day_sms_text or '').strip() or (
                "Happy celebration wishes for {celebrant_name}'s {event_name} from {company_name}! "
                "Celebrate with family & friends — Grab a party here: {booking_url}"
            )

        tokens = {
            'guest_name': guest_name,
            'celebrant_name': celebrant_name,
            'event_name': f"{emoji_prefix}{self.celebration_event_name or appt.name}".strip(),
            'occasion_title': occasion_title,
            'special_day': special_day_str,
            'company_name': company.name or '',
            'booking_url': self._get_celebration_wish_booking_url(),
        }
        pattern = re.compile(r'\{(' + '|'.join(re.escape(k) for k in tokens) + r')\}')
        return pattern.sub(lambda m: tokens[m.group(1)], raw_tpl)

    def _send_celebration_wish(self, kind='day', target_year=None):
        self.ensure_one()
        booking = self.sudo()
        if not booking.access_token:
            booking.with_context(skip_event_sync=True).write({'access_token': str(uuid.uuid4())})

        sent_email = False
        if booking._get_recipient_email():
            appt = booking.appointment_type_id
            if kind == 'advance':
                template = appt.wish_advance_email_template_id or self.env.ref(
                    'hudson_pos_booking.email_template_celebration_advance', raise_if_not_found=False)
            else:
                template = appt.wish_day_email_template_id or self.env.ref(
                    'hudson_pos_booking.email_template_celebration_day', raise_if_not_found=False)
            if template:
                try:
                    with self.env.cr.savepoint():
                        template.sudo().with_context(
                            wish_kind=kind,
                            wish_target_year=target_year,
                        ).send_mail(booking.id, force_send=False)
                    sent_email = True
                except Exception:
                    _logger.exception("Celebration wish email (%s) failed for booking %s", kind, booking.id)

        sent_sms = booking._hudson_queue_sms(
            booking._format_celebration_wish_message(kind=kind, target_year=target_year)
        ) if booking._get_recipient_phone() else False

        sent_any = bool(sent_email or sent_sms)
        if sent_any and target_year:
            field_name = 'wish_last_advance_year' if kind == 'advance' else 'wish_last_day_year'
            if booking[field_name] < target_year:
                booking.with_context(skip_event_sync=True).write({field_name: target_year})
        return {'sent': sent_any, 'email': sent_email, 'sms': sent_sms}

    def action_send_celebration_wish(self):
        self.ensure_one()
        if not self._get_recipient_email() and not self._get_recipient_phone():
            raise UserError(_("Please set a guest phone number or email address before sending celebration wishes."))
        appt = self.appointment_type_id
        kind = 'day' if appt.wish_send_on_day or not appt.wish_send_advance_invite else 'advance'
        res = self._send_celebration_wish(kind=kind, target_year=fields.Date.context_today(self).year)
        if not res['sent']:
            raise UserError(_("No celebration wish could be queued. Check email/phone details and templates."))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Celebration Wish Queued'),
                'message': _('Email / SMS celebration wish has been queued for %s.') % (self._get_guest_display_name() or self.name),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def _cron_send_celebration_wishes(self, reference_date=None):
        """Daily job to send next-year pre-celebration invites (T-N days) and/or Special Day wishes."""
        explicit_ref_date = fields.Date.to_date(reference_date) if reference_date else False
        now_utc = fields.Datetime.now()
        bookings = self.sudo().search([
            ('state', 'in', ('confirmed', 'checked_in', 'checked_out')),
            ('occasion_date', '!=', False),
            ('appointment_type_id.enable_anniversary_wishes', '=', True),
        ])
        email_queued = False
        stats = {'advance_sent': 0, 'day_sent': 0}

        for booking in bookings:
            appt = booking.appointment_type_id
            tz = booking._hudson_booking_tz()
            if explicit_ref_date:
                today_local = explicit_ref_date
            else:
                utc_now = pytz.UTC.localize(now_utc) if not now_utc.tzinfo else now_utc.astimezone(pytz.UTC)
                today_local = utc_now.astimezone(tz).date()

            booked_ref = booking.start_datetime or booking.create_date or now_utc
            booked_utc = pytz.UTC.localize(booked_ref) if not booked_ref.tzinfo else booked_ref.astimezone(pytz.UTC)
            booked_local_date = booked_utc.astimezone(tz).date()

            occ_date = booking.occasion_date
            if not occ_date:
                continue

            # 1. Advance invite (T - wish_advance_days)
            if appt.wish_send_advance_invite:
                adv_days = appt.wish_advance_days or 0
                if adv_days >= 1:
                    target_anniv = today_local + timedelta(days=adv_days)
                    target_year = target_anniv.year
                    expected_anniv = self._get_anniversary_date_for_year(occ_date, target_year)
                    if (
                        expected_anniv == target_anniv
                        and target_year > booked_local_date.year
                        and (target_anniv - booked_local_date).days >= 14
                        and booking.wish_last_advance_year < target_year
                    ):
                        res = booking._send_celebration_wish(kind='advance', target_year=target_year)
                        if res['sent']:
                            stats['advance_sent'] += 1
                        if res['email']:
                            email_queued = True

            # 2. On Special Day wish (exact anniversary date)
            if appt.wish_send_on_day:
                target_year = today_local.year
                expected_anniv = self._get_anniversary_date_for_year(occ_date, target_year)
                if (
                    expected_anniv == today_local
                    and target_year > booked_local_date.year
                    and (today_local - booked_local_date).days >= 14
                    and booking.wish_last_day_year < target_year
                ):
                    res = booking._send_celebration_wish(kind='day', target_year=target_year)
                    if res['sent']:
                        stats['day_sent'] += 1
                    if res['email']:
                        email_queued = True

        if email_queued:
            mail_queue = self.env.ref('mail.ir_cron_mail_scheduler_action', raise_if_not_found=False)
            if mail_queue:
                mail_queue._trigger()
        return stats
