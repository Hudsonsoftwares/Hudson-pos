# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

DEFAULT_ROOT_DIRECTORIES = [
    ("Projects", "fa-tasks"),
    ("Products", "fa-cube"),
    ("Recruitment", "fa-user-plus"),
    ("Employees", "fa-users"),
    ("Accounting", "fa-calculator"),
    ("Finance", "fa-money"),
    ("Approvals", "fa-check-circle-o"),
    ("Signatures", "fa-pencil-square-o"),
    ("Sales", "fa-line-chart"),
    ("Purchases", "fa-shopping-cart"),
    ("Helpdesk", "fa-support"),
    ("Fleet", "fa-car"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            try:
                self.env["dms.directory"].sudo()._ensure_company_default_directories(company)
            except Exception as e:
                _logger.warning("Could not auto-generate default DMS folders for company %s: %s", company.name, e)
        return companies
