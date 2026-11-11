# -*- coding: utf-8 -*-
import logging
from odoo import fields

_logger = logging.getLogger(__name__)


class LWFRateService:
    """
    Domain Service for querying active Labour Welfare Fund (LWF) State Rate configurations.
    Decoupled from calculation math and payslip state.

    Responsibility:
    - Given a res.country.state record, evaluation date, and optional company,
      retrieve the matching active lwf.state.rate record.
    - Evaluate deduction schedule applicability based on month frequency.
    """

    def __init__(self, env):
        self.env = env

    def get_rate_config(self, state, eval_date=None, company=None):
        """
        Retrieves the active LWF configuration record matching state, evaluation date, and company.

        :param state: res.country.state recordset (single record)
        :param eval_date: datetime.date object (defaults to today if omitted)
        :param company: res.company recordset or None
        :return: lwf.state.rate recordset (single record) or False
        """
        if not state:
            return False

        if not eval_date:
            eval_date = fields.Date.today()

        domain = [
            ('state_id', '=', state.id),
            ('active', '=', True),
            ('date_from', '<=', eval_date),
            '|', ('date_to', '=', False), ('date_to', '>=', eval_date)
        ]

        if company:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]

        records = self.env['lwf.state.rate'].search(domain)
        if not records:
            _logger.info("No active LWF rate configuration found for state %s on date %s", state.name, eval_date)
            return False

        # Sort company-specific records first, then newest date_from
        if company:
            matching = records.filtered(lambda r: r.company_id.id == company.id)
            if matching:
                return matching.sorted(lambda r: r.date_from or fields.Date.today(), reverse=True)[0]

        global_matching = records.filtered(lambda r: not r.company_id)
        if global_matching:
            return global_matching.sorted(lambda r: r.date_from or fields.Date.today(), reverse=True)[0]

        return records.sorted(lambda r: r.date_from or fields.Date.today(), reverse=True)[0]

    def is_deduction_scheduled(self, rate_config, eval_date=None):
        """
        Determines whether the given evaluation date's month triggers LWF statutory deduction.

        :param rate_config: lwf.state.rate recordset (single record)
        :param eval_date: datetime.date object
        :return: bool
        """
        if not rate_config:
            return False
        if not eval_date:
            eval_date = fields.Date.today()
        return rate_config.is_deduction_month(eval_date)
