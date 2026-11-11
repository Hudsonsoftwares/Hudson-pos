# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hds_payroll_account_salary_expense_id = fields.Many2one(related='company_id.hds_payroll_account_salary_expense_id', readonly=False)
    hds_payroll_account_employer_expense_id = fields.Many2one(related='company_id.hds_payroll_account_employer_expense_id', readonly=False)
    hds_payroll_account_pf_employee_id = fields.Many2one(related='company_id.hds_payroll_account_pf_employee_id', readonly=False)
    hds_payroll_account_pf_employer_id = fields.Many2one(related='company_id.hds_payroll_account_pf_employer_id', readonly=False)
    hds_payroll_account_pf_admin_id = fields.Many2one(related='company_id.hds_payroll_account_pf_admin_id', readonly=False)
    hds_payroll_account_net_payable_id = fields.Many2one(related='company_id.hds_payroll_account_net_payable_id', readonly=False)
    hds_payroll_account_tds_id = fields.Many2one(related='company_id.hds_payroll_account_tds_id', readonly=False)
    hds_payroll_account_pt_id = fields.Many2one(related='company_id.hds_payroll_account_pt_id', readonly=False)
    hds_payroll_account_esic_employee_id = fields.Many2one(related='company_id.hds_payroll_account_esic_employee_id', readonly=False)
    hds_payroll_account_esic_employer_id = fields.Many2one(related='company_id.hds_payroll_account_esic_employer_id', readonly=False)
    hds_payroll_account_lwf_employee_id = fields.Many2one(related='company_id.hds_payroll_account_lwf_employee_id', readonly=False)
    hds_payroll_account_lwf_employer_id = fields.Many2one(related='company_id.hds_payroll_account_lwf_employer_id', readonly=False)
    hds_payroll_account_other_deductions_id = fields.Many2one(related='company_id.hds_payroll_account_other_deductions_id', readonly=False)

    @api.model
    def default_get(self, fields_list):
        # Opening the settings shows the payroll accounts already mapped: the chart of accounts'
        # payroll accounts, and the missing ones created (only when accounting is set up)
        company = self.env.company
        if any(name.startswith('hds_payroll_account_') for name in fields_list) and company._hds_has_chart_of_accounts():
            company._hds_get_payroll_accounts()
        return super().default_get(fields_list)

    def action_hds_create_payroll_accounts(self):
        """Create the company's missing payroll accounts (Salary Expense, PF / ESIC / PT / LWF / TDS payables...)."""
        self.ensure_one()
        if not self.company_id._hds_has_chart_of_accounts():
            raise UserError(_("Set up the chart of accounts of %s first (Settings > Invoicing > Fiscal Localization).",
                              self.company_id.name))
        self.company_id._hds_get_payroll_accounts()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
