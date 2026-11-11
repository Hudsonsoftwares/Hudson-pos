# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .previous_employer_income_service import PreviousEmployerIncomeService

_logger = logging.getLogger(__name__)


class PreviousEmployerTdsService(BaseStatutoryService):
    """
    Phase 10 Service: Previous Employer TDS Service.
    Resolves Form 12B declared TDS deducted by previous employer during the current Financial Year.
    """

    def get_previous_employer_tds(self, employee, financial_year):
        """
        Retrieves Form 12B previous employer TDS deducted.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :return: float (Previous Employer TDS Amount)
        """
        if not employee or not financial_year:
            return 0.0

        prev_svc = PreviousEmployerIncomeService(self.env)
        prev_res = prev_svc.aggregate_previous_employer_income(employee, financial_year)
        return prev_res.tds_deducted or 0.0
