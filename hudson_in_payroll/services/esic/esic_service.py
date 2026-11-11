# -*- coding: utf-8 -*-
import logging
from ..audit.audit_service import StatutoryAuditSession
from .validator import ESICValidator
from .employee_calculator import ESICEmployeeCalculator
from .employer_calculator import ESICEmployerCalculator

_logger = logging.getLogger(__name__)


class ESICService:
    """
    Unified Pure Python Facade for ESIC Domain Services with Statutory Audit Integration.
    Instantiated by HrPayslip with `env` and optional `localdict`. Zero ORM inheritance overhead.
    Follows exact same architecture as EPFService.
    """

    def __init__(self, env, localdict=None):
        self.env = env
        self.localdict = localdict
        self.validator = ESICValidator(env)
        self.employee_calc = ESICEmployeeCalculator(env, self.validator)
        self.employer_calc = ESICEmployerCalculator(env, self.validator)

    def _get_gross_wage(self, payslip=None):
        """Extracts gross wage from localdict ESIC_WAGE, localdict categories, evaluated rule dict, or active contract wage fallback."""
        ld = self.localdict or {}

        # 1. Single Source of Truth: Reuse previously computed ESIC_WAGE in localdict if available
        if 'ESIC_WAGE' in ld:
            return float(ld['ESIC_WAGE'] or 0.0)

        # Check if payslip has 0 paid days due to full unpaid leave / LOP
        ps = payslip or (ld.get('payslip_record') if hasattr(ld.get('payslip_record'), 'worked_days_line_ids') else False)
        if ps and hasattr(ps, 'worked_days_line_ids') and ps.worked_days_line_ids:
            unpaid_codes = ('UNPAID', 'ABSENT', 'LEAVE_UNPAID', 'LOP', 'SHORTAGE')
            paid_lines = ps.worked_days_line_ids.filtered(lambda l: (l.code or '').upper() not in unpaid_codes and (l.number_of_days or 0.0) > 0)
            if not paid_lines and any((l.code or '').upper() in unpaid_codes for l in ps.worked_days_line_ids):
                return 0.0

        # 2. Extract evaluated gross wage from localdict
        gross_wage = None
        if 'GROSS' in ld and isinstance(ld['GROSS'], (int, float)):
            gross_wage = float(ld['GROSS'])
        elif ld.get('categories') and hasattr(ld['categories'], 'GROSS'):
            gross_wage = float(getattr(ld['categories'], 'GROSS', 0.0) or 0.0)
        elif ld:
            summed = 0.0
            found_earning = False
            for k, v in ld.items():
                if isinstance(v, (int, float)) and k not in ('result', 'result_qty', 'result_rate', 'NET', 'ESIC_EE', 'ESIC_ER', 'EPF_EE', 'EPF_ER', 'PT', 'LWF', 'ESIC_WAGE', 'PF_WAGE', 'GROSS', 'wage'):
                    summed += float(v)
                    found_earning = True
            if found_earning:
                gross_wage = summed

        # 3. Fallback to contract.wage ONLY when localdict is empty or outside payslip evaluation context
        if gross_wage is None:
            contract = ld.get('contract') or (ps.contract_id if ps else False)
            if not contract and ps and getattr(ps, 'employee_id', False):
                contracts = self.env['hr.version'].search([('employee_id', '=', ps.employee_id.id)])
                contract = contracts[0] if contracts else False
            if contract:
                bd = float(getattr(contract, 'breakdown_total', 0.0) or 0.0)
                gross_wage = bd if bd > 0.0 else float(getattr(contract, 'wage', 0.0) or 0.0)
            else:
                gross_wage = 0.0

        if ps and hasattr(ps, '_get_earned_wage_ratio'):
            ratio = ps._get_earned_wage_ratio(localdict=ld)
            gross_wage = gross_wage * ratio

        return max(round(gross_wage, 2), 0.0)

    def _get_esic_contributable_wage(self, payslip):
        """Single entry eligibility validation & gross wage resolution."""
        gross_wage = self._get_gross_wage(payslip)
        if not self.validator.is_esic_eligible(payslip, gross_wage=gross_wage):
            return 0.0
        return gross_wage

    def compute_esic_wage(self, payslip):
        _logger.info("--> [ESICService] compute_esic_wage(payslip=%s)", payslip)
        with StatutoryAuditSession(self.env, payslip, statutory_module='esic', rule_code='ESIC_WAGE') as audit:
            esic_wage = self._get_esic_contributable_wage(payslip)
            ceiling = self.validator.get_applicable_ceiling(payslip)
            audit.attach_input('is_pwd', payslip.employee_id.hds_in_is_pwd if payslip.employee_id else False)
            audit.attach_parameter('APPLICABLE_ESIC_CEILING', ceiling)
            audit.attach_output('esic_wage', esic_wage)
            _logger.info("<-- [ESICService] compute_esic_wage -> %s", esic_wage)
            return esic_wage

    def check_daily_wage_exemption(self, payslip, esic_wage=None, eval_date=None):
        """Public facade method for evaluating Rule 51-B daily-wage exemption."""
        if esic_wage is None:
            esic_wage = self._get_esic_contributable_wage(payslip)
        return self.employee_calc.check_daily_wage_exemption(payslip, esic_wage=esic_wage, eval_date=eval_date)

    def compute_esic_employee(self, payslip):
        _logger.info("--> [ESICService] compute_esic_employee(payslip=%s)", payslip)
        with StatutoryAuditSession(self.env, payslip, statutory_module='esic', rule_code='ESIC_EE') as audit:
            esic_wage = self._get_esic_contributable_wage(payslip)
            eval_date = payslip.date_to or self.env.context.get('date')
            ee_rate = self.env['hr.rule.parameter'].get_parameter('hds_in_esic_employee_rate', date=eval_date, as_decimal=False)
            ceiling = self.validator.get_applicable_ceiling(payslip)

            is_exempt, avg_daily_wage, paid_days, threshold = self.employee_calc.check_daily_wage_exemption(
                payslip, esic_wage=esic_wage, eval_date=eval_date
            )

            audit.attach_input('esic_wage', esic_wage)
            audit.attach_input('is_pwd', payslip.employee_id.hds_in_is_pwd if payslip.employee_id else False)
            audit.attach_input('paid_days_in_period', paid_days)
            audit.attach_input('average_daily_wage', avg_daily_wage)
            audit.attach_parameter('ESIC_EE_RATE', ee_rate)
            audit.attach_parameter('APPLICABLE_ESIC_CEILING', ceiling)
            audit.attach_parameter('ESIC_DAILY_WAGE_EXEMPTION_THRESHOLD', threshold)
            audit.attach_output('esic_daily_wage_exempt', is_exempt)

            if is_exempt:
                amount = 0.0
                audit.log_message(
                    f"Rule 51-B Exemption Applied: Average daily wage (₹{avg_daily_wage:,.2f}) <= Threshold (₹{threshold:,.2f}). "
                    f"Employee contribution is ₹0.00."
                )
            else:
                amount = self.employee_calc.compute(payslip, esic_wage=esic_wage)

            audit.attach_output('esic_employee_deduction', amount)
            _logger.info("<-- [ESICService] compute_esic_employee -> %s (is_exempt=%s, avg_daily_wage=%s)", amount, is_exempt, avg_daily_wage)

            # Persist audit snapshot directly to payslip if present
            if hasattr(payslip, 'hds_in_esic_daily_wage_exempt'):
                payslip.hds_in_esic_daily_wage_exempt = is_exempt
                payslip.hds_in_esic_average_daily_wage = avg_daily_wage
                payslip.hds_in_esic_paid_days = paid_days

            return amount

    def compute_esic_employer(self, payslip):
        _logger.info("--> [ESICService] compute_esic_employer(payslip=%s)", payslip)
        with StatutoryAuditSession(self.env, payslip, statutory_module='esic', rule_code='ESIC_ER') as audit:
            esic_wage = self._get_esic_contributable_wage(payslip)
            eval_date = payslip.date_to or self.env.context.get('date')
            er_rate = self.env['hr.rule.parameter'].get_parameter('hds_in_esic_employer_rate', date=eval_date, as_decimal=False)

            audit.attach_input('esic_wage', esic_wage)
            audit.attach_parameter('ESIC_ER_RATE', er_rate)

            amount = self.employer_calc.compute(payslip, esic_wage=esic_wage)
            audit.attach_output('esic_employer_contribution', amount)
            _logger.info("<-- [ESICService] compute_esic_employer -> %s", amount)
            return amount
