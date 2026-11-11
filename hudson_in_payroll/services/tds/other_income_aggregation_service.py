# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class OtherIncomeAggregationResult:
    """
    Data Transfer Object (DTO) holding aggregated non-payroll income from other sources & house property.
    """
    def __init__(self, savings_interest=0.0, fd_interest=0.0, dividend_income=0.0,
                 other_sources_misc=0.0, total_other_sources=0.0,
                 gross_let_out_rent=0.0, municipal_taxes=0.0, nav=0.0,
                 property_std_deduction=0.0, let_out_interest=0.0,
                 net_house_property_income_loss=0.0, total_other_income=0.0,
                 allowed_hp_loss_set_off=0.0, effective_hp_gti_impact=0.0,
                 hp_loss_limit=0.0, regime_code='new', has_declaration=False,
                 family_pension_gross=None, family_pension_deduction=None,
                 family_pension_net=None):
        self.savings_interest = savings_interest
        self.fd_interest = fd_interest
        self.dividend_income = dividend_income
        self.other_sources_misc = other_sources_misc
        self.total_other_sources = total_other_sources
        self.gross_let_out_rent = gross_let_out_rent
        self.municipal_taxes = municipal_taxes
        self.nav = nav
        self.property_std_deduction = property_std_deduction
        self.let_out_interest = let_out_interest
        self.net_house_property_income_loss = net_house_property_income_loss
        self.total_other_income = total_other_income
        self.allowed_hp_loss_set_off = allowed_hp_loss_set_off
        self.effective_hp_gti_impact = effective_hp_gti_impact
        self.hp_loss_limit = hp_loss_limit
        self.regime_code = regime_code
        self.has_declaration = has_declaration
        self.family_pension_gross = family_pension_gross
        self.family_pension_deduction = family_pension_deduction
        self.family_pension_net = family_pension_net


class OtherIncomeAggregationService(BaseStatutoryService):
    """
    Phase 4 Service: Other Income Aggregation Service.
    Aggregates non-payroll Category A regime-neutral declared incomes:
    1. Income from Other Sources (Savings Interest, FD Interest, Dividends, Miscellaneous)
    2. Income / Loss from Let-Out House Property (Gross Rent - Municipal Taxes - 30% NAV - Loan Interest)
       - Old Regime: House property loss set-off against salary/GTI is allowed up to Section 71(3A) ceiling (default ₹2,00,000).
       - New Regime: Section 115BAC strictly prohibits house property loss set-off against salary/GTI (set-off = ₹0.0).
    """

    def aggregate_other_income(self, employee, financial_year, regime_code='new', eval_date=None):
        """
        Aggregates non-payroll income for the employee in the specified Financial Year.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param eval_date: Date (optional evaluation date)
        :return: OtherIncomeAggregationResult
        """
        eval_date = eval_date or fields.Date.today()
        regime_code = (regime_code or 'new').lower()
        tds_param_svc = TdsParameterService(self.env)

        inc_decl = self.env['tds.employee.income.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id),
        ], limit=1)

        _logger.warning("========== OTHER INCOME AGGREGATION ==========")
        _logger.warning(
            "Employee: %s | FY: %s | Regime: %s",
            employee.name if employee else "Unknown",
            financial_year.name if financial_year else "Unknown",
            regime_code.upper()
        )
        _logger.warning(
            "Declaration Found: %s",
            inc_decl.id if inc_decl else "None"
        )
        _logger.warning(
            "Savings Interest: %s",
            inc_decl.savings_bank_interest if inc_decl else 0.0
        )
        _logger.warning(
            "FD Interest: %s",
            inc_decl.fixed_deposit_interest if inc_decl else 0.0
        )
        _logger.warning(
            "Dividend Income: %s",
            inc_decl.dividend_income if inc_decl else 0.0
        )
        _logger.warning(
            "Other Misc Income: %s",
            inc_decl.other_sources_income if inc_decl else 0.0
        )
        _logger.warning(
            "Gross Rent: %s",
            inc_decl.annual_let_out_rent if inc_decl else 0.0
        )
        _logger.warning(
            "Municipal Tax: %s",
            inc_decl.municipal_taxes_paid if inc_decl else 0.0
        )
        _logger.warning(
            "Let Out Interest: %s",
            inc_decl.let_out_interest_paid if inc_decl else 0.0
        )

        savings_interest = inc_decl.savings_bank_interest or 0.0 if inc_decl else 0.0
        fd_interest = inc_decl.fixed_deposit_interest or 0.0 if inc_decl else 0.0
        dividend_income = inc_decl.dividend_income or 0.0 if inc_decl else 0.0
        other_misc = inc_decl.other_sources_income or 0.0 if inc_decl else 0.0

        # Include Family Pension Income declared on Employee Tax Declaration
        # Initialised to None outside tds_decl if-block; netted under Income from Other Sources
        family_pension_gross = None
        family_pension_deduction = None
        family_pension_net = None

        if employee and financial_year:
            tds_decl = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
                ('state', '!=', 'rejected')
            ], order='submission_date desc, create_date desc, id desc', limit=1)
            if tds_decl:
                gross_pension = float(getattr(tds_decl, 'decl_57iia_family_pension', 0.0) or 0.0)
                line_57 = next((l for l in getattr(tds_decl, 'declaration_line_ids', []) if l.category == '57iia' and getattr(l, 'active', True)), None)
                if not gross_pension and line_57:
                    gross_pension = float(line_57.declared_amount or 0.0)
                is_post_proof = getattr(tds_decl, 'state', 'draft') in ('proof_verified', 'approved')
                if is_post_proof and line_57:
                    line_appr = float(getattr(line_57, 'tax_firm_approved_amount', 0.0) or getattr(line_57, 'approved_amount', 0.0) or 0.0)
                    if line_appr > 0.0:
                        gross_pension = line_appr

                if gross_pension > 0.0 or line_57:
                    from .section_57iia_deduction_service import Section57IIADeductionService
                    p_svc = Section57IIADeductionService(self.env)
                    p_res = p_svc.validate_and_trace(
                        tds_decl,
                        eval_date=eval_date,
                        regime_code=regime_code,
                        employee=employee,
                        financial_year=financial_year
                    )
                    allowed_ded = float(getattr(p_res, 'allowed_deduction', 0.0) or 0.0)
                    family_pension_gross = gross_pension
                    family_pension_deduction = allowed_ded
                    family_pension_net = max(0.0, gross_pension - allowed_ded)
                else:
                    family_pension_gross = 0.0
                    family_pension_deduction = 0.0
                    family_pension_net = 0.0

        if not inc_decl and (family_pension_gross is None or (family_pension_gross == 0.0 and (family_pension_net or 0.0) == 0.0)):
            _logger.warning("Total Other Sources: 0.0")
            _logger.warning("Net House Property Income/Loss: 0.0")
            _logger.warning("Total Other Income Returned: 0.0")
            _logger.warning("=============================================")
            return OtherIncomeAggregationResult(
                regime_code=regime_code,
                has_declaration=False,
                family_pension_gross=family_pension_gross,
                family_pension_deduction=family_pension_deduction,
                family_pension_net=family_pension_net
            )

        total_other_sources = savings_interest + fd_interest + dividend_income + other_misc + (family_pension_net or 0.0)

        # House Property Computation (NAV, Section 24(a) 30% Statutory Allowance, Interest)
        gross_rent = inc_decl.annual_let_out_rent or 0.0 if inc_decl else 0.0
        munc_tax = inc_decl.municipal_taxes_paid or 0.0 if inc_decl else 0.0
        nav = max(0.0, gross_rent - munc_tax)
        prop_std_ded = nav * 0.30  # Section 24(a) 30% NAV statutory repair allowance
        let_out_interest = inc_decl.let_out_interest_paid or 0.0 if inc_decl else 0.0

        # Unadjusted raw Net House Property Income or Loss
        net_property = nav - prop_std_ded - let_out_interest

        # Statutory Loss Set-Off Rules (Section 71(3A) & Section 115BAC)
        effective_hp_gti_impact = self.calculate_effective_hp_impact(net_property, regime_code=regime_code, eval_date=eval_date)
        if effective_hp_gti_impact > 0.0 and employee and financial_year:
            effective_hp_gti_impact = self.apply_previous_carry_forward_losses(
                employee.id, financial_year.id, effective_hp_gti_impact, regime_code=regime_code, eval_date=eval_date
            )

        if net_property >= 0.0:
            hp_loss_limit = 0.0
            allowed_hp_loss_set_off = 0.0
        else:
            raw_hp_loss = abs(net_property)
            if regime_code == 'new':
                hp_loss_limit = 0.0
                allowed_hp_loss_set_off = 0.0
            else:
                hp_loss_limit = tds_param_svc.get_house_property_loss_limit(eval_date=eval_date)
                allowed_hp_loss_set_off = min(raw_hp_loss, hp_loss_limit)

        total_other_income = total_other_sources + effective_hp_gti_impact

        raw_hp_loss = abs(net_property) if net_property < 0 else 0.0

        _logger.warning(
            "\n[SECTION 24(b) - LET-OUT PROPERTY TRACE]\n"
            "==================================================\n"
            "Data Origin                         : tds.employee.income.declaration (ID: %s)\n"
            "Tax Regime                          : %s\n"
            "Gross Annual Rent                   : ₹%s  [Source: inc_decl.annual_let_out_rent]\n"
            "Municipal Taxes Paid                : ₹%s  [Source: inc_decl.municipal_taxes_paid]\n"
            "Net Annual Value (NAV)              : ₹%s  [Formula: max(0, Rent - Municipal Tax)]\n"
            "30%% Section 24(a) Deduction         : ₹%s  [Formula: NAV * 30%% u/s 24(a)]\n"
            "Section 24(b) - Let-Out Interest    : ₹%s  [Field: let_out_interest_paid via OtherIncomeAggregationService]\n"
            "Section 24(b) Interest Cap          : UNCAPPED (Actual Let-Out Interest Allowed u/s 24(b))\n"
            "Raw House Property Income/Loss      : ₹%s  [Formula: NAV - 30%% Ded - Let-Out Interest]\n"
            "House Property Loss Amount          : ₹%s  [Raw Loss if Net HP < 0]\n"
            "Allowed House Property Loss Set-Off : ₹%s  [Rule: NEW=₹0 | OLD=₹2,00,000 Parameter]\n"
            "Effective GTI Impact                : ₹%s  [HP Income OR -Allowed Set-Off]\n"
            "Other Sources Income                : ₹%s  [Savings + FD + Dividends + Misc + FamPension]\n"
            "Final Other Income Returned to Engine: ₹%s\n"
            "==================================================",
            inc_decl.id if inc_decl else "None",
            regime_code.upper(),
            f"{gross_rent:,.2f}",
            f"{munc_tax:,.2f}",
            f"{nav:,.2f}",
            f"{prop_std_ded:,.2f}",
            f"{let_out_interest:,.2f}",
            f"{net_property:,.2f}",
            f"{raw_hp_loss:,.2f}",
            f"{allowed_hp_loss_set_off:,.2f}",
            f"{effective_hp_gti_impact:,.2f}",
            f"{total_other_sources:,.2f}",
            f"{total_other_income:,.2f}"
        )

        return OtherIncomeAggregationResult(
            savings_interest=savings_interest,
            fd_interest=fd_interest,
            dividend_income=dividend_income,
            other_sources_misc=other_misc,
            total_other_sources=total_other_sources,
            gross_let_out_rent=gross_rent,
            municipal_taxes=munc_tax,
            nav=nav,
            property_std_deduction=prop_std_ded,
            let_out_interest=let_out_interest,
            net_house_property_income_loss=net_property,
            total_other_income=total_other_income,
            allowed_hp_loss_set_off=allowed_hp_loss_set_off,
            effective_hp_gti_impact=effective_hp_gti_impact,
            hp_loss_limit=hp_loss_limit,
            regime_code=regime_code,
            has_declaration=bool(inc_decl) or bool(family_pension_gross is not None and family_pension_gross > 0.0),
            family_pension_gross=family_pension_gross,
            family_pension_deduction=family_pension_deduction,
            family_pension_net=family_pension_net
        )

    def calculate_effective_hp_impact(self, net_property, regime_code='new', eval_date=None):
        """
        Calculates current-year regime-adjusted House Property GTI impact.
        - Positive net_property: taxable under both regimes.
        - Negative net_property (loss):
          - New Regime (Section 115BAC): loss set-off prohibited (0.0).
          - Old Regime (Section 71(3A)): loss set-off allowed up to statutory parameter ceiling (default ₹2,00,000).
        """
        eval_date = eval_date or fields.Date.today()
        regime_code = (regime_code or 'new').lower()
        tds_param_svc = TdsParameterService(self.env)

        if net_property >= 0.0:
            return net_property
        else:
            raw_hp_loss = abs(net_property)
            if regime_code == 'new':
                return 0.0
            else:
                hp_loss_limit = tds_param_svc.get_house_property_loss_limit(eval_date=eval_date)
                allowed_hp_loss_set_off = min(raw_hp_loss, hp_loss_limit)
                return -allowed_hp_loss_set_off

    def apply_previous_carry_forward_losses(self, employee_id, financial_year_id, positive_hp_income, regime_code='new', eval_date=None):
        """
        Applies prior-year unabsorbed House Property carry-forward losses (Section 71B, FIFO, 8-AY limit)
        against positive current-year House Property income before it reaches GTI.
        """
        if positive_hp_income <= 0.0 or not employee_id or not financial_year_id:
            return max(0.0, positive_hp_income)

        if 'tds.house.property.loss.carryforward' not in self.env:
            return positive_hp_income

        eval_date = eval_date or fields.Date.today()
        curr_fy = self.env['tds.financial.year'].sudo().browse(financial_year_id)
        if not curr_fy or not curr_fy.start_date:
            return positive_hp_income

        cf_records = self.env['tds.house.property.loss.carryforward'].sudo().search([
            ('employee_id', '=', employee_id),
            ('unabsorbed_loss_amount', '>', 0.0),
            ('financial_year_id', '!=', financial_year_id),
        ], order='financial_year_id asc, id asc')

        remaining_income = positive_hp_income
        for cf in cf_records:
            if remaining_income <= 0.0:
                break
            if cf.financial_year_id and cf.financial_year_id.start_date:
                start_year = cf.financial_year_id.start_date.year
                curr_year = curr_fy.start_date.year
                if (curr_year - start_year) > 8:
                    continue
            available_loss = cf.unabsorbed_loss_amount or 0.0
            setoff_amount = min(remaining_income, available_loss)
            remaining_income -= setoff_amount

        return max(0.0, remaining_income)
