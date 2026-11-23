# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Single published celebration type. It keeps the historic
# ``appointment_type_event_other`` XML id so the POS config default, the POS
# booking screen and existing bookings stay connected to the same record.
LIFE_EVENTS_TYPE_NAME = 'Celebrate Your Life Events'
EVENT_TYPE_SPECS = [
    {
        'xml_id': 'appointment_type_event_other',
        'name': LIFE_EVENTS_TYPE_NAME,
        'event_category': 'other',
        'event_emoji': '🎉',
        'legacy_names': ('Other Celebrations',),
    },
]

# Former per-occasion types created by older versions: their tables, bookings and
# POS configs are moved to the Life Events type and the types are deleted.
LEGACY_EVENT_TYPE_XMLIDS = (
    'appointment_type_event_birthday',
    'appointment_type_event_anniversary',
    'appointment_type_event_win',
)

LIFE_EVENT_ANSWERS = ('Birthday', 'Anniversary', 'Engagement', 'Wedding', 'Other')

# Question roles that belong to the Event / Celebration booking flow.
CELEBRATION_QUESTION_ROLES = ('celebration_type', 'occasion_date', 'celebrant_name', 'occasion_title')


class AppointmentTypePos(models.Model):
    _name = 'appointment.type'
    _inherit = ['appointment.type', 'pos.load.mixin']

    # ------------------------------------------------------------------
    # Celebration / Event Booking & Next-Year Wishing Configuration
    # (owned by the bridge; the stock appointment module stays untouched)
    # ------------------------------------------------------------------
    is_event_booking = fields.Boolean(
        string='Event / Celebration Booking', default=False,
        help="Mark this appointment type as a celebration/event booking with special day tracking and wishes.")
    event_category = fields.Selection([
        ('birthday', 'Birthday Celebration'),
        ('anniversary', 'Wedding Anniversary'),
        ('win', 'Win Celebration'),
        ('other', 'Other Celebration'),
    ], string='Celebration Category')
    event_emoji = fields.Char(string='Event Emoji', size=16)

    enable_anniversary_wishes = fields.Boolean(
        string='Enable Yearly Celebration Wishes', default=False,
        help="Automatically send celebration wishes via Email/SMS starting on next year's anniversary of the Special Day.")
    wish_send_advance_invite = fields.Boolean(
        string='Send Pre-Celebration Invite', default=True,
        help="Send an invitation X days before next year's Special Day anniversary.")
    wish_advance_days = fields.Integer(
        string='Invite Days Before', default=7,
        help="Number of days before the Special Day anniversary to send the invitation.")
    wish_send_on_day = fields.Boolean(
        string='Send Special Day Wish', default=True,
        help="Send a warm celebration wish directly on next year's Special Day.")
    wish_advance_email_template_id = fields.Many2one(
        'mail.template', string='Pre-Celebration Email Template',
        domain=[('model', '=', 'appointment.booking')],
        default=lambda self: self.env.ref('hudson_pos_booking.email_template_celebration_advance', raise_if_not_found=False))
    wish_day_email_template_id = fields.Many2one(
        'mail.template', string='Special Day Email Template',
        domain=[('model', '=', 'appointment.booking')],
        default=lambda self: self.env.ref('hudson_pos_booking.email_template_celebration_day', raise_if_not_found=False))
    wish_advance_sms_text = fields.Text(
        string='Advance Invite SMS Text',
        default=(
            "Hi {guest_name}! {celebrant_name}'s {event_name} celebration is coming up on {special_day}. "
            "Reserve a table with us at {company_name}! Grab a party here: {booking_url}"
        ),
        help="Available placeholders: {guest_name}, {celebrant_name}, {event_name}, {occasion_title}, {special_day}, {company_name}, {booking_url}")
    wish_day_sms_text = fields.Text(
        string='Special Day Wish SMS Text',
        default=(
            "Happy celebration wishes for {celebrant_name}'s {event_name} from {company_name}! "
            "Celebrate with family & friends — Grab a party here: {booking_url}"
        ),
        help="Available placeholders: {guest_name}, {celebrant_name}, {event_name}, {occasion_title}, {special_day}, {company_name}, {booking_url}")

    # ------------------------------------------------------------------
    # Website Pre-Food option (available on every appointment type)
    # ------------------------------------------------------------------
    pre_food_required = fields.Boolean(
        string='Pre-Food Required', default=False,
        help="Show the Pre-Order Food selection and Special Notes on the website booking form.")

    # ------------------------------------------------------------------
    # 'Event / Celebration Booking' toggle -> celebration questions on the website
    # ------------------------------------------------------------------
    @api.model
    def _hudson_celebration_questions(self):
        """Reusable Event Type + Special Day Date questions provisioned by the bridge."""
        Question = self.env['appointment.question'].sudo()
        questions = Question.browse()
        for xml_id in ('question_event_celebration_type', 'question_event_occasion_date'):
            rec = self.env.ref(f'hudson_pos_booking.{xml_id}', raise_if_not_found=False)
            if rec and rec.exists():
                questions |= rec
        return questions

    def _hudson_ensure_celebration_setup(self):
        """Attach the celebration questions (and a default emoji) to celebration types."""
        questions = self._hudson_celebration_questions()
        for at in self.sudo().filtered('is_event_booking'):
            vals = {}
            missing = questions - at.question_ids
            if missing:
                vals['question_ids'] = [(4, q.id) for q in missing]
            if not at.event_emoji:
                vals['event_emoji'] = '🎉'
            if vals:
                at.with_context(hudson_skip_celebration_setup=True).write(vals)

    @api.onchange('is_event_booking')
    def _onchange_is_event_booking_questions(self):
        for at in self:
            if at.is_event_booking:
                at.question_ids |= self._hudson_celebration_questions()
                if not at.event_emoji:
                    at.event_emoji = '🎉'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('hudson_skip_celebration_setup'):
            records.filtered('is_event_booking')._hudson_ensure_celebration_setup()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_event_booking') and not self.env.context.get('hudson_skip_celebration_setup'):
            self._hudson_ensure_celebration_setup()
        return res

    def _hudson_is_celebration_question(self, question):
        """Celebration questions (Event Type, Special Day Date, Celebrant, Occasion)
        are shown / required on the website only when 'Event / Celebration Booking' is on."""
        self.ensure_one()
        question = question.sudo()
        return bool(question.is_occasion_date or question.question_role in CELEBRATION_QUESTION_ROLES)

    def _hudson_website_questions(self):
        """Questions shown and validated on the website booking form."""
        self.ensure_one()
        at = self.sudo()
        if at.is_event_booking:
            return at.question_ids
        return at.question_ids.filtered(lambda q: not at._hudson_is_celebration_question(q))

    def _hudson_prefood_allowed(self):
        """Website shows / accepts food pre-orders and special notes only when this is True."""
        self.ensure_one()
        return bool(self.sudo().pre_food_required)

    # ------------------------------------------------------------------
    # Resource (table) configuration hints for celebration types. A type
    # without resources can still be saved and published.
    # ------------------------------------------------------------------
    hudson_resource_config_warning = fields.Text(
        string='Resource Configuration Warning', compute='_compute_hudson_resource_config')

    @api.depends('is_event_booking', 'booking_target', 'resource_ids', 'resource_ids.capacity',
                 'availability_ids', 'max_schedule_days')
    def _compute_hudson_resource_config(self):
        for at in self:
            at.hudson_resource_config_warning = '\n'.join(at._hudson_get_resource_config_issues())

    def _hudson_is_resource_event_type(self):
        self.ensure_one()
        return bool(self.is_event_booking and self.booking_target == 'resources')

    def _hudson_get_resource_config_issues(self):
        """Human readable reasons why the website could not offer valid
        date / time / party-size options for this celebration type."""
        self.ensure_one()
        if not self._hudson_is_resource_event_type():
            return []
        issues = []
        if self.resource_ids and not any(cap > 0 for cap in self.resource_ids.mapped('capacity')):
            issues.append(_("The assigned resources have no seating capacity, so no party size can be offered."))
        if 'availability_ids' in self._fields and not self.availability_ids:
            issues.append(_("No opening hours (availability) are defined, so no time slots can be offered."))
        if 'max_schedule_days' in self._fields and self.max_schedule_days <= 0:
            issues.append(_("'Schedule up to' days must be greater than 0, so dates can be offered."))
        return issues

    def action_hudson_configure_resources(self):
        """Backend popup on the stock Resources (resource_ids) field of this type."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Configure Resources"),
            'res_model': 'appointment.type',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('hudson_pos_booking.appointment_type_view_form_hudson_configure_resources').id, 'form')],
            'target': 'new',
        }

    def _hudson_apply_resource_config(self, publish=False):
        for at in self:
            vals = {}
            if at._hudson_is_resource_event_type():
                # The table is assigned automatically: no resource picker on the website.
                if at.assign_method != 'random':
                    vals['assign_method'] = 'random'
                if at.schedule_based_on != 'website':
                    vals['schedule_based_on'] = 'website'
            if publish and not at.is_published:
                vals['is_published'] = True
            if vals:
                at.write(vals)
        return {'type': 'ir.actions.act_window_close'}

    def action_hudson_save_resources(self):
        # The dialog has already saved resource_ids before calling this button.
        return self._hudson_apply_resource_config(publish=False)

    def action_hudson_save_resources_and_publish(self):
        return self._hudson_apply_resource_config(publish=True)

    @api.constrains('wish_advance_days', 'wish_send_advance_invite')
    def _check_wish_advance_days(self):
        for record in self:
            if record.wish_send_advance_invite and record.wish_advance_days < 1:
                raise ValidationError(
                    _("Invite Days Before must be at least 1 day when Pre-Celebration Invite is enabled.")
                )

    @api.model
    def load_pos_data_force_loading(self):
        return True

    @api.model
    def _load_pos_data_domain(self, data):
        config = data.get('pos.config')
        if not config or not config.use_booking:
            return [('id', '=', False)]
        return [
            ('booking_target', '=', 'resources'),
            '|', ('company_id', '=', False), ('company_id', '=', config.company_id.id),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        base_fields = ['name', 'appointment_duration', 'resource_ids']
        optional_fields = ['event_category', 'event_emoji', 'is_event_booking', 'is_published']
        return [f for f in base_fields + optional_fields if f in self._fields]

    @api.model
    def _get_or_create_xmlid_record(self, model_name, xml_id_name, search_domain, create_vals):
        IrModelData = self.env['ir.model.data'].sudo()
        full_xml_id = f'hudson_pos_booking.{xml_id_name}'
        existing = self.env.ref(full_xml_id, raise_if_not_found=False)
        created = False
        if existing and existing.exists():
            return existing, created

        Model = self.env[model_name].sudo().with_context(active_test=False)
        safe_domain = []
        for leaf in search_domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                field_name = leaf[0]
                if field_name not in Model._fields:
                    continue
            safe_domain.append(leaf)

        rec = Model.browse()
        if safe_domain:
            try:
                rec = Model.search(safe_domain, order='id asc', limit=1)
            except Exception:
                rec = Model.browse()

        if not rec and 'name' in Model._fields and 'name' in create_vals:
            try:
                rec = Model.search([('name', '=', create_vals['name'])], order='id asc', limit=1)
            except Exception:
                rec = Model.browse()

        if not rec:
            safe_create_vals = {k: v for k, v in create_vals.items() if k in Model._fields}
            rec = Model.create(safe_create_vals)
            created = True

        if rec:
            imd = IrModelData.search([
                ('module', '=', 'hudson_pos_booking'),
                ('name', '=', xml_id_name),
            ], limit=1)
            if imd:
                imd.write({
                    'model': model_name,
                    'res_id': rec.id,
                    'noupdate': True,
                })
            else:
                IrModelData.create({
                    'name': xml_id_name,
                    'module': 'hudson_pos_booking',
                    'model': model_name,
                    'res_id': rec.id,
                    'noupdate': True,
                })
        return rec, created

    @api.model
    def _hudson_remove_legacy_event_types(self, legacy_types, life_events_type):
        """Delete the retired per-occasion types. Their bookings are moved to the
        Life Events type (the occasion is kept in ``celebration_type``) and POS
        configs are repointed first, so no history is lost. A type that cannot be
        deleted stays unpublished, so the install / upgrade never fails on it."""
        Booking = self.env['appointment.booking'].sudo().with_context(active_test=False, skip_table_sync=True)
        PosConfig = self.env['pos.config'].sudo().with_context(active_test=False, skip_table_sync=True)
        has_celebration_type = 'celebration_type' in Booking._fields
        category_to_event = {'birthday': 'birthday', 'anniversary': 'anniversary', 'win': 'other'}
        for legacy in legacy_types:
            try:
                with self.env.cr.savepoint():
                    bookings = Booking.search([('appointment_type_id', '=', legacy.id)])
                    if has_celebration_type:
                        event_key = category_to_event.get(legacy.event_category, 'other')
                        bookings.filtered(lambda b: not b.celebration_type).write({'celebration_type': event_key})
                    if bookings:
                        bookings.write({'appointment_type_id': life_events_type.id})
                    PosConfig.search([('booking_appointment_type_id', '=', legacy.id)]).write({
                        'booking_appointment_type_id': life_events_type.id,
                    })
                    name = legacy.name
                    legacy.unlink()
                    _logger.info("hudson_pos_booking: removed retired appointment type '%s' (%s bookings moved).",
                                 name, len(bookings))
            except Exception:
                _logger.warning("hudson_pos_booking: could not remove retired appointment type %s; it stays unpublished.",
                                legacy.id, exc_info=True)

    @api.model
    def _ensure_default_event_booking_setup(self):
        """
        Idempotently provision:
        1) 3 reusable event questions (Event Type, Special Day Date, Special Requests)
        2) 1 resource-based 'Celebrate Your Life Events' appointment.type; the former
           Birthday / Anniversary / Win types are deleted after their tables and bookings move over
        3) Unpublish legacy 'Table Booking' (without deleting historical records) and repoint pos.config to 'Other Celebrations'
        """
        Question = self.env['appointment.question'].sudo()
        has_q_role = 'question_role' in Question._fields
        has_q_reusable = 'is_reusable' in Question._fields
        has_occ_date = 'is_occasion_date' in Question._fields

        # 1. Ensure the 3 reusable Life Event questions exist:
        #    Event type / Special day date / Special requests
        question_specs = [
            {
                'xml_id': 'question_event_celebration_type',
                'search_domain': ([('question_role', '=', 'celebration_type')] if has_q_role else [('name', '=', 'Event Type')])
                                 + ([('is_reusable', '=', True)] if has_q_reusable else []),
                'vals': {
                    'name': 'Event Type',
                    'question_type': 'select',
                    'question_role': 'celebration_type',
                    'is_required': True,
                    'is_reusable': True,
                    'sequence': 10,
                    'company_id': False,
                    'answer_ids': [(0, 0, {'name': name, 'sequence': (i + 1) * 10})
                                   for i, name in enumerate(LIFE_EVENT_ANSWERS)],
                },
            },
            {
                'xml_id': 'question_event_occasion_date',
                'search_domain': ([('question_role', '=', 'occasion_date')] if has_q_role else [('name', '=', 'Special Day / Birthdate')])
                                 + ([('is_reusable', '=', True)] if has_q_reusable else []),
                'vals': {
                    'name': 'Special Day Date',
                    'question_type': 'date',
                    'question_role': 'occasion_date',
                    'is_occasion_date': True,
                    'is_required': True,
                    'is_reusable': True,
                    'sequence': 20,
                    'company_id': False,
                },
            },
            {
                'xml_id': 'question_event_special_requests',
                'search_domain': ([('question_role', '=', 'special_requests')] if has_q_role else [('name', '=', 'Special Requests')])
                                 + ([('is_reusable', '=', True)] if has_q_reusable else []),
                'vals': {
                    'name': 'Special Requests',
                    'question_type': 'text',
                    'question_role': 'special_requests',
                    'is_required': False,
                    'is_reusable': True,
                    'sequence': 30,
                    'placeholder': 'e.g. Cake at 8 PM, window table, 1 guest allergic to shellfish...',
                    'company_id': False,
                },
            },
        ]
        # Questions of the former multi-type setup that are no longer asked.
        retired_question_roles = ('celebrant_name', 'occasion_title')

        event_questions = Question.browse()
        for q_spec in question_specs:
            q_rec, q_created = self._get_or_create_xmlid_record(
                'appointment.question',
                q_spec['xml_id'],
                q_spec['search_domain'],
                q_spec['vals'],
            )
            if not q_created and q_rec:
                q_fix = {}
                target_role = q_spec['vals']['question_role']
                if has_q_role and getattr(q_rec, 'question_role', False) != target_role:
                    q_fix['question_role'] = target_role
                if target_role == 'occasion_date':
                    if 'question_type' in Question._fields and q_rec.question_type != 'date':
                        q_fix['question_type'] = 'date'
                    if has_occ_date and not getattr(q_rec, 'is_occasion_date', False):
                        q_fix['is_occasion_date'] = True
                    if q_rec.name in ('Special Day / Birthdate', 'Special Day / Anniversary Date'):
                        q_fix['name'] = q_spec['vals']['name']
                if target_role == 'celebration_type':
                    if q_rec.question_type not in ('select', 'radio'):
                        q_fix['question_type'] = 'select'
                    existing_answers = set(q_rec.answer_ids.mapped('name'))
                    missing = [(0, 0, {'name': name, 'sequence': (i + 1) * 10})
                               for i, name in enumerate(LIFE_EVENT_ANSWERS) if name not in existing_answers]
                    if missing:
                        q_fix['answer_ids'] = missing
                if has_q_reusable and not getattr(q_rec, 'is_reusable', False):
                    q_fix['is_reusable'] = True
                if q_fix:
                    q_rec.write(q_fix)
            if q_rec:
                event_questions |= q_rec

        # 2. Gather default templates & legacy schedule hints without clobbering existing types
        AppType = self.env['appointment.type'].sudo().with_context(active_test=False)
        has_is_event_booking = 'is_event_booking' in AppType._fields
        if has_is_event_booking:
            legacy_table_types = AppType.search([
                ('is_event_booking', '=', False),
                ('name', 'ilike', 'Table Booking'),
            ], order='id asc')
        else:
            legacy_table_types = AppType.search([
                ('name', 'ilike', 'Table Booking'),
            ], order='id asc')
        legacy_primary = legacy_table_types[:1]

        tpl_confirm = self.env.ref('appointment.email_template_booking_confirmation', raise_if_not_found=False)
        tpl_cancel = self.env.ref('appointment.email_template_booking_cancellation', raise_if_not_found=False)
        tpl_wish_adv = self.env.ref('hudson_pos_booking.email_template_celebration_advance', raise_if_not_found=False)
        tpl_wish_day = self.env.ref('hudson_pos_booking.email_template_celebration_day', raise_if_not_found=False)

        default_company = (
            (legacy_primary.company_id if legacy_primary and legacy_primary.company_id else False)
            or self.env['pos.config'].sudo().with_context(active_test=False).search([
                ('module_pos_restaurant', '=', True),
            ], order='id asc', limit=1).company_id
            or self.env.company
        )
        tz_name = (
            (legacy_primary.appointment_tz if legacy_primary else False)
            or default_company.partner_id.tz
            or self.env.user.tz
            or 'Asia/Calcutta'
        )
        default_avail_tuples = [
            (str(day), 11.0, 22.0) for day in range(7)
        ]
        if legacy_primary and legacy_primary.availability_ids:
            default_avail_tuples = [
                (av.day_of_week, av.start_time, av.end_time)
                for av in legacy_primary.availability_ids
            ]

        created_by_cat = {}
        for spec in EVENT_TYPE_SPECS:
            avail_cmds = [
                (0, 0, {'day_of_week': dow, 'start_time': h_from, 'end_time': h_to})
                for dow, h_from, h_to in default_avail_tuples
            ]
            create_vals = {
                'name': spec['name'],
                'booking_target': 'resources',
                'assign_method': 'random',
                'schedule_based_on': 'website',
                'appointment_duration': legacy_primary.appointment_duration if (legacy_primary and legacy_primary.appointment_duration > 0) else 2.0,
                'slot_interval': legacy_primary.slot_interval if (legacy_primary and legacy_primary.slot_interval > 0) else 1.0,
                'max_schedule_days': legacy_primary.max_schedule_days if (legacy_primary and legacy_primary.max_schedule_days > 0) else 30,
                'min_schedule_hours': legacy_primary.min_schedule_hours if legacy_primary else 1.0,
                'min_cancellation_hours': legacy_primary.min_cancellation_hours if legacy_primary else 1.0,
                'location': 'custom',
                'location_details': legacy_primary.location_details if legacy_primary else False,
                'appointment_tz': tz_name,
                'is_published': False,  # published by the admin once a resource is configured
                'company_id': False,  # shared across all companies for POS table booking
                'user_ids': [(5, 0, 0)],
                'question_ids': [(6, 0, event_questions.ids)],
                'booking_template_id': tpl_confirm.id if tpl_confirm else False,
                'cancel_template_id': tpl_cancel.id if tpl_cancel else False,
                'availability_ids': avail_cmds,
            }
            if has_is_event_booking:
                create_vals['is_event_booking'] = True
            if 'event_category' in AppType._fields:
                create_vals['event_category'] = spec['event_category']
            if 'event_emoji' in AppType._fields:
                create_vals['event_emoji'] = spec['event_emoji']
            if 'enable_anniversary_wishes' in AppType._fields:
                create_vals['enable_anniversary_wishes'] = True
                create_vals['wish_send_advance_invite'] = True
                create_vals['wish_advance_days'] = 7
                create_vals['wish_send_on_day'] = True
                create_vals['wish_advance_email_template_id'] = tpl_wish_adv.id if tpl_wish_adv else False
                create_vals['wish_day_email_template_id'] = tpl_wish_day.id if tpl_wish_day else False

            at_rec, at_created = self._get_or_create_xmlid_record(
                'appointment.type',
                spec['xml_id'],
                [('booking_target', '=', 'resources'),
                 ('name', 'in', [spec['name'], *spec.get('legacy_names', ())])],
                create_vals,
            )
            if not at_created and at_rec:
                update_vals = {}
                if at_rec.name in spec.get('legacy_names', ()):
                    update_vals['name'] = spec['name']
                if 'company_id' in AppType._fields and at_rec.company_id:
                    update_vals['company_id'] = False
                if has_is_event_booking and not getattr(at_rec, 'is_event_booking', False):
                    update_vals['is_event_booking'] = True
                if 'event_category' in AppType._fields and not getattr(at_rec, 'event_category', False):
                    update_vals['event_category'] = spec['event_category']
                if 'event_emoji' in AppType._fields and not getattr(at_rec, 'event_emoji', False):
                    update_vals['event_emoji'] = spec['event_emoji']
                if 'booking_target' in AppType._fields and at_rec.booking_target != 'resources':
                    update_vals['booking_target'] = 'resources'
                if 'assign_method' in AppType._fields and at_rec.assign_method != 'random':
                    update_vals['assign_method'] = 'random'
                if 'schedule_based_on' in AppType._fields and at_rec.schedule_based_on != 'website':
                    update_vals['schedule_based_on'] = 'website'
                if 'booking_template_id' in AppType._fields and not at_rec.booking_template_id and tpl_confirm:
                    update_vals['booking_template_id'] = tpl_confirm.id
                if 'cancel_template_id' in AppType._fields and not at_rec.cancel_template_id and tpl_cancel:
                    update_vals['cancel_template_id'] = tpl_cancel.id
                if 'wish_advance_email_template_id' in AppType._fields and not getattr(at_rec, 'wish_advance_email_template_id', False) and tpl_wish_adv:
                    update_vals['wish_advance_email_template_id'] = tpl_wish_adv.id
                if 'wish_day_email_template_id' in AppType._fields and not getattr(at_rec, 'wish_day_email_template_id', False) and tpl_wish_day:
                    update_vals['wish_day_email_template_id'] = tpl_wish_day.id
                if 'question_ids' in AppType._fields:
                    q_cmds = [(4, qid) for qid in event_questions.ids if qid not in at_rec.question_ids.ids]
                    if has_q_role:
                        q_cmds += [(3, q.id) for q in at_rec.question_ids
                                   if q.question_role in retired_question_roles]
                    if q_cmds:
                        update_vals['question_ids'] = q_cmds
                if 'availability_ids' in AppType._fields and not at_rec.availability_ids:
                    update_vals['availability_ids'] = avail_cmds
                if update_vals:
                    at_rec.write(update_vals)
            if at_rec:
                created_by_cat[spec['event_category']] = at_rec

        # 3. Unpublish legacy 'Table Booking' records (never delete historical bookings) and release any stale resources they held
        to_unpublish = legacy_table_types.filtered(lambda t: t.is_published)
        if to_unpublish:
            to_unpublish.write({'is_published': False})
        legacy_with_res = legacy_table_types.filtered(lambda t: not t.is_published and t.resource_ids)
        if legacy_with_res:
            legacy_with_res.with_context(skip_table_sync=True).write({'resource_ids': [(5, 0, 0)]})

        # 3b. Remove the former Birthday / Anniversary / Win types: their tables, bookings
        # and POS configs move to the Life Events type, then the types are deleted.
        other_type = created_by_cat.get('other')
        legacy_event_types = AppType.browse()
        for xml_id in LEGACY_EVENT_TYPE_XMLIDS:
            legacy = self.env.ref(f'hudson_pos_booking.{xml_id}', raise_if_not_found=False)
            if legacy and legacy.exists() and legacy != other_type:
                legacy_event_types |= legacy
        if legacy_event_types:
            released = legacy_event_types.resource_ids
            legacy_event_types.with_context(skip_table_sync=True).write({
                'is_published': False,
                'resource_ids': [(5, 0, 0)],
            })
            if other_type and released:
                other_type.with_context(skip_table_sync=True).write({
                    'resource_ids': [(4, rid) for rid in released.ids if rid not in other_type.resource_ids.ids],
                })
            if other_type:
                self._hudson_remove_legacy_event_types(legacy_event_types, other_type)
                legacy_event_types = legacy_event_types.exists()

        # 4. Repoint POS configs that have no type, a retired celebration type, or an unpublished 'Table Booking'
        if other_type:
            PosConfig = self.env['pos.config'].sudo().with_context(active_test=False)
            for cfg in PosConfig.search([]):
                cur_type = cfg.booking_appointment_type_id
                cur_is_event = getattr(cur_type, 'is_event_booking', False) if cur_type else False
                if not cur_type or cur_type in legacy_event_types or (
                    not cur_is_event
                    and not cur_type.is_published
                    and 'table booking' in (cur_type.name or '').lower()
                ):
                    cfg.with_context(skip_table_sync=True).write({
                        'booking_appointment_type_id': other_type.id,
                    })

        # 5. Sync appointment.resource records for active POS tables (without auto-allocating to appointment types)
        tables = self.env['restaurant.table'].sudo().with_context(active_test=False).search([])
        tables._sync_appointment_resource()

        # 5b. Cleanup any duplicate auto-allocated resources shared across >1 resource-based appointment type
        # so tables remain strictly exclusive per event/appointment type.
        all_res_types = AppType.search([
            ('active', '=', True),
            ('booking_target', '=', 'resources'),
            ('resource_ids', '!=', False),
        ])
        res_to_types = {}
        for at in all_res_types:
            for r in at.resource_ids:
                res_to_types.setdefault(r.id, AppType.browse())
                res_to_types[r.id] |= at
        for rid, owners in res_to_types.items():
            if len(owners) > 1:
                for at in owners:
                    at.with_context(skip_table_sync=True).write({'resource_ids': [(3, rid)]})

        _logger.info(
            "hudson_pos_booking: ensured %s celebration appointment types and %s reusable event questions.",
            len(created_by_cat), len(event_questions),
        )
        return created_by_cat

