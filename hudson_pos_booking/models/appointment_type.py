# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

EVENT_TYPE_SPECS = [
    {
        'xml_id': 'appointment_type_event_birthday',
        'name': 'Celebrate Your Birthday',
        'event_category': 'birthday',
        'event_emoji': '🎂',
    },
    {
        'xml_id': 'appointment_type_event_anniversary',
        'name': 'Wedding Anniversary',
        'event_category': 'anniversary',
        'event_emoji': '💍',
    },
    {
        'xml_id': 'appointment_type_event_win',
        'name': 'Your Win Celebration',
        'event_category': 'win',
        'event_emoji': '🏆',
    },
    {
        'xml_id': 'appointment_type_event_other',
        'name': 'Other Celebrations',
        'event_category': 'other',
        'event_emoji': '🎉',
    },
]


class AppointmentTypePos(models.Model):
    _name = 'appointment.type'
    _inherit = ['appointment.type', 'pos.load.mixin']

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
        return [
            'name',
            'event_category',
            'event_emoji',
            'is_event_booking',
            'is_published',
            'appointment_duration',
            'resource_ids',
        ]

    @api.model
    def _get_or_create_xmlid_record(self, model_name, xml_id_name, search_domain, create_vals):
        IrModelData = self.env['ir.model.data'].sudo()
        full_xml_id = f'hudson_pos_booking.{xml_id_name}'
        existing = self.env.ref(full_xml_id, raise_if_not_found=False)
        created = False
        if existing and existing.exists():
            return existing, created

        Model = self.env[model_name].sudo().with_context(active_test=False)
        rec = Model.search(search_domain, order='id asc', limit=1)
        if not rec:
            rec = self.env[model_name].sudo().create(create_vals)
            created = True

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
    def _ensure_default_event_booking_setup(self):
        """
        Idempotently provision:
        1) 3 reusable event questions (Celebrant Name, Occasion Details, Special Day)
        2) 4 published resource-based celebration appointment.type records (with manual resource_ids configuration)
        3) Unpublish legacy 'Table Booking' (without deleting historical records) and repoint pos.config to 'Other Celebrations'
        """
        # 1. Ensure 3 reusable Event Questions exist
        question_specs = [
            {
                'xml_id': 'question_event_celebrant_name',
                'search_domain': [('question_role', '=', 'celebrant_name'), ('is_reusable', '=', True)],
                'vals': {
                    'name': 'Celebrant / Honoree Name',
                    'question_type': 'char',
                    'question_role': 'celebrant_name',
                    'is_required': True,
                    'is_reusable': True,
                    'sequence': 10,
                    'placeholder': 'e.g. Rahul, Mom & Dad, Team Hudson',
                    'company_id': False,
                },
            },
            {
                'xml_id': 'question_event_occasion_title',
                'search_domain': [('question_role', '=', 'occasion_title'), ('is_reusable', '=', True)],
                'vals': {
                    'name': 'Occasion / Celebration Details',
                    'question_type': 'text',
                    'question_role': 'occasion_title',
                    'is_required': False,
                    'is_reusable': True,
                    'sequence': 20,
                    'placeholder': 'e.g. 25th Birthday, 10th Wedding Anniversary, Promotion...',
                    'company_id': False,
                },
            },
            {
                'xml_id': 'question_event_occasion_date',
                'search_domain': [('question_role', '=', 'occasion_date'), ('is_reusable', '=', True)],
                'vals': {
                    'name': 'Special Day / Birthdate',
                    'question_type': 'date',
                    'question_role': 'occasion_date',
                    'is_occasion_date': True,
                    'is_required': True,
                    'is_reusable': True,
                    'sequence': 30,
                    'company_id': False,
                },
            },
        ]

        Question = self.env['appointment.question'].sudo()
        event_questions = Question.browse()
        for q_spec in question_specs:
            q_rec, q_created = self._get_or_create_xmlid_record(
                'appointment.question',
                q_spec['xml_id'],
                q_spec['search_domain'],
                q_spec['vals'],
            )
            if not q_created:
                q_fix = {}
                target_role = q_spec['vals']['question_role']
                if q_rec.question_role != target_role:
                    q_fix['question_role'] = target_role
                if target_role == 'occasion_date':
                    if q_rec.question_type != 'date':
                        q_fix['question_type'] = 'date'
                    if not q_rec.is_occasion_date:
                        q_fix['is_occasion_date'] = True
                if not q_rec.is_reusable:
                    q_fix['is_reusable'] = True
                if q_fix:
                    q_rec.write(q_fix)
            event_questions |= q_rec

        # 2. Gather default templates & legacy schedule hints without clobbering existing types
        AppType = self.env['appointment.type'].sudo().with_context(active_test=False)
        legacy_table_types = AppType.search([
            ('is_event_booking', '=', False),
            ('name', 'ilike', 'Table Booking'),
        ], order='id asc')
        legacy_primary = legacy_table_types[:1]

        tpl_confirm = self.env.ref('appointment.email_template_booking_confirmation', raise_if_not_found=False)
        tpl_cancel = self.env.ref('appointment.email_template_booking_cancellation', raise_if_not_found=False)
        tpl_wish_adv = self.env.ref('appointment.email_template_celebration_advance', raise_if_not_found=False)
        tpl_wish_day = self.env.ref('appointment.email_template_celebration_day', raise_if_not_found=False)

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
                'is_event_booking': True,
                'event_category': spec['event_category'],
                'event_emoji': spec['event_emoji'],
                'booking_target': 'resources',
                'assign_method': 'customer',
                'schedule_based_on': 'website',
                'appointment_duration': legacy_primary.appointment_duration if (legacy_primary and legacy_primary.appointment_duration > 0) else 2.0,
                'slot_interval': legacy_primary.slot_interval if (legacy_primary and legacy_primary.slot_interval > 0) else 1.0,
                'max_schedule_days': legacy_primary.max_schedule_days if (legacy_primary and legacy_primary.max_schedule_days > 0) else 30,
                'min_schedule_hours': legacy_primary.min_schedule_hours if legacy_primary else 1.0,
                'min_cancellation_hours': legacy_primary.min_cancellation_hours if legacy_primary else 1.0,
                'location': 'custom',
                'location_details': legacy_primary.location_details if legacy_primary else False,
                'appointment_tz': tz_name,
                'is_published': True,
                'company_id': default_company.id if default_company else False,
                'user_ids': [(5, 0, 0)],
                'question_ids': [(6, 0, event_questions.ids)],
                'enable_anniversary_wishes': True,
                'wish_send_advance_invite': True,
                'wish_advance_days': 7,
                'wish_send_on_day': True,
                'booking_template_id': tpl_confirm.id if tpl_confirm else False,
                'cancel_template_id': tpl_cancel.id if tpl_cancel else False,
                'wish_advance_email_template_id': tpl_wish_adv.id if tpl_wish_adv else False,
                'wish_day_email_template_id': tpl_wish_day.id if tpl_wish_day else False,
                'availability_ids': avail_cmds,
            }
            at_rec, at_created = self._get_or_create_xmlid_record(
                'appointment.type',
                spec['xml_id'],
                [('booking_target', '=', 'resources'), ('name', '=', spec['name'])],
                create_vals,
            )
            if not at_created:
                update_vals = {}
                if not at_rec.company_id and default_company:
                    update_vals['company_id'] = default_company.id
                if not at_rec.is_event_booking:
                    update_vals['is_event_booking'] = True
                if not at_rec.event_category:
                    update_vals['event_category'] = spec['event_category']
                if not at_rec.event_emoji:
                    update_vals['event_emoji'] = spec['event_emoji']
                if at_rec.booking_target != 'resources':
                    update_vals['booking_target'] = 'resources'
                if at_rec.assign_method != 'customer':
                    update_vals['assign_method'] = 'customer'
                if at_rec.schedule_based_on != 'website':
                    update_vals['schedule_based_on'] = 'website'
                if not at_rec.booking_template_id and tpl_confirm:
                    update_vals['booking_template_id'] = tpl_confirm.id
                if not at_rec.cancel_template_id and tpl_cancel:
                    update_vals['cancel_template_id'] = tpl_cancel.id
                if not at_rec.wish_advance_email_template_id and tpl_wish_adv:
                    update_vals['wish_advance_email_template_id'] = tpl_wish_adv.id
                if not at_rec.wish_day_email_template_id and tpl_wish_day:
                    update_vals['wish_day_email_template_id'] = tpl_wish_day.id
                missing_q_ids = [qid for qid in event_questions.ids if qid not in at_rec.question_ids.ids]
                if missing_q_ids:
                    update_vals['question_ids'] = [(4, qid) for qid in missing_q_ids]
                if not at_rec.availability_ids:
                    update_vals['availability_ids'] = avail_cmds
                if update_vals:
                    at_rec.write(update_vals)
            created_by_cat[spec['event_category']] = at_rec

        # 3. Unpublish legacy 'Table Booking' records (never delete historical bookings) and release any stale resources they held
        to_unpublish = legacy_table_types.filtered(lambda t: t.is_published)
        if to_unpublish:
            to_unpublish.write({'is_published': False})
        legacy_with_res = legacy_table_types.filtered(lambda t: not t.is_published and t.resource_ids)
        if legacy_with_res:
            legacy_with_res.with_context(skip_table_sync=True).write({'resource_ids': [(5, 0, 0)]})

        # 4. Repoint POS configs that have no type or point to unpublished 'Table Booking'
        other_type = created_by_cat.get('other')
        if other_type:
            PosConfig = self.env['pos.config'].sudo().with_context(active_test=False)
            for cfg in PosConfig.search([]):
                cur_type = cfg.booking_appointment_type_id
                if not cur_type or (
                    not cur_type.is_event_booking
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

