# -*- encoding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EhHrVisitorPurpose(models.Model):
    _name = 'eh.hr.visitor.purpose'
    _description = 'Visit Purpose'
    _order = 'sequence, name'

    name = fields.Char(string='Purpose', required=True, translate=True)
    code = fields.Char(string='Code', required=True, help="URL-safe identifier. Letters, digits, dashes and underscores only.")
    sequence = fields.Integer(default=10)
    nda_required = fields.Boolean(string='Require NDA', default=False)
    photo_required = fields.Boolean(string='Require photo', default=False)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )

    if hasattr(models, 'Constraint'):
        _unique_code_per_company = models.Constraint('UNIQUE(code, company_id)', 'Purpose code must be unique per company.')
    else:
        _sql_constraints = [('unique_code_per_company', 'UNIQUE(code, company_id)', 'Purpose code must be unique per company.')]

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code or not re.match(r'^[A-Za-z0-9_-]+$', record.code):
                raise ValidationError(_("Purpose code must be a non-empty string of letters, digits, dashes and underscores."))
