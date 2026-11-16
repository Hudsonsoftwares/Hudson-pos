# -*- encoding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    eh_consent_ids = fields.One2many(
        'eh.hr.consent',
        'employee_id',
        string='Consent records',
    )
    eh_face_consent_state = fields.Selection(
        [
            ('not_set', 'Not set'),
            ('pending', 'Pending'),
            ('granted', 'Granted'),
            ('withdrawn', 'Withdrawn'),
            ('expired', 'Expired'),
        ],
        string='Face consent',
        compute='_compute_eh_face_consent_state',
        search='_search_eh_face_consent_state',
        store=False,
    )
    eh_kiosk_pin = fields.Char(
        string='Kiosk PIN',
        copy=False,
        groups='eh_hr_attendance_base.group_eh_hr_manager',
        help="Optional fallback PIN used at the kiosk when face match is unavailable. Manager-only field.",
    )
    eh_kiosk_site_default_id = fields.Many2one(
        'eh.hr.kiosk.site',
        string='Default kiosk site',
        help="Suggested site for this employee. Other sites still accept this employee unless their record rules forbid it.",
    )
    eh_face_enrolled = fields.Boolean(
        string='Face enrolled',
        default=False,
        copy=False,
        help="Set to True by the face kiosk module once at least one face template has been stored. Reset on consent withdrawal.",
    )

    @api.depends('eh_consent_ids.consent_type', 'eh_consent_ids.state')
    def _compute_eh_face_consent_state(self):
        for employee in self:
            face_consents = employee.eh_consent_ids.filtered(lambda c: c.consent_type == 'face')
            if not face_consents:
                employee.eh_face_consent_state = 'not_set'
                continue
            sorted_consents = face_consents.sorted(key=lambda c: c.create_date or fields.Datetime.now(), reverse=True)
            latest = sorted_consents[0]
            employee.eh_face_consent_state = latest.state

    def _search_eh_face_consent_state(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return [('id', 'in', [])]
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        if 'not_set' in values:
            employees_with_face = self.env['eh.hr.consent'].search([
                ('consent_type', '=', 'face'),
            ]).mapped('employee_id.id')
            if operator in ('=', 'in'):
                return [('id', 'not in', employees_with_face)]
            else:
                return [('id', 'in', employees_with_face)]
        consents = self.env['eh.hr.consent'].search([
            ('consent_type', '=', 'face'),
            ('state', 'in', values),
        ])
        employee_ids = consents.mapped('employee_id.id')
        if operator in ('=', 'in'):
            return [('id', 'in', employee_ids)]
        else:
            return [('id', 'not in', employee_ids)]
