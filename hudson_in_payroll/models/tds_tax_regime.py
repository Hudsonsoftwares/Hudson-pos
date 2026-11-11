# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TdsTaxRegime(models.Model):
    """
    TDS Tax Regime Master Model.
    Manages Income Tax Regimes (New Tax Regime Income-tax Act, 2025 — Section 202(1), Old Tax Regime, and future statutory regimes).
    Decouples regime logic from hardcoded Python conditions.
    """
    _name = 'tds.tax.regime'
    _description = 'TDS Tax Regime'
    _order = 'sequence, id'

    name = fields.Char(
        string="Regime Name",
        required=True,
        help="e.g. New Tax Regime Income-tax Act, 2025 — Section 202(1) or Old Tax Regime"
    )
    code = fields.Selection(
        selection=[
            ('new', 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'),
            ('old', 'Old Tax Regime'),
        ],
        string="Regime Code",
        required=True,
        help="Technical identifier code used for regime resolution ('new' or 'old')."
    )
    description = fields.Text(
        string="Description / Statutory Basis",
        help="Explanations, Section references (e.g. Section 202(1) of Income-tax Act, 2025), or caveats."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display ordering sequence."
    )
    is_default = fields.Boolean(
        string="Company Default Preference",
        default=False,
        help="Check to set as default regime selection for new employee declarations."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Set to false to archive obsolete regimes."
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The Tax Regime Code must be unique!')
    ]
