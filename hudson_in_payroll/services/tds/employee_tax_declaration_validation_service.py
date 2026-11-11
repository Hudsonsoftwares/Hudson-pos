# -*- coding: utf-8 -*-
import logging
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService
from .section_80eea_eligibility_service import Section80EEAEligibilityService

_logger = logging.getLogger(__name__)


class EmployeeDeclarationValidationReport:
    """
    Data Transfer Object representing the result of an Employee Tax Declaration statutory audit.
    """
    def __init__(self, declaration_id, regime_code, is_compliant, total_declared, total_approved, line_results=None, error_messages=None):
        self.declaration_id = declaration_id
        self.regime_code = regime_code
        self.is_compliant = is_compliant
        self.total_declared = total_declared
        self.total_approved = total_approved
        self.line_results = line_results or []
        self.error_messages = error_messages or []


class EmployeeTaxDeclarationValidationService(BaseStatutoryService):
    """
    Centralized Validation Service for Employee Tax Declarations & Investment Proofs.
    Enforces regime compatibility (New vs Old) and resolves statutory deduction ceilings
    exclusively through TdsParameterService.
    """

    # Deduction categories strictly prohibited under New Tax Regime (Section 115BAC)
    NEW_REGIME_DISALLOWED_CATEGORIES = {
        '80c', 'nps_employee', '80ccd1b', '80d_self', '80d_parents', '80d_preventive',
        '80tta', '80ttb', '80dd', '24b', '80eea', 'hra', 'children_edu',
        'hostel', 'lta'
    }

    # Enterprise Mutually Exclusive Category Sets (Categories within each set cannot coexist in the same Financial Year)
    MUTUALLY_EXCLUSIVE_CATEGORY_SETS = [
        {
            'categories': {'80tta', '80ttb'},
            'rule_name': 'Section 80TTA / 80TTB Mutual Exclusivity',
            'conflict_remarks': "Statutory Conflict: Section 80TTA (Non-Senior Savings Interest) and Section 80TTB (Senior Citizen Deposit Interest) are mutually exclusive under Section 80TTA(2). An employee cannot claim both in the same Financial Year."
        }
    ]


    def _is_employee_senior_citizen_in_fy(self, employee, financial_year, eval_date=None):
        """
        Determines whether an employee attains age 60 at ANY time during the Financial Year
        under Indian Income Tax statutory rules (CBDT Circular No. 19/2015 & Circular No. 28/2018).

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param eval_date: Date (optional fallback)
        :return: Boolean (True if employee turns 60 by March 31 of the Financial Year)
        """
        if not employee or not employee.birthday:
            return False

        if financial_year and financial_year.end_date:
            fy_end = financial_year.end_date
        elif eval_date:
            fy_year = eval_date.year if eval_date.month >= 4 else eval_date.year - 1
            fy_end = fields.Date.from_string(f"{fy_year + 1}-03-31")
        else:
            today = fields.Date.today()
            fy_year = today.year if today.month >= 4 else today.year - 1
            fy_end = fields.Date.from_string(f"{fy_year + 1}-03-31")

        # Calendar-aware exact age determination at Financial Year end
        age_at_fy_end = relativedelta(fy_end, employee.birthday).years
        return age_at_fy_end >= 60

    def validate_declaration(self, declaration_record, regime_code=None, eval_date=None):

        """
        Validates an employee declaration header and all underlying declaration line items.

        :param declaration_record: tds.employee.declaration recordset
        :param regime_code: str ('old' or 'new') optional override
        :param eval_date: Date (optional)
        :return: EmployeeDeclarationValidationReport
        """
        declaration_record.ensure_one()
        tds_param_svc = TdsParameterService(self.env)
        eea_svc = Section80EEAEligibilityService(self.env)

        eval_date = eval_date or fields.Date.today()
        if not regime_code:
            regime_code = (declaration_record.regime_code or 'new').lower()
        else:
            regime_code = regime_code.lower()
        max_80c_ceiling = tds_param_svc.get_80c_limit(eval_date=eval_date)

        is_compliant = True
        line_results = []
        error_messages = []
        accumulated_80c = 0.0
        declared_categories = {l.category for l in declaration_record.declaration_line_ids}

        for line in declaration_record.declaration_line_ids:

            cat = line.category
            declared_val = line.declared_amount or 0.0

            # -----------------------------------------------------------------
            # 1. NEW REGIME & CONFIGURABLE CATEGORY PERMISSION ENFORCEMENT
            # -----------------------------------------------------------------
            from .tds_section_config_service import TdsSectionConfigService
            sec_config_svc = TdsSectionConfigService(self.env)

            if not sec_config_svc.is_category_permitted(cat, regime_code=regime_code, eval_date=eval_date):
                line.sudo().write({
                    'is_regime_permitted': False,
                    'validation_status': 'ineligible_regime',
                    'approved_amount': 0.0,
                    'validation_remarks': f"Category '{cat}' is not permitted or active under the selected {regime_code.upper()} Tax Regime.",
                })
                is_compliant = False
                error_messages.append(f"Line '{line.description}': {line.section_code} not permitted under {regime_code.upper()} Regime.")
                line_results.append({'line_id': line.id, 'category': cat, 'approved_amount': 0.0, 'status': 'ineligible_regime'})
                continue

            # -----------------------------------------------------------------
            # 2. OLD REGIME & SHARED CATEGORY STATUTORY VALIDATION
            # -----------------------------------------------------------------
            is_post_proof = declaration_record.state in ('proof_verified', 'approved')
            is_proof_phase = declaration_record.state in ('proof_under_review', 'proof_verified', 'approved')
            line.is_regime_permitted = True
            manual_appr = (
                float(getattr(line, 'tax_firm_approved_amount', 0.0) or 0.0)
                or float(getattr(line, 'approved_amount', 0.0) or 0.0)
                or float(getattr(line, 'verified_amount', 0.0) or 0.0)
            )
            has_manual_approval = is_proof_phase and manual_appr > 0.0
            base_claim = min(declared_val, manual_appr) if has_manual_approval else declared_val
            target_claim = base_claim if is_proof_phase else declared_val
            approved_val = target_claim
            val_status = 'valid'
            val_remarks = "Statutory deduction verified and valid."

            if cat in ('80c', 'nps_employee'):
                # Group ceiling enforcement across multiple 80C / 80CCD(1) lines
                remaining_80c_cap = max(0.0, max_80c_ceiling - accumulated_80c)
                if target_claim > remaining_80c_cap:
                    approved_val = remaining_80c_cap
                    val_status = 'exceeds_limit'
                    val_remarks = f"Section 80C / 80CCD(1) cumulative claim capped at statutory limit of ₹{max_80c_ceiling:,.2f}."
                else:
                    approved_val = target_claim
                accumulated_80c += approved_val

            elif cat == '80ccd1b':
                ceiling = tds_param_svc.get_80ccd1b_limit(eval_date=eval_date) or 50000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Section 80CCD(1B) additional NPS claim capped at statutory limit of ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == '80d_self':
                emp_is_senior = (
                    line.is_senior_citizen
                    or bool(getattr(declaration_record, 'decl_80d_self_is_senior', False))
                    or self._is_employee_senior_citizen_in_fy(
                        declaration_record.employee_id,
                        declaration_record.financial_year_id,
                        eval_date=eval_date
                    )
                )
                ceiling = tds_param_svc.get_80d_limit(is_senior=emp_is_senior, is_parents=False, eval_date=eval_date) or 25000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Section 80D (Self {'Senior Citizen' if emp_is_senior else 'Non-Senior'}) claim capped at statutory limit of ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == '80d_parents':
                parent_is_senior = (
                    line.is_senior_citizen
                    or bool(getattr(declaration_record, 'decl_80d_parents_is_senior', False))
                    or (declaration_record.employee_id and bool(getattr(declaration_record.employee_id, 'hds_in_decl_80d_parents_is_senior', False)))
                )
                ceiling = tds_param_svc.get_80d_limit(is_senior=parent_is_senior, is_parents=True, eval_date=eval_date) or 25000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Section 80D (Parents {'Senior Citizen' if parent_is_senior else 'Non-Senior'}) claim capped at statutory limit of ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == '80d_preventive':
                preventive_sublimit = tds_param_svc.get_parameter('80D_PREVENTIVE_CHECKUP_LIMIT', eval_date=eval_date) or 5000.0
                emp_is_senior = self._is_employee_senior_citizen_in_fy(
                    declaration_record.employee_id,
                    declaration_record.financial_year_id,
                    eval_date=eval_date
                )
                overall_self_ceiling = tds_param_svc.get_80d_limit(is_senior=emp_is_senior, is_parents=False, eval_date=eval_date) or 25000.0

                # 1. Self Medical Insurance lines already declared in this declaration
                self_insurance_lines = declaration_record.declaration_line_ids.filtered(lambda l: l.category == '80d_self')
                declared_self_ins = sum(
                    (float(l.tax_firm_approved_amount or 0.0) or float(l.approved_amount or 0.0) or float(l.declared_amount or 0.0))
                    if is_proof_phase else float(l.declared_amount or 0.0)
                    for l in self_insurance_lines
                )

                # 2. Apply preventive sub-limit (₹5,000 max)
                allowed_preventive_sublimit = min(target_claim, preventive_sublimit)

                # 3. Combined Self & Family bucket amount
                combined_bucket_raw = declared_self_ins + allowed_preventive_sublimit

                # 4. Apply overall Self & Family limit
                eligible_bucket_deduction = min(combined_bucket_raw, overall_self_ceiling)
                excess_bucket_amount = max(0.0, combined_bucket_raw - eligible_bucket_deduction)

                # 5. Determine approved amount for this preventive line
                remaining_overall_cap = max(0.0, overall_self_ceiling - declared_self_ins)
                approved_val = min(allowed_preventive_sublimit, remaining_overall_cap)

                if target_claim > preventive_sublimit or combined_bucket_raw > overall_self_ceiling:
                    val_status = 'exceeds_limit'
                    val_remarks = (
                        f"Section 80D Preventive Check-up capped at ₹{approved_val:,.2f} "
                        f"(Sub-limit: ₹{preventive_sublimit:,.2f}, Overall Self Ceiling: ₹{overall_self_ceiling:,.2f})."
                    )

                _logger.info(
                    "\n========================================\n"
                    "SECTION 80D BUCKET TRACE\n"
                    "========================================\n"
                    "Medical Insurance Amount    : ₹%s\n"
                    "Preventive Check-up Amount  : ₹%s\n"
                    "Combined Bucket Amount      : ₹%s\n"
                    "Preventive Sub-limit Applied: ₹%s\n"
                    "Overall 80D Limit Applied   : ₹%s\n"
                    "Eligible Deduction          : ₹%s\n"
                    "Excess Amount               : ₹%s\n"
                    "========================================",
                    f"{declared_self_ins:,.2f}", f"{target_claim:,.2f}", f"{combined_bucket_raw:,.2f}",
                    f"{preventive_sublimit:,.2f}", f"{overall_self_ceiling:,.2f}",
                    f"{eligible_bucket_deduction:,.2f}", f"{excess_bucket_amount:,.2f}"
                )

            elif cat == '80tta':
                is_emp_senior = self._is_employee_senior_citizen_in_fy(
                    declaration_record.employee_id,
                    declaration_record.financial_year_id,
                    eval_date=eval_date
                )
                if is_emp_senior:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = "Ineligible under Section 80TTA(2): Employee is a Senior Citizen (Age 60+). Senior Citizens are prohibited from claiming Section 80TTA and must claim Section 80TTB instead."
                    is_compliant = False
                    error_messages.append(f"Section 80TTA: {val_remarks}")
                elif '80ttb' in declared_categories:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = "Statutory Conflict: Section 80TTA and Section 80TTB are mutually exclusive under Section 80TTA(2). Simultaneous claims in the same Financial Year are prohibited."
                    is_compliant = False
                    error_messages.append(f"Section 80TTA / 80TTB: {val_remarks}")
                else:
                    ceiling = tds_param_svc.get_parameter('80TTA_MAX_LIMIT', eval_date=eval_date) or 10000.0
                    if target_claim > ceiling:
                        approved_val = ceiling
                        val_status = 'exceeds_limit'
                        val_remarks = f"Section 80TTA Savings Interest claim capped at statutory limit of ₹{ceiling:,.2f}."
                    else:
                        approved_val = target_claim

            elif cat == '80ttb':
                is_emp_senior = self._is_employee_senior_citizen_in_fy(
                    declaration_record.employee_id,
                    declaration_record.financial_year_id,
                    eval_date=eval_date
                )
                if not is_emp_senior:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = "Ineligible under Section 80TTB: Section 80TTB is restricted strictly to Senior Citizens (Age 60+). Non-Senior employees must claim Section 80TTA instead."
                    is_compliant = False
                    error_messages.append(f"Section 80TTB: {val_remarks}")
                elif '80tta' in declared_categories and is_emp_senior:
                    # If both exist and employee is senior, 80TTB is valid, but 80TTA above gets rejected
                    ceiling = tds_param_svc.get_parameter('80TTB_MAX_LIMIT', eval_date=eval_date) or 50000.0
                    if target_claim > ceiling:
                        approved_val = ceiling
                        val_status = 'exceeds_limit'
                        val_remarks = f"Section 80TTB Senior Citizen Deposit Interest claim capped at statutory limit of ₹{ceiling:,.2f}."
                    else:
                        approved_val = target_claim
                else:
                    ceiling = tds_param_svc.get_parameter('80TTB_MAX_LIMIT', eval_date=eval_date) or 50000.0
                    if target_claim > ceiling:
                        approved_val = ceiling
                        val_status = 'exceeds_limit'
                        val_remarks = f"Section 80TTB Senior Citizen Deposit Interest claim capped at statutory limit of ₹{ceiling:,.2f}."
                    else:
                        approved_val = target_claim

            elif cat == '80dd':
                from .section_80dd_deduction_service import Section80DDDeductionService
                dd_svc = Section80DDDeductionService(self.env)
                dd_res = dd_svc.validate_and_trace(line, eval_date=eval_date, regime_code=regime_code)
                if not dd_res.is_eligible and declared_val > 0.0:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = dd_res.remarks
                    is_compliant = False
                    error_messages.append(f"Section 80DD: {dd_res.remarks}")
                else:
                    approved_val = dd_res.allowed_deduction
                    val_status = 'valid' if dd_res.is_eligible else 'ineligible_regime'
                    val_remarks = dd_res.remarks

            elif cat == '80gg':
                from .section_80gg_deduction_service import Section80GGDeductionService
                gg_svc = Section80GGDeductionService(self.env)
                gg_res = gg_svc.validate_and_trace(line, eval_date=eval_date, regime_code=regime_code, employee=declaration_record.employee_id, financial_year=declaration_record.financial_year_id)
                if not gg_res.is_eligible and declared_val > 0.0:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = gg_res.remarks
                    is_compliant = False
                    error_messages.append(f"Section 80GG: {gg_res.rejection_reason}")
                else:
                    approved_val = gg_res.allowed_deduction
                    val_status = 'valid' if gg_res.is_eligible else 'ineligible_regime'
                    val_remarks = gg_res.remarks

            elif cat == '24b':
                ceiling = tds_param_svc.get_home_loan_interest_limit(eval_date=eval_date) or 200000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Section 24(b) Self-Occupied Housing Interest claim capped at ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == '80eea':
                if target_claim <= 0.0:
                    approved_val = 0.0
                    val_status = 'valid'
                    val_remarks = "No Section 80EEA deduction claimed."
                else:
                    # Validate against declaration_record if it has 80EEA fields, or search home_loans
                    res = None
                    if getattr(declaration_record, 'decl_80eea_loan_sanction_date', False):
                        res = eea_svc.validate_eligibility(declaration_record, eval_date=eval_date, claimed_interest_amount=target_claim)
                    else:
                        home_loans = self.env['tds.employee.home.loan'].search([
                            ('employee_id', '=', declaration_record.employee_id.id),
                            ('financial_year_id', '=', declaration_record.financial_year_id.id),
                            ('claimed_interest_amount', '>', 0)
                        ], limit=1)
                        if home_loans:
                            res = eea_svc.validate_eligibility(home_loans, eval_date=eval_date, claimed_interest_amount=target_claim)

                    if res and res.is_eligible:
                        approved_val = min(target_claim, res.allowed_deduction)
                        val_status = 'valid' if target_claim <= res.allowed_deduction else 'exceeds_limit'
                        val_remarks = res.remarks
                    elif res:
                        approved_val = 0.0
                        val_status = 'ineligible_regime'
                        val_remarks = res.remarks
                        is_compliant = False
                        error_messages.append(f"Section 80EEA: {res.remarks}")
                    else:
                        approved_val = 0.0
                        val_status = 'pending_proof'
                        val_remarks = "Section 80EEA Ineligible: No Housing Loan declaration record or 80EEA loan details found for employee in this FY."
                        is_compliant = False
                        error_messages.append(f"Section 80EEA: {val_remarks}")

            elif cat == 'hra':
                # Landlord PAN Validation Rule (CBDT Circular): Mandatory if annual rent exceeds ₹1,00,000 p.a.
                landlord_pan = getattr(line.declaration_id, 'decl_hra_landlord_pan', False) or getattr(line, 'landlord_pan', False)
                if target_claim > 100000.0 and not landlord_pan:
                    val_remarks = "Landlord PAN is mandatory under CBDT circulars for annual rent claims exceeding ₹1,00,000 p.a. Please provide Landlord PAN."
                    val_status = 'pending_proof'
                    approved_val = 100000.0
                else:
                    val_remarks = f"HRA Rent Declaration of ₹{target_claim:,.2f} verified. Exemption calculation delegated to Section10HraExemptionService during payslip computation."
                    val_status = 'valid'
                    approved_val = target_claim

            elif cat == 'children_edu':
                # Statutory Ceiling: ₹100 per month per child for max 2 children (₹2,400 p.a.)
                monthly_limit = tds_param_svc.get_parameter('CHILDREN_EDU_ALLOWANCE_MONTHLY', eval_date=eval_date) or 100.0
                ceiling = monthly_limit * 12 * 2  # Max 2 children
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Children Education Allowance exemption capped at statutory ceiling of ₹{ceiling:,.2f} (₹{monthly_limit:.0f}/month x 12 months x max 2 children)."
                else:
                    approved_val = target_claim

            elif cat == 'hostel':
                # Statutory Ceiling: ₹300 per month per child for max 2 children (₹7,200 p.a.)
                monthly_limit = tds_param_svc.get_parameter('HOSTEL_ALLOWANCE_MONTHLY', eval_date=eval_date) or 300.0
                ceiling = monthly_limit * 12 * 2  # Max 2 children
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Hostel Expenditure Allowance exemption capped at statutory ceiling of ₹{ceiling:,.2f} (₹{monthly_limit:.0f}/month x 12 months x max 2 children)."
                else:
                    approved_val = target_claim

            elif cat == 'lta':
                # Delegate to Section10LtaExemptionService
                from .section10_lta_exemption_service import Section10LtaExemptionService
                lta_svc = Section10LtaExemptionService(self.env)
                lta_res = lta_svc.validate_and_calculate(
                    employee_id=declaration_record.employee_id.id,
                    declared_fare=target_claim,
                    eval_date=eval_date
                )
                approved_val = lta_res.exempt_amount
                val_status = 'valid' if lta_res.is_eligible and target_claim == approved_val else ('exceeds_limit' if lta_res.is_eligible else 'ineligible_regime')
                val_remarks = lta_res.remarks

            elif cat == 'leave_encashment':
                ceiling = tds_param_svc.get_leave_encashment_ceiling(eval_date=eval_date) or 2500000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"Leave Encashment Exemption capped at statutory ceiling of ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == 'vrs':
                ceiling = tds_param_svc.get_parameter('VRS_EXEMPTION_CEILING', eval_date=eval_date) or 500000.0
                if target_claim > ceiling:
                    approved_val = ceiling
                    val_status = 'exceeds_limit'
                    val_remarks = f"VRS Compensation Exemption capped at statutory ceiling of ₹{ceiling:,.2f}."
                else:
                    approved_val = target_claim

            elif cat == '80g':
                eff_cat = getattr(line, 'decl_80g_category', False) or getattr(declaration_record, 'decl_80g_category', False)
                if (declared_val > 0.0 or (line.approved_amount or 0.0) > 0.0 or (line.tax_firm_approved_amount or 0.0) > 0.0) and not eff_cat:
                    is_compliant = False
                    val_status = 'pending_proof'
                    val_remarks = "Section 80G category is mandatory when donation amount is declared or approved."
                    error_messages.append(f"Line '{line.description}': 80G category is mandatory for declared/approved donation.")
                else:
                    from .section_80g_deduction_service import Section80GDeductionService
                    g_svc = Section80GDeductionService(self.env)
                    g_res = g_svc.validate_and_trace(line, eval_date=eval_date, regime_code=regime_code)
                    approved_val = g_res.allowed_deduction
                    if not g_res.is_eligible and declared_val > 0.0:
                        is_compliant = False
                        error_messages.append(f"Section 80G: {g_res.remarks}")
                    val_status = 'valid' if g_res.is_eligible else 'ineligible_regime'
                    val_remarks = g_res.remarks

            elif cat == '80e':
                from .section_80e_deduction_service import Section80EDeductionService
                e_svc = Section80EDeductionService(self.env)
                e_res = e_svc.validate_and_trace(line, eval_date=eval_date, regime_code=regime_code)
                if not e_res.is_eligible and declared_val > 0.0:
                    approved_val = 0.0
                    val_status = 'ineligible_regime'
                    val_remarks = e_res.remarks
                    is_compliant = False
                    error_messages.append(f"Section 80E: {e_res.remarks}")
                else:
                    approved_val = e_res.allowed_deduction
                    val_status = 'valid' if e_res.is_eligible else 'ineligible_regime'
                    val_remarks = e_res.remarks

            # Determine target approved_amount based on declaration lifecycle state
            existing_approved = float(line.approved_amount or 0.0)
            if is_post_proof:
                final_approved = approved_val
                action_str = "APPROVED_AMOUNT_PERSISTED"
                reason_str = "HR proof verification completed; approved amount persisted."
            elif declaration_record.state in ('proof_under_review', 'proof_submitted'):
                if has_manual_approval:
                    final_approved = approved_val
                    action_str = "PROOF_REVIEW_APPROVED_SAVED"
                    reason_str = "Proof review in progress; manually entered approved amount validated and preserved."
                else:
                    final_approved = 0.0
                    action_str = "AWAITING_PROOF_REVIEW"
                    reason_str = "Proof under review; awaiting HR/tax firm verification input."
            else:
                final_approved = approved_val
                action_str = "PRE_PROOF_CAPPED_VALIDATION"
                reason_str = "Pre-proof validation: statutory capping evaluated."

            _logger.warning(
                "\n=========================================================\n"
                "TDS APPROVAL LIFECYCLE TRACE\n"
                "=========================================================\n"
                "Declaration ID       : %s\n"
                "Section              : %s\n"
                "State                : %s\n"
                "Eligible Amount      : INR %s\n"
                "Existing Approved    : INR %s\n"
                "Final Approved       : INR %s\n"
                "Action               : %s\n"
                "Reason               : %s\n"
                "=========================================================",
                declaration_record.id, line.section_code or line.category, declaration_record.state,
                f"{approved_val:,.2f}", f"{existing_approved:,.2f}", f"{final_approved:,.2f}",
                action_str, reason_str
            )

            line.sudo().write({
                'is_regime_permitted': True,
                'approved_amount': final_approved,
                'tax_firm_approved_amount': final_approved,
                'validation_status': val_status,
                'validation_remarks': val_remarks,
            })
            line_results.append({'line_id': line.id, 'category': cat, 'approved_amount': final_approved, 'status': val_status})

        # Validate header-level 80E if declared without lines
        if '80e' not in declared_categories and (declaration_record.decl_80e_interest or 0.0) > 0.0:
            from .section_80e_deduction_service import Section80EDeductionService
            e_svc = Section80EDeductionService(self.env)
            e_res = e_svc.validate_and_trace(declaration_record, eval_date=eval_date, regime_code=regime_code)
            if not e_res.is_eligible:
                is_compliant = False
                error_messages.append(f"Section 80E: {e_res.remarks}")

        # Validate header-level 80DD if declared without lines
        if '80dd' not in declared_categories and (declaration_record.decl_80dd_disability_exists or declaration_record.decl_80dd_dependent_name or (declaration_record.decl_80dd_amount or 0.0) > 0.0):
            from .section_80dd_deduction_service import Section80DDDeductionService
            dd_svc = Section80DDDeductionService(self.env)
            dd_res = dd_svc.validate_and_trace(declaration_record, eval_date=eval_date, regime_code=regime_code)
            if not dd_res.is_eligible:
                is_compliant = False
                error_messages.append(f"Section 80DD: {dd_res.remarks}")

        # Validate header-level 80GG if declared without lines
        if '80gg' not in declared_categories and ((declaration_record.decl_80gg_rent or 0.0) > 0.0 or declaration_record.decl_80gg_form_10ba_filed):
            from .section_80gg_deduction_service import Section80GGDeductionService
            gg_svc = Section80GGDeductionService(self.env)
            gg_res = gg_svc.validate_and_trace(declaration_record, eval_date=eval_date, regime_code=regime_code, employee=declaration_record.employee_id, financial_year=declaration_record.financial_year_id)
            if not gg_res.is_eligible and (declaration_record.decl_80gg_rent or 0.0) > 0.0:
                is_compliant = False
                error_messages.append(f"Section 80GG: {gg_res.rejection_reason}")

        declaration_record._compute_totals()

        return EmployeeDeclarationValidationReport(
            declaration_id=declaration_record.id,
            regime_code=regime_code,
            is_compliant=is_compliant,
            total_declared=declaration_record.total_declared_amount,
            total_approved=declaration_record.total_approved_amount,
            line_results=line_results,
            error_messages=error_messages
        )
