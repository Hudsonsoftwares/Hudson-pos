# -*- coding: utf-8 -*-
from odoo import fields, models


class UaeLabourAuthority(models.Model):
    """
    UAE Labour Authority Master Model.
    Represents regulatory bodies such as MOHRE, Free Zone Authorities, etc.
    """
    _name = 'uae.labour.authority'
    _description = 'UAE Labour Authority'
    _order = 'name'

    name = fields.Char(string='Authority Name', required=True, translate=True)
    code = fields.Char(string='Authority Code', required=True, index=True)
    authority_type = fields.Selection([
        ('mohre', 'Ministry of Human Resources & Emiratisation (MOHRE)'),
        ('free_zone', 'Free Zone Authority'),
        ('other', 'Other Applicable Authority'),
    ], string='Authority Type', default='mohre', required=True)
    jurisdiction_type = fields.Selection([
        ('mainland', 'Mainland'),
        ('free_zone', 'Free Zone'),
    ], string='Jurisdiction Type', default='mainland', required=True)
    emirate_id = fields.Many2one(
        'uae.emirate',
        string='Emirate',
        help='Applicable Emirate if authority is Emirate-specific.'
    )
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The Labour Authority code must be unique!')
    ]
