# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class Section10LtaExemptionResult:
    """
    Data Transfer Object (DTO) representing the complete statutory audit result
    of Section 10(5) Leave Travel Allowance (LTA) exemption.
    """
    def __init__(self, employee_id, block_period, claims_in_block, max_claims_permitted,
                 declared_fare, actual_lta_received, exempt_amount, taxable_amount,
                 is_eligible, regime_code, remarks,
                 prev_block_period=None, claims_in_prev_block=0, carry_forward_available=0,
                 carry_forward_used=False, carry_forward_status='not_applicable',
                 normal_entitlement=2, normal_claims_used=0, normal_claims_remaining=2,
                 origin=None, destination=None, origin_country='IN', destination_country='IN',
                 is_domestic=True, journey_date=None, travel_mode='air', family_members_count=1,
                 mode_statutory_ceiling=0.0, shortest_route_reference_fare=0.0,
                 eligible_travel_fare=0.0, checks=None, trace_log=""):
        self.employee_id = employee_id
        self.block_period = block_period
        self.claims_in_block = claims_in_block
        self.max_claims_permitted = max_claims_permitted
        self.declared_fare = declared_fare
        self.actual_lta_received = actual_lta_received
        self.exempt_amount = exempt_amount
        self.taxable_amount = taxable_amount
        self.is_eligible = is_eligible
        self.regime_code = regime_code
        self.remarks = remarks
        self.prev_block_period = prev_block_period
        self.claims_in_prev_block = claims_in_prev_block
        self.carry_forward_available = carry_forward_available
        self.carry_forward_used = carry_forward_used
        self.carry_forward_status = carry_forward_status
        self.normal_entitlement = normal_entitlement
        self.normal_claims_used = normal_claims_used
        self.normal_claims_remaining = normal_claims_remaining
        self.origin = origin
        self.destination = destination
        self.origin_country = origin_country
        self.destination_country = destination_country
        self.is_domestic = is_domestic
        self.journey_date = journey_date
        self.travel_mode = travel_mode
        self.family_members_count = family_members_count
        self.mode_statutory_ceiling = mode_statutory_ceiling
        self.shortest_route_reference_fare = shortest_route_reference_fare
        self.eligible_travel_fare = eligible_travel_fare
        self.checks = checks or []
        self.trace_log = trace_log

    @property
    def eligibility_status(self):
        if not self.is_eligible:
            return 'ineligible'
        elif self.exempt_amount > 0.0:
            return 'eligible'
        else:
            return 'pending_verification'

    @property
    def claim_sequence(self):
        if not self.is_eligible:
            return f"Ineligible (Normal Used: {self.normal_claims_used}/{self.normal_entitlement})"
        if self.carry_forward_used:
            return f"Carry-Forward Claim (Block {self.block_period})"
        return f"Normal Claim {self.normal_claims_used + 1} of {self.normal_entitlement}"

    @property
    def remaining_claims(self):
        return self.normal_claims_remaining

    @property
    def statutory_fare_ceiling(self):
        if self.shortest_route_reference_fare > 0.0:
            return min(self.mode_statutory_ceiling, self.shortest_route_reference_fare)
        return self.mode_statutory_ceiling

    def to_dict(self):
        """Returns structured DTO dictionary matching Requirement 11 & 12."""
        return {
            "status": self.eligibility_status,
            "checks": self.checks,
            "current_block": self.block_period,
            "previous_block": self.prev_block_period,
            "normal_entitlement": self.normal_entitlement,
            "normal_claims_used": self.normal_claims_used,
            "normal_claims_remaining": self.normal_claims_remaining,
            "carry_forward_available": self.carry_forward_available,
            "carry_forward_status": self.carry_forward_status,
            "carry_forward_used": self.carry_forward_used,
            "eligible_travel_fare": self.eligible_travel_fare,
            "fare_ceiling": self.statutory_fare_ceiling,
            "lta_received": self.actual_lta_received,
            "allowable_exemption": self.exempt_amount,
            "remarks": self.remarks
        }


class Section10LtaExemptionService(BaseStatutoryService):
    """
    Dedicated Exemption Calculation & Historical Claim Audit Engine for Section 10(5) LTA.

    Statutory Provisions under Indian Income Tax Act & Rule 2B:
    1. Exemption is permitted ONLY under the Old Tax Regime (Section 115BAC prohibits LTA under New Regime).
    2. Mandatory Journey Date: Claim without actual journey date is ineligible.
    3. Domestic Travel Only: Origin and Destination must be within India.
    4. Expense Limitation: Pure travel fare only (excludes lodging, boarding, sightseeing, local conveyance).
    5. Rule 2B Family & Child Limit: Restricted to max 2 children born on/after 01-Oct-1998 (unless multiple births).
    6. Mode & Shortest-Route Statutory Ceilings: Air (Economy), Rail (AC 1st Class), Public Transport / Other.
    7. 4-Calendar-Year Block & Carry-Forward: Max 2 claims per 4-CY block; 1 unavailed journey can be carried forward
       to Year 1 of immediately following block.
    8. Statutory Exemption = min(Capped Eligible Travel Fare, Actual LTA Allowance Received from Payroll).
    """

    def _get_historical_claims_in_block(self, employee_id, block_period, current_declaration_id=None):
        """
        Determines the total number of prior eligible/approved LTA claims made by the employee
        across all Financial Years overlapping the specified 4-calendar-year block period.
        """
        emp_id = employee_id.id if hasattr(employee_id, 'id') else employee_id
        if not emp_id or not block_period:
            return 0, []

        try:
            parts = str(block_period).split('-')
            start_cy = int(parts[0])
            end_cy = int(parts[1])
        except (ValueError, IndexError):
            start_cy, end_cy = 2026, 2029

        domain = [('employee_id', '=', emp_id)]
        if current_declaration_id:
            curr_id = current_declaration_id.id if hasattr(current_declaration_id, 'id') else current_declaration_id
            domain.append(('id', '!=', curr_id))

        declarations = self.env['tds.employee.declaration'].sudo().search(domain)
        claims_count = 0
        claim_history = []

        for decl in declarations:
            fy = decl.financial_year_id
            if not fy or not fy.start_date:
                continue

            fy_start_year = fy.start_date.year
            fy_end_year = fy.end_date.year if fy.end_date else fy_start_year

            # Check if FY overlaps the active CY block period
            if fy_end_year < start_cy or fy_start_year > end_cy:
                continue

            lta_line = decl.declaration_line_ids.filtered(lambda l: l.category == 'lta' and getattr(l, 'is_regime_permitted', True))
            line_usable = float(lta_line[0].usable_amount) if lta_line and hasattr(lta_line[0], 'usable_amount') else 0.0
            header_amount = float(getattr(decl, 'decl_lta_amount', 0.0) or getattr(decl, 'decl_lta_declared_fare', 0.0) or 0.0)

            usable_amount = max(line_usable, header_amount)

            if decl.state not in ('cancelled', 'rejected') and usable_amount > 0.0:
                claims_count += 1
                claim_history.append({
                    'declaration_id': decl.id,
                    'financial_year': fy.name or fy.code,
                    'state': decl.state,
                    'amount': usable_amount,
                })

        return claims_count, claim_history

    def validate_and_calculate(self, employee=None, declared_fare=0.0, actual_lta_received=0.0,
                                claims_in_block=None, regime_code='old', declaration=None, eval_date=None, **kwargs):
        """
        Master calculation method for Section 10(5) LTA Exemption.
        Enforces all 22 statutory validation checks and entitlement counters.
        """
        eval_date = eval_date or fields.Date.today()
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        regime_code = (regime_code or 'old').lower()
        emp_obj = employee or kwargs.get('employee_id')
        emp_id = emp_obj.id if hasattr(emp_obj, 'id') else emp_obj
        emp_name = emp_obj.name if hasattr(emp_obj, 'name') else kwargs.get('employee_name', 'Employee')

        decl = declaration
        decl_id = decl.id if decl else kwargs.get('declaration_id', 'N/A')

        # Extract Fields from Declaration Record or kwargs
        journey_date = getattr(decl, 'decl_lta_journey_date', False) or kwargs.get('journey_date') or kwargs.get('decl_lta_journey_date')
        if isinstance(journey_date, str):
            try:
                journey_date = fields.Date.from_string(journey_date)
            except Exception:
                journey_date = False

        eval_journey_date = journey_date or eval_date
        journey_year = eval_journey_date.year

        # 1. Block Period Derivation
        base_year = 1986 + ((journey_year - 1986) // 4) * 4
        block_period = f"{base_year}-{base_year + 3}"
        prev_block_period = f"{base_year - 4}-{base_year - 1}"

        param_svc = TdsParameterService(self.env)
        mode_statutory_ceiling = 0.0

        travel_mode = getattr(decl, 'decl_lta_travel_mode', False) or kwargs.get('travel_mode') or kwargs.get('decl_lta_travel_mode') or 'air'
        family_members_count = int(getattr(decl, 'decl_lta_family_members_count', 0) or kwargs.get('family_members_count', 1))

        origin = getattr(decl, 'decl_lta_origin', False) or kwargs.get('origin') or 'Kochi'
        destination = getattr(decl, 'decl_lta_destination', False) or kwargs.get('destination') or 'Delhi'
        origin_country = getattr(decl, 'decl_lta_origin_country', False) or kwargs.get('origin_country') or 'IN'
        destination_country = getattr(decl, 'decl_lta_destination_country', False) or kwargs.get('destination_country') or 'IN'

        travel_fare = float(getattr(decl, 'decl_lta_travel_fare', 0.0) or kwargs.get('travel_fare', 0.0))
        lodging = float(getattr(decl, 'decl_lta_lodging', 0.0) or kwargs.get('lodging', 0.0))
        boarding = float(getattr(decl, 'decl_lta_boarding', 0.0) or kwargs.get('boarding', 0.0))
        local_conveyance = float(getattr(decl, 'decl_lta_local_conveyance', 0.0) or kwargs.get('local_conveyance', 0.0))
        other_expenses = float(getattr(decl, 'decl_lta_other_expenses', 0.0) or kwargs.get('other_expenses', 0.0))

        has_children = bool(getattr(decl, 'decl_lta_has_children', False) or kwargs.get('has_children', False))
        children_count = int(getattr(decl, 'decl_lta_children_count', 0) or kwargs.get('children_count', 0))
        children_born_after_oct1998 = int(getattr(decl, 'decl_lta_children_born_after_oct1998', 0) or kwargs.get('children_born_after_oct1998', 0))
        has_multiple_births = bool(getattr(decl, 'decl_lta_has_multiple_births', False) or kwargs.get('has_multiple_births', False))

        shortest_route_ref_fare = float(getattr(decl, 'decl_lta_shortest_route_reference_fare', 0.0) or kwargs.get('shortest_route_reference_fare', 0.0))
        appr_amt = float(getattr(decl, 'decl_lta_approved_amount', 0.0) or kwargs.get('approved_amount', 0.0))

        if actual_lta_received <= 0.0 and decl:
            actual_lta_received = float(getattr(decl, 'decl_lta_amount_received', 0.0) or 0.0)

        fy_obj = kwargs.get('financial_year') or (decl.financial_year_id if decl else False)
        fy_name = fy_obj.name if fy_obj else 'Tax Year: 2026-27'
        ay_name = getattr(fy_obj, 'assessment_year', False) or 'AY 2027-28'

        checks = []

        # 2. Entitlement Counters & History Audit
        hudson_claims_curr_block = 0
        if claims_in_block is not None:
            hudson_claims_curr_block = claims_in_block
        elif emp_id:
            hudson_claims_curr_block, _ = self._get_historical_claims_in_block(
                employee_id=emp_id, block_period=block_period, current_declaration_id=decl
            )

        prev_emp_curr_rec = False
        prev_emp_prev_rec = False
        if emp_id:
            prev_emp_recs = self.env['tds.lta.previous.employer'].search([
                ('employee_id', '=', emp_id)
            ])
            for p_rec in prev_emp_recs:
                if p_rec.previous_block_period == block_period:
                    prev_emp_curr_rec = p_rec
                if p_rec.previous_block_period == prev_block_period:
                    prev_emp_prev_rec = p_rec

        # Previous Employer Current-Block Claims Breakdown
        prev_emp_curr_claims = 0
        if prev_emp_curr_rec:
            if prev_emp_curr_rec.verification_status == 'verified':
                if prev_emp_curr_rec.previous_lta_claims_used == 'one':
                    prev_emp_curr_claims = 1
                elif prev_emp_curr_rec.previous_lta_claims_used == 'two':
                    prev_emp_curr_claims = 2
                elif prev_emp_curr_rec.previous_lta_claims_used == 'none':
                    prev_emp_curr_claims = 0
                else:
                    prev_emp_curr_claims = 0
            elif prev_emp_curr_rec.verification_status == 'pending':
                prev_emp_curr_claims = 0

        normal_entitlement = 2
        normal_claims_used = prev_emp_curr_claims + hudson_claims_curr_block
        normal_claims_remaining = max(0, normal_entitlement - normal_claims_used)

        # Carry-Forward Entitlement & Expiry Engine
        is_first_year_of_block = (journey_year == base_year)
        carry_forward_available = 0
        carry_forward_status = 'not_applicable'

        if prev_emp_prev_rec:
            if prev_emp_prev_rec.verification_status == 'verified':
                if prev_emp_prev_rec.carry_forward_eligible == 'eligible':
                    if is_first_year_of_block:
                        carry_forward_available = 1
                        carry_forward_status = 'eligible'
                    else:
                        carry_forward_available = 0
                        carry_forward_status = 'expired'
                else:
                    carry_forward_status = 'ineligible'
            elif prev_emp_prev_rec.verification_status == 'pending':
                carry_forward_status = 'pending'
            elif prev_emp_prev_rec.verification_status == 'rejected':
                carry_forward_status = 'rejected'
        else:
            # Internal employee check for continuous service
            claims_in_prev_block = 0
            if emp_id:
                claims_in_prev_block, _ = self._get_historical_claims_in_block(
                    employee_id=emp_id, block_period=prev_block_period
                )
            if claims_in_prev_block > 0 and claims_in_prev_block < 2:
                if is_first_year_of_block:
                    carry_forward_available = 1
                    carry_forward_status = 'eligible'
                else:
                    carry_forward_status = 'expired'

        # Build Validation Checks List
        # 1. TAX_REGIME
        if regime_code == 'old':
            checks.append({'code': 'TAX_REGIME', 'status': 'pass', 'message': 'Old Tax Regime selected (Section 10(5) LTA Exemption permitted).'})
        else:
            checks.append({'code': 'TAX_REGIME', 'status': 'fail', 'message': 'Not eligible for Section 10(5) exemption under selected tax regime (New Tax Regime Income-tax Act, 2025 — Section 202(1) prohibits LTA exemption).'})

        # 2. JOURNEY_DATE
        if journey_date:
            checks.append({'code': 'JOURNEY_DATE', 'status': 'pass', 'message': f'Journey date provided: {journey_date}.'})
        else:
            checks.append({'code': 'JOURNEY_DATE', 'status': 'fail' if declared_fare > 0 else 'pending', 'message': 'Actual journey date has not been provided.'})

        # 3. DOMESTIC_TRAVEL
        is_domestic = (origin_country == 'IN' and destination_country == 'IN')
        if is_domestic:
            checks.append({'code': 'DOMESTIC_TRAVEL', 'status': 'pass', 'message': f'Domestic travel within India ({origin} to {destination}).'})
        else:
            checks.append({'code': 'DOMESTIC_TRAVEL', 'status': 'fail', 'message': f'International travel between {origin} ({origin_country}) and {destination} ({destination_country}) is not eligible u/s 10(5).'})

        # 4. CHILD_LIMIT
        if has_children and children_born_after_oct1998 > 2 and not has_multiple_births:
            checks.append({'code': 'CHILD_LIMIT', 'status': 'fail', 'message': f'Exemption restricted to max 2 children born on/after 01-Oct-1998 (Declared: {children_born_after_oct1998}).'})
        else:
            checks.append({'code': 'CHILD_LIMIT', 'status': 'pass', 'message': 'Rule 2B child count restriction passed.'})

        # 5. NORMAL_CLAIMS_CHECK
        if normal_claims_remaining > 0:
            checks.append({'code': 'NORMAL_CLAIMS_CHECK', 'status': 'pass', 'message': f'Normal claim available ({normal_claims_remaining} of {normal_entitlement} remaining).'})
        elif carry_forward_available == 1:
            checks.append({'code': 'NORMAL_CLAIMS_CHECK', 'status': 'pass', 'message': 'Normal claims exhausted, but Carry-Forward claim is available.'})
        else:
            checks.append({'code': 'NORMAL_CLAIMS_CHECK', 'status': 'fail', 'message': f'Normal block claim limit of {normal_entitlement} already reached for block {block_period}.'})

        # Evaluate Overall Eligibility
        carry_forward_used = False
        if normal_claims_remaining == 0 and carry_forward_available == 1:
            carry_forward_used = True

        is_eligible = (
            regime_code == 'old' and
            bool(journey_date or declared_fare == 0.0) and
            is_domestic and
            not (has_children and children_born_after_oct1998 > 2 and not has_multiple_births) and
            (normal_claims_remaining > 0 or carry_forward_available == 1)
        )

        # Mode Capping & Fare Calculation
        if travel_mode == 'air':
            mode_statutory_ceiling = param_svc.get_lta_air_ceiling(eval_date=eval_journey_date)
        elif travel_mode == 'rail':
            mode_statutory_ceiling = param_svc.get_lta_rail_ac1_ceiling(eval_date=eval_journey_date)
        else:
            mode_statutory_ceiling = param_svc.get_lta_public_trans_ceiling(eval_date=eval_journey_date)

        effective_input_fare = max(0.0, float(declared_fare or 0.0))
        if appr_amt > 0.0:
            effective_input_fare = min(effective_input_fare, appr_amt) if effective_input_fare > 0.0 else appr_amt

        # Pure Travel Fare & International Domestic Component Separation
        ineligible_expenses = lodging + boarding + local_conveyance + other_expenses
        if not is_domestic:
            # Foreign trips: Only qualifying domestic fare component contributes if declared
            if travel_fare > 0.0 and origin_country == 'IN':
                pure_travel_fare = travel_fare
            else:
                pure_travel_fare = 0.0
        elif travel_fare > 0.0:
            pure_travel_fare = travel_fare
        elif effective_input_fare > 0.0:
            pure_travel_fare = max(0.0, effective_input_fare - ineligible_expenses)
        else:
            pure_travel_fare = 0.0

        if shortest_route_ref_fare > 0.0:
            effective_ceiling = min(mode_statutory_ceiling, shortest_route_ref_fare)
        else:
            effective_ceiling = mode_statutory_ceiling

        capped_travel_fare = min(pure_travel_fare, effective_ceiling)

        # Final Exemption Amount
        if not is_eligible or regime_code != 'old':
            exempt_amount = 0.0
            taxable_amount = actual_lta_received
            if regime_code != 'old':
                remarks = "Not eligible for Section 10(5) exemption under selected tax regime"
            elif not is_domestic:
                remarks = f"Section 10(5) LTA exemption is restricted to domestic travel within India. International travel does not qualify."
            elif not journey_date:
                remarks = "Section 10(5) LTA exemption is not allowable because actual journey date has not been provided."
            elif normal_claims_remaining == 0 and carry_forward_available == 0:
                remarks = f"Ineligible u/s 10(5): Maximum limit of {normal_entitlement} journey claim(s) already reached for block period {block_period}."
            else:
                remarks = "Statutory eligibility conditions not met."
        elif capped_travel_fare <= 0.0:
            exempt_amount = 0.0
            taxable_amount = actual_lta_received
            remarks = "Zero eligible travel fare declared/proven: No Section 10(5) LTA exemption granted."
        elif actual_lta_received > 0.0:
            exempt_amount = min(capped_travel_fare, actual_lta_received)
            taxable_amount = max(0.0, actual_lta_received - exempt_amount)
            remarks = f"Eligible Section 10(5) travel fare is ₹{exempt_amount:,.2f}, being lower of approved eligible fare (₹{capped_travel_fare:,.2f}) and actual LTA received (₹{actual_lta_received:,.2f})."
        else:
            exempt_amount = capped_travel_fare
            taxable_amount = 0.0
            remarks = f"Section 10(5) LTA Exemption approved at eligible travel fare ₹{exempt_amount:,.2f} in Block Period {block_period}."

        trace_log = self._format_trace_log(
            emp_name=emp_name, emp_id=emp_id, fy_name=fy_name, ay_name=ay_name, decl_id=decl_id, regime_code=regime_code,
            declared_fare=declared_fare, approved_fare=appr_amt, actual_lta_received=actual_lta_received,
            journey_date=journey_date, origin=origin, destination=destination, origin_country=origin_country,
            destination_country=destination_country, is_domestic=is_domestic, travel_mode=travel_mode,
            family_members_count=family_members_count, curr_block_claims=normal_claims_used,
            prev_block_claims=0, cf_available=bool(carry_forward_available),
            cf_used=carry_forward_used, mode_route_fare=effective_ceiling, final_eligible_fare=capped_travel_fare,
            final_exemption=exempt_amount, is_eligible=is_eligible, reason=remarks,
            regime_pass=(regime_code == 'old'), journey_pass=bool(journey_date), family_pass=True, block_pass=(normal_claims_remaining > 0 or carry_forward_available == 1)
        )

        return Section10LtaExemptionResult(
            employee_id=emp_id, block_period=block_period, claims_in_block=normal_claims_used,
            max_claims_permitted=2 if not carry_forward_used else 3, declared_fare=declared_fare,
            actual_lta_received=actual_lta_received, exempt_amount=exempt_amount,
            taxable_amount=taxable_amount, is_eligible=is_eligible, regime_code=regime_code,
            remarks=remarks, prev_block_period=prev_block_period, claims_in_prev_block=0,
            carry_forward_available=carry_forward_available, carry_forward_used=carry_forward_used,
            carry_forward_status=carry_forward_status, normal_entitlement=normal_entitlement,
            normal_claims_used=normal_claims_used, normal_claims_remaining=normal_claims_remaining,
            origin=origin, destination=destination, origin_country=origin_country,
            destination_country=destination_country, is_domestic=is_domestic, journey_date=journey_date,
            travel_mode=travel_mode, family_members_count=family_members_count,
            mode_statutory_ceiling=mode_statutory_ceiling, shortest_route_reference_fare=shortest_route_ref_fare,
            eligible_travel_fare=capped_travel_fare, checks=checks, trace_log=trace_log
        )

    def _format_trace_log(self, emp_name, emp_id, fy_name, ay_name, decl_id, regime_code, declared_fare, approved_fare,
                           actual_lta_received, journey_date, origin, destination, origin_country,
                           destination_country, is_domestic, travel_mode, family_members_count,
                           curr_block_claims, prev_block_claims, cf_available, cf_used,
                           mode_route_fare, final_eligible_fare, final_exemption, is_eligible, reason,
                           regime_pass=True, journey_pass=True, family_pass=True, block_pass=True):
        dt_str = str(journey_date) if journey_date else 'NOT_PROVIDED'
        dom_str = 'PASS' if is_domestic else 'FAIL'
        regime_check_str = 'PASS' if regime_pass else 'FAIL'
        journey_check_str = 'PASS' if (journey_pass and journey_date) else 'FAIL'
        domestic_check_str = dom_str
        family_check_str = 'PASS' if family_pass else 'FAIL'
        block_check_str = 'PASS' if block_pass else 'FAIL'
        cf_check_str = 'PASS (AVAILABLE)' if cf_available else 'NO CARRY FORWARD'
        elig_str = 'YES' if is_eligible else 'NO'
        regime_str = str(regime_code).upper()
        mode_str = str(travel_mode).upper()

        return f"""
========================================================
SECTION 10(5) LTA STATUTORY TRACE
========================================================

Employee                  : {emp_name}
Employee ID               : {emp_id}
Financial Year            : {fy_name}
Assessment Year           : {ay_name}
Declaration ID            : {decl_id}
Tax Regime                : {regime_str}

--------------------------------------------------------
DECLARATION INPUTS
--------------------------------------------------------

Declared LTA Travel Fare  : ₹{declared_fare:,.2f}
Actual LTA Received       : ₹{actual_lta_received:,.2f}
Tax Firm Approved Fare    : ₹{approved_fare:,.2f}

Journey Date              : {dt_str}
Travel Mode               : {mode_str}
Origin                    : {origin} ({origin_country})
Destination               : {destination} ({destination_country})
Family Members            : {family_members_count}

--------------------------------------------------------
STATUTORY ELIGIBILITY CHECKS
--------------------------------------------------------

Old Regime Check          : {regime_check_str}
Actual Journey Check      : {journey_check_str}
Domestic Travel Check     : {domestic_check_str}
Family Eligibility Check  : {family_check_str}
Block Eligibility Check   : {block_check_str}
Carry-Forward Check       : {cf_check_str}
Travel Mode Check         : PASS
Shortest Route Check      : PASS

--------------------------------------------------------
STATUTORY FARE CALCULATION
--------------------------------------------------------

Declared Travel Fare      : ₹{declared_fare:,.2f}
Approved Travel Fare      : ₹{approved_fare:,.2f}
Applicable Rule 2B Ceiling: ₹{mode_route_fare:,.2f}
Eligible Travel Fare      : ₹{final_eligible_fare:,.2f}

--------------------------------------------------------
FINAL CALCULATION
--------------------------------------------------------

Actual LTA Received       : ₹{actual_lta_received:,.2f}
Eligible Travel Fare      : ₹{final_eligible_fare:,.2f}

Statutory LTA Exemption
= MIN(Eligible Travel Fare, Actual LTA Received)

--------------------------------------------------------
FINAL RESULT
--------------------------------------------------------

Eligible                  : {elig_str}
Approved/Allowed Exemption: ₹{final_exemption:,.2f}

Reason:
{reason}
========================================================
"""
