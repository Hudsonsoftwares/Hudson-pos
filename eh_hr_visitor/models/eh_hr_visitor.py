# -*- encoding: utf-8 -*-
from datetime import timedelta, datetime
import base64
import io
import logging
import uuid
import pytz

try:
    import qrcode
except ImportError:
    qrcode = None

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

AGREEMENT_PDF_FILENAME = "Agreements_%s.pdf"
VISITOR_PHOTO_FILENAME = "visitor_photo.jpg"


VISITOR_STATES = [
    ('draft', 'Draft'),
    ('invitation_sent', 'Invitation Sent'),
    ('pending', 'Pending'),
    ('confirmed', 'Confirmed'),
    ('arrived', 'Arrived'),
    ('signed_in', 'Checked In'),
    ('signed_out', 'Checked Out'),
    ('cancelled', 'Cancelled'),
    ('expired', 'Expired'),
]



class EhHrVisitor(models.Model):
    _name = 'eh.hr.visitor'
    _description = 'Visitor Sign-in Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'arrived_on desc, id desc'

    _sql_constraints = [
        ('visit_number_uniq', 'unique(visit_number)', 'Visit number must be unique!')
    ]

    name = fields.Char(string='Visitor name', required=True, tracking=True)
    visitor_company = fields.Char(string='Visitor organisation', tracking=True)
    visitor_email = fields.Char(string='Visitor email')
    visitor_phone = fields.Char(string='Visitor phone')

    host_employee_id = fields.Many2one(
        'hr.employee',
        string='Host',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    host_department_id = fields.Many2one(
        'hr.department',
        related='host_employee_id.department_id',
        store=True,
        string='Host Department',
        index=True,
    )
    purpose_id = fields.Many2one(
        'eh.hr.visitor.purpose',
        string='Purpose',
        required=True,
        ondelete='restrict',
    )

    site_id = fields.Many2one('eh.hr.kiosk.site', string='Kiosk site', ondelete='set null', index=True)
    device_id = fields.Many2one('eh.hr.kiosk.terminal', string='Kiosk device', ondelete='set null')

    arrived_on = fields.Datetime(string='Signed in', readonly=True)
    signed_out_on = fields.Datetime(string='Signed out', readonly=True, tracking=True)
    auto_signed_out = fields.Boolean(string='Auto-signed out', readonly=True)

    state = fields.Selection(
        VISITOR_STATES,
        string='Status',
        default='pending',
        required=True,
        tracking=True,
        index=True,
    )
    registration_type = fields.Selection([
        ('walk-in', 'Walk-in'),
        ('pre-registered', 'Pre-Registered')
    ], string='Registration Type', default='walk-in', index=True, tracking=True)

    nda_required = fields.Boolean(string='NDA required', tracking=True)
    nda_accepted = fields.Boolean(string='NDA accepted', tracking=True)
    nda_text = fields.Text(string='NDA text shown')
    
    visitor_agreement_required = fields.Boolean(string='Require Visitor Agreement', tracking=True)
    visitor_agreement_accepted = fields.Boolean(string='Visitor Agreement Accepted', tracking=True)
    visitor_agreement_text = fields.Text(string='Visitor Agreement Text Shown')
    
    safety_declaration_required = fields.Boolean(string='Require Safety Declaration', tracking=True)
    safety_declaration_accepted = fields.Boolean(string='Safety Declaration Accepted', tracking=True)
    safety_declaration_text = fields.Text(string='Safety Declaration Text Shown')
    
    privacy_consent_required = fields.Boolean(string='Require Privacy Consent', tracking=True)
    privacy_consent_text = fields.Text(string='Privacy Consent Text Shown')
    
    agreement_accepted_date = fields.Datetime(string='Agreement Accepted Date', readonly=True)
    signed_pdf = fields.Binary(string='Signed PDF', attachment=True, readonly=True)
    signed_pdf_filename = fields.Char(string='Signed PDF Filename', readonly=True)
    
    agreement_status = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('completed', 'Completed')
    ], string='Agreement Status', compute='_compute_agreement_status', store=True, tracking=True)

    photo = fields.Binary(string='Photo', attachment=True)
    photo_filename = fields.Char(string='Photo filename')

    visit_number = fields.Char(string='Visit number', readonly=True, copy=False, index=True)
    is_vip = fields.Boolean(string='VIP Visitor', tracking=True)

    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    station_id = fields.Many2one(
        'eh.hr.visitor.station',
        string='Frontdesk Station',
        ondelete='set null',
        index=True,
    )
    drink_id = fields.Many2one(
        'eh.hr.visitor.drink',
        string='Drink requested',
        ondelete='set null',
    )

    duration_minutes = fields.Integer(string='Duration (min)', compute='_compute_duration', store=True)

    # Pre-registration Fields
    visitor_type = fields.Selection([
        ('Customer', 'Customer'),
        ('Vendor', 'Vendor'),
        ('Interview', 'Interview'),
        ('Consultant', 'Consultant'),
        ('Guest', 'Guest'),
        ('Contractor', 'Contractor'),
        ('Delivery', 'Delivery'),
        ('Government', 'Government'),
        ('Other', 'Other'),
    ], string='Visitor Type', default='Other')
    expected_arrival = fields.Datetime(string='Expected Arrival Time')
    expected_departure = fields.Datetime(string='Expected Departure Time')
    meeting_title = fields.Char(string='Meeting Title')
    meeting_room_id = fields.Many2one('eh.hr.meeting.room', string='Meeting Room')
    
    # Registration details
    designation = fields.Char(string='Designation')
    visitor_address = fields.Char(string='Address')
    visitor_city = fields.Char(string='City')
    visitor_country = fields.Char(string='Country')
    identity_type = fields.Selection([
        ('passport', 'Passport'),
        ('id_card', 'ID Card'),
        ('driver_license', 'Driver License'),
        ('other', 'Other')
    ], string='Identity Type', default='id_card')
    identity_proof = fields.Binary(string='Identity Proof')
    identity_number = fields.Char(string='Identity Number')
    emergency_contact_name = fields.Char(string='Emergency Contact Name')
    emergency_contact_number = fields.Char(string='Emergency Contact Number')

    accept_privacy_policy = fields.Boolean(string='Accepted Privacy Policy')
    digital_signature = fields.Binary(string='Digital Signature')
    
    parking_required = fields.Boolean(string='Parking Required')
    special_instructions = fields.Text(string='Special Instructions')
    registration_token = fields.Char(string='Registration Token', copy=False, index=True)
    qr_code = fields.Binary(string='QR Code', copy=False)


    @api.depends('arrived_on', 'signed_out_on')
    def _compute_duration(self):
        for record in self:
            if record.arrived_on and record.signed_out_on:
                delta = record.signed_out_on - record.arrived_on
                record.duration_minutes = int(delta.total_seconds() // 60)
            else:
                record.duration_minutes = 0

    @api.depends('nda_required', 'visitor_agreement_required', 'safety_declaration_required', 'privacy_consent_required',
                 'nda_accepted', 'visitor_agreement_accepted', 'safety_declaration_accepted', 'accept_privacy_policy', 'digital_signature')
    def _compute_agreement_status(self):
        for rec in self:
            required = any([rec.nda_required, rec.visitor_agreement_required, rec.safety_declaration_required, rec.privacy_consent_required])
            if not required:
                rec.agreement_status = 'not_required'
            else:
                accepted = True
                if rec.nda_required and not rec.nda_accepted: accepted = False
                if rec.visitor_agreement_required and not rec.visitor_agreement_accepted: accepted = False
                if rec.safety_declaration_required and not rec.safety_declaration_accepted: accepted = False
                if rec.privacy_consent_required and not rec.accept_privacy_policy: accepted = False
                if not rec.digital_signature: accepted = False
                
                if accepted:
                    rec.agreement_status = 'completed'
                else:
                    rec.agreement_status = 'pending'

    @api.constrains('nda_required', 'nda_accepted', 'visitor_agreement_required', 'visitor_agreement_accepted', 'safety_declaration_required', 'safety_declaration_accepted', 'privacy_consent_required', 'accept_privacy_policy', 'digital_signature', 'agreement_status')
    def _check_nda_acceptance(self):
        for record in self:
            if record.agreement_status == 'pending' and record.state != 'pending':
                raise ValidationError(_("Visitor must complete required agreements before Check-In."))

    @api.constrains('meeting_room_id', 'expected_arrival', 'expected_departure')
    def _check_meeting_room_booking(self):
        for record in self:
            if record.meeting_room_id and record.expected_arrival and record.expected_departure:
                domain = [
                    ('meeting_room_id', '=', record.meeting_room_id.id),
                    ('id', '!=', record.id),
                    ('state', 'in', ['confirmed', 'arrived', 'signed_in']),
                    ('expected_arrival', '<', record.expected_departure),
                    ('expected_departure', '>', record.expected_arrival),
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The meeting room %s is already booked for this time slot.") % record.meeting_room_id.name)

    @api.constrains('host_employee_id', 'expected_arrival', 'expected_departure')
    def _check_host_availability(self):
        hr_leave_env = self.env.get('hr.leave')
        for record in self:
            if record.host_employee_id and record.expected_arrival and record.expected_departure:
                domain = [
                    ('host_employee_id', '=', record.host_employee_id.id),
                    ('id', '!=', record.id),
                    ('state', 'in', ['confirmed', 'arrived', 'signed_in']),
                    ('expected_arrival', '<', record.expected_departure),
                    ('expected_departure', '>', record.expected_arrival),
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The host %s already has another visitor expected during this time slot.") % record.host_employee_id.name)
                
                if hr_leave_env is not None:
                    leave_domain = [
                        ('employee_id', '=', record.host_employee_id.id),
                        ('state', '=', 'validate'),
                        ('date_from', '<=', record.expected_departure),
                        ('date_to', '>=', record.expected_arrival),
                    ]
                    if hr_leave_env.sudo().search_count(leave_domain) > 0:
                        raise ValidationError(_("The host %s is on leave during this time slot.") % record.host_employee_id.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('visit_number'):
                vals['visit_number'] = self.env['ir.sequence'].next_by_code('eh.hr.visitor') or self._fallback_visit_number()
        return super().create(vals_list)

    def _fallback_visit_number(self):
        """If the sequence record has not been seeded, fall back to a
        timestamp-based number so the sign-in flow still works on a fresh
        install before any data file has run."""
        return fields.Datetime.now().strftime('V%Y%m%d%H%M%S%f')

    def _generate_agreement_pdf(self, raise_exceptions=False):
        for record in self:
            try:
                pdf, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf('eh_hr_visitor.report_visitor_agreement', record.ids)
                record.sudo().write({
                    'signed_pdf': base64.b64encode(pdf),
                    'signed_pdf_filename': AGREEMENT_PDF_FILENAME % record.visit_number
                })
            except Exception as e:
                _logger.exception("Error generating agreement PDF for visitor %s", record.visit_number)
                if raise_exceptions:
                    raise ValidationError(_("Error generating PDF: %s") % str(e))

    @api.model
    def _cron_generate_agreement_pdfs(self, batch_limit=50):
        records = self.search([
            ('signed_pdf', '=', False),
            ('digital_signature', '!=', False),
            ('agreement_status', '=', 'completed')
        ], limit=batch_limit)
        records._generate_agreement_pdf(raise_exceptions=False)

    def action_sign_in(self):
        for record in self:
            if record.state == 'signed_in':
                continue
            if record.state not in ['pending', 'confirmed', 'arrived']:
                raise ValidationError(_("Cannot sign in from state: %s") % record.state)
            if record.agreement_status == 'pending':
                raise ValidationError(_("Visitor must complete required agreements before Check-In."))
            record.write({
                'state': 'signed_in',
                'arrived_on': record.arrived_on or fields.Datetime.now(),
            })
            record._notify_host()

    def action_sign_out(self):
        for record in self:
            if record.state != 'signed_in':
                continue
            record.write({
                'state': 'signed_out',
                'signed_out_on': fields.Datetime.now(),
            })

    def action_reset_agreements(self):
        if not self.env.user.has_group('base.group_system') and not self.env.user.has_group('hr.group_hr_manager'):
            raise ValidationError(_("Only Administrators can reset agreements."))
        for record in self:
            record.write({
                'nda_accepted': False,
                'visitor_agreement_accepted': False,
                'safety_declaration_accepted': False,
                'accept_privacy_policy': False,
                'digital_signature': False,
                'signed_pdf': False,
                'signed_pdf_filename': False,
                'agreement_accepted_date': False,
            })

    def action_regenerate_agreement_pdf(self):
        if not self.env.user.has_group('base.group_system') and not self.env.user.has_group('hr.group_hr_manager'):
            raise ValidationError(_("Only Administrators can regenerate agreement PDFs."))
        records = self.filtered(lambda r: r.agreement_status == 'completed' and r.digital_signature)
        records._generate_agreement_pdf(raise_exceptions=True)

    def action_send_invitation(self):
        for record in self:
            if record.state in ['draft', 'cancelled']:
                token = str(uuid.uuid4())
                record.write({
                    'registration_token': token,
                    'state': 'invitation_sent',
                })
                # Send email logic will go here (triggered via email template)
                template = self.env.ref('eh_hr_visitor.email_template_visitor_invitation', raise_if_not_found=False)
                if template:
                    template.send_mail(record.id, force_send=True, email_values={'email_to': record.visitor_email})

    def action_resend_invitation(self):
        for record in self:
            if record.state == 'invitation_sent':
                template = self.env.ref('eh_hr_visitor.email_template_visitor_invitation', raise_if_not_found=False)
                if template:
                    template.send_mail(record.id, force_send=True, email_values={'email_to': record.visitor_email})

    def action_cancel_invitation(self):
        for record in self:
            if record.state not in ['signed_in', 'signed_out']:
                record.write({'state': 'cancelled'})

    def action_simulate_qr_scan(self):
        for record in self:
            if record.state in ['confirmed', 'pending']:
                record.write({'state': 'arrived'})
            else:
                raise ValidationError(_("Visitor must be Confirmed or Pending to register arrival."))

    def action_open_qr_scan_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Simulate QR Scan',
            'res_model': 'eh.hr.visitor.qr.scan.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
                
    def _generate_qr_code(self):
        for record in self:
            if not record.qr_code and record.visit_number:
                if not qrcode:
                    _logger.warning("qrcode library might not be installed in all environments, fallback to barcode if needed")
                    continue
                try:
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                    qr.add_data(record.visit_number)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    record.qr_code = base64.b64encode(buffer.getvalue())
                except Exception as e:
                    _logger.exception("Error generating QR code: %s", str(e))


    def _notify_host(self):
        """Email the host that their visitor has arrived. Uses the
        seeded mail.template if it exists, otherwise falls back to a
        plain message_post on the visitor's chatter."""
        for record in self:
            if record.station_id:
                body = _("Visitor %(name)s arrived to see %(host)s. Purpose: %(purpose)s") % {
                    'name': record.name,
                    'host': record.host_employee_id.name,
                    'purpose': record.purpose_id.name,
                }
                if record.drink_id:
                    body += _("\nDrink requested: %s") % record.drink_id.name

                partner_ids = record.host_employee_id.user_id.partner_id.ids if record.host_employee_id.user_id else (record.host_employee_id.work_contact_id.ids if record.host_employee_id.work_contact_id else [])

                if record.station_id.notify_discuss and partner_ids:
                    record.message_post(
                        body=body,
                        partner_ids=partner_ids,
                        message_type='comment',
                        subtype_xmlid='mail.mt_note'
                    )
                
                if record.station_id.notify_email:
                    if not record.host_employee_id.work_email:
                        record.message_post(
                            body=_("Host %s has no work email; could not notify by email.") % record.host_employee_id.name,
                        )
                    else:
                        template = self.env.ref('eh_hr_visitor.email_template_visitor_arrived', raise_if_not_found=False)
                        if template:
                            template.send_mail(record.id, force_send=False)
                        else:
                            record.message_post(
                                body=body,
                                partner_ids=partner_ids,
                            )

                if record.station_id.notify_sms and self.env['ir.module.module'].sudo().search([('name', '=', 'sms'), ('state', '=', 'installed')]):
                    phone = record.host_employee_id.mobile_phone or record.host_employee_id.work_phone
                    if phone:
                        try:
                            self.env['sms.sms'].sudo().create({
                                'number': phone,
                                'body': body,
                            })
                        except Exception:
                            _logger.exception("Error sending SMS notification to %s", phone)
            else:
                if not record.host_employee_id.work_email:
                    record.message_post(
                        body=_("Host %s has no work email; could not notify by email.") % record.host_employee_id.name,
                    )
                    continue
                template = self.env.ref('eh_hr_visitor.email_template_visitor_arrived', raise_if_not_found=False)
                if template:
                    template.send_mail(record.id, force_send=False)
                else:
                    body = _("Visitor %s arrived to see %s. Purpose: %s") % (
                        record.name, record.host_employee_id.name, record.purpose_id.name,
                    )
                    if record.drink_id:
                        body += _("\nDrink requested: %s") % record.drink_id.name
                    record.message_post(
                        body=body,
                        partner_ids=record.host_employee_id.work_contact_id.ids if record.host_employee_id.work_contact_id else [],
                    )

    @api.model
    def _cron_auto_sign_out(self, *, batch_limit=500):
        """End-of-day auto sign-out for visitors still on site past the
        configured hour. Each company's hour applied independently.
        """
        now_utc = fields.Datetime.now()
        signed_out_count = 0
        # Track the companies actually due for sign-out and whether the batch
        # limit cut the run short, so the cron's remaining-work report is
        # accurate and the framework re-triggers the job to drain a backlog.
        eligible_company_ids = []
        hit_limit = False
        for company in self.env['res.company'].search([]):
            if not company.eh_hr_visitor_auto_checkout_enabled:
                continue
            cutoff_hour = company.eh_hr_visitor_auto_checkout_hour
            if cutoff_hour is None:
                cutoff_hour = 18
            tz_name = company.partner_id.tz or 'UTC'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
            local_now = pytz.utc.localize(now_utc).astimezone(tz)
            if local_now.hour < cutoff_hour:
                continue
            eligible_company_ids.append(company.id)

            remaining = batch_limit - signed_out_count
            if remaining <= 0:
                hit_limit = True
                break
            stale = self.search([
                ('company_id', '=', company.id),
                ('state', '=', 'signed_in'),
            ], limit=remaining)
            if stale:
                stale.write({
                    'state': 'signed_out',
                    'signed_out_on': fields.Datetime.now(),
                    'auto_signed_out': True,
                })
                signed_out_count += len(stale)

        cron_id = self.env.context.get('cron_id')
        cron = self.env['ir.cron']
        if cron_id and hasattr(cron, '_commit_progress'):
            still_pending = 0
            if hit_limit and eligible_company_ids:
                still_pending = self.search_count([
                    ('company_id', 'in', eligible_company_ids),
                    ('state', '=', 'signed_in'),
                ])
            cron._commit_progress(signed_out_count, remaining=still_pending)
        return signed_out_count

    @api.model
    def _cron_expire_invitations(self):
        """Daily/Hourly cron to expire unconfirmed or missed invitations."""
        now = fields.Datetime.now()
        expired = self.search([
            ('state', 'in', ['draft', 'invitation_sent', 'confirmed']),
            ('expected_arrival', '<', now)
        ])
        if expired:
            expired.write({'state': 'expired'})


    @api.model
    def _cron_retention_sweep(self, *, batch_limit=500):
        """Daily. Delete signed-out visitor rows past the company's
        retention window. NDA snapshots and photos are deleted as part
        of the visitor row, so the privacy promise that "we do not keep
        visitor data forever" is enforced in code, not by paperwork.
        """
        now = fields.Datetime.now()
        deleted = 0
        # Remember each company's cutoff so the remaining backlog can be
        # counted accurately for the cron progress report.
        company_cutoffs = []
        for company in self.env['res.company'].search([]):
            retention_days = company.eh_hr_visitor_retention_days or 365
            cutoff = now - timedelta(days=retention_days)
            company_cutoffs.append((company.id, cutoff))
            remaining = batch_limit - deleted
            if remaining <= 0:
                break
            stale = self.search([
                ('company_id', '=', company.id),
                ('state', '=', 'signed_out'),
                ('signed_out_on', '<=', cutoff),
            ], limit=remaining)
            if stale:
                deleted += len(stale)
                stale.unlink()

        cron_id = self.env.context.get('cron_id')
        cron = self.env['ir.cron']
        if cron_id and hasattr(cron, '_commit_progress'):
            still_pending = 0
            cutoff_groups = {}
            for company_id, cutoff in company_cutoffs:
                cutoff_groups.setdefault(cutoff, []).append(company_id)
            for cutoff, company_ids in cutoff_groups.items():
                still_pending += self.search_count([
                    ('company_id', 'in', company_ids),
                    ('state', '=', 'signed_out'),
                    ('signed_out_on', '<=', cutoff),
                ])
            cron._commit_progress(deleted, remaining=still_pending)
        return deleted

    @api.model
    def get_dashboard_data(self):
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        
        now_utc = fields.Datetime.now()
        
        local_now = pytz.utc.localize(now_utc).astimezone(tz)
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        today_start_utc = local_start.astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = local_end.astimezone(pytz.utc).replace(tzinfo=None)
        
        domain_today = [('arrived_on', '>=', today_start_utc), ('arrived_on', '<=', today_end_utc)]
        
        walkin = self.search_count([('arrived_on', '>=', today_start_utc), ('arrived_on', '<=', today_end_utc), ('registration_token', '=', False)])
        checked_in = self.search_count([('state', '=', 'signed_in')])
        checked_out = self.search_count([('state', '=', 'signed_out'), ('arrived_on', '>=', today_start_utc), ('arrived_on', '<=', today_end_utc)])
        
        expected = self.search_count([('state', 'in', ['confirmed', 'arrived']), ('expected_arrival', '>=', today_start_utc), ('expected_arrival', '<=', today_end_utc)])
        upcoming = self.search_count([('state', 'in', ['draft', 'invitation_sent', 'confirmed']), ('expected_arrival', '>', now_utc)])
        late = self.search_count([('state', 'in', ['confirmed', 'arrived']), ('expected_arrival', '<', now_utc), ('expected_arrival', '>=', today_start_utc)])
        cancelled = self.search_count([('state', '=', 'cancelled'), ('expected_arrival', '>=', today_start_utc), ('expected_arrival', '<=', today_end_utc)])
        
        visitors_today = self.search(domain_today)
        
        purpose_counts = {}
        hour_counts = {str(i): 0 for i in range(24)}
        
        for v in visitors_today:
            p_name = v.purpose_id.name or 'Other'
            purpose_counts[p_name] = purpose_counts.get(p_name, 0) + 1
            
            if v.arrived_on:
                local_dt = pytz.utc.localize(v.arrived_on).astimezone(tz)
                hour_counts[str(local_dt.hour)] += 1
                
        visitors_by_purpose = {
            'labels': list(purpose_counts.keys()),
            'data': list(purpose_counts.values())
        }
        
        peak_hours_labels = [f"{i}:00" for i in range(6, 21)]
        peak_hours_data = [hour_counts[str(i)] for i in range(6, 21)]
        
        peak_hours = {
            'labels': peak_hours_labels,
            'data': peak_hours_data
        }
        
        latest_records = self.search([], limit=10, order='arrived_on desc, expected_arrival desc, id desc')
        latest_visitors = []
        for r in latest_records:
            check_in_time = ''
            if r.arrived_on:
                local_dt = pytz.utc.localize(r.arrived_on).astimezone(tz)
                check_in_time = local_dt.strftime('%Y-%m-%d %H:%M')
            elif r.expected_arrival:
                local_dt = pytz.utc.localize(r.expected_arrival).astimezone(tz)
                check_in_time = 'Expected: ' + local_dt.strftime('%Y-%m-%d %H:%M')
                
            latest_visitors.append({
                'id': r.id,
                'name': r.name,
                'company': r.visitor_company or '',
                'host': r.host_employee_id.name or '',
                'purpose': r.purpose_id.name or '',
                'check_in_time': check_in_time,
                'state': r.state,
            })
            
        return {
            'expected': expected,
            'walkin': walkin,
            'checked_in': checked_in,
            'checked_out': checked_out,
            'upcoming': upcoming,
            'late': late,
            'cancelled': cancelled,
            'visitors_by_purpose': visitors_by_purpose,
            'peak_hours': peak_hours,
            'latest_visitors': latest_visitors
        }

