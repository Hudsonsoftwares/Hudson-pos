# -*- coding: utf-8 -*-
from odoo import api, fields, models


class UaePensionScheme(models.Model):
    """
    UAE Pension Scheme Master Model.

    Manages statutory pension schemes (Legacy Scheme under Federal Law No. 7 of 1999 /
    Law No. 2 of 2000 vs New Law Scheme under Federal Decree-Law No. 57 of 2023 / Law No. 22 of 2023).

    Follows the established design pattern of TDS Tax Regimes (tds.tax.regime),
    enabling concurrent employee cohorts to coexist within the same company and payroll run.
    """
    _name = 'uae.pension.scheme'
    _description = 'UAE Pension Scheme'
    _order = 'sequence, name'

    name = fields.Char(
        string='Pension Scheme Name',
        required=True,
        translate=True,
        help="e.g. Legacy Scheme (Federal Law No. 7 of 1999) or New Law Scheme (Federal Decree-Law No. 57 of 2023)"
    )
    code = fields.Char(
        string='Scheme Code',
        required=True,
        index=True,
        help="Technical identifier for scheme parameter resolution ('legacy' or 'new_law')."
    )
    description = fields.Text(
        string='Description / Statutory Basis',
        help="Explanations, decree-law references, and eligibility guidelines."
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Display ordering sequence."
    )
    pension_authority_ids = fields.Many2many(
        'uae.pension.authority',
        'uae_pension_scheme_authority_rel',
        'scheme_id',
        'authority_id',
        string='Applicable Pension Authorities',
        help='Statutory pension authorities under which this scheme operates. If empty, applies to all authorities.'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help="Set to false to archive obsolete schemes."
    )
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', compute='_compute_status', store=True, index=True)

    @api.depends('active')
    def _compute_status(self):
        for scheme in self:
            scheme.status = 'active' if scheme.active else 'inactive'

    @api.depends('name', 'active')
    def _compute_display_name(self):
        for scheme in self:
            if not scheme.active:
                scheme.display_name = f"{scheme.name} (Inactive)"
            else:
                scheme.display_name = scheme.name

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The Pension Scheme code must be unique!')
    ]
