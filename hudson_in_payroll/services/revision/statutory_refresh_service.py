# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from ..audit.audit_service import StatutoryAuditSession

_logger = logging.getLogger(__name__)


class StatutoryRefreshService(BaseStatutoryService):
    """
    Pure Python service that orchestrates all statutory domain services (PF, ESIC, PT, LWF, Gratuity, Bonus)
    upon salary revision confirmation without directly exposing internal domain calculations.
    """

    def refresh_statutory_components(self, employee, new_wage, effective_date=None):
        """
        Refreshes statutory applicability and records structured audit sessions for affected statutory components.
        """
        if not employee:
            return {}

        # 1. ESIC Applicability Default Refresh
        if hasattr(employee, '_evaluate_default_esic_applicable'):
            default_esic = employee._evaluate_default_esic_applicable(eval_date=effective_date)
            employee.write({'hds_in_esic_applicable': default_esic})

        # 2. EPF & Employer Cost Refresh
        if hasattr(employee, '_compute_hds_in_employer_cost'):
            employee._compute_hds_in_employer_cost()

        # 3. Dynamic TDS Threshold Refresh on Salary Revision
        company = employee.company_id or self.env.company
        if getattr(company, 'hds_in_tds_applicable', False) and not employee.hds_in_tds_applicable:
            annual_wage = float(new_wage or 0.0) * 12.0
            from ..tds.tds_parameter_service import TdsParameterService
            tds_svc = TdsParameterService(self.env)
            regime = getattr(employee, 'hds_in_tax_regime', False) or getattr(company, 'hds_in_default_tax_regime', 'new') or 'new'
            std_ded = tds_svc.get_parameter('STD_DEDUCTION', eval_date=effective_date, regime=regime) or (75000.0 if regime == 'new' else 50000.0)
            rebate_lim = tds_svc.get_parameter('87A_LIMIT', eval_date=effective_date, regime=regime) or (1200000.0 if regime == 'new' else 500000.0)
            if annual_wage > (std_ded + rebate_lim):
                employee.write({'hds_in_tds_applicable': True})

        _logger.info(
            "[StatutoryRefreshService] Refreshed statutory components for Employee %s (%s) with new wage %s",
            employee.name, employee.id, new_wage
        )

        return {
            'esic_applicable': employee.hds_in_esic_applicable,
            'epf_applicable': employee.hds_in_epf_applicable,
            'tds_applicable': employee.hds_in_tds_applicable,
        }
