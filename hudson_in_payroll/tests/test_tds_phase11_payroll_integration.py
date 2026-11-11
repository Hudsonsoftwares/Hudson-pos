# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestTdsPhase11PayrollIntegration(TransactionCase):

    def setUp(self):
        super(TestTdsPhase11PayrollIntegration, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({
                'name': 'New Tax Regime (Section 115BAC)',
                'code': 'new',
                'active': True,
            })

        self.employee = self.env['hr.employee'].create({
            'name': 'Phase 11 Payroll Integration Test Employee',
            'birthday': '1991-03-10',
            'hds_in_tds_applicable': True,
        })

        existing_contract = getattr(self.employee, 'version_id', False) or (
            self.env['hr.version'].search([('employee_id', '=', self.employee.id)], limit=1)
            if 'hr.version' in self.env else False
        )
        if existing_contract:
            existing_contract.write({
                'wage': 100000.0,
                'date_start': '2025-04-01',
                'contract_date_start': '2025-04-01',
                'date_version': '2025-04-01',
            })
            self.contract = existing_contract
        else:
            contract_model = 'hr.version' if 'hr.version' in self.env else 'hr.contract'
            contract_vals = {
                'name': 'Integration Test Contract',
                'employee_id': self.employee.id,
                'wage': 100000.0,
                'date_start': '2025-04-01',
            }
            if contract_model == 'hr.contract':
                contract_vals['state'] = 'open'
            self.contract = self.env[contract_model].create(contract_vals)
            if hasattr(self.employee, 'contract_id'):
                self.employee.contract_id = self.contract.id
            if hasattr(self.employee, 'version_id'):
                self.employee.version_id = self.contract.id

        self.env.company.write({'hds_in_tds_applicable': True})

        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_new.id,
        })

    def test_01_hr_payslip_hds_in_compute_tds(self):
        """Test hr.payslip model method hds_in_compute_tds() producing current month TDS."""
        payslip = self.env['hr.payslip'].create({
            'name': 'April 2025 Payslip Integration Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
        })

        tds_amount = payslip.hds_in_compute_tds()
        # Annual Salary = 12,00,000, Std Ded = 75,000, Taxable = 11,25,000
        # Base Tax = 52,500, Cess = 2,100, Total Annual Tax = 54,600
        # Monthly TDS (April, 12 periods) = 54,600 / 12 = 4,550
        self.assertEqual(tds_amount, 4550.0)

    def test_02_payslip_compute_sheet_generates_tds_line(self):
        """Test full payslip compute_sheet() generating the HDS_IN_TDS salary rule line."""
        payslip = self.env['hr.payslip'].create({
            'name': 'April 2025 Full Payslip Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.env.ref('hudson_payroll_base.structure_base').id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
        })

        payslip.action_compute_sheet()
        tds_line = payslip.line_ids.filtered(lambda l: l.code == 'HDS_IN_TDS')
        self.assertTrue(tds_line)
        self.assertEqual(tds_line.total, 4550.0)

    def test_03_tds_disabled_when_company_tds_applicable_false(self):
        """When company TDS is disabled, TDS calculation returns 0.0 without requiring a Financial Year."""
        self.env.company.write({'hds_in_tds_applicable': False})
        payslip = self.env['hr.payslip'].create({
            'name': 'September 2026 Payslip Without TDS Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.env.ref('hudson_payroll_base.structure_base').id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        tds_amount = payslip.hds_in_compute_tds()
        self.assertEqual(tds_amount, 0.0)
        payslip.action_compute_sheet()
        # TDS disabled for the company: the payslip shows no TDS line
        tds_line = payslip.line_ids.filtered(lambda l: l.code == 'HDS_IN_TDS')
        self.assertFalse(tds_line)

    def test_04_download_tax_report_button_visibility_and_employee_tds_check(self):
        """Verify that download tax calculation report button visibility (hds_in_tds_applicable)
        strictly honors employee-level Enable TDS setting."""
        from odoo.exceptions import UserError

        self.env.company.write({'hds_in_tds_applicable': True})
        self.employee.write({'hds_in_tds_applicable': True})

        payslip = self.env['hr.payslip'].create({
            'name': 'Test TDS Visible Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.env.ref('hudson_payroll_base.structure_base').id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
        })
        self.assertTrue(payslip.hds_in_tds_applicable)

        # When employee TDS is disabled (unchecked):
        self.employee.write({'hds_in_tds_applicable': False})
        payslip.invalidate_recordset(['hds_in_tds_applicable'])
        self.assertFalse(payslip.hds_in_tds_applicable)

        with self.assertRaises(UserError):
            payslip.action_print_statutory_report()

    def test_05_tax_report_online_viewer_modal_action(self):
        """Verify that action_print_statutory_report opens the online viewer wizard modal
        with rendered PDF and that the wizard's action_download_pdf returns the report action."""
        self.env.company.write({'hds_in_tds_applicable': True})
        self.employee.write({'hds_in_tds_applicable': True})

        payslip = self.env['hr.payslip'].create({
            'name': 'Modal Viewer Test Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.env.ref('hudson_payroll_base.structure_base').id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
        })
        payslip.action_compute_sheet()

        action = payslip.action_print_statutory_report()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'hds.tax.report.viewer.wizard')
        self.assertEqual(action.get('target'), 'new')
        self.assertEqual(action.get('context', {}).get('dialog_size'), 'extra-large')

        wizard = self.env['hds.tax.report.viewer.wizard'].browse(action['res_id'])
        self.assertTrue(wizard.exists())
        self.assertEqual(wizard.payslip_id, payslip)
        self.assertEqual(wizard.employee_id, self.employee)
        self.assertTrue(wizard.pdf_file)
        self.assertTrue(wizard.pdf_filename.endswith('.pdf'))

        download_action = wizard.action_download_pdf()
        self.assertEqual(download_action.get('type'), 'ir.actions.report')
        self.assertEqual(download_action.get('report_name'), 'hudson_in_payroll.report_statutory_tax_payslip')

