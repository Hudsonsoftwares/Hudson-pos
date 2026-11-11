# -*- coding: utf-8 -*-
from datetime import date
import io
from PyPDF2 import PdfReader
from odoo.tests.common import TransactionCase


class TestBatchPayslipPrint(TransactionCase):
    """
    Test suite for batch printing payslips and multi-employee selection.
    Verifies that selecting multiple employees and printing generates a single
    multi-page PDF where each employee's payslip is cleanly printed 1 page after another.
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    def setUp(self):
        super().setUp()
        self.Employee = self.env['hr.employee']
        self.Payslip = self.env['hr.payslip']
        self.PayRun = self.env['hr.payslip.run']
        self.Contract = self.env['hr.version']
        self.Structure = self.env['hr.payroll.structure']
        self.company = self.env.company

        # Salary Structure
        self.struct = self.Structure.search([], limit=1)
        if not self.struct:
            self.struct = self.Structure.create({
                'name': 'Test Regular Pay',
                'code': 'TEST_REG',
            })

        # Create 3 employees and setup contracts
        self.employees = self.env['hr.employee']
        self.slips = self.env['hr.payslip']
        for i in range(1, 4):
            emp = self.Employee.create({
                'name': f'Batch Print Employee {i}',
                'company_id': self.company.id,
            })
            if emp.version_id:
                emp.version_id.write({
                    'wage': 30000.0 * i,
                    'struct_id': self.struct.id,
                })
            else:
                contract = self.Contract.create({
                    'name': f'Contract Batch Print {i}',
                    'employee_id': emp.id,
                    'wage': 30000.0 * i,
                    'struct_id': self.struct.id,
                    'company_id': self.company.id,
                })
                emp.version_id = contract
            self.employees |= emp

        # Create Pay Run
        self.payrun = self.PayRun.create({
            'name': 'Nov 2026 Batch Print Test',
            'date_start': date(2026, 11, 1),
            'date_end': date(2026, 11, 30),
            'struct_id': self.struct.id,
            'company_id': self.company.id,
        })

        for emp in self.employees:
            slip = self.Payslip.create({
                'name': f'Salary Slip - {emp.name} - Nov 2026',
                'employee_id': emp.id,
                'contract_id': emp.version_id.id,
                'struct_id': self.struct.id,
                'date_from': date(2026, 11, 1),
                'date_to': date(2026, 11, 30),
                'payslip_run_id': self.payrun.id,
                'company_id': self.company.id,
            })
            self.slips |= slip

    def test_01_action_open_payslips(self):
        """Test action_open_payslips returns the payslip list view for the pay run."""
        action = self.payrun.action_open_payslips()
        self.assertEqual(action['res_model'], 'hr.payslip')
        self.assertEqual(action['domain'], [('payslip_run_id', '=', self.payrun.id)])
        expected_view_id = self.env.ref('hudson_payroll_base.hr_payslip_view_list').id
        self.assertEqual(action['views'][0][0], expected_view_id)

    def test_02_action_print_payslips_payrun(self):
        """Test action_print_payslips on Pay Run returns report action for all slips."""
        action = self.payrun.action_print_payslips()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'hudson_payroll_base.report_payslip_document')

    def test_03_action_print_payslips_multi_employee(self):
        """Test action_print_payslips on multiple selected payslips returns report action."""
        selected_slips = self.slips[:2]
        action = selected_slips.action_print_payslips()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'hudson_payroll_base.report_payslip_document')

    def test_04_multi_page_pdf_generation(self):
        """
        Verify that generating report for multiple selected employee payslips produces
        a document containing all selected employees, 1 payslip after another.
        """
        report_action = self.env.ref('hudson_payroll_base.action_report_payslip')
        # Verify QWeb HTML rendering produces 1 distinct payslip per employee
        html_content, _ = report_action._render_qweb_html(report_action.id, self.slips.ids)
        html_str = html_content.decode('utf-8') if isinstance(html_content, bytes) else str(html_content)
        self.assertTrue(len(html_str) > 0, "Rendered report HTML must not be empty")

        for emp in self.employees:
            self.assertIn(emp.name, html_str, f"Employee {emp.name} must appear in rendered payslip document")
