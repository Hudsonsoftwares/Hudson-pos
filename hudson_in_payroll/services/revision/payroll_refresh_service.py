# -*- coding: utf-8 -*-
from ..base import BaseStatutoryService
from ..payroll.salary_breakdown_service import SalaryBreakdownService


class PayrollRefreshService(BaseStatutoryService):
    """
    Pure Python service responsible for refreshing dependent payroll components
    and updating the employee's active contract upon confirmed salary revision.
    """

    def __init__(self, env):
        super().__init__(env)
        self.breakdown_service = SalaryBreakdownService(env)

    def refresh_contract_payroll(self, contract, new_wage, effective_date=None, mode='auto_structure', manual_dict=None):
        """
        Regenerates or updates employee contract salary breakdown components
        according to distribution mode and recalculates employer cost to company (CTC).
        """
        if not contract:
            return False

        # 1. Regenerate and apply component breakdown to target contract instance
        self.breakdown_service.apply_breakdown_to_contract(contract, new_wage, mode=mode, manual_dict=manual_dict)

        # 2. Recalculate Employer Cost to Company (CTC)
        if hasattr(contract, '_compute_employer_cost'):
            contract._compute_employer_cost()

        return True
