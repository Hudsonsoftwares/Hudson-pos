# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class Section10HraExemptionResult:
    """
    Data Transfer Object representing the result of Section 10(13A) HRA Exemption calculation.
    """
    def __init__(self, actual_hra_received, annual_rent_paid, basic_salary, is_metro,
                 rent_excess_basic, basic_pct_limit, exempt_amount, taxable_hra, remarks,
                 is_eligible=True, rejection_reason=None, own_residential_property_at_workplace=False,
                 rent_period_from=None, rent_period_to=None, regime_code='old', trace_log=None):
        self.actual_hra_received = actual_hra_received
        self.annual_rent_paid = annual_rent_paid
        self.basic_salary = basic_salary
        self.is_metro = is_metro
        self.rent_excess_basic = rent_excess_basic
        self.basic_pct_limit = basic_pct_limit
        self.exempt_amount = exempt_amount
        self.allowed_hra_exemption = exempt_amount
        self.taxable_hra = taxable_hra
        self.remarks = remarks
        self.is_eligible = is_eligible
        self.rejection_reason = rejection_reason
        self.own_residential_property_at_workplace = own_residential_property_at_workplace
        self.rent_period_from = rent_period_from
        self.rent_period_to = rent_period_to
        self.regime_code = regime_code
        self.trace_log = trace_log

    @property
    def usable_amount(self):
        return self.exempt_amount if self.is_eligible else 0.0

    @property
    def allowed_deduction(self):
        return self.exempt_amount if self.is_eligible else 0.0


class Section10HraExemptionService(BaseStatutoryService):
    """
    Dedicated Exemption Calculation Service for Section 10(13A) House Rent Allowance (HRA).
    Enforces the statutory eligibility rules and 3-way minimum formula under Indian Income Tax Act:
    
    Eligibility Conditions:
    1. Tax Regime: Old Regime only (New Regime u/s 115BAC does not allow HRA exemption).
    2. Actual HRA received > 0 from employer payroll.
    3. Rent paid > 0 for residential accommodation.
    4. Employee must NOT own residential property at place of work/residence (own_residential_property_at_workplace == False).
    5. Rent Period From must be provided.
    6. Rent Period To must be provided and Rent Period To >= Rent Period From.
    7. Claimed rent period must fall within the relevant financial year.
    
    Formula (Least of 3):
    1. Actual HRA received from employer
    2. Rent Paid minus 10% of Basic Salary (+ DA)
    3. 50% of Basic Salary (+ DA) for Metro cities OR 40% for Non-Metro cities
    """

    def calculate_exemption(self, annual_rent_paid, actual_hra_received, annual_basic_salary, is_metro=True, eval_date=None, **kwargs):
        """
        Calculates statutory HRA exemption under Section 10(13A) and prints structured audit trace.

        :param annual_rent_paid: Float (Annual rent paid by employee)
        :param actual_hra_received: Float (Annual HRA allowance received from payroll)
        :param annual_basic_salary: Float (Annual Basic Salary + DA)
        :param is_metro: Boolean (True if accommodation is in Metro city: Delhi, Mumbai, Kolkata, Chennai)
        :param eval_date: Date (optional)
        :param kwargs: Optional context parameters (employee, financial_year, declaration, declaration_line, regime_code,
                       own_residential_property_at_workplace, rent_period_from, rent_period_to,
                       annual_basic_component, annual_da_component)
        :return: Section10HraExemptionResult
        """
        tds_param_svc = TdsParameterService(self.env)
        eval_date = eval_date or fields.Date.today()

        # Context Extraction
        employee = kwargs.get('employee')
        fy = kwargs.get('financial_year')
        decl = kwargs.get('declaration')
        decl_line = kwargs.get('declaration_line')

        # 1. Resolve Regime Code
        regime_code = (
            kwargs.get('regime_code') or
            (decl.regime_code if decl and getattr(decl, 'regime_code', False) else None) or
            'old'
        ).lower()

        # 2. Resolve Own Residential Property at Workplace
        own_prop = kwargs.get('own_residential_property_at_workplace')
        if own_prop is None:
            if decl_line and hasattr(decl_line, 'own_residential_property_at_workplace'):
                own_prop = bool(decl_line.own_residential_property_at_workplace)
            elif decl:
                own_prop = bool(
                    getattr(decl, 'own_residential_property_at_workplace', False) or
                    getattr(decl, 'decl_hra_own_residential_property_at_workplace', False)
                )
            else:
                own_prop = False
        else:
            own_prop = bool(own_prop)

        # 3. Resolve Rent Period From & To
        rent_from = kwargs.get('rent_period_from')
        if rent_from is None:
            if decl_line and getattr(decl_line, 'rent_period_from', None):
                rent_from = decl_line.rent_period_from
            elif decl:
                rent_from = getattr(decl, 'rent_period_from', None) or getattr(decl, 'decl_hra_rent_period_from', None)

        rent_to = kwargs.get('rent_period_to')
        if rent_to is None:
            if decl_line and getattr(decl_line, 'rent_period_to', None):
                rent_to = decl_line.rent_period_to
            elif decl:
                rent_to = getattr(decl, 'rent_period_to', None) or getattr(decl, 'decl_hra_rent_period_to', None)

        # Convert string dates if necessary
        if isinstance(rent_from, str):
            rent_from = fields.Date.from_string(rent_from)
        if isinstance(rent_to, str):
            rent_to = fields.Date.from_string(rent_to)

        # 4. Resolve Financial Year Dates
        fy_start = None
        fy_end = None
        if fy:
            fy_start = fy.start_date
            fy_end = fy.end_date
        elif decl and decl.financial_year_id:
            fy_start = decl.financial_year_id.start_date
            fy_end = decl.financial_year_id.end_date

        if isinstance(fy_start, str):
            fy_start = fields.Date.from_string(fy_start)
        if isinstance(fy_end, str):
            fy_end = fields.Date.from_string(fy_end)

        # If rent dates are completely unspecified in kwargs, fallback to FY dates or eval_date FY for legacy callers
        if rent_from is None and 'rent_period_from' not in kwargs:
            if fy_start:
                rent_from = fy_start
            elif eval_date:
                eval_yr = eval_date.year if eval_date.month >= 4 else eval_date.year - 1
                rent_from = fields.Date.from_string(f"{eval_yr}-04-01")

        if rent_to is None and 'rent_period_to' not in kwargs:
            if fy_end:
                rent_to = fy_end
            elif eval_date:
                eval_yr = eval_date.year if eval_date.month >= 4 else eval_date.year - 1
                rent_to = fields.Date.from_string(f"{eval_yr + 1}-03-31")

        # Resolve effective-dated parameters via TdsParameterService
        metro_pct = tds_param_svc.get_hra_percentage(is_metro=True, eval_date=eval_date, as_decimal=True) or 0.50
        non_metro_pct = tds_param_svc.get_hra_percentage(is_metro=False, eval_date=eval_date, as_decimal=True) or 0.40
        rent_excess_pct = tds_param_svc.get_parameter('HRA_RENT_EXCESS_BASIC_PERCENT', eval_date=eval_date, as_decimal=True) or 0.10

        basic_pct = metro_pct if is_metro else non_metro_pct

        # 1. Component 1: Actual HRA Received
        comp_actual_hra = max(0.0, float(actual_hra_received or 0.0))

        # 2. Component 2: Rent Paid - 10% of Basic Salary
        ten_pct_salary = rent_excess_pct * float(annual_basic_salary or 0.0)
        rent_excess_basic = max(0.0, float(annual_rent_paid or 0.0) - ten_pct_salary)

        # 3. Component 3: 50% or 40% of Basic Salary
        basic_pct_limit = max(0.0, basic_pct * float(annual_basic_salary or 0.0))

        # -------------------------------------------------------------------------
        # SECTION 10(13A) ELIGIBILITY EVALUATION
        # -------------------------------------------------------------------------
        is_eligible = True
        rejection_reason = "N/A"

        # Condition 1: Tax Regime = Old
        cond_regime_ok = (regime_code == 'old')
        if not cond_regime_ok:
            is_eligible = False
            rejection_reason = "Section 10(13A) HRA exemption is available only under the Old Tax Regime."

        # Condition 2: Actual HRA Received > 0
        comp_actual_hra = max(0.0, float(actual_hra_received or 0.0))
        cond_hra_received_ok = (comp_actual_hra > 0.0)
        if is_eligible and not cond_hra_received_ok:
            is_eligible = False
            rejection_reason = "Section 10(13A) not eligible: No HRA was received during the relevant period."

        # Condition 3: Annual Rent Paid > 0
        annual_rent_num = float(annual_rent_paid or 0.0)
        cond_rent_paid_ok = (annual_rent_num > 0.0)
        if is_eligible and not cond_rent_paid_ok:
            is_eligible = False
            rejection_reason = "Section 10(13A) not eligible: No actual rent was paid."

        # Condition 4: Own Residential Property at Workplace/Residence
        cond_own_prop_ok = (not own_prop)
        if is_eligible and not cond_own_prop_ok:
            is_eligible = False
            rejection_reason = "Section 10(13A) not eligible: Employee owns a residential property at the place of work/residence."

        # Rent Period Validation (within selected Financial Year):
        # 1. rent_period_from >= FY_start
        # 2. rent_period_to <= FY_end
        # 3. rent_period_to >= rent_period_from
        cond_rent_from_ok = bool(rent_from)
        cond_rent_to_ok = bool(rent_to)
        cond_rent_dates_order_ok = bool(rent_from and rent_to and rent_to >= rent_from)
        cond_rent_within_fy_ok = bool(
            rent_from and rent_to and
            (not fy_start or rent_from >= fy_start) and
            (not fy_end or rent_to <= fy_end)
        )

        if is_eligible:
            if not cond_rent_from_ok or not cond_rent_to_ok or not cond_rent_dates_order_ok or not cond_rent_within_fy_ok:
                is_eligible = False
                rejection_reason = "Invalid rent period: Rent period must fall within the selected Financial Year."

        # -------------------------------------------------------------------------
        # STATUTORY FORMULA EVALUATION (ONLY IF ELIGIBLE)
        # -------------------------------------------------------------------------
        raw_rent_excess = float(annual_rent_paid or 0.0) - ten_pct_salary

        if not is_eligible:
            exempt_amount = 0.0
            taxable_hra = comp_actual_hra
            reason = rejection_reason
            remarks = f"Section 10(13A) HRA Exemption: ₹0.00 ({rejection_reason})"
        elif float(annual_basic_salary or 0.0) <= 0:
            exempt_amount = 0.0
            reason = "No HRA exemption allowable: Salary considered (Basic + DA) is zero."
            remarks = "No HRA exemption: Salary considered (Basic + DA) is zero."
            taxable_hra = comp_actual_hra
        else:
            exempt_amount = min(comp_actual_hra, rent_excess_basic, basic_pct_limit)
            if exempt_amount == 0.0 and raw_rent_excess <= 0.0:
                reason = f"No HRA exemption allowable because Formula 2 (Rent Paid minus 10% Salary = INR {raw_rent_excess:,.2f}) evaluated to zero after applying the statutory floor under Section 10(13A)."
            elif exempt_amount == comp_actual_hra:
                reason = f"Formula 1 (Actual HRA Received = INR {comp_actual_hra:,.2f}) is the lowest of the three statutory components under Section 10(13A)."
            elif exempt_amount == rent_excess_basic:
                reason = f"Formula 2 (Rent Paid minus 10% Salary = INR {rent_excess_basic:,.2f}) is the lowest of the three statutory components under Section 10(13A)."
            else:
                reason = f"Formula 3 (Statutory {int(basic_pct * 100)}% of Salary limit = INR {basic_pct_limit:,.2f}) is the lowest of the three statutory components under Section 10(13A)."

            remarks = f"Section 10(13A) HRA Exemption calculated as min(Actual HRA INR {comp_actual_hra:,.2f}, Rent Excess 10% Basic INR {rent_excess_basic:,.2f}, {int(basic_pct*100)}% Basic INR {basic_pct_limit:,.2f}) = INR {exempt_amount:,.2f}."
            taxable_hra = max(0.0, comp_actual_hra - exempt_amount)

        # Context Extraction for Trace Header
        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = fy.name if fy else kwargs.get('financial_year_name', 'N/A')
        decl_id = decl.id if decl else kwargs.get('declaration_id', 'N/A')

        landlord_name = (decl.decl_hra_landlord_name if decl else False) or kwargs.get('landlord_name', 'N/A') or 'N/A'
        landlord_pan = (decl.decl_hra_landlord_pan if decl else False) or kwargs.get('landlord_pan', 'N/A') or 'N/A'

        basic_comp = kwargs.get('annual_basic_component', annual_basic_salary)
        da_comp = kwargs.get('annual_da_component', 0.0)

        # Print Structured SECTION 10(13A) HRA ELIGIBILITY & STATUTORY TRACE
        trace_log = f"""
=========================================================
SECTION 10(13A) HRA ELIGIBILITY & EXEMPTION TRACE
=========================================================

Employee                        : {emp_name} (ID: {emp_id})
Financial Year                  : {fy_name}
Declaration ID                  : {decl_id}

---------------------------------------------------------
ELIGIBILITY CONDITIONS
---------------------------------------------------------
1. Tax Regime (Old Regime)      : {"OLD" if regime_code == 'old' else "NEW"} [{'PASS' if cond_regime_ok else 'FAIL'}]
2. Actual HRA Received > 0      : INR {comp_actual_hra:,.2f} [{'PASS' if cond_hra_received_ok else 'FAIL'}]
3. Annual Rent Paid > 0         : INR {annual_rent_num:,.2f} [{'PASS' if cond_rent_paid_ok else 'FAIL'}]
4. Own Residential Property     : {"YES (Disqualified)" if own_prop else "NO"} [{'PASS' if cond_own_prop_ok else 'FAIL'}]
5. Rent Period From             : {rent_from or 'Not Provided'} [{'PASS' if cond_rent_from_ok else 'FAIL'}]
6. Rent Period To               : {rent_to or 'Not Provided'} [{'PASS' if (cond_rent_to_ok and cond_rent_dates_order_ok) else 'FAIL'}]
7. Period in Financial Year     : {f"{fy_start} to {fy_end}" if fy_start else "N/A"} [{'PASS' if cond_rent_within_fy_ok else 'FAIL'}]

---------------------------------------------------------
ELIGIBILITY RESULT
---------------------------------------------------------
Final Eligibility               : {"ELIGIBLE" if is_eligible else "NOT_ELIGIBLE"}
Eligibility Status              : {"PASS" if is_eligible else "REJECTED"}
Rejection Reason                : {rejection_reason}

---------------------------------------------------------
DECLARATION INPUTS
---------------------------------------------------------
Annual Rent Paid                : INR {annual_rent_num:,.2f}
Metro City                      : {"YES" if is_metro else "NO"}
Landlord Name                   : {landlord_name}
Landlord PAN                    : {landlord_pan}

---------------------------------------------------------
SALARY PROJECTION INPUTS
---------------------------------------------------------
Annual Basic Salary             : INR {float(basic_comp or 0.0):,.2f}
Annual Dearness Allowance       : INR {float(da_comp or 0.0):,.2f}
Salary considered (Basic + DA)  : INR {float(annual_basic_salary or 0.0):,.2f}
Actual HRA Received             : INR {comp_actual_hra:,.2f}

---------------------------------------------------------
STATUTORY FORMULAS
---------------------------------------------------------
Formula 1 (Actual HRA Received) : INR {comp_actual_hra:,.2f}
Formula 2 (Rent minus 10% Sal)  : INR {rent_excess_basic:,.2f}
Formula 3 ({int(basic_pct * 100)}% Basic Salary)      : INR {basic_pct_limit:,.2f}

=========================================================
FINAL HRA EXEMPTION
=========================================================
Allowed HRA Exemption           : INR {exempt_amount:,.2f}
Taxable HRA                     : INR {taxable_hra:,.2f}
Reason                          : {reason}
=========================================================
"""
        _logger.warning(trace_log)

        _logger.warning("""[HRA_ELIGIBILITY_TRACE]
employee=%s
regime=%s
actual_hra_received=%s
annual_rent_paid=%s
own_residential_property_at_workplace=%s
rent_period_from=%s
rent_period_to=%s
is_eligible=%s
allowed_hra_exemption=%s
rejection_reason=%s""",
            emp_name, regime_code, comp_actual_hra, annual_rent_num,
            own_prop, rent_from, rent_to,
            is_eligible, exempt_amount, rejection_reason
        )

        return Section10HraExemptionResult(
            actual_hra_received=comp_actual_hra,
            annual_rent_paid=annual_rent_paid,
            basic_salary=annual_basic_salary,
            is_metro=is_metro,
            rent_excess_basic=rent_excess_basic,
            basic_pct_limit=basic_pct_limit,
            exempt_amount=exempt_amount,
            taxable_hra=taxable_hra,
            remarks=remarks,
            is_eligible=is_eligible,
            rejection_reason=rejection_reason,
            own_residential_property_at_workplace=own_prop,
            rent_period_from=rent_from,
            rent_period_to=rent_to,
            regime_code=regime_code,
            trace_log=trace_log
        )

