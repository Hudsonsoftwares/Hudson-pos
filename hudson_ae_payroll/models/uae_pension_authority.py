# -*- coding: utf-8 -*-
from odoo import fields, models


class UaePensionAuthority(models.Model):
    """
    UAE Pension & Social Security Authority Master Model.
    Represents governing pension/social security bodies (GPSSA, Abu Dhabi Pension Fund, etc.).
    Note: Contribution rates and ceilings are NOT stored here; they belong to the parameter engine.
    """
    _name = 'uae.pension.authority'
    _description = 'UAE Pension Authority'
    _order = 'name'

    name = fields.Char(string='Pension Authority Name', required=True, translate=True)
    code = fields.Char(string='Authority Code', required=True, index=True)
    emirate_id = fields.Many2one(
        'uae.emirate',
        string='Emirate',
        help='Applicable Emirate if authority is Emirate-specific (e.g. Abu Dhabi Pension Fund).'
    )
    authority_type = fields.Selection([
        ('federal', 'Federal Authority (GPSSA)'),
        ('emirate', 'Emirate Authority (e.g. ADPF / ADFCA)'),
        ('free_zone', 'Free Zone Savings Scheme (e.g. DEWS)'),
        ('gcc', 'GCC Unified Social Security Scheme'),
        ('other', 'Other Pension/Savings Authority'),
    ], string='Authority Type', default='federal', required=True)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The Pension Authority code must be unique!')
    ]
