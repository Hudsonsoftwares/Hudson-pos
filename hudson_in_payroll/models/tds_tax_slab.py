# -*- coding: utf-8 -*-
import re
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class TdsTaxSlab(models.Model):
    """
    TDS Income Tax Slab Master Model.
    Stores structured, range-based Income Tax Slabs per Financial Year and Tax Regime.
    Supports effective-dating and non-overlapping income range validation.
    """
    _name = 'tds.tax.slab'
    _description = 'TDS Income Tax Slab'
    _order = 'financial_year_id desc, regime_code, age_category, sequence, income_from'

    name = fields.Char(
        string="Slab Title",
        compute='_compute_name',
        store=True,
        help="Automated slab display title."
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        ondelete='cascade',
        help="Tax year for which this income slab is applicable."
    )
    regime_id = fields.Many2one(
        'tds.tax.regime',
        string="Tax Regime Master",
        help="Optional reference to tds.tax.regime model."
    )
    regime_code = fields.Selection(
        selection=[
            ('new', 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'),
            ('old', 'Old Regime'),
        ],
        string="Tax Regime",
        required=True,
        default='new',
        help="Tax Regime ('new' for Income-tax Act, 2025 — Section 202(1), 'old' for Old Regime)."
    )
    age_category = fields.Selection(
        selection=[
            ('general', 'General (Below 60)'),
            ('senior', 'Senior Citizen (60–79)'),
            ('super_senior', 'Super Senior Citizen (80+)'),
        ],
        string="Age Category",
        required=True,
        default='general',
        help="Taxpayer age category for slab selection. Under the Old Regime, different basic "
             "exemption limits apply per age category (General: ₹2,50,000; Senior: ₹3,00,000; "
             "Super Senior: ₹5,00,000). Under the New Regime, all categories use the same slabs."
    )
    income_from = fields.Float(
        string="Income From (₹)",
        required=True,
        default=0.0,
        help="Lower threshold limit of taxable annual income in Rupees (inclusive)."
    )
    income_to = fields.Float(
        string="Income To (₹)",
        default=0.0,
        help="Upper limit of taxable annual income in Rupees. Set to 0.0 or leave blank for open-ended top slab."
    )
    display_income_to = fields.Char(
        string="Income To (₹)",
        compute='_compute_display_income_to',
        inverse='_inverse_display_income_to',
        help="Upper limit of taxable annual income in Rupees, or 'Above' for open-ended top slab."
    )
    rate = fields.Float(
        string="Tax Rate (%)",
        required=True,
        default=0.0,
        help="Income tax rate percentage applied to income falling within this slab range."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of slab evaluation."
    )
    date_from = fields.Date(
        string="Effective From",
        help="Optional start date of validity for this slab."
    )
    date_to = fields.Date(
        string="Effective To",
        help="Optional end date of validity for this slab."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Set to false to archive obsolete slabs."
    )

    @api.depends('financial_year_id.name', 'regime_code', 'age_category', 'income_from', 'income_to', 'rate')
    def _compute_name(self):
        AGE_CAT_LABELS = {
            'general': 'General',
            'senior': 'Senior Citizen',
            'super_senior': 'Super Senior Citizen',
        }
        for rec in self:
            fy_str = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            reg_str = 'New Regime' if rec.regime_code == 'new' else 'Old Regime'
            to_str = f"₹{rec.income_to:,.0f}" if rec.income_to > 0 else "Above"
            # Include age category label for Old Regime slabs (Senior/Super Senior)
            age_suffix = ''
            if rec.regime_code == 'old' and rec.age_category and rec.age_category != 'general':
                age_suffix = f" [{AGE_CAT_LABELS.get(rec.age_category, rec.age_category)}]"
            rec.name = f"{fy_str} ({reg_str}{age_suffix}): ₹{rec.income_from:,.0f} - {to_str} @ {rec.rate}%"

    @api.depends('income_to')
    def _compute_display_income_to(self):
        for rec in self:
            if rec.income_to and rec.income_to > 0:
                rec.display_income_to = f"{rec.income_to:,.2f}"
            else:
                rec.display_income_to = "Above"

    def _inverse_display_income_to(self):
        for rec in self:
            val = (rec.display_income_to or '').strip().lower()
            if not val or any(k in val for k in ('above', 'limit', 'inf', 'none', 'na', 'n/a', '-', 'nil')):
                rec.income_to = 0.0
            else:
                cleaned = re.sub(r'[^\d.]', '', val)
                try:
                    num = float(cleaned) if cleaned else 0.0
                    rec.income_to = num if num > 0 else 0.0
                except ValueError:
                    rec.income_to = 0.0

    @api.constrains('income_from', 'income_to')
    def _check_income_bounds(self):
        for rec in self:
            if rec.income_to > 0 and rec.income_from >= rec.income_to:
                raise ValidationError(_(
                    "Income From (₹%s) must be strictly less than Income To (₹%s) for slab '%s'."
                ) % (rec.income_from, rec.income_to, rec.name))

    @api.constrains('financial_year_id', 'regime_code', 'age_category', 'income_from', 'income_to', 'active')
    def _check_overlapping_slabs(self):
        """
        Validates that income tax slabs for the same Financial Year, Tax Regime,
        and Age Category do not have overlapping income ranges.
        """
        for rec in self:
            if not rec.active or not rec.financial_year_id:
                continue

            domain = [
                ('id', '!=', rec.id),
                ('active', '=', True),
                ('financial_year_id', '=', rec.financial_year_id.id),
                ('regime_code', '=', rec.regime_code),
                ('age_category', '=', rec.age_category),
            ]
            other_slabs = self.search(domain)
            for other in other_slabs:
                rec_max = rec.income_to if rec.income_to > 0 else float('inf')
                other_max = other.income_to if other.income_to > 0 else float('inf')

                # Check range overlap: max(A_start, B_start) < min(A_end, B_end)
                overlap_start = max(rec.income_from, other.income_from)
                overlap_end = min(rec_max, other_max)

                if overlap_start < overlap_end:
                    raise ValidationError(_(
                        "Overlapping Income Tax Slab detected for %s (%s, %s)! "
                        "Slab ₹%s - ₹%s overlaps with existing slab ₹%s - ₹%s."
                    ) % (
                        rec.financial_year_id.name,
                        'New Regime' if rec.regime_code == 'new' else 'Old Regime',
                        dict(rec._fields['age_category'].selection).get(rec.age_category, rec.age_category),
                        f"{rec.income_from:,.0f}", f"{rec.income_to:,.0f}" if rec.income_to > 0 else "Above",
                        f"{other.income_from:,.0f}", f"{other.income_to:,.0f}" if other.income_to > 0 else "Above",
                    ))
