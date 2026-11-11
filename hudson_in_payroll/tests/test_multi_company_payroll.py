# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import common
from odoo.exceptions import ValidationError


class TestMultiCompanyPayroll(common.TransactionCase):
    """
    Test suite verifying that standard salary rules and structures are company-agnostic
    and function seamlessly across multiple companies without Access Errors or empty payslips.
    """

    def setUp(self):
        super().setUp()
        self.Company = self.env['res.company']
        self.Employee = self.env['hr.employee']
        self.Payslip = self.env['hr.payslip']
        self.Structure = self.env.ref('hudson_payroll_base.structure_base')
        self.SalaryRule = self.env['hr.salary.rule']
        self.Category = self.env['hr.salary.rule.category']

        # Existing primary company
        self.company_main = self.env.ref('base.main_company')
        self.country_in = self.env.ref('base.in')

        # Create secondary company (e.g. Ouseph Group)
        self.company_secondary = self.Company.create({
            'name': 'Ouseph Group',
            'country_id': self.country_in.id,
            'resource_calendar_id': self.company_main.resource_calendar_id.id if self.company_main.resource_calendar_id else False,
            'hds_in_epf_applicable': True,
            'hds_in_eps_applicable': True,
            'hds_in_edli_applicable': True,
            'hds_in_esic_applicable': True,
        })

    def test_01_standard_records_are_company_agnostic(self):
        """Standard structures, rules, and categories must have company_id=False (shared)."""
        self.assertFalse(
            self.Structure.company_id,
            "Standard structure 'structure_base' must be shared across all companies (company_id=False)."
        )

        structure_worker = self.env.ref('hudson_payroll_base.structure_worker', raise_if_not_found=False)
        if structure_worker:
            self.assertFalse(
                structure_worker.company_id,
                "Standard structure 'structure_worker' must be shared across all companies (company_id=False)."
            )

        core_rules = self.SalaryRule.search([('struct_id', '=', self.Structure.id)])
        self.assertTrue(len(core_rules) > 0, "Structure must have salary rules.")
        for rule in core_rules:
            self.assertFalse(
                rule.company_id,
                f"Standard salary rule '{rule.code}' must have company_id=False to be shared across companies."
            )

    def test_02_secondary_company_visibility(self):
        """A user working inside the secondary company must see all shared structures and rules."""
        env_secondary = self.env(context={'allowed_company_ids': [self.company_secondary.id]})

        visible_structs = env_secondary['hr.payroll.structure'].search([('id', '=', self.Structure.id)])
        self.assertEqual(len(visible_structs), 1, "structure_base must be visible to the secondary company.")

        visible_rules = env_secondary['hr.salary.rule'].search([('struct_id', '=', self.Structure.id)])
        self.assertTrue(len(visible_rules) >= 5, "Salary rules must be visible to the secondary company.")

    def test_03_secondary_company_payslip_computation(self):
        """Payslips generated inside the secondary company must compute successfully with non-zero pay."""
        # Create an employee in secondary company
        employee = self.Employee.create({
            'name': 'Secondary Co Employee',
            'company_id': self.company_secondary.id,
            'hds_in_epf_applicable': True,
        })

        # Set up version / contract in secondary company
        contract = employee.version_id
        if contract:
            contract.write({
                'wage': 50000.0,
                'basic_salary': 30000.0,
                'struct_id': self.Structure.id,
                'date_start': '2026-04-01',
                'pay_by_attendance': False,
                'enable_attendance_threshold': False,
            })

        # Create payslip in secondary company
        payslip = self.Payslip.create({
            'name': 'Payslip - Secondary Co',
            'employee_id': employee.id,
            'contract_id': contract.id if contract else False,
            'struct_id': self.Structure.id,
            'company_id': self.company_secondary.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })

        # Compute payslip lines
        payslip.compute_sheet()

        # Verify that salary rules computed lines (not 0.00 and not empty!)
        self.assertTrue(len(payslip.line_ids) > 0, "Payslip in secondary company must generate salary lines.")

        basic_line = payslip.line_ids.filtered(lambda l: l.code == 'BASIC')
        self.assertTrue(basic_line, "BASIC salary line must be generated.")
        self.assertGreater(basic_line.total, 0.0, "BASIC salary must be greater than 0.")

        net_line = payslip.line_ids.filtered(lambda l: l.code == 'NET')
        self.assertTrue(net_line, "NET salary line must be generated.")
        self.assertGreater(net_line.total, 0.0, "NET salary must be greater than 0.")

    def test_04_company_specific_rule_override(self):
        """A company-specific salary rule override takes priority over the shared rule."""
        rule_basic_shared = self.SalaryRule.search([
            ('code', '=', 'BASIC'),
            ('struct_id', '=', self.Structure.id),
            ('company_id', '=', False),
        ], limit=1)
        self.assertTrue(rule_basic_shared, "Shared BASIC rule must exist.")

        # Create a company-specific BASIC override for company_secondary
        rule_basic_override = self.SalaryRule.create({
            'name': 'Basic Salary (Ouseph Custom)',
            'code': 'BASIC',
            'category_id': rule_basic_shared.category_id.id,
            'struct_id': self.Structure.id,
            'company_id': self.company_secondary.id,
            'sequence': rule_basic_shared.sequence,
            'condition_select': 'none',
            'amount_select': 'code',
            'amount_python_compute': 'result = 99999.0',
        })

        # Test get_all_rules under secondary company context
        struct_under_secondary = self.Structure.with_context(allowed_company_ids=[self.company_secondary.id])
        rules = struct_under_secondary.get_all_rules()
        effective_basic = rules.filtered(lambda r: r.code == 'BASIC')

        self.assertEqual(len(effective_basic), 1, "Exactly one BASIC rule should be returned.")
        self.assertEqual(
            effective_basic.id,
            rule_basic_override.id,
            "Company-specific rule must override the shared rule for that company."
        )

    def test_05_payment_mode_multi_company_isolation(self):
        """Verifies that payment modes created in one company are isolated from other companies."""
        # 1. Seeded payment modes must be global (company_id=False)
        seeded_bank = self.env.ref('hudson_in_payroll.payment_mode_bank_transfer', raise_if_not_found=False)
        if seeded_bank:
            self.assertFalse(
                seeded_bank.company_id,
                "Seeded payment modes (e.g. Bank Transfer) must have company_id=False to be accessible across all companies."
            )

        # 2. Setup non-superuser users for each company to evaluate record rules
        user_main_vals = {
            'name': 'Main Co Payroll User',
            'login': 'user_main_payroll_pm',
            'email': 'user_main_pm@example.com',
            'company_id': self.company_main.id,
            'company_ids': [(6, 0, [self.company_main.id])],
        }
        if 'group_ids' in self.env['res.users']._fields:
            user_main_vals['group_ids'] = [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('hudson_payroll_base.group_payroll_user').id),
            ]
        user_main = self.env['res.users'].create(user_main_vals)

        user_sec_vals = {
            'name': 'Secondary Co Payroll User',
            'login': 'user_sec_payroll_pm',
            'email': 'user_sec_pm@example.com',
            'company_id': self.company_secondary.id,
            'company_ids': [(6, 0, [self.company_secondary.id])],
        }
        if 'group_ids' in self.env['res.users']._fields:
            user_sec_vals['group_ids'] = [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('hudson_payroll_base.group_payroll_user').id),
            ]
        user_sec = self.env['res.users'].create(user_sec_vals)

        # 3. Create company-specific payment modes
        mode_main = self.env['hds.payment.mode'].create({
            'name': 'Main Co Cheque Batch',
            'code': 'main_cheque_batch',
            'company_id': self.company_main.id,
        })
        mode_sec = self.env['hds.payment.mode'].create({
            'name': 'Ouseph Cash Counter',
            'code': 'ouseph_cash_counter',
            'company_id': self.company_secondary.id,
            'is_cash': True,
        })

        # 4. Record rule isolation check
        modes_for_main = self.env['hds.payment.mode'].with_user(user_main).search([])
        self.assertIn(mode_main, modes_for_main, "Main Co user must see Main Co payment mode.")
        self.assertNotIn(mode_sec, modes_for_main, "Main Co user must NOT see Secondary Co payment mode.")
        if seeded_bank:
            self.assertIn(seeded_bank, modes_for_main, "Main Co user must see global seeded payment mode.")

        modes_for_sec = self.env['hds.payment.mode'].with_user(user_sec).search([])
        self.assertIn(mode_sec, modes_for_sec, "Secondary Co user must see Secondary Co payment mode.")
        self.assertNotIn(mode_main, modes_for_sec, "Secondary Co user must NOT see Main Co payment mode.")
        if seeded_bank:
            self.assertIn(seeded_bank, modes_for_sec, "Secondary Co user must see global seeded payment mode.")

        # 5. Model constraint checks on hr.employee
        emp_sec = self.Employee.create({
            'name': 'Employee In Secondary Co',
            'company_id': self.company_secondary.id,
        })
        # Allowed: assigning secondary mode
        emp_sec.write({'hds_in_payment_mode': mode_sec.id})
        self.assertEqual(emp_sec.hds_in_payment_mode.id, mode_sec.id)

        # Prohibited: assigning main company mode to secondary company employee
        with self.assertRaises(ValidationError):
            emp_sec.write({'hds_in_payment_mode': mode_main.id})

        # 6. Model constraint checks on hr.payslip
        payslip_sec = self.Payslip.create({
            'name': 'Payslip Sec Test',
            'employee_id': emp_sec.id,
            'company_id': self.company_secondary.id,
            'date_from': '2026-05-01',
            'date_to': '2026-05-31',
        })
        # Prohibited: assigning main company mode to secondary company payslip
        with self.assertRaises(ValidationError):
            payslip_sec.write({'hds_in_payment_mode': mode_main.id})

