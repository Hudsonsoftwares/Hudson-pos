# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Statutory rules of the Indian structures, by the company switch (Payroll settings) that enables them
COMPANY_SWITCH_RULES = {
    'hds_in_tds_applicable': ('HDS_IN_TDS', 'TDS_GRATUITY'),
    'hds_in_enable_professional_tax': ('PT',),
    'hds_in_epf_applicable': ('PF_WAGE', 'EPF', 'EMPLOYER_EPF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'),
    'hds_in_esic_applicable': ('ESIC_WAGE', 'ESIC_EE', 'ESIC_ER'),
    'hds_in_enable_lwf': ('LWF_EE', 'LWF_ER'),
    'hds_in_enable_gratuity': ('GRATUITY',),
    'hds_in_enable_leave_encashment': ('LEAVE_ENCASH', 'EXIT_LEAVE_ENCASH'),
}
RULE_COMPANY_SWITCH = {code: switch for switch, codes in COMPANY_SWITCH_RULES.items() for code in codes}


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    hds_in_include_in_pf_wage = fields.Boolean(
        string="Include in PF Wage",
        default=False,
        help="If enabled, the calculated amount of this salary rule is included when determining the employee's PF-eligible wage."
    )
    hds_in_contributes_to_employer_cost = fields.Boolean(
        string="Contributes to Employer Cost",
        default=False,
        help="If checked, this salary rule amount will be included in the calculation of Employer Cost to Company (CTC)."
    )
    hds_in_is_bonus = fields.Boolean(
        string="Is Bonus",
        default=False,
        help="If checked, this salary rule is treated as a bonus component with configurable eligibility and tax rules."
    )
    hds_in_exclude_notice_period = fields.Boolean(
        string="Exclude Notice Period",
        default=True,
        help="If checked, employees currently serving notice period or with approved resignation will not receive this bonus."
    )
    hds_in_apply_tds = fields.Boolean(
        string="Apply TDS",
        default=True,
        help="If checked, this bonus will be included in taxable income and subject to TDS calculation."
    )

    def _satisfies_condition(self, localdict):
        """A statutory rule of an Indian structure applies only when its company switch is enabled
        (its amount is already zero otherwise); the payslip then shows no line for it."""
        switch = RULE_COMPANY_SWITCH.get(self.code)
        if switch and self.struct_id.country_id.code == 'IN':
            payslip = localdict.get('payslip_record')
            company = (payslip and payslip.company_id) or self.env.company
            if not company[switch]:
                return False
        return super()._satisfies_condition(localdict)


