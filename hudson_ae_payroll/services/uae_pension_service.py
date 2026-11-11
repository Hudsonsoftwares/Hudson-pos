# -*- coding: utf-8 -*-
import logging
from odoo import fields

_logger = logging.getLogger(__name__)


class UAEPensionCalculationService:
    """
    Centralized UAE Pension & Social Insurance Calculation Service.
    Phase 1: UAE Nationals only.

    Evaluation Pipeline:
    1. Check UAE National eligibility (uae_employee_category == 'uae_national')
    2. Resolve Pension Authority (Precedence: Employee Jur -> Co Jur -> Employee Emirate -> Co Emirate)
    3. Fresh Company Authority Enablement Check (company.is_pension_authority_enabled)
    4. Resolve Active Pension Scheme (employee scheme or default active company scheme)
    5. Shared Contribution Base Resolver (rules with hds_ae_include_in_gpssa_base or BASIC+HRA/contract wage)
    6. Rate Parameter Resolver (hr.rule.parameter.resolve_uae_pension_rates)
    7. Calculate Employee & Employer Contributions
    """

    def __init__(self, env):
        self.env = env

    def calculate_pension(self, employee, payslip=None, contract=None, localdict=None, eval_date=None):
        """
        Master calculation entry point consumed by salary rules SIEC and SICC.
        Returns a standardized dictionary with explicit status:
          - ELIGIBLE
          - NOT_UAE_NATIONAL
          - NO_PENSION_AUTHORITY
          - AUTHORITY_NOT_ENABLED_AT_COMPANY
          - NO_ACTIVE_SCHEME
          - NO_CONTRIBUTION_BASE
        """
        # 0. Check transient cache in localdict to guarantee single-execution per payslip run
        if localdict is not None and isinstance(localdict, dict) and 'uae_pension_result' in localdict:
            cached_res = localdict['uae_pension_result']
            if cached_res and isinstance(cached_res, dict):
                _logger.info(
                    "[UAE_PENSION_TRACE] [CACHE HIT] Reusing cached pension calculation for employee %s (ID: %s) | Status: %s | EE Contrib: %.2f | ER Contrib: %.2f",
                    employee.name if employee else 'N/A',
                    employee.id if employee else 'N/A',
                    cached_res.get('status'),
                    cached_res.get('employee_contribution', 0.0),
                    cached_res.get('employer_contribution', 0.0)
                )
                return cached_res

        if not employee:
            _logger.warning("[UAE_PENSION_TRACE] [INIT] calculate_pension called without an employee record.")
            return self._empty_result('NOT_UAE_NATIONAL', reason="No employee specified.")

        emp_name = employee.name or f"Employee#{employee.id}"
        company = employee.company_id or (payslip.company_id if payslip else self.env.company)
        calculation_date = eval_date or (payslip.date_to if payslip else fields.Date.today())

        _logger.info(
            "[UAE_PENSION_TRACE] ==================== START PENSION CALCULATION ===================="
        )
        _logger.info(
            "[UAE_PENSION_TRACE] Employee: %s (ID: %s) | Company: %s | Calculation Date: %s",
            emp_name, employee.id, company.name if company else 'None', calculation_date
        )

        # ---------------------------------------------------------------------
        # STEP 1: Check UAE National Eligibility (Phase 1: UAE Nationals only)
        # ---------------------------------------------------------------------
        category = getattr(employee, 'uae_employee_category', False)
        # Fallback to nationality if category not computed
        if not category and employee.country_id:
            country_code = (employee.country_id.code or '').upper()
            if country_code in ('AE', 'ARE'):
                category = 'uae_national'

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 1: UAE National Eligibility] Employee category: '%s' | Country: '%s'",
            category, employee.country_id.code if employee.country_id else 'None'
        )

        if category != 'uae_national':
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 1: Ineligible] Employee '%s' is NOT a UAE National (category: '%s'). "
                "Phase 1 applies to UAE Nationals only -> Status: NOT_UAE_NATIONAL (Contribution: 0.0)",
                emp_name, category
            )
            res = self._empty_result('NOT_UAE_NATIONAL', reason=f"Employee category is {category}; UAE Nationals only in Phase 1.")
            self._cache_result(localdict, res)
            _logger.info("[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (INELIGIBLE) ====================")
            return res

        _logger.info("[UAE_PENSION_TRACE] [STEP 1: Passed] Verified employee '%s' is UAE National.", emp_name)

        # ---------------------------------------------------------------------
        # STEP 2: Resolve Pension Authority (Strict 4-Tier Precedence)
        # 1. Employee Applicable Jurisdiction
        # 2. Company Applicable Jurisdiction
        # 3. Employee Applicable Emirate
        # 4. Company Emirate
        # ---------------------------------------------------------------------
        authority, matched_tier = self._resolve_authority_with_tier(employee, company)
        if not authority:
            _logger.warning(
                "[UAE_PENSION_TRACE] [STEP 2: Failed] No Pension Authority could be resolved for employee %s -> Status: NO_PENSION_AUTHORITY",
                emp_name
            )
            res = self._empty_result('NO_PENSION_AUTHORITY', reason="Unable to resolve governing Pension Authority.")
            self._cache_result(localdict, res)
            _logger.info("[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (NO AUTHORITY) ====================")
            return res

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 2: Passed] Resolved Authority: '%s' (Code: %s) via %s",
            authority.name, authority.code, matched_tier
        )

        # ---------------------------------------------------------------------
        # STEP 3: Fresh Company Authority Enablement Check
        # (Always check current company settings dynamically; never rely on stale status)
        # ---------------------------------------------------------------------
        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 3: Fresh Company Check] Checking if authority '%s' is currently enabled on company '%s'...",
            authority.code or authority.name, company.name
        )
        is_enabled = False
        if hasattr(company, 'is_pension_authority_enabled'):
            is_enabled = company.is_pension_authority_enabled(authority)
        else:
            auth_code = (authority.code or '').upper()
            if auth_code == 'GPSSA':
                is_enabled = getattr(company, 'hds_ae_enable_gpssa', False)
            elif auth_code == 'ADPF':
                is_enabled = getattr(company, 'hds_ae_enable_adpf', False)

        if not is_enabled:
            _logger.warning(
                "[UAE_PENSION_TRACE] [STEP 3: Failed] Fresh check failed: Authority '%s' is NOT enabled on company '%s' -> Status: AUTHORITY_NOT_ENABLED_AT_COMPANY",
                authority.code or authority.name, company.name
            )
            res = self._empty_result(
                'AUTHORITY_NOT_ENABLED_AT_COMPANY',
                authority=authority,
                reason=f"Pension Authority '{authority.code}' is not enabled on company '{company.name}'."
            )
            self._cache_result(localdict, res)
            _logger.info("[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (NOT ENABLED) ====================")
            return res

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 3: Passed] Authority '%s' is ENABLED on company '%s'.",
            authority.code or authority.name, company.name
        )

        # ---------------------------------------------------------------------
        # STEP 4: Resolve Active Pension Scheme
        # ---------------------------------------------------------------------
        scheme, scheme_tier = self._resolve_active_scheme_with_tier(employee, company, authority)
        if not scheme:
            _logger.warning(
                "[UAE_PENSION_TRACE] [STEP 4: Failed] No active Pension Scheme resolved for employee %s -> Status: NO_ACTIVE_SCHEME",
                emp_name
            )
            res = self._empty_result(
                'NO_ACTIVE_SCHEME',
                authority=authority,
                reason=f"No active Pension Scheme configured or enabled for authority '{authority.code}'."
            )
            self._cache_result(localdict, res)
            _logger.info("[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (NO ACTIVE SCHEME) ====================")
            return res

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 4: Passed] Resolved Active Scheme: '%s' (Code: %s) via %s",
            scheme.name, scheme.code, scheme_tier
        )

        # ---------------------------------------------------------------------
        # STEP 5: Shared Contribution Base Resolver
        # ---------------------------------------------------------------------
        contributory_wage = self._resolve_contribution_base(
            employee=employee,
            payslip=payslip,
            contract=contract,
            localdict=localdict
        )

        if contributory_wage <= 0.0:
            _logger.warning(
                "[UAE_PENSION_TRACE] [STEP 5: Failed] Contributory wage base is %.2f <= 0 for employee %s -> Status: NO_CONTRIBUTION_BASE",
                contributory_wage, emp_name
            )
            res = self._empty_result(
                'NO_CONTRIBUTION_BASE',
                authority=authority,
                scheme=scheme,
                reason="Calculated contributory wage base is zero or negative."
            )
            self._cache_result(localdict, res)
            _logger.info("[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (NO CONTRIBUTION BASE) ====================")
            return res

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 5: Passed] Resolved Contributory Base: %.2f AED",
            contributory_wage
        )

        # ---------------------------------------------------------------------
        # STEP 6: Rate Parameter Resolver (hr.rule.parameter)
        # ---------------------------------------------------------------------
        rates = self._resolve_rates_and_limits(authority, scheme, calculation_date)
        ee_rate = rates.get('employee_rate', 0.0)
        er_rate = rates.get('employer_rate', 0.0)
        max_wage = rates.get('max_wage_limit', 0.0)
        min_wage = rates.get('min_wage_limit', 0.0)

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 6: Passed] Dynamic Rates from hr.rule.parameter: "
            "EE Rate=%.2f%% (%.4f) | ER Rate=%.2f%% (%.4f) | Min Wage=%.2f AED | Max Wage=%.2f AED",
            ee_rate * 100, ee_rate, er_rate * 100, er_rate, min_wage, max_wage
        )

        # ---------------------------------------------------------------------
        # STEP 7: Calculate Employee & Employer Contributions
        # ---------------------------------------------------------------------
        capped_wage = contributory_wage
        if max_wage > 0.0 and capped_wage > max_wage:
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 7: Wage Capped] Base %.2f AED exceeds statutory ceiling %.2f AED -> Capped to %.2f AED",
                contributory_wage, max_wage, max_wage
            )
            capped_wage = max_wage

        if min_wage > 0.0 and capped_wage < min_wage:
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 7: Wage Floored] Base %.2f AED below statutory floor %.2f AED -> Raised to %.2f AED",
                capped_wage, min_wage, min_wage
            )
            capped_wage = min_wage

        ee_contrib = round(capped_wage * ee_rate, 2)
        er_contrib = round(capped_wage * er_rate, 2)

        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 7: Calculation] "
            "Employee (SIEC): %.2f * %.4f = %.2f AED | Employer (SICC): %.2f * %.4f = %.2f AED",
            capped_wage, ee_rate, ee_contrib, capped_wage, er_rate, er_contrib
        )
        _logger.info(
            "[UAE_PENSION_TRACE] [STEP 7: COMPLETE] ELIGIBLE for %s | Authority: %s | Scheme: %s | "
            "Base: %.2f (Effective: %.2f) | EE Contrib: %.2f AED | ER Contrib: %.2f AED",
            emp_name, authority.code, scheme.code, contributory_wage, capped_wage, ee_contrib, er_contrib
        )
        _logger.info(
            "[UAE_PENSION_TRACE] ==================== END PENSION CALCULATION (SUCCESS) ===================="
        )

        res = {
            'status': 'ELIGIBLE',
            'authority': authority,
            'authority_code': authority.code,
            'authority_name': authority.name,
            'scheme': scheme,
            'scheme_code': scheme.code,
            'scheme_name': scheme.name,
            'contributory_wage': contributory_wage,
            'capped_wage': capped_wage,
            'employee_rate': ee_rate,
            'employer_rate': er_rate,
            'employee_contribution': ee_contrib,
            'employer_contribution': er_contrib,
            'reason': 'Eligible UAE National statutory pension contribution calculated successfully.'
        }
        self._cache_result(localdict, res)
        return res

    # -------------------------------------------------------------------------
    # HELPER RESOLVER METHODS
    # -------------------------------------------------------------------------

    def _resolve_authority_with_tier(self, employee, company):
        """
        Resolve Pension Authority using strict 4-tier precedence:
        1. Employee Applicable Jurisdiction.pension_authority_id
        2. Company Applicable Jurisdiction.pension_authority_id
        3. Employee Applicable Emirate.pension_authority_id
        4. Company Emirate.pension_authority_id
        """
        # 1. Employee Jurisdiction
        emp_jur = getattr(employee, 'uae_jurisdiction_id', False)
        if emp_jur and getattr(emp_jur, 'pension_authority_id', False):
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 2: Tier 1 Matched] Employee Jurisdiction '%s' -> Authority '%s'",
                emp_jur.name, emp_jur.pension_authority_id.code
            )
            return emp_jur.pension_authority_id, f"Tier 1 (Employee Jurisdiction '{emp_jur.name}')"

        # 2. Company Jurisdiction
        comp_jur = getattr(company, 'uae_jurisdiction_id', False)
        if comp_jur and getattr(comp_jur, 'pension_authority_id', False):
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 2: Tier 2 Matched] Company Jurisdiction '%s' -> Authority '%s'",
                comp_jur.name, comp_jur.pension_authority_id.code
            )
            return comp_jur.pension_authority_id, f"Tier 2 (Company Jurisdiction '{comp_jur.name}')"

        # 3. Employee Emirate
        emp_emirate = getattr(employee, 'uae_emirate_id', False)
        if emp_emirate and getattr(emp_emirate, 'pension_authority_id', False):
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 2: Tier 3 Matched] Employee Emirate '%s' -> Authority '%s'",
                emp_emirate.name, emp_emirate.pension_authority_id.code
            )
            return emp_emirate.pension_authority_id, f"Tier 3 (Employee Emirate '{emp_emirate.name}')"

        # 4. Company Emirate
        comp_emirate = getattr(company, 'uae_emirate_id', False)
        if comp_emirate and getattr(comp_emirate, 'pension_authority_id', False):
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 2: Tier 4 Matched] Company Emirate '%s' -> Authority '%s'",
                comp_emirate.name, comp_emirate.pension_authority_id.code
            )
            return comp_emirate.pension_authority_id, f"Tier 4 (Company Emirate '{comp_emirate.name}')"

        # Fallback to direct computed field on employee if set
        if getattr(employee, 'uae_pension_authority_id', False):
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 2: Fallback Matched] Employee Computed Authority -> '%s'",
                employee.uae_pension_authority_id.code
            )
            return employee.uae_pension_authority_id, "Fallback (Employee uae_pension_authority_id)"

        return False, "No match"

    def _resolve_authority(self, employee, company):
        auth, _tier = self._resolve_authority_with_tier(employee, company)
        return auth

    def _resolve_active_scheme_with_tier(self, employee, company, authority):
        """
        Resolve active scheme applicable to employee and authority.
        """
        # 1. Direct employee assigned scheme (must be active)
        emp_scheme = getattr(employee, 'uae_pension_scheme_id', False)
        if emp_scheme:
            if emp_scheme.active and (not emp_scheme.pension_authority_ids or authority in emp_scheme.pension_authority_ids):
                _logger.info(
                    "[UAE_PENSION_TRACE] [STEP 4: Tier 1 Matched] Employee assigned scheme '%s' (Active: True)",
                    emp_scheme.name
                )
                return emp_scheme, f"Tier 1 (Employee Scheme '{emp_scheme.name}')"
            else:
                _logger.info(
                    "[UAE_PENSION_TRACE] [STEP 4: Tier 1 Skipped] Employee assigned scheme '%s' is inactive or does not match authority '%s'",
                    emp_scheme.name, authority.code
                )

        # 2. Scheme enabled on company matching authority
        if company and hasattr(company, 'uae_pension_scheme_ids') and company.uae_pension_scheme_ids:
            for s in company.uae_pension_scheme_ids:
                if s.active and (not s.pension_authority_ids or authority in s.pension_authority_ids):
                    _logger.info(
                        "[UAE_PENSION_TRACE] [STEP 4: Tier 2 Matched] Company enabled scheme '%s'",
                        s.name
                    )
                    return s, f"Tier 2 (Company Scheme '{s.name}')"

        # 3. Active scheme in master data matching authority
        Scheme = self.env['uae.pension.scheme']
        active_schemes = Scheme.search([
            ('active', '=', True),
            ('|'), ('pension_authority_ids', '=', False), ('pension_authority_ids', 'in', [authority.id])
        ], order='sequence asc, id asc')
        if active_schemes:
            new_law = active_schemes.filtered(lambda s: s.code == 'new_law')
            chosen = new_law[0] if new_law else active_schemes[0]
            _logger.info(
                "[UAE_PENSION_TRACE] [STEP 4: Tier 3 Matched] Master data active scheme '%s' (Code: %s)",
                chosen.name, chosen.code
            )
            return chosen, f"Tier 3 (Master Data Default '{chosen.name}')"

        return False, "No match"

    def _resolve_active_scheme(self, employee, company, authority):
        scheme, _tier = self._resolve_active_scheme_with_tier(employee, company, authority)
        return scheme

    def _resolve_contribution_base(self, employee, payslip=None, contract=None, localdict=None):
        """
        Shared contribution-base resolver:
        1. Check computed rules in payslip/localdict that have hds_ae_include_in_gpssa_base = True.
        2. If none, check standard contributory earning codes in localdict: BASIC + HRA / HOUALLOWINP.
        3. If still zero, fallback to contract wage.
        """
        contributory_wage = 0.0
        used_flag_rules = False

        # Case A: Evaluated within payslip execution context
        if localdict is not None and isinstance(localdict, dict):
            rule_model = self.env['hr.salary.rule']
            base_rules = rule_model.search([('hds_ae_include_in_gpssa_base', '=', True)])
            if base_rules:
                for rule in base_rules:
                    val = localdict.get(rule.code, 0.0)
                    if isinstance(val, (int, float)) and val > 0:
                        contributory_wage += float(val)
                        used_flag_rules = True
                        _logger.info(
                            "[UAE_PENSION_TRACE] [STEP 5: Base Rule] Rule '%s' (code: %s, flagged for base) = %.2f AED",
                            rule.name, rule.code, val
                        )

            # If no flagged rules produced an amount, check standard contributory components
            if not used_flag_rules:
                basic = localdict.get('BASIC', 0.0)
                if isinstance(basic, (int, float)) and basic > 0:
                    contributory_wage += float(basic)
                    _logger.info("[UAE_PENSION_TRACE] [STEP 5: Base Rule] Component 'BASIC' = %.2f AED", basic)
                hra = localdict.get('HRA', 0.0)
                if isinstance(hra, (int, float)) and hra > 0:
                    contributory_wage += float(hra)
                    _logger.info("[UAE_PENSION_TRACE] [STEP 5: Base Rule] Component 'HRA' = %.2f AED", hra)
                hou = localdict.get('HOUALLOWINP', 0.0)
                if isinstance(hou, (int, float)) and hou > 0:
                    contributory_wage += float(hou)
                    _logger.info("[UAE_PENSION_TRACE] [STEP 5: Base Rule] Component 'HOUALLOWINP' = %.2f AED", hou)

        # Case B: Fallback to payslip line records if available
        if contributory_wage <= 0.0 and payslip and hasattr(payslip, 'line_ids') and payslip.line_ids:
            for line in payslip.line_ids:
                if line.salary_rule_id and line.salary_rule_id.hds_ae_include_in_gpssa_base:
                    contributory_wage += float(line.total or 0.0)
                    used_flag_rules = True
                    _logger.info(
                        "[UAE_PENSION_TRACE] [STEP 5: Payslip Line] Line '%s' (code: %s, flagged) = %.2f AED",
                        line.name, line.code, line.total
                    )

            if not used_flag_rules:
                for line in payslip.line_ids:
                    if line.code in ('BASIC', 'HRA', 'HOUALLOWINP') and line.total:
                        contributory_wage += float(line.total or 0.0)
                        _logger.info(
                            "[UAE_PENSION_TRACE] [STEP 5: Payslip Line] Line '%s' (code: %s) = %.2f AED",
                            line.name, line.code, line.total
                        )

        # Case C: Fallback to contract wage
        if contributory_wage <= 0.0:
            target_contract = contract or (payslip.contract_id if payslip else False) or (
                employee.contract_id if hasattr(employee, 'contract_id') else False
            )
            if target_contract and getattr(target_contract, 'wage', False):
                contributory_wage = float(target_contract.wage or 0.0)
                _logger.info(
                    "[UAE_PENSION_TRACE] [STEP 5: Contract Fallback] Wage from contract = %.2f AED",
                    contributory_wage
                )

        return float(contributory_wage)

    def _resolve_rates_and_limits(self, authority, scheme, calculation_date):
        """
        Dynamically resolves statutory rates and wage limits using hr.rule.parameter.
        Zero hardcoded rates.
        """
        param_model = self.env['hr.rule.parameter']
        authority_code = (authority.code or '').lower()
        scheme_code = scheme.code if scheme else None

        if hasattr(param_model, 'resolve_uae_pension_rates'):
            return param_model.resolve_uae_pension_rates(
                authority_code=authority_code,
                scheme_code=scheme_code,
                date=calculation_date,
                as_decimal=True
            )

        # Resilient fallback if method not yet reloaded
        prefix = 'ADPF' if 'adpf' in authority_code else 'GPSSA'
        ee = param_model.get_uae_pension_parameter(f'{prefix}_EE_RATE', scheme_code=scheme_code, date=calculation_date, as_decimal=True)
        er = param_model.get_uae_pension_parameter(f'{prefix}_ER_RATE', scheme_code=scheme_code, date=calculation_date, as_decimal=True)
        max_w = param_model.get_uae_pension_parameter(f'{prefix}_MAX_WAGE', scheme_code=scheme_code, date=calculation_date)
        min_w = param_model.get_uae_pension_parameter(f'{prefix}_MIN_WAGE', scheme_code=scheme_code, date=calculation_date)
        return {
            'employee_rate': ee,
            'employer_rate': er,
            'max_wage_limit': max_w,
            'min_wage_limit': min_w,
        }

    def _empty_result(self, status, authority=None, scheme=None, reason=''):
        """Construct zero-contribution response for ineligibility or configuration gaps."""
        return {
            'status': status,
            'authority': authority,
            'authority_code': authority.code if authority else None,
            'authority_name': authority.name if authority else None,
            'scheme': scheme,
            'scheme_code': scheme.code if scheme else None,
            'scheme_name': scheme.name if scheme else None,
            'contributory_wage': 0.0,
            'capped_wage': 0.0,
            'employee_rate': 0.0,
            'employer_rate': 0.0,
            'employee_contribution': 0.0,
            'employer_contribution': 0.0,
            'reason': reason,
        }

    def _cache_result(self, localdict, result):
        """Save calculation in localdict cache so subsequent rules do not repeat work."""
        if localdict is not None and isinstance(localdict, dict):
            localdict['uae_pension_result'] = result
