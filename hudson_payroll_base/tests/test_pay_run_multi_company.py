# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestPayRunMultiCompany(TransactionCase):
    """
    Test suite for Multi-Company isolation in Pay Run batches and the Add Employees wizard.
    Ensures standalone / off-cycle payslips belonging to sister companies are never hijacked or re-linked.
    """

    @classmethod
    def _gc_filestore(cls):
        # Override Windows filestore temp file GC assertion
        pass

    def setUp(self):
        super().setUp()
        self.Company = self.env['res.company']
        self.Employee = self.env['hr.employee']
        self.Payslip = self.env['hr.payslip']
        self.PayRun = self.env['hr.payslip.run']
        self.Contract = self.env['hr.version']
        self.Structure = self.env['hr.payroll.structure']
        self.Wizard = self.env['hr.payslip.employees']

        # 1. Ensure two distinct companies
        self.company_a = self.env.company
        self.company_b = self.Company.search([('id', '!=', self.company_a.id)], limit=1)
        if not self.company_b:
            self.company_b = self.Company.create({
                'name': 'Sister Company Test',
                'currency_id': self.company_a.currency_id.id,
            })

        # 2. Reusable Salary Structure
        self.struct = self.Structure.search([], limit=1)
        if not self.struct:
            self.struct = self.Structure.create({
                'name': 'Test Regular Pay',
                'code': 'TEST_REG',
            })

        # 3. Create Employees in respective companies
        self.emp_a = self.Employee.create({
            'name': 'Employee A (Company A)',
            'company_id': self.company_a.id,
        })
        self.contract_a = self._configure_contract(self.emp_a, {
            'wage': 50000.0,
            'struct_id': self.struct.id,
            'company_id': self.company_a.id,
        })

        self.emp_b = self.Employee.create({
            'name': 'Employee B (Company B)',
            'company_id': self.company_b.id,
        })
        self.contract_b = self._configure_contract(self.emp_b, {
            'wage': 60000.0,
            'struct_id': self.struct.id,
            'company_id': self.company_b.id,
        })

    def _configure_contract(self, employee, vals):
        contract = employee.version_id
        if not contract:
            contract = self.Contract.search([('employee_id', '=', employee.id)], limit=1)
        if contract:
            contract.write(vals)
        else:
            contract = self.Contract.create({
                'name': f"Contract {employee.name}",
                'employee_id': employee.id,
                **vals
            })
            employee.version_id = contract
        return contract

    def test_01_wizard_ignores_sister_company_off_cycle_payslip(self):
        """
        Verify that an unattached off-cycle payslip under Company A is NOT captured or re-linked
        when running Add Employees inside a Pay Run belonging to Company B.
        """
        # Standalone payslip under Company A
        slip_a = self.Payslip.create({
            'name': 'Off-Cycle Slip - Emp A - Oct 2026',
            'employee_id': self.emp_a.id,
            'contract_id': self.contract_a.id,
            'struct_id': self.struct.id,
            'company_id': self.company_a.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': False,
        })
        self.assertFalse(slip_a.payslip_run_id)

        # Pay Run batch under Company B
        run_b = self.PayRun.create({
            'name': 'Oct 2026 Pay Run - Company B',
            'company_id': self.company_b.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })

        # Run wizard with context having both companies active (multi-company session)
        ctx = {
            'active_id': run_b.id,
            'active_model': 'hr.payslip.run',
            'allowed_company_ids': [self.company_b.id, self.company_a.id],
            'test_mode': True,
        }

        # Initialize wizard
        defaults = self.Wizard.with_context(ctx).default_get(['employee_ids', 'company_id'])
        self.assertEqual(defaults.get('company_id'), self.company_b.id)

        # Instantiate wizard and attempt to compute
        wizard = self.Wizard.with_context(ctx).create({
            'company_id': self.company_b.id,
            'employee_ids': [(6, 0, [self.emp_a.id, self.emp_b.id])],
        })
        wizard.compute_sheet()

        # Employee A's slip must NOT be linked to Company B's pay run
        slip_a.invalidate_recordset()
        self.assertFalse(
            slip_a.payslip_run_id,
            "Off-cycle payslip belonging to Company A was incorrectly attached to Company B's pay run!"
        )

        # Company B's batch must not contain slip_a
        self.assertNotIn(slip_a, run_b.slip_ids)

        # Employee B should have a payslip under Company B in the run
        slip_b = run_b.slip_ids.filtered(lambda s: s.employee_id == self.emp_b)
        self.assertTrue(slip_b, "Employee B's payslip should have been created in Company B's pay run.")
        self.assertEqual(slip_b.company_id, self.company_b)

    def test_02_wizard_attaches_same_company_off_cycle_payslip(self):
        """
        Verify that an unattached off-cycle payslip under the SAME company (Company B)
        IS properly re-linked when running Add Employees on Company B's Pay Run.
        """
        slip_b_offcycle = self.Payslip.create({
            'name': 'Off-Cycle Slip - Emp B - Oct 2026',
            'employee_id': self.emp_b.id,
            'contract_id': self.contract_b.id,
            'struct_id': self.struct.id,
            'company_id': self.company_b.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': False,
        })

        run_b = self.PayRun.create({
            'name': 'Oct 2026 Pay Run - Company B',
            'company_id': self.company_b.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })

        ctx = {
            'active_id': run_b.id,
            'active_model': 'hr.payslip.run',
            'allowed_company_ids': [self.company_b.id],
            'test_mode': True,
        }

        wizard = self.Wizard.with_context(ctx).create({
            'company_id': self.company_b.id,
            'employee_ids': [(6, 0, [self.emp_b.id])],
        })
        wizard.compute_sheet()

        slip_b_offcycle.invalidate_recordset()
        self.assertEqual(
            slip_b_offcycle.payslip_run_id,
            run_b,
            "Off-cycle payslip under Company B should be linked to Company B's pay run."
        )

    def test_03_payslip_company_alignment_constraint(self):
        """
        Verify that hr.payslip raises a ValidationError if payslip.company_id != payslip_run_id.company_id.
        """
        run_b = self.PayRun.create({
            'name': 'Oct 2026 Pay Run - Company B',
            'company_id': self.company_b.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })

        slip_a = self.Payslip.create({
            'name': 'Payslip Company A',
            'employee_id': self.emp_a.id,
            'contract_id': self.contract_a.id,
            'struct_id': self.struct.id,
            'company_id': self.company_a.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })

        with self.assertRaises(ValidationError):
            slip_a.write({'payslip_run_id': run_b.id})

    def test_04_payrun_creation_wizard_multi_company(self):
        """
        Verify that the New Pay Run creation wizard respects the selected company
        when multiple companies are enabled in allowed_company_ids.
        """
        Department = self.env['hr.department']
        dept_a = Department.create({'name': 'Engineering A', 'company_id': self.company_a.id})
        dept_b = Department.create({'name': 'Engineering B', 'company_id': self.company_b.id})

        ctx = {
            'allowed_company_ids': [self.company_a.id, self.company_b.id],
            'test_mode': True,
        }

        wizard = self.env['hudson.payroll.payrun.wizard'].with_context(ctx).new({
            'name': 'Nov 2026 Batch Test',
            'company_id': self.company_a.id,
            'department_ids': [(6, 0, [dept_a.id])],
            'date_start': date(2026, 11, 1),
            'date_end': date(2026, 11, 30),
        })

        # Switch company to Company B and run onchange
        wizard.company_id = self.company_b
        wizard._onchange_company_id()
        self.assertNotIn(
            dept_a.id,
            wizard.department_ids.ids,
            "Incompatible department belonging to Company A must be cleared when switching to Company B."
        )

        # Create record in DB and generate batch
        wizard_record = self.env['hudson.payroll.payrun.wizard'].with_context(ctx).create({
            'name': 'Nov 2026 Batch Test',
            'company_id': self.company_b.id,
            'date_start': date(2026, 11, 1),
            'date_end': date(2026, 11, 30),
        })
        action = wizard_record.action_confirm_and_generate()
        self.assertEqual(action.get('res_model'), 'hr.payslip.run')

        # Find the created pay run
        run = self.PayRun.search([('name', '=', 'Nov 2026 Batch Test')], limit=1)
        self.assertTrue(run, "Pay run batch should be created.")
        self.assertEqual(run.company_id, self.company_b, "Created pay run must belong to Company B.")

        # Ensure generated payslips belong strictly to Company B and its employees
        self.assertTrue(run.slip_ids, "Payslips should be generated for Company B.")
        for slip in run.slip_ids:
            self.assertEqual(slip.company_id, self.company_b, "Generated slip must belong to Company B.")
            self.assertNotEqual(slip.employee_id, self.emp_a, "Company A employee must not be in Company B pay run.")

    def test_05_branch_company_fiscal_year_delegation(self):
        """
        Verify that branch companies automatically synchronize root-delegated fields
        (such as fiscalyear_last_month and fiscalyear_last_day) from the parent/root company,
        preventing 'The Fiscal year Last Month of a subsidiary must be the same as it's root company' errors.
        """
        # Configure parent with Dec fiscal year end (month 12)
        if 'fiscalyear_last_month' in self.company_a._fields:
            self.company_a.write({'fiscalyear_last_month': '12', 'fiscalyear_last_day': 31})

            # 1. Simulate UI branch creation where default_parent_id is in context (Branches tab One2many)
            vals = {
                'name': 'Test Branch UI Context Flow',
                'country_id': self.env.ref('base.in').id,
            }
            branch = self.Company.with_context(default_parent_id=self.company_a.id).create(vals)
            self.assertEqual(
                branch.fiscalyear_last_month,
                '12',
                "Branch company created with default_parent_id must inherit parent's fiscalyear_last_month (12)."
            )
            self.assertEqual(
                branch.fiscalyear_last_day,
                31,
                "Branch company created with default_parent_id must inherit parent's fiscalyear_last_day (31)."
            )

            # 2. Simulate chart template loading or external write attempting to change fiscalyear_last_month to '3'
            branch.write({'fiscalyear_last_month': '3'})
            self.assertEqual(
                branch.fiscalyear_last_month,
                '12',
                "Direct write attempting to change fiscalyear_last_month on branch must stay aligned with root company (12)."
            )

            # 3. Test onchange
            new_branch = self.Company.new({'parent_id': self.company_a.id})
            new_branch._onchange_parent_id()
            self.assertEqual(new_branch.fiscalyear_last_month, '12')

    def test_06_add_employees_wizard_excludes_already_present_employees(self):
        """
        Verify that hr.payslip.employees wizard excludes employees who already
        have payslips in the pay run, preventing duplicate listing.
        """
        run = self.PayRun.create({
            'name': 'Test Run - Exclusion Check',
            'company_id': self.company_b.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        # Add employee B's payslip to the run
        self.Payslip.create({
            'name': 'Slip - Emp B',
            'employee_id': self.emp_b.id,
            'contract_id': self.contract_b.id,
            'struct_id': self.struct.id,
            'company_id': self.company_b.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': run.id,
        })

        ctx = {
            'active_id': run.id,
            'active_model': 'hr.payslip.run',
        }
        wiz = self.Wizard.with_context(ctx).create({'company_id': self.company_b.id})
        self.assertIn(self.emp_b, wiz.existing_employee_ids, "Existing employees in pay run must be identified.")

        defaults = self.Wizard.with_context(ctx).default_get(['existing_employee_ids', 'company_id'])
        self.assertIn(self.emp_b.id, defaults.get('existing_employee_ids', [[]])[0][2])

    def test_07_company_bank_account_in_payrun_and_pay_wizard(self):
        """
        Verify that Company Bank Account can be configured on a Pay Run,
        is auto-defaulted to the Pay wizard, and correctly links to payment advice.
        """
        PartnerBank = self.env['res.partner.bank']
        co_bank = PartnerBank.create({
            'acc_number': 'CO-DISBURSE-BANK-101',
            'account_number': 'CO-DISBURSE-BANK-101',
            'partner_id': self.company_b.partner_id.id,
            'company_id': self.company_b.id,
        })

        run = self.PayRun.create({
            'name': 'Test Run - Company Bank Account',
            'company_id': self.company_b.id,
            'company_bank_id': co_bank.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        self.assertEqual(run.company_bank_id, co_bank)

        # Ensure employee B has a bank account configured for payment advice
        emp_bank = PartnerBank.create({
            'acc_number': 'EMP-B-BANK-001',
            'partner_id': self.emp_b.work_contact_id.id if self.emp_b.work_contact_id else self.company_b.partner_id.id,
            'company_id': self.company_b.id,
        })
        self.emp_b.bank_account_id = emp_bank

        # Create payslip in run
        slip = self.Payslip.create({
            'name': 'Slip - Emp B - Paid Check',
            'employee_id': self.emp_b.id,
            'contract_id': self.contract_b.id,
            'struct_id': self.struct.id,
            'company_id': self.company_b.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': run.id,
        })
        slip.action_compute_sheet()
        # Only validated payslips can be paid
        slip.action_payslip_done()

        # Open Pay Wizard
        ctx = {
            'active_id': run.id,
            'active_model': 'hr.payslip.run',
        }
        pay_wiz = self.env['hr.payslip.run.pay.wizard'].with_context(ctx).create({
            'payslip_run_id': run.id,
            'mode': 'advice',
            'company_bank_id': co_bank.id,
        })
        self.assertEqual(pay_wiz.company_bank_id, co_bank)
        advice = pay_wiz._ensure_payment_advice()
        # Verify mandatory check: wizard without company bank account cannot generate PDF or XLSX
        pay_wiz_empty = self.env['hr.payslip.run.pay.wizard'].with_context(ctx).create({
            'payslip_run_id': run.id,
            'mode': 'advice',
            'company_bank_id': False,
        })
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            pay_wiz_empty.action_create_pdf()
        with self.assertRaises(UserError):
            pay_wiz_empty.action_create_xlsx()
        with self.assertRaises(UserError):
            pay_wiz_empty.action_mark_paid()

        # Verify New Pay Run wizard defaults company_bank_id
        new_payrun_wiz_cls = self.env['hudson.payroll.payrun.wizard'].with_company(self.company_b)
        wiz_defaults = new_payrun_wiz_cls.default_get(['company_id', 'company_bank_id'])
        self.assertEqual(wiz_defaults.get('company_bank_id'), co_bank.id)

        # Verify quick bank creation via name_create
        quick_bank_id, quick_bank_name = PartnerBank.with_context(
            default_company_id=self.company_b.id,
            default_partner_id=self.company_b.partner_id.id,
        ).name_create('QUICK-CO-BANK-999')
        quick_bank = PartnerBank.browse(quick_bank_id)
        self.assertEqual(quick_bank.partner_id, self.company_b.partner_id)
        self.assertEqual(quick_bank.company_id, self.company_b)

        # Verify existing bank lookup in name_create (idempotency)
        reused_bank_id, _ = PartnerBank.with_context(
            default_company_id=self.company_b.id,
            default_partner_id=self.company_b.partner_id.id,
        ).name_create('QUICK-CO-BANK-999')
        self.assertEqual(reused_bank_id, quick_bank_id)




