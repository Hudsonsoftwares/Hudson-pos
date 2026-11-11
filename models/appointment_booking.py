# pyrefly: ignore [missing-import]
from odoo import models, fields, api, _

# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
import uuid

class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _description = 'Appointment Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Reference', required=True, copy=False, readonly=True, default='New')
    appointment_type_id = fields.Many2one('appointment.type', string='Appointment Type', required=True)
    
    def _compute_display_name(self):
        for booking in self:
            booking.display_name = booking.partner_id.name if booking.partner_id else booking.name

    partner_id = fields.Many2one('res.partner', string='Customer')
    staff_user_id = fields.Many2one('res.users', string='Staff')
    resource_ids = fields.Many2many('appointment.resource', string='Resource')
    party_size = fields.Integer('Party Size', default=1)
    
    subject = fields.Char('Subject', compute='_compute_subject', store=True, readonly=False)
    asked_capacity = fields.Integer('Total Capacity Asked', compute='_compute_capacities')
    total_capacity_reserved = fields.Integer('Total Capacity Reserved', compute='_compute_capacities')

    guest_details = fields.Text('Guest Details / Answers')
    
    start_datetime = fields.Datetime('Start Datetime', required=True)
    end_datetime = fields.Datetime('End Datetime', required=True)
    duration = fields.Float('Duration', compute='_compute_duration', inverse='_inverse_duration', store=True)
    
    access_token = fields.Char('Access Token', default=lambda self: str(uuid.uuid4()))
    
    @api.depends('start_datetime', 'end_datetime')
    def _compute_duration(self):
        for booking in self:
            if booking.start_datetime and booking.end_datetime:
                diff = booking.end_datetime - booking.start_datetime
                booking.duration = diff.total_seconds() / 3600.0
            else:
                booking.duration = 0.0

    def _inverse_duration(self):
        from datetime import timedelta
        for booking in self:
            if booking.start_datetime and booking.duration:
                booking.end_datetime = booking.start_datetime + timedelta(hours=booking.duration)
    
    @api.depends('partner_id', 'appointment_type_id', 'name')
    def _compute_subject(self):
        for booking in self:
            partner_name = booking.partner_id.name if booking.partner_id else booking.name
            type_name = booking.appointment_type_id.name if booking.appointment_type_id else ''
            booking.subject = f"{partner_name} - {type_name}" if partner_name and type_name else (partner_name or type_name or '')

    @api.depends('party_size', 'resource_ids', 'resource_ids.capacity', 'appointment_type_id.booking_target')
    def _compute_capacities(self):
        for booking in self:
            if booking.appointment_type_id.booking_target == 'resources':
                booking.asked_capacity = booking.party_size
                booking.total_capacity_reserved = sum(booking.resource_ids.mapped('capacity'))
            else:
                booking.asked_capacity = booking.party_size
                booking.total_capacity_reserved = booking.party_size

    @api.constrains('start_datetime', 'end_datetime')
    def _check_date_integrity(self):
        for booking in self:
            if booking.start_datetime and booking.end_datetime:
                if booking.end_datetime <= booking.start_datetime:
                    raise ValidationError("The end date and time must be later than the start date and time.")

    @api.constrains('staff_user_id', 'resource_ids', 'start_datetime', 'end_datetime', 'state', 'party_size')
    def _check_overlapping_appointments(self):
        for booking in self:
            if not booking.appointment_type_id or booking.state == 'cancelled' or not booking.start_datetime or not booking.end_datetime:
                continue
                
            if booking.appointment_type_id.booking_target == 'users' and booking.staff_user_id:
                overlapping = self.search([
                    ('staff_user_id', '=', booking.staff_user_id.id),
                    ('id', '!=', booking.id),
                    ('state', '!=', 'cancelled'),
                    ('start_datetime', '<', booking.end_datetime),
                    ('end_datetime', '>', booking.start_datetime),
                    ('appointment_type_id.booking_target', '=', 'users')
                ])
                if overlapping:
                    # Allow overlaps ONLY if they are the exact same group booking type and within capacity
                    if booking.appointment_type_id.group_booking and all(o.appointment_type_id.id == booking.appointment_type_id.id for o in overlapping):
                        user_capacity = getattr(booking.staff_user_id, 'capacity', booking.appointment_type_id.capacity)
                        total_party = booking.party_size + sum(overlapping.mapped('party_size'))
                        if total_party <= user_capacity:
                            continue
                            
                    raise ValidationError(
                        _("Staff member %s already has an appointment during this time period or has reached maximum capacity.") % booking.staff_user_id.name
                    )
            
            elif booking.appointment_type_id.booking_target == 'resources' and booking.resource_ids:
                for resource in booking.resource_ids:
                    overlapping = self.search([
                        ('resource_ids', 'in', [resource.id]),
                        ('id', '!=', booking.id),
                        ('state', '!=', 'cancelled'),
                        ('start_datetime', '<', booking.end_datetime),
                        ('end_datetime', '>', booking.start_datetime),
                    ])
                    if overlapping:
                        if not resource.shareable:
                            raise ValidationError(
                                _("Resource %s is not shareable and is already booked for this time period.") % resource.name
                            )
                        
                        total_party = booking.party_size + sum(overlapping.mapped('party_size'))
                        if total_party > resource.capacity:
                            raise ValidationError(
                                _("Resource %(resource_name)s has reached its maximum capacity of %(capacity)s for this time period (Total requested: %(total)s).") % {
                                    'resource_name': resource.name,
                                    'capacity': resource.capacity,
                                    'total': total_party
                                }
                            )
    
    calendar_contact_details = fields.Html('Contact Details', compute='_compute_calendar_contact_details')
    
    @api.depends('partner_id', 'partner_id.name', 'partner_id.email', 'partner_id.phone', 'guest_details')
    def _compute_calendar_contact_details(self):
        for booking in self:
            details = ""
            if booking.partner_id:
                details += f"<b>{booking.partner_id.name}</b><br/>"
                if booking.partner_id.email:
                    details += f"<span style='color: #28a745;'>{booking.partner_id.email}</span><br/>"
                if booking.partner_id.phone:
                    details += f"<span style='color: #28a745;'>{booking.partner_id.phone}</span><br/>"
            
            if booking.guest_details:
                details += f"<br/>{booking.guest_details.replace(chr(10), '<br/>')}"
                
            booking.calendar_contact_details = details
    
    sale_order_id = fields.Many2one('sale.order', string="Sales Order", readonly=True)
    
    state = fields.Selection([
        ('draft', 'Request'),
        ('pending_payment', 'Pending Payment'),
        ('confirmed', 'Booked'),
        ('checked_in', 'Checked-In'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)

    allday = fields.Boolean('All Day', default=False)
    location = fields.Char('Location')
    videocall_location = fields.Char('Video Link')
    show_as = fields.Selection([('busy', 'Busy'), ('free', 'Free')], string='Status', default='busy')
    privacy = fields.Selection([('public', 'Public'), ('private', 'Private'), ('confidential', 'Only internal users')], string='Visibility', default='public')
    attendee_ids = fields.Many2many('res.partner', string='Attendees')
    description = fields.Html(related='calendar_event_id.description', string='Description', readonly=False)
    answer_ids = fields.One2many('appointment.answer', 'booking_id', string='Answers')

    calendar_event_id = fields.Many2one('calendar.event', string='Calendar Event')
    tag_ids = fields.Many2many(related='calendar_event_id.categ_ids', string='Tags', readonly=False)
    alarm_ids = fields.Many2many(related='calendar_event_id.alarm_ids', string='Reminders', readonly=False)
    recurrency = fields.Boolean(related='calendar_event_id.recurrency', string='Recurrent', readonly=False)
    event_attendee_ids = fields.One2many(related='calendar_event_id.attendee_ids', string='Event Attendees', readonly=True)

    def action_send_email(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': {
                'default_model': 'appointment.booking',
                'default_res_ids': self.ids,
                'default_composition_mode': 'comment',
                'default_partner_ids': self.partner_id.ids if self.partner_id else [],
            },
        }

    def action_send_sms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sms.composer',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': {
                'default_res_model': 'appointment.booking',
                'default_res_id': self.id,
                'default_composition_mode': 'comment',
                'default_recipient_single_number_itf': self.partner_id.phone or self.partner_id.mobile if self.partner_id else False,
            },
        }

    def action_check_in(self):
        for booking in self:
            booking.state = 'checked_in'

    def action_no_show(self):
        for booking in self:
            booking.state = 'no_show'

    def action_cancel(self):
        for booking in self:
            booking.state = 'cancelled'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New':
                seq = self.env['ir.sequence'].next_by_code('appointment.booking')
                vals['name'] = seq or 'APT/MISSING-SEQ'
                
            attendee_ids = vals.get('attendee_ids', [])
            if isinstance(attendee_ids, list) and not attendee_ids:
                partners = []
                if vals.get('partner_id'):
                    partners.append(vals['partner_id'])
                if vals.get('staff_user_id'):
                    staff = self.env['res.users'].browse(vals['staff_user_id'])
                    if staff.partner_id:
                        partners.append(staff.partner_id.id)
                if partners:
                    vals['attendee_ids'] = [(6, 0, partners)]
        
        bookings = super(AppointmentBooking, self).create(vals_list)
        for booking in bookings:
            if booking.state == 'confirmed':
                booking._create_calendar_event()
        return bookings

    def write(self, vals):
        res = super(AppointmentBooking, self).write(vals)
        if 'state' in vals and vals['state'] == 'confirmed':
            for booking in self:
                if not booking.calendar_event_id:
                    booking._create_calendar_event()
        return res

    def _create_calendar_event(self):
        for booking in self:
            if not booking.calendar_event_id:
                partner_ids = []
                if booking.partner_id:
                    partner_ids.append(booking.partner_id.id)
                if booking.staff_user_id and booking.staff_user_id.partner_id:
                    partner_ids.append(booking.staff_user_id.partner_id.id)
                
                desc = []
                desc.append("<b>Description of the event</b>")
                if booking.appointment_type_id and booking.appointment_type_id.message_intro:
                    desc.append(booking.appointment_type_id.message_intro)
                desc.append("<br/>")
                
                if booking.partner_id:
                    desc.append("<b>Contact Details</b>")
                    desc.append(f"{booking.partner_id.name}")
                    if booking.partner_id.email:
                        desc.append(f"<a href='mailto:{booking.partner_id.email}'>{booking.partner_id.email}</a>")
                    if booking.partner_id.phone:
                        desc.append(f"<a href='tel:{booking.partner_id.phone}'>{booking.partner_id.phone}</a>")
                
                if booking.answer_ids:
                    for answer in booking.answer_ids:
                        desc.append(f"<br/>{answer.question_id.name} -<br/>{answer.value_text or ''}")
                elif booking.guest_details:
                    desc.append("<br/>" + booking.guest_details.replace('\n', '<br/>'))
                    
                description_html = "<br/>".join(desc)
                
                event_vals = {
                    'name': booking.name or booking.appointment_type_id.name,
                    'start': booking.start_datetime,
                    'stop': booking.end_datetime,
                    'allday': False,
                    'partner_ids': [(6, 0, partner_ids)],
                    'user_id': booking.staff_user_id.id if booking.staff_user_id else self.env.user.id,
                    'description': description_html,
                }
                event = self.env['calendar.event'].sudo().create(event_vals)
                booking.calendar_event_id = event.id
