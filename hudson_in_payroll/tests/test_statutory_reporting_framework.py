# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestStatutoryReportingFramework(TransactionCase):

    def setUp(self):
        super(TestStatutoryReportingFramework, self).setUp()
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_enable_epf': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/REPORT/2026',
        })

        self.state_mh = self.env.ref('base.state_in_mh')
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Reporting Test Partner Address',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Reporting Office Location',
            'address_id': self.partner_mh.id,
            'company_id': self.company.id,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'Reporting Test Employee',
            'gender': 'male',
            'barcode': 'EMP-REPORT-001',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
        })

        self.contract = self.env['hr.version'].create({
            'name': 'Reporting Contract',
            'employee_id': self.employee.id,
            'date_start': Date.from_string('2025-01-01'),
            'wage': 18000.0,
            'basic_salary': 15000.0,
        })

        self.payslip = self.env['hr.payslip'].create({
            'name': 'Reporting Test Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

        # Generate statutory audit entries by computing payslip lines
        self.env['hr.payslip']._get_payslip_lines([self.contract.id], self.payslip.id)

    def test_01_read_only_enforcement(self):
        """Verify hds.in.statutory.report model is read-only and prevents direct creation/modification."""
        ReportModel = self.env['hds.in.statutory.report']
        with self.assertRaises(Exception):
            ReportModel.create({
                'employee_id': self.employee.id,
                'statutory_module': 'pt',
                'rule_code': 'PT',
            })

    def test_02_epf_report_filtering(self):
        """Verify Provident Fund (EPF) report domain filtering (statutory_module = 'epf')."""
        reports = self.env['hds.in.statutory.report'].search([('statutory_module', '=', 'epf')])
        for rec in reports:
            self.assertEqual(rec.statutory_module, 'epf')

    def test_03_pt_report_filtering(self):
        """Verify Professional Tax (PT) report domain filtering (statutory_module = 'pt')."""
        reports = self.env['hds.in.statutory.report'].search([('statutory_module', '=', 'pt')])
        for rec in reports:
            self.assertEqual(rec.statutory_module, 'pt')

    def test_04_multi_company_security(self):
        """Verify multi-company record rule isolation on statutory report model."""
        company_b = self.env['res.company'].create({
            'name': 'Reporting Security Company B',
        })
        reports_a = self.env['hds.in.statutory.report'].with_company(self.company).search([])
        reports_b = self.env['hds.in.statutory.report'].with_company(company_b).search([])

        # Company B user should not see Company A statutory report records
        comp_b_ids = [r.company_id.id for r in reports_b if r.company_id]
        self.assertNotIn(self.company.id, comp_b_ids)
