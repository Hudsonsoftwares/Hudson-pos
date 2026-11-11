# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class CurrentFinancialYearTdsService(BaseStatutoryService):
    """
    Phase 10 Service: Current Financial Year TDS Service.
    Queries confirmed/done payslips for the employee within the Financial Year boundaries
    and sums YTD TDS withheld by current employer.
    """

    def get_ytd_tds_deducted(self, employee, financial_year, eval_date=None):
        """
        Retrieves total YTD TDS deducted on current employer payslips.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param eval_date: Date (optional) - if passed, queries prior completed payslips before eval_date month
        :return: float (YTD Current Employer TDS Deducted)
        """
        if not employee or not financial_year:
            return 0.0

        fy_start = financial_year.start_date
        fy_end = financial_year.end_date

        domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '>=', fy_start),
            ('state', 'in', ['done', 'paid'])
        ]

        if eval_date:
            if isinstance(eval_date, str):
                eval_date = fields.Date.from_string(eval_date)

            eval_start = eval_date.replace(day=1)
            domain.append(('date_to', '<', eval_start))
        else:
            domain.append(('date_to', '<=', fy_end))

        payslips = self.env['hr.payslip'].search(domain)

        ytd_tds = 0.0
        _logger.warning("[80E_AUDIT] PREVIOUS_PAYSLIPS_AUDIT: previous_payslip_count=%s", len(payslips))
        for slip in payslips:
            slip_tds = 0.0
            for line in slip.line_ids:
                if (line.code or '').upper() in ('TDS', 'HDS_IN_TDS', 'INCOME_TAX', 'TDS_GRATUITY'):
                    slip_tds += abs(line.total or 0.0)
            _logger.warning("[80E_AUDIT] PREVIOUS_PAYSLIP: id=%s date_from=%s date_to=%s name=%s tds=%s",
                slip.id, slip.date_from, slip.date_to, slip.name, slip_tds)
            ytd_tds += slip_tds

        return ytd_tds
