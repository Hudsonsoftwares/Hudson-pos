# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests.common import TransactionCase, tagged

from ..models.hr_salary_rule import COMPANY_SWITCH_RULES, RULE_COMPANY_SWITCH


@tagged('post_install', '-at_install')
class TestCompanyStatutoryLines(TransactionCase):
    """A statutory payslip line (TDS, PT, EPF, ESIC, LWF, Gratuity, Leave Encashment) shows only when
    its switch is enabled in the company's Payroll settings."""

    def setUp(self):
        super().setUp()
        self.company = self.env['res.company'].create({
            'name': 'Statutory Switch Co', 'country_id': self.env.ref('base.in').id,
            **{switch: False for switch in COMPANY_SWITCH_RULES},
        })
        self.structure = self.env.ref('hudson_payroll_base.structure_base')
        self.employee = self.env['hr.employee'].with_company(self.company).create({
            'name': 'Switch Employee', 'company_id': self.company.id})
        vals = {'wage': 15000.0, 'basic_salary': 15000.0, 'date_version': date(2026, 1, 1),
                'struct_id': self.structure.id}
        if 'pay_by_attendance' in self.env['hr.version']._fields:
            vals['pay_by_attendance'] = False  # fixed monthly salary, no attendance needed
        if 'contract_date_start' in self.env['hr.version']._fields:
            vals['contract_date_start'] = date(2026, 1, 1)
        self.employee.version_id.write(vals)

    def _payslip_codes(self):
        slip = self.env['hr.payslip'].with_company(self.company).create({
            'name': 'Switch Slip', 'employee_id': self.employee.id, 'company_id': self.company.id,
            'contract_id': self.employee.version_id.id, 'struct_id': self.structure.id,
            'date_from': date(2026, 3, 1), 'date_to': date(2026, 3, 31)})
        self.assertFalse(slip.has_no_running_contract)
        slip.action_compute_sheet()
        return set(slip.line_ids.mapped('code')), slip

    def test_disabled_switches_hide_the_lines(self):
        codes, slip = self._payslip_codes()
        self.assertTrue({'BASIC', 'GROSS', 'NET'} <= codes, codes)
        self.assertFalse(codes & set(RULE_COMPANY_SWITCH), "statutory lines shown although disabled for the company")
        # No statutory deduction: the net is the gross
        total = {line.code: line.total for line in slip.line_ids}
        self.assertGreater(total['GROSS'], 0.0)
        self.assertEqual(total['NET'], total['GROSS'])

    def test_enabled_switch_applies_the_rule(self):
        rule = self.env.ref('hudson_in_payroll.hds_in_rule_esic_ee')
        slip = self.env['hr.payslip'].new({'company_id': self.company.id})
        localdict = {'payslip_record': slip}
        self.assertFalse(rule._satisfies_condition(localdict))
        self.company.hds_in_esic_applicable = True
        self.assertTrue(rule._satisfies_condition(localdict))
        # Each switch controls its own rules only
        tds = self.env.ref('hudson_in_payroll.hds_in_rule_tds')
        self.assertFalse(tds._satisfies_condition(localdict))
        self.company.hds_in_tds_applicable = True
        self.assertTrue(tds._satisfies_condition(localdict))
        lwf = self.env.ref('hudson_in_payroll.hds_in_rule_lwf_ee')
        self.assertFalse(lwf._satisfies_condition(localdict))

    def test_other_countries_are_not_affected(self):
        structure = self.env['hr.payroll.structure'].create({
            'name': 'Non-India Structure', 'code': 'NON_IN_TEST', 'country_id': self.env.ref('base.ae').id})
        rule = self.env['hr.salary.rule'].create({
            'name': 'Gratuity', 'code': 'GRATUITY', 'struct_id': structure.id, 'sequence': 100,
            'category_id': self.env.ref('hudson_in_payroll.hds_in_rule_gratuity').category_id.id,
            'condition_select': 'none', 'amount_select': 'fix', 'amount_fix': 1.0})
        slip = self.env['hr.payslip'].new({'company_id': self.company.id})
        self.assertTrue(rule._satisfies_condition({'payslip_record': slip}))
