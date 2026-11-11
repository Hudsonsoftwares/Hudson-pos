# -*- coding: utf-8 -*-
import logging
from dateutil.relativedelta import relativedelta
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class IncomeTaxSlabResult:
    """
    Data Transfer Object (DTO) holding income tax slab computation details.
    """
    def __init__(self, net_taxable_income, base_tax_liability, slab_breakdown, age_category='general'):
        self.net_taxable_income = net_taxable_income
        self.base_tax_liability = base_tax_liability
        self.slab_breakdown = slab_breakdown
        self.age_category = age_category


AGE_CATEGORY_LABELS = {
    'general': 'General (Below 60)',
    'senior': 'Senior Citizen (60–79)',
    'super_senior': 'Super Senior Citizen (80+)',
}


class IncomeTaxSlabService(BaseStatutoryService):
    """
    Phase 4 Pipeline Service: Income Tax Slab Engine Service.
    Resolves progressive income tax slabs from tds.tax.slab for the resolved Financial Year,
    Tax Regime, and Age Category, computing the base annual tax liability before rebates.

    Age-based slab differentiation applies only under the Old Tax Regime:
    - General (Below 60): Basic exemption ₹2,50,000
    - Senior Citizen (60–79): Basic exemption ₹3,00,000
    - Super Senior Citizen (80+): Basic exemption ₹5,00,000
    Under the New Tax Regime, all age categories use the same uniform slabs.
    """

    @staticmethod
    def resolve_age_category(employee, financial_year, eval_date=None):
        """
        Determines employee's tax age category based on age at the end of the Financial Year.

        Per CBDT Circular No. 19/2015 & Circular No. 28/2018: the age of the assessee
        is determined as of the last day of the relevant previous year (i.e., March 31
        of the Financial Year).

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param eval_date: Date (optional fallback if financial_year has no end_date)
        :return: str - 'general', 'senior', or 'super_senior'
        """
        if not employee or not employee.birthday:
            return 'general'

        # Determine FY end date (March 31)
        try:
            # pyrefly: ignore [missing-import]
            from odoo import fields as odoo_fields
        except ImportError:
            odoo_fields = None

        if financial_year and financial_year.end_date:
            fy_end = financial_year.end_date
        elif eval_date:
            fy_year = eval_date.year if eval_date.month >= 4 else eval_date.year - 1
            if odoo_fields:
                fy_end = odoo_fields.Date.from_string(f"{fy_year + 1}-03-31")
            else:
                from datetime import date
                fy_end = date(fy_year + 1, 3, 31)
        else:
            from datetime import date
            today = date.today()
            fy_year = today.year if today.month >= 4 else today.year - 1
            if odoo_fields:
                fy_end = odoo_fields.Date.from_string(f"{fy_year + 1}-03-31")
            else:
                fy_end = date(fy_year + 1, 3, 31)

        # Calendar-aware exact age determination at Financial Year end
        age_at_fy_end = relativedelta(fy_end, employee.birthday).years

        if age_at_fy_end >= 80:
            return 'super_senior'
        elif age_at_fy_end >= 60:
            return 'senior'
        else:
            return 'general'

    def calculate_base_tax(self, net_taxable_income, financial_year, regime_code, age_category='general'):
        """
        Calculates progressive annual income tax before rebates.

        :param net_taxable_income: float (Net Taxable Income)
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param age_category: str ('general', 'senior', or 'super_senior')
        :return: IncomeTaxSlabResult
        """
        regime_code = (regime_code or 'new').lower()
        age_category = (age_category or 'general').lower()

        # New Regime: age category is irrelevant — always use 'general' uniform slabs
        if regime_code == 'new':
            age_category = 'general'

        # Query effective-dated income tax slabs from master
        slabs = self.env['tds.tax.slab'].search([
            ('financial_year_id', '=', financial_year.id),
            ('regime_code', '=', regime_code),
            ('age_category', '=', age_category)
        ], order='income_from asc')

        # Fallback default slabs if unconfigured in seed data
        if not slabs:
            slabs = self._get_fallback_slabs(financial_year, regime_code, age_category)

        base_tax = 0.0
        slab_breakdown = []

        for slab in slabs:
            inc_from = slab.income_from
            inc_to = slab.income_to if slab.income_to > 0 else float('inf')
            rate = slab.rate / 100.0

            if net_taxable_income > inc_from:
                taxable_in_slab = min(net_taxable_income, inc_to) - inc_from
                if taxable_in_slab > 0:
                    tax_in_slab = taxable_in_slab * rate
                    base_tax += tax_in_slab
                    slab_breakdown.append({
                        'slab_name': slab.name or f"₹{inc_from:,.0f} - ₹{inc_to:,.0f}",
                        'income_from': inc_from,
                        'income_to': inc_to,
                        'taxable_amount': taxable_in_slab,
                        'rate_pct': slab.rate,
                        'tax_amount': tax_in_slab,
                    })

        age_cat_label = AGE_CATEGORY_LABELS.get(age_category, age_category)

        _logger.warning("""[80E_AUDIT] TAX_SLAB_CALCULATION
taxable_income=%s, age_category=%s""", net_taxable_income, age_cat_label)
        for item in slab_breakdown:
            _logger.warning("[80E_AUDIT] SLAB: lower=%s upper=%s taxable=%s rate=%s tax=%s",
                item.get('income_from', 0.0), item.get('income_to', 0.0), item['taxable_amount'], item['rate_pct'], item['tax_amount'])
        _logger.warning("[80E_AUDIT] tax_before_rebate=%s", base_tax)

        breakdown_lines = []
        for item in slab_breakdown:
            breakdown_lines.append(f"- {item['slab_name']} @ {item['rate_pct']}%: ₹{item['tax_amount']:,.2f}")
        breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "- No taxable slabs applicable"

        summary_log = f"""
========================================================
INCOME TAX SLAB SERVICE
========================================================
Tax Regime              : {regime_code.upper()}
Age Category            : {age_cat_label}
Net Taxable Income      : ₹{net_taxable_income:,.2f}

Slab Breakdown:
{breakdown_text}

Base Tax Liability      : ₹{base_tax:,.2f}
========================================================
"""
        _logger.warning("""[FORENSIC_TDS_TRACE]
step=ANNUAL_TAX_SLABS
input=net_taxable_income:INR %s, regime:%s, age_category:%s, fy:%s
output=base_annual_tax_liability:INR %s, slab_count:%s
source_method=IncomeTaxSlabService.calculate_base_tax
branch_used=%s""",
            f"{net_taxable_income:,.2f}",
            regime_code.upper(),
            age_cat_label,
            financial_year.code if financial_year else 'N/A',
            f"{base_tax:,.2f}",
            len(slab_breakdown),
            f"{'OLD_REGIME_SLAB_PROGRESSIVE_CALCULATION' if regime_code == 'old' else 'NEW_REGIME_115BAC_SLAB_PROGRESSIVE_CALCULATION'}_{age_category.upper()}"
        )

        return IncomeTaxSlabResult(
            net_taxable_income=net_taxable_income,
            base_tax_liability=base_tax,
            slab_breakdown=slab_breakdown,
            age_category=age_category
        )

    def _get_fallback_slabs(self, financial_year, regime_code, age_category='general'):
        """Standard statutory fallbacks if tax slabs are unseeded."""
        class DummySlab:
            def __init__(self, name, inc_from, inc_to, rate):
                self.name = name
                self.income_from = inc_from
                self.income_to = inc_to
                self.rate = rate

        if regime_code == 'new':
            # New Regime Slabs (Finance Act 2025 / FY 2025-26) — uniform for all ages
            return [
                DummySlab("Up to ₹4.0L", 0.0, 400000.0, 0.0),
                DummySlab("₹4.0L - ₹8.0L", 400000.0, 800000.0, 5.0),
                DummySlab("₹8.0L - ₹12.0L", 800000.0, 1200000.0, 10.0),
                DummySlab("₹12.0L - ₹16.0L", 1200000.0, 1600000.0, 15.0),
                DummySlab("₹16.0L - ₹20.0L", 1600000.0, 2000000.0, 20.0),
                DummySlab("₹20.0L - ₹24.0L", 2000000.0, 2400000.0, 25.0),
                DummySlab("Above ₹24.0L", 2400000.0, 0.0, 30.0),
            ]
        else:
            # Old Regime Slabs — age-category-aware
            if age_category == 'super_senior':
                # Super Senior Citizen (80+): Exemption up to ₹5,00,000, no 5% slab
                return [
                    DummySlab("Up to ₹5.0L [Super Senior]", 0.0, 500000.0, 0.0),
                    DummySlab("₹5.0L - ₹10.0L [Super Senior]", 500000.0, 1000000.0, 20.0),
                    DummySlab("Above ₹10.0L [Super Senior]", 1000000.0, 0.0, 30.0),
                ]
            elif age_category == 'senior':
                # Senior Citizen (60–79): Exemption up to ₹3,00,000
                return [
                    DummySlab("Up to ₹3.0L [Senior]", 0.0, 300000.0, 0.0),
                    DummySlab("₹3.0L - ₹5.0L [Senior]", 300000.0, 500000.0, 5.0),
                    DummySlab("₹5.0L - ₹10.0L [Senior]", 500000.0, 1000000.0, 20.0),
                    DummySlab("Above ₹10.0L [Senior]", 1000000.0, 0.0, 30.0),
                ]
            else:
                # General (Below 60): Exemption up to ₹2,50,000
                return [
                    DummySlab("Up to ₹2.5L", 0.0, 250000.0, 0.0),
                    DummySlab("₹2.5L - ₹5.0L", 250000.0, 500000.0, 5.0),
                    DummySlab("₹5.0L - ₹10.0L", 500000.0, 1000000.0, 20.0),
                    DummySlab("Above ₹10.0L", 1000000.0, 0.0, 30.0),
                ]
