# -*- coding: utf-8 -*-
"""eh.hr.settings.entry - typed, per-company key/value registry.

Used by every engine and feature module instead of ir.config_parameter.
Reasons:

    * Typed values (str, int, float, bool, json).
    * Per-company scoping by default.
    * Versioned: a write archives the previous value, never destroys it.
    * Schema-validated via the policy engine where applicable.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrSettingsEntry(models.Model):
    _name = 'eh.hr.settings.entry'
    _description = 'EH HR Platform - settings entry'
    _order = 'company_id, key, id DESC'

    company_id = fields.Many2one('res.company', required=True, index=True,
                                  default=lambda self: self.env.company)
    key = fields.Char(required=True, index=True,
                      help='Dotted key, e.g. attendance.kiosk.idle_timeout_s')
    value_type = fields.Selection([
        ('str', 'String'), ('int', 'Integer'), ('float', 'Float'),
        ('bool', 'Boolean'), ('json', 'JSON'),
    ], required=True, default='str')
    value = fields.Char(help='Raw stored value; use :py:meth:`typed` to read.')
    active = fields.Boolean(default=True)
    superseded_by = fields.Many2one('eh.hr.settings.entry', readonly=True,
                                    help='Versioning pointer.')

    # Odoo 19 builds constraints from models.Constraint, not the
    # _sql_constraints list. Keep both so constraints hold on 16 to 19.
    if hasattr(models, 'Constraint'):
        _uniq_active_per_company_key = models.Constraint(
            'unique(company_id, key, active)',
            'Only one active settings entry per (company, key) is allowed.')
    else:
        _sql_constraints = [
            ('uniq_active_per_company_key', 'unique(company_id, key, active)', 'Only one active settings entry per (company, key) is allowed.'),
        ]

    def typed(self):
        """Return the value cast to its declared type."""
        self.ensure_one()
        import json
        v = self.value
        if v is None:
            return None
        try:
            if self.value_type == 'int':
                return int(v)
            if self.value_type == 'float':
                return float(v)
            if self.value_type == 'bool':
                return str(v).lower() in {'1', 'true', 'yes', 'on'}
            if self.value_type == 'json':
                return json.loads(v)
            return v
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                f'Settings entry {self.key} cannot be cast to {self.value_type}: {exc}'
            )

    @api.model
    def get(self, key, default=None, company=None):
        """Read the active value for a key in the current company."""
        company = company or self.env.company
        entry = self.search([
            ('company_id', '=', company.id),
            ('key', '=', key),
            ('active', '=', True),
        ], limit=1)
        return entry.typed() if entry else default

    @api.model
    def set(self, key, value, value_type='str', company=None):
        """Version-safe upsert: archives the old entry, writes a new one."""
        company = company or self.env.company
        prev = self.search([
            ('company_id', '=', company.id),
            ('key', '=', key),
            ('active', '=', True),
        ], limit=1)
        new = self.create({
            'company_id': company.id,
            'key': key,
            'value': str(value),
            'value_type': value_type,
        })
        if prev:
            prev.write({'active': False, 'superseded_by': new.id})
        return new
