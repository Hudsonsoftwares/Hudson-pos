# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
from odoo.fields import Date# pyrefly: ignore [missing-import]


class TestTdsUnifiedGratuity(TransactionCase):
    """
    Unit Tests for SalaryProjectionService and TDS Engine Unified Gratuity Handling.
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestTdsUnifiedGratuity, cls).tearDownClass()
        except BaseException:
            pass

    def setUp(self):
        super(TestTdsUnifiedGratuity, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Gratuity TDS Test Company',
            'hds_in_enable_gratuity': True,
            'hds_in_tds_applicable': True,
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Gratuity TDS Test Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2015-01-01'),
            'hds_in_tds_applicable': True,
        })

        self.fy = self.env['tds.financial.year'].search([
            ('start_date', '<=', '2026-03-31'),
            ('end_date', '>=', '2026-03-31')
        ], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'FY 2025-2026',
                'code': '2025-2026',
                'start_date': Date.from_string('2025-04-01'),
                'end_date': Date.from_string('2026-03-31'),
                'assessment_year': '2026-2027',
                'active': True,
            })

        contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)
        if contract_model:
            struct = self.env.ref('hudson_in_payroll.hds_in_structure_final_settlement', raise_if_not_found=False)
            if not struct:
                struct = self.env['hr.payroll.structure'].search([('code', '=', 'FINAL_SETTLEMENT_STRUCT')], limit=1)
            self.contract = getattr(self.employee, 'version_id', False) or self.env[contract_model].search([
                ('employee_id', '=', self.employee.id)
            ], limit=1)
            vals = {
                'name': 'Gratuity TDS Test Contract',
                'employee_id': self.employee.id,
                'company_id': self.company.id,
                'wage': 120000.0,
                'basic_salary': 100000.0,
                'da': 20000.0,
                'date_start': Date.from_string('2015-01-01'),
                'struct_id': struct.id if struct else False,
            }
            if self.contract:
                self.contract.write(vals)
            else:
                self.contract = self.env[contract_model].create(vals)

    def test_01_salary_projection_preserves_taxable_gratuity_in_final_settlement(self):
        """Verify taxable gratuity is NOT suppressed to 0 even when FINAL_SETTLEMENT_STRUCT is used."""
        struct = self.env['hr.payroll.structure'].search([('code', '=', 'FINAL_SETTLEMENT_STRUCT')], limit=1)
        payslip = self.env['hr.payslip'].create({
            'name': 'Final Settlement Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'company_id': self.company.id,
            'struct_id': struct.id if struct else False,
            'date_from': Date.from_string('2026-03-01'),
            'date_to': Date.from_string('2026-03-31'),
        })

        rule = self.env['hr.salary.rule'].search([], limit=1)
        # Add mock gratuity line of 33,23,076.92
        gross_gratuity = 3323076.92
        self.env['hr.payslip.line'].create({
            'slip_id': payslip.id,
            'salary_rule_id': rule.id if rule else False,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'name': 'Gratuity',
            'code': 'GRATUITY',
            'amount': gross_gratuity,
            'total': gross_gratuity,
        })

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        service = SalaryProjectionService(self.env)
        proj = service.project_salary(self.employee, self.fy, eval_date=Date.from_string('2026-03-31'), payslip=payslip)

        self.assertAlmostEqual(proj.total_gratuity, gross_gratuity, places=2)
        self.assertAlmostEqual(proj.exempt_gratuity, 2000000.0, places=2)
        self.assertAlmostEqual(proj.taxable_gratuity, 1323076.92, places=2)

        # Taxable gratuity must be included in total_projected_current_salary
        self.assertGreaterEqual(proj.total_projected_current_salary, 1323076.92)

    def test_02_prior_ytd_tds_includes_legacy_tds_gratuity(self):
        """Verify CurrentFinancialYearTdsService aggregates legacy TDS_GRATUITY lines from paid payslips."""
        rule = self.env['hr.salary.rule'].search([], limit=1)
        paid_slip = self.env['hr.payslip'].create({
            'name': 'Paid Payslip with Legacy Gratuity TDS',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'company_id': self.company.id,
            'date_from': Date.from_string('2025-05-01'),
            'date_to': Date.from_string('2025-05-31'),
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': paid_slip.id,
            'salary_rule_id': rule.id if rule else False,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'name': 'TDS on Gratuity',
            'code': 'TDS_GRATUITY',
            'amount': -50000.0,
            'total': -50000.0,
        })
        self.env['hr.payslip.line'].create({
            'slip_id': paid_slip.id,
            'salary_rule_id': rule.id if rule else False,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'name': 'Regular TDS',
            'code': 'HDS_IN_TDS',
            'amount': -15000.0,
            'total': -15000.0,
        })

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.tds.current_financial_year_tds_service import CurrentFinancialYearTdsService
        ytd_svc = CurrentFinancialYearTdsService(self.env)
        ytd_tds = ytd_svc.get_ytd_tds_deducted(self.employee, self.fy, eval_date=Date.from_string('2026-03-31'))
        self.assertEqual(ytd_tds, 65000.0)
