# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TdsSurcharge(models.Model):
    """
    TDS Surcharge Master Model.
    Stores structured, range-based Income Tax Surcharge percentage bands per Financial Year and Tax Regime.
    Supports effective-dating and non-overlapping income range validation.
    """
    _name = 'tds.surcharge'
    _description = 'TDS Surcharge Slab'
    _order = 'financial_year_id desc, regime_code, sequence, income_from'

    name = fields.Char(
        string="Surcharge Title",
        compute='_compute_name',
        store=True,
        help="Automated surcharge slab display title."
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        ondelete='cascade',
        help="Tax year for which this surcharge slab applies."
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
    income_from = fields.Float(
        string="Income From (₹)",
        required=True,
        default=0.0,
        help="Lower threshold limit of total net income in Rupees for surcharge applicability (exclusive/inclusive)."
    )
    income_to = fields.Float(
        string="Income To (₹)",
        default=0.0,
        help="Upper threshold limit of total net income in Rupees. Set to 0.0 or leave blank for open-ended top surcharge slab."
    )
    display_income_to = fields.Char(
        string="Income To (₹)",
        compute='_compute_display_income_to',
        inverse='_inverse_display_income_to',
        help="Upper threshold limit of total net income in Rupees, or 'Above' for open-ended top surcharge slab."
    )
    surcharge_rate = fields.Float(
        string="Surcharge Rate (%)",
        required=True,
        default=0.0,
        help="Surcharge percentage rate applied to total income tax."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of surcharge evaluation."
    )
    date_from = fields.Date(
        string="Effective From",
        help="Optional start date of validity for this surcharge slab."
    )
    date_to = fields.Date(
        string="Effective To",
        help="Optional end date of validity for this surcharge slab."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Set to false to archive obsolete surcharge slabs."
    )

    @api.depends('financial_year_id.name', 'regime_code', 'income_from', 'income_to', 'surcharge_rate')
    def _compute_name(self):
        for rec in self:
            fy_str = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            reg_str = 'New Regime' if rec.regime_code == 'new' else 'Old Regime'
            to_str = f"₹{rec.income_to:,.0f}" if rec.income_to > 0 else "Above"
            rec.name = f"{fy_str} ({reg_str}) Surcharge: ₹{rec.income_from:,.0f} - {to_str} @ {rec.surcharge_rate}%"

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
                    "Income From (₹%s) must be strictly less than Income To (₹%s) for surcharge slab '%s'."
                ) % (rec.income_from, rec.income_to, rec.name))

    @api.constrains('financial_year_id', 'regime_code', 'income_from', 'income_to', 'active')
    def _check_overlapping_surcharges(self):
        """
        Validates that surcharge slabs for the same Financial Year and Tax Regime do not have overlapping ranges.
        """
        for rec in self:
            if not rec.active or not rec.financial_year_id:
                continue

            domain = [
                ('id', '!=', rec.id),
                ('active', '=', True),
                ('financial_year_id', '=', rec.financial_year_id.id),
                ('regime_code', '=', rec.regime_code),
            ]
            other_surcharges = self.search(domain)
            for other in other_surcharges:
                rec_max = rec.income_to if rec.income_to > 0 else float('inf')
                other_max = other.income_to if other.income_to > 0 else float('inf')

                overlap_start = max(rec.income_from, other.income_from)
                overlap_end = min(rec_max, other_max)

                if overlap_start < overlap_end:
                    raise ValidationError(_(
                        "Overlapping Surcharge Slab detected for %s (%s)! "
                        "Range ₹%s - ₹%s overlaps with existing surcharge slab ₹%s - ₹%s."
                    ) % (
                        rec.financial_year_id.name,
                        'New Regime' if rec.regime_code == 'new' else 'Old Regime',
                        f"{rec.income_from:,.0f}", f"{rec.income_to:,.0f}" if rec.income_to > 0 else "Above",
                        f"{other.income_from:,.0f}", f"{other.income_to:,.0f}" if other.income_to > 0 else "Above",
                    ))
