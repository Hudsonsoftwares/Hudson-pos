# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Celebration question roles & Date questions.

These extensions used to live inside the customised ``appointment`` module.
They are owned by the POS Table Booking Bridge so the stock ``appointment``
module can be installed/upgraded untouched.
"""

from odoo import api, fields, models


class AppointmentQuestion(models.Model):
    _inherit = 'appointment.question'

    question_type = fields.Selection(
        selection_add=[('date', 'Date')],
        ondelete={'date': 'set default'},
    )
    question_role = fields.Selection([
        ('none', 'Standard Question'),
        ('celebrant_name', 'Celebrant / Honoree Name'),
        ('occasion_title', 'Occasion / Celebration Details'),
        ('occasion_date', 'Special Day / Anniversary Date'),
        ('celebration_type', 'Celebration Event Type'),
        ('special_requests', 'Special Requests'),
    ], string='Celebration Field Mapping', default='none', required=True,
       help="Maps answers on the website booking form to structured Celebration fields used for yearly wishes.")
    is_occasion_date = fields.Boolean(
        'Is Special Day / Occasion Date', default=False,
        help="Mark this Date question as the Special Day used to schedule next-year celebration wishes.")

    @api.onchange('question_role')
    def _onchange_question_role(self):
        for question in self:
            question.is_occasion_date = (question.question_role == 'occasion_date')

    @api.onchange('is_occasion_date')
    def _onchange_is_occasion_date(self):
        for question in self:
            if question.is_occasion_date:
                question.question_role = 'occasion_date'
            elif question.question_role == 'occasion_date':
                question.question_role = 'none'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'question_role' in vals and 'is_occasion_date' not in vals:
                vals['is_occasion_date'] = (vals['question_role'] == 'occasion_date')
            elif vals.get('is_occasion_date') and 'question_role' not in vals:
                vals['question_role'] = 'occasion_date'
        return super().create(vals_list)

    def write(self, vals):
        if 'question_role' in vals and 'is_occasion_date' not in vals:
            vals = dict(vals, is_occasion_date=(vals['question_role'] == 'occasion_date'))
        elif 'is_occasion_date' in vals and 'question_role' not in vals:
            if vals['is_occasion_date']:
                vals = dict(vals, question_role='occasion_date')
            else:
                res = True
                for question in self:
                    per_vals = dict(vals)
                    if question.question_role == 'occasion_date':
                        per_vals['question_role'] = 'none'
                    res = super(AppointmentQuestion, question).write(per_vals) and res
                return res
        return super().write(vals)


class AppointmentAnswer(models.Model):
    _inherit = 'appointment.answer'

    value_date = fields.Date('Date Answer')

    @api.model
    def _parse_date_value(self, raw_val):
        if not raw_val:
            return False
        if isinstance(raw_val, str):
            raw_val = raw_val.strip()
            if not raw_val:
                return False
        try:
            return fields.Date.to_date(raw_val)
        except Exception:
            return False

    def _prepare_date_answer_vals(self, vals, question=None):
        vals = dict(vals)
        q = question or (vals.get('question_id') and self.env['appointment.question'].browse(vals['question_id']))
        is_date_q = q and q.question_type == 'date'
        if 'value_date' in vals:
            parsed = self._parse_date_value(vals.get('value_date'))
            vals['value_date'] = parsed
            if parsed and 'value_text' not in vals:
                vals['value_text'] = fields.Date.to_string(parsed)
        elif is_date_q and 'value_text' in vals:
            parsed = self._parse_date_value(vals.get('value_text'))
            vals['value_date'] = parsed
            if parsed:
                vals['value_text'] = fields.Date.to_string(parsed)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = [self._prepare_date_answer_vals(vals) for vals in vals_list]
        answers = super().create(prepared)
        if not self.env.context.get('skip_event_sync'):
            answers.mapped('booking_id')._sync_event_fields_from_answers()
        return answers

    def write(self, vals):
        if not ({'value_date', 'value_text', 'value_answer_ids'} & set(vals)):
            return super().write(vals)
        if 'value_date' in vals or 'value_text' in vals:
            res = True
            for answer in self:
                prepared_vals = self._prepare_date_answer_vals(vals, question=answer.question_id)
                res = super(AppointmentAnswer, answer).write(prepared_vals) and res
        else:
            res = super().write(vals)
        if not self.env.context.get('skip_event_sync'):
            self.mapped('booking_id')._sync_event_fields_from_answers()
        return res
