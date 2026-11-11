# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class TdsTaxSectionConfig(models.Model):
    """
    Tax Declaration Section Configuration Master.
    Controls section visibility, regime applicability, and effective date constraints for UI and guidelines.
    Does NOT contain statutory monetary caps (which remain in hr.rule.parameter / TdsParameterService).
    """
    _name = 'tds.tax.section.config'
    _description = 'Tax Declaration Section Configuration'
    _order = 'sequence, id'

    name = fields.Char(
        string="Section Name",
        required=True,
        help="e.g. Section 80C Investments, Section 80D Health Insurance"
    )
    code = fields.Char(
        string="Section Code",
        required=True,
        help="e.g. 80C, 80D, 80CCD1B, HRA, 24B"
    )
    old_regime_allowed = fields.Boolean(
        string="Allowed in Old Regime",
        default=True,
        help="Whether this tax section can be declared under the Old Tax Regime."
    )
    new_regime_allowed = fields.Boolean(
        string="Allowed in New Regime",
        default=False,
        help="Whether this tax section can be declared under the New Tax Regime."
    )
    effective_from = fields.Date(
        string="Effective From",
        required=True,
        default=fields.Date.today,
        help="Start date from which this section configuration is effective."
    )
    effective_to = fields.Date(
        string="Effective To",
        help="End date after which this section configuration is inactive. Leave blank for indefinite."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Master active toggle to enable/disable section in declaration forms."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display ordering in configuration lists and guidance tabs."
    )
    component_ids = fields.One2many(
        'tds.tax.component.config',
        'section_id',
        string="Sub-Components / Investment Categories"
    )
    eligibility_guidance = fields.Text(
        string="Statutory Eligibility Guidance",
        help="Informational text describing the statutory purpose and rules of this section."
    )
    typical_documents = fields.Text(
        string="Typical Supporting Documents",
        help="Informational list of typical documents associated with this section."
    )


class TdsTaxComponentConfig(models.Model):
    """
    Tax Declaration Sub-Component Configuration Master.
    Controls individual investment category availability (e.g., PPF, ELSS, EPF under 80C).
    Allows adding or deactivating sub-components per Financial Year/Regime without modifying code.
    """
    _name = 'tds.tax.component.config'
    _description = 'Tax Declaration Sub-Component Configuration'
    _order = 'sequence, id'

    section_id = fields.Many2one(
        'tds.tax.section.config',
        string="Parent Section",
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(
        string="Component Name",
        required=True,
        help="e.g. Public Provident Fund (PPF), ELSS Mutual Funds"
    )
    code = fields.Char(
        string="Component Code",
        required=True,
        help="Unique category code (e.g. 80c_ppf, 80c_elss, 80ccd1b_nps)"
    )
    python_field_name = fields.Char(
        string="Python Field Name",
        help="Corresponding field name on declaration header (e.g. decl_80c_ppf) if applicable."
    )
    old_regime_allowed = fields.Boolean(
        string="Allowed in Old Regime",
        default=True
    )
    new_regime_allowed = fields.Boolean(
        string="Allowed in New Regime",
        default=False
    )
    effective_from = fields.Date(
        string="Effective From",
        required=True,
        default=fields.Date.today
    )
    effective_to = fields.Date(
        string="Effective To"
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10
    )
    eligibility_guidance = fields.Text(
        string="Component Guidance"
    )
    typical_documents = fields.Text(
        string="Typical Supporting Documents"
    )
