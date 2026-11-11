# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class ESICValidator(BaseStatutoryService):
    """
    Pure Python eligibility engine for ESIC statutory compliance.
    Validates company enablement, employee applicability, active status, IP number presence,
    and statutory contribution period validity.
    """

    def is_esic_eligible(self, payslip, gross_wage=None):
        """
        Executes statutory ESIC eligibility checks in sequence:
        1. Company ESIC Enabled?
        2. Employee ESIC Applicable?
        3. Employee Active?
        4. Valid ESIC IP Number? (Logs warning if missing, continues)
        5. Contribution Period Valid & Exit Date?
        """
        company = payslip.company_id
        employee = payslip.employee_id

        # 1. Company ESIC Enabled?
        if not company or not company.hds_in_esic_applicable:
            return False

        # 2. Employee ESIC Applicable?
        if not employee.hds_in_esic_applicable:
            return False

        # 3. Employee Active?
        if hasattr(employee, 'active') and not employee.active:
            return False

        # 4. Exit Date & Resigned Check
        if employee.hds_in_esic_exit_date and payslip.date_from:
            if employee.hds_in_esic_exit_date < payslip.date_from:
                return False
        elif employee.hds_in_esic_ip_status == 'resigned':
            return False
        elif employee.hds_in_esic_ip_status == 'exempt' and not employee.hds_in_esic_applicable:
            return False

        # 5. Contribution Period Valid? (Regulation 31 Continuity)
        from .contribution_period_service import ESICContributionPeriodService
        period_service = ESICContributionPeriodService(self.env)
        eval_date = payslip.date_to or payslip.date_from
        is_covered = period_service.is_covered_for_contribution_period(employee, eval_date=eval_date, current_wage=gross_wage)

        if not is_covered:
            return False

        # 6. Valid ESIC IP Number? (Log statutory warning if missing)
        if not employee.hds_in_esic_ip_number:
            _logger.warning(
                "[ESICValidator] Employee %s (%s) has ESIC Applicable = True but is missing ESIC IP Number.",
                employee.name, employee.id
            )

        return True

    def is_esic_applicable(self, payslip, gross_wage=None):
        """Alias for is_esic_eligible."""
        return self.is_esic_eligible(payslip, gross_wage=gross_wage)

    def get_applicable_ceiling(self, payslip):
        """
        Determines applicable ESIC wage ceiling dynamically from hr.rule.parameter:
        - IF Employee hds_in_is_pwd = True -> Use ESIC PWD Wage Ceiling ('hds_in_esic_pwd_wage_ceiling')
        - ELSE -> Use Standard ESIC Wage Ceiling ('hds_in_esic_wage_ceiling')
        """
        eval_date = payslip.date_to or self.env.context.get('date')
        if payslip.employee_id and payslip.employee_id.hds_in_is_pwd:
            return self.get_parameter('hds_in_esic_pwd_wage_ceiling', date=eval_date, as_decimal=False)
        return self.get_parameter('hds_in_esic_wage_ceiling', date=eval_date, as_decimal=False)
