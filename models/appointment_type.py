# pyrefly: ignore [missing-import]
from odoo import models, fields, api, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

class AppointmentType(models.Model):
    _name = 'appointment.type'
    _description = 'Appointment Type'
    _inherit = ['mail.thread', 'website.published.mixin', 'image.mixin']

    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    appointment_duration = fields.Float('Duration', default=1.0, required=True, help="Duration in hours")
    location = fields.Selection([
        ('office', 'Office'),
        ('online', 'Online Meeting'),
        ('custom', 'Custom Location')
    ], string='Location', default='online', help="Location of the appointments")
    location_details = fields.Char("Location Details", help="Enter the custom location address or details")
    video_link = fields.Selection([
        ('none', 'None'),
        ('discuss', 'Odoo Discuss'),
        ('meet', 'Google Meet')
    ], string='Video Link', default='none', help="Link for the video conference")
    @api.depends('name')
    def _compute_website_url(self):
        for appointment_type in self:
            appointment_type.website_url = f'/appointment/{appointment_type.id}'
            

    availability_ids = fields.One2many('appointment.availability', 'appointment_type_id', string='Availabilities')
    
    # Booking targets
    booking_target = fields.Selection([
        ('users', 'Users'),
        ('resources', 'Resources')
    ], string='Book', default='users', required=True)
    
    user_ids = fields.Many2many('res.users', string='Users', default=lambda self: self.env.user)
    resource_ids = fields.Many2many('appointment.resource', string='Resources')
    
    assign_method = fields.Selection([
        ('random', 'Automatically'),
        ('customer', 'By visitor')
    ], string='Assign', default='random')
    
    schedule_based_on = fields.Selection([
        ('website', 'Date'),
        ('users', 'User / Resource')
    ], string='Starts with', default='website', required=True)
    
    group_booking = fields.Boolean('Group Bookings', help="Allow multiple people to book the same time slot")
    capacity = fields.Integer('Up to', default=1, help="Maximum number of simultaneous appointments per user/resource")
    appointment_count = fields.Integer(compute='_compute_appointment_count')
    resource_count = fields.Integer(compute='_compute_appointment_count')

    appointment_tz = fields.Selection('_tz_get', string='Timezone', default=lambda self: self.env.user.tz or 'UTC')
    country_ids = fields.Many2many('res.country', string='Allowed Countries')

    @api.model
    def _tz_get(self):
        import pytz
        return [(x, x) for x in pytz.all_timezones]

    @api.depends('resource_ids')
    def _compute_appointment_count(self):
        for record in self:
            record.appointment_count = 0
            record.resource_count = len(record.resource_ids)
            
        if self.ids:
            appointment_data = self.env['appointment.booking']._read_group(
                [
                    ('appointment_type_id', 'in', self.ids),
                    ('start_datetime', '>=', fields.Datetime.now()),
                    ('state', 'in', ['confirmed', 'checked_in'])
                ],
                ['appointment_type_id'],
                ['__count']
            )
            mapped_data = {app_type.id: count for app_type, count in appointment_data}
            for record in self:
                record.appointment_count = mapped_data.get(record.id, 0)

    resource_total_capacity = fields.Integer(compute='_compute_resource_total_capacity')

    @api.depends('resource_ids', 'resource_ids.capacity')
    def _compute_resource_total_capacity(self):
        for record in self:
            record.resource_total_capacity = sum(record.resource_ids.mapped('capacity'))

    has_multiple_targets = fields.Boolean(compute='_compute_has_multiple_targets')

    @api.depends('user_ids', 'resource_ids')
    def _compute_has_multiple_targets(self):
        for record in self:
            if record.booking_target == 'resources':
                record.has_multiple_targets = len(record.resource_ids) > 1
            else:
                record.has_multiple_targets = len(record.user_ids) > 1

    def action_view_resources(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Resources',
            'res_model': 'appointment.resource',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.resource_ids.ids)],
            'context': {
                'default_appointment_type_ids': [(4, self.id)],
            },
        }


    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/appointment/{self.id}?preview=True',
            'target': 'self',
        }

    def action_open_bookings(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Staff Bookings',
            'res_model': 'appointment.booking',
            'view_mode': 'calendar,list,form',
            'domain': [('appointment_type_id', '=', self.id)],
            'context': {
                'default_appointment_type_id': self.id,
            },
        }
        return action

    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configure Appointment Type',
            'res_model': 'appointment.type',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_share(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create a Share Link',
            'res_model': 'appointment.invite',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appointment_type_ids': [(4, self.id)],
            },
        }

    def action_connect_google(self):
        try:
            # pyrefly: ignore [missing-import]
            from odoo.addons.google_calendar.utils.google_calendar_service import GoogleCalendarService
        except ImportError:
            return True

        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        google_service = self.env['google.service'].with_context(base_url=base_url)
        GoogleCal = GoogleCalendarService(google_service)

        client_id = google_service._get_client_id('calendar')
        if not client_id or client_id == '':
            action_id = self.env.ref('base_setup.action_general_configuration').id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'res.config.settings',
                'views': [[False, 'form']],
                'target': 'current',
                'res_id': action_id,
            }

        if not GoogleCal.is_authorized(self.env.user):
            url = GoogleCal._google_authentication_url(from_url='/web')
            return {
                'type': 'ir.actions.act_url',
                'url': url,
                'target': 'self',
            }
            
        self.env.user.sudo()._sync_google_calendars(GoogleCal)
        # Commit calendar changes so that the @after_commit calls to the Google API are performed before
        # continuing with event sync.
        self.env.cr.commit()
        self.env.user.sudo()._sync_google_events(GoogleCal)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Google Calendar',
                'message': 'Your calendar is already connected and successfully synchronized!',
                'type': 'success',
                'sticky': False,
            }
        }

    # Phase 5 Fields
    # Questions Tab
    question_ids = fields.One2many('appointment.question', 'appointment_type_id', string='Questions')
    
    # Communication Tab
    message_intro = fields.Html('Introduction Message', translate=True)
    message_confirmation = fields.Html('Confirmation Message', translate=True)
    reminder_ids = fields.Many2many('calendar.alarm', string="Reminders")
    booking_template_id = fields.Many2one('mail.template', string='Booking Email', domain=[('model', '=', 'appointment.booking')])
    cancel_template_id = fields.Many2one('mail.template', string='Cancellation Email', domain=[('model', '=', 'appointment.booking')])
    
    # Options Tab
    allow_invitations = fields.Boolean(string="Allow Invitations", default=False)
    create_opportunity = fields.Boolean(string="Create Opportunity", default=False, help="Automatically create a CRM Lead/Opportunity when an appointment is booked.")
    has_payment_step = fields.Boolean(string="Up-front Payment", default=False)
    product_id = fields.Many2one('product.product', string="Booking Fees", domain=[('type', '=', 'service')])
    auto_confirm = fields.Boolean(string="Auto Confirm", default=True)
    auto_confirm_limit = fields.Integer('Auto Confirm Limit', default=100)
    display_pictures = fields.Boolean('Display pictures', default=True)
    schedule_type = fields.Selection([('weekly', 'Weekly'), ('flexible', 'Flexible')], string='Schedule', default='weekly')
    max_schedule_days = fields.Integer('Within the next X days', default=15)
    min_schedule_hours = fields.Float('at least X hours before', default=1.0)
    slot_interval = fields.Float('Create slot every', default=1.0)
    min_cancellation_hours = fields.Float('Cancellation up to', default=1.0)
    employee_schedule = fields.Boolean('Employee Schedule', default=False)

    @api.model
    def _create_and_open_appointment(self, vals):
        new_type = self.create(vals)
        return {
            'name': 'Appointment Type',
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.type',
            'res_id': new_type.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_preset_meeting(self):
        return self._create_and_open_appointment({
            'name': 'Meeting',
            'appointment_duration': 1.0,
            'location': 'office',
        })

    @api.model
    def action_preset_video(self):
        return self._create_and_open_appointment({
            'name': 'Video Call',
            'appointment_duration': 1.0,
            'location': 'online',
        })

    @api.model
    def action_preset_table(self):
        return self._create_and_open_appointment({
            'name': 'Table Booking',
            'appointment_duration': 2.0,
            'location': 'custom',
            'booking_target': 'resources',
        })

    @api.model
    def action_preset_resource(self):
        return self._create_and_open_appointment({
            'name': 'Book a Resource',
            'appointment_duration': 1.0,
            'booking_target': 'resources',
        })

    @api.constrains('slot_interval', 'appointment_duration')
    def _check_slot_configuration(self):
        for record in self:
            if getattr(record, 'slot_interval', 1.0) <= 0:
                raise ValidationError(
                    _("Slot Interval must be greater than 0.")
                )

            if getattr(record, 'appointment_duration', 1.0) <= 0:
                raise ValidationError(
                    _("Appointment Duration must be greater than 0.")
                )
