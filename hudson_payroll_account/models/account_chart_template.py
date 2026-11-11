# -*- coding: utf-8 -*-
from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _post_load_data(self, template_code, company, template_data):
        res = super()._post_load_data(template_code, company, template_data)
        # A new chart of accounts maps the company's payroll accounts to its accounts
        company._hds_assign_default_payroll_accounts()
        return res
