# -*- coding: utf-8 -*-
from odoo import models


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def _get_partner_id(self, credit_account=False):
        """Returns the partner_id to associate with the journal item line."""
        self.ensure_one()
        rule = self.salary_rule_id
        account = rule.account_credit_id if credit_account else rule.account_debit_id
        emp = self.employee_id
        emp_partner = (
            getattr(emp, 'work_contact_id', False)
            or getattr(emp, 'address_home_id', False)
            or (emp.user_id and emp.user_id.partner_id)
            or False
        )
        if rule.set_employee_on_account_line:
            return emp_partner.id if emp_partner else False

        if account and account.account_type in ('asset_receivable', 'liability_payable'):
            return emp_partner.id if emp_partner else False
        return False
