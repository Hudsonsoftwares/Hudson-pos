# -*- coding: utf-8 -*-
from odoo import fields, models


class UaeEmirate(models.Model):
    """
    UAE Emirate Master Model.
    Represents the 7 Emirates of the United Arab Emirates.
    Reusable for jurisdiction resolution, pension authority, and reporting.
    """
    _name = 'uae.emirate'
    _description = 'UAE Emirate'
    _order = 'name'

    name = fields.Char(string='Emirate Name', required=True, translate=True)
    code = fields.Char(string='Emirate Code', required=True, index=True)
    pension_authority_id = fields.Many2one(
        'uae.pension.authority',
        string='Pension Authority',
        help='Governing statutory pension authority for this Emirate (e.g. ADPF for Abu Dhabi, GPSSA for other Emirates).'
    )
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The Emirate code must be unique!')
    ]
