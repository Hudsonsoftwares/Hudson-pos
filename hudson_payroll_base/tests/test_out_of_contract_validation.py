# -*- coding: utf-8 -*-
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class TestOutOfContractValidation(TransactionCase):
    """Test suite for Out of Contract detection, banners, 0 net wage, and validation blocking."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company

        # Create isolated test salary structure to keep base test completely self-contained
        self.struct_test = self.env['hr.payroll.structure'].create({
            'name': 'Test Simple Salary Structure',
            'code': 'TEST_SIMPLE',
        })
        self.cat_basic = self.env.ref('hudson_payroll_base.rule_category_basic', raise_if_not_found=False)
        if not self.cat_basic:
            self.cat_basic = self.env['hr.salary.rule.category'].create({
                'name': 'Basic',
                'code': 'BASIC',
            })
        self.cat_net = self.env.ref('hudson_payroll_base.rule_category_net', raise_if_not_found=False)
        if not self.cat_net:
            self.cat_net = self.env['hr.salary.rule.category'].create({
                'name': 'Net',
                'code': 'NET',
            })

        self.env['hr.salary.rule'].create({
            'name': 'Basic Salary',
            'struct_id': self.struct_test.id,
            'sequence': 1,
            'code': 'BASIC',
            'category_id': self.cat_basic.id,
            'condition_select': 'none',
            'amount_select': 'code',
            'amount_python_compute': 'result = contract.basic_salary or contract.wage or 0.0',
        })
        self.env['hr.salary.rule'].create({
            'name': 'Net Salary',
            'struct_id': self.struct_test.id,
            'sequence': 200,
            'code': 'NET',
            'category_id': self.cat_net.id,
            'condition_select': 'none',
            'amount_select': 'code',
            'amount_python_compute': 'result = categories.BASIC',
        })

    def _configure_contract(self, employee, vals):
        contract = employee.version_id
        if not contract:
            contract = self.env['hr.version'].create({
                'name': f"Contract {employee.name}",
                'employee_id': employee.id,
                'company_id': self.company.id,
                **vals
            })
            employee.version_id = contract
        else:
            contract.write(vals)
        return contract

    def test_01_pre_contract_out_of_contract_handling(self):
        """Employee joined on Oct 1, 2026, HR generates payslip in April 2026."""
        employee = self.env['hr.employee'].create({
            'name': 'Gino James PreContract',
            'company_id': self.company.id,
        })
        contract = self._configure_contract(employee, {
            'wage': 25000.0,
            'basic_salary': 15000.0,
            'date_start': date(2026, 10, 1),
            'contract_date_start': date(2026, 10, 1),
            'date_end': False,
            'contract_date_end': False,
            'struct_id': self.struct_test.id,
        })

        # Generate April 2026 payslip (before joining)
        slip = self.env['hr.payslip'].create({
            'name': 'Salary Slip - PreContract - April 2026',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.struct_test.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })

        # 1. Verify No Running Contract flag is True
        self.assertTrue(slip.has_no_running_contract, "has_no_running_contract must be True before contract start date!")
        self.assertFalse(slip.has_zero_or_negative_net, "Zero net banner should only show after compute sheet!")

        # 2. Verify Worked Days contains Out of Contract line with 0.0 amount
        out_line = slip.worked_days_line_ids.filtered(lambda l: l.code == 'OUT_OF_CONTRACT')
        self.assertTrue(out_line, "An OUT_OF_CONTRACT worked days line must be generated for pre-joining period!")
        self.assertEqual(out_line.amount, 0.0, "OUT_OF_CONTRACT line amount must be ₹0.00!")
        self.assertGreater(out_line.number_of_days, 0.0, "OUT_OF_CONTRACT must reflect scheduled period days!")
        
        # Verify no normal working days line
        work100 = slip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
        self.assertFalse(work100, "Normal Working Days (WORK100) must not exist for a period that is 100% out of contract!")

        # 3. Compute Sheet -> Net Wage must be 0.0 and zero net banner must become True
        slip.action_compute_sheet()
        self.assertEqual(slip.net_wage, 0.0, "Net wage must be 0.0 when employee is out of contract!")
        self.assertEqual(slip.gross_wage, 0.0, "Gross wage must be 0.0 when employee is out of contract!")
        self.assertTrue(slip.has_zero_or_negative_net, "has_zero_or_negative_net must be True after compute sheet!")

        # 4. Attempting to Validate must raise ValidationError("• No running contract")
        with self.assertRaises(ValidationError) as cm:
            slip.action_payslip_done()
        self.assertIn("No running contract", str(cm.exception), "ValidationError must mention 'No running contract'!")

    def test_02_post_expiry_out_of_contract_handling(self):
        """Contract expired on Dec 31, 2025, HR generates payslip in April 2026."""
        employee = self.env['hr.employee'].create({
            'name': 'Gino James Expired',
            'company_id': self.company.id,
        })
        contract = self._configure_contract(employee, {
            'wage': 25000.0,
            'basic_salary': 15000.0,
            'date_start': date(2025, 1, 1),
            'contract_date_start': date(2025, 1, 1),
            'date_end': date(2025, 12, 31),
            'contract_date_end': date(2025, 12, 31),
            'struct_id': self.struct_test.id,
        })

        slip = self.env['hr.payslip'].create({
            'name': 'Salary Slip - Expired - April 2026',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.struct_test.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })

        self.assertTrue(slip.has_no_running_contract, "has_no_running_contract must be True after contract expiry!")

        slip.action_compute_sheet()
        self.assertEqual(slip.net_wage, 0.0)

        with self.assertRaises(ValidationError) as cm:
            slip.action_payslip_done()
        self.assertIn("No running contract", str(cm.exception))

    def test_03_no_contract_at_all(self):
        """Employee has no contract record assigned."""
        employee = self.env['hr.employee'].create({
            'name': 'No Contract Employee',
            'company_id': self.company.id,
        })
        slip = self.env['hr.payslip'].create({
            'name': 'Salary Slip - No Contract',
            'employee_id': employee.id,
            'contract_id': False,
            'struct_id': self.struct_test.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })

        self.assertTrue(slip.has_no_running_contract, "has_no_running_contract must be True when contract_id is False!")

        with self.assertRaises(ValidationError) as cm:
            slip.action_payslip_done()
        self.assertIn("No running contract", str(cm.exception))

    def test_04_active_running_contract_validates_successfully(self):
        """Active running contract validates normally without error."""
        employee = self.env['hr.employee'].create({
            'name': 'Active Contract Employee',
            'company_id': self.company.id,
        })
        contract = self._configure_contract(employee, {
            'wage': 30000.0,
            'basic_salary': 18000.0,
            'date_start': date(2026, 1, 1),
            'contract_date_start': date(2026, 1, 1),
            'date_end': False,
            'contract_date_end': False,
            'struct_id': self.struct_test.id,
        })

        slip = self.env['hr.payslip'].create({
            'name': 'Salary Slip - Active - April 2026',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.struct_test.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })

        self.assertFalse(slip.has_no_running_contract, "has_no_running_contract must be False for active contract!")

        work100 = slip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
        self.assertTrue(work100, "Active contract must generate WORK100 lines!")

        slip.action_compute_sheet()
        self.assertGreater(slip.net_wage, 0.0, "Net wage must be greater than 0 for active contract!")
        self.assertFalse(slip.has_zero_or_negative_net)

        # Validation must succeed
        slip.action_payslip_done()
        self.assertEqual(slip.state, 'done', "Payslip must reach done state!")

    def test_05_action_open_contract(self):
        """Test action_open_contract returns act_window action to view contract."""
        employee = self.env['hr.employee'].create({
            'name': 'Action Contract Employee',
            'company_id': self.company.id,
        })
        contract = self._configure_contract(employee, {
            'date_start': date(2026, 10, 1),
            'contract_date_start': date(2026, 10, 1),
        })
        slip = self.env['hr.payslip'].create({
            'name': 'Salary Slip Test Action',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.struct_test.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })
        action = slip.action_open_contract()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'hr.employee')
        self.assertEqual(action.get('res_id'), employee.id)
        self.assertEqual(action.get('state', {}).get('activeNotebookPages', {}).get(0), 'payroll_information')

    def test_06_no_employee_selected_no_banners(self):
        """When creating a draft payslip without an employee chosen yet, banners must NOT be shown."""
        slip = self.env['hr.payslip'].new({
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
            'company_id': self.company.id,
        })
        slip._compute_contract_status()
        slip._compute_has_bank_account()
        slip._compute_payslip_warning()
        self.assertFalse(slip.has_no_running_contract, "has_no_running_contract must be False when no employee is selected!")
        self.assertFalse(slip.has_zero_or_negative_net, "has_zero_or_negative_net must be False when no employee is selected!")
        self.assertFalse(slip.payslip_warning, "payslip_warning must be False when no employee is selected!")

