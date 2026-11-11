# -*- coding: utf-8 -*-
from odoo import fields, models


class UaePayrollJurisdiction(models.Model):
    """
    UAE Payroll Jurisdiction Master Model.
    Represents regulatory operating zones (Mainland, Free Zones) across Emirates.
    """
    _name = 'uae.payroll.jurisdiction'
    _description = 'UAE Payroll Jurisdiction'
    _order = 'name'

    name = fields.Char(string='Jurisdiction Name', required=True, translate=True)
    code = fields.Char(string='Jurisdiction Code', required=True, index=True)
    jurisdiction_type = fields.Selection([
        ('mainland', 'Mainland'),
        ('free_zone', 'Free Zone'),
    ], string='Jurisdiction Type', default='mainland', required=True)
    emirate_id = fields.Many2one('uae.emirate', string='Emirate')
    labour_authority_id = fields.Many2one('uae.labour.authority', string='Governing Labour Authority')
    pension_authority_id = fields.Many2one(
        'uae.pension.authority',
        string='Pension Authority',
        help='Governing statutory pension authority for this jurisdiction (e.g. ADPF for Abu Dhabi, GPSSA for Dubai/Northern Emirates). If not set, defaults from Emirate.'
    )
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The Jurisdiction code must be unique!')
    ]
