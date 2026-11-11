# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase


class TestDuplicatePayslips(TransactionCase):
    """
    Test suite for Duplicate Payslips detection in Pay Run batches and Wizards.
    Matches Odoo Online flagging duplicate payslips and prompting a warning popup.
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    def setUp(self):
        super().setUp()
        self.Company = self.env['res.company']
        self.Employee = self.env['hr.employee']
        self.Payslip = self.env['hr.payslip']
        self.PayRun = self.env['hr.payslip.run']
        self.Contract = self.env['hr.version']
        self.Structure = self.env['hr.payroll.structure']
        self.company = self.env.company

        # Reusable Salary Structure
        self.struct = self.Structure.search([], limit=1)
        if not self.struct:
            self.struct = self.Structure.create({
                'name': 'Test Regular Pay',
                'code': 'TEST_REG',
            })

        # Create Employee
        self.employee = self.Employee.create({
            'name': 'Duplicate Test Employee',
            'company_id': self.company.id,
        })
        self.contract = self.Contract.create({
            'name': 'Contract Duplicate Test',
            'employee_id': self.employee.id,
            'wage': 50000.0,
            'struct_id': self.struct.id,
            'company_id': self.company.id,
        })
        self.employee.version_id = self.contract

    def test_01_duplicate_payslip_flagged_and_validation_intercepted(self):
        """
        Verify that when a payslip already exists for an employee in that month:
        1. Newly generated payslip in pay run is flagged as 'Duplicate' in payslip_warning.
        2. Pay run batch computes has_duplicate_payslips = True.
        3. action_batch_validate() intercepts with the duplicate warning wizard.
        4. action_remove_and_validate() removes duplicate and successfully validates the batch.
        """
        # 1. Existing standalone payslip generated for Oct 2026
        existing_slip = self.Payslip.create({
            'name': 'Salary Slip - Duplicate Test Employee - October 2026',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.struct.id,
            'company_id': self.company.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'state': 'draft',
        })
        self.assertFalse(existing_slip.has_duplicate_payslip)

        # 2. Pay run batch for October 2026
        run = self.PayRun.create({
            'name': 'October 2026 Pay Run Batch',
            'company_id': self.company.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
            'state': 'draft',
        })

        # Create a second payslip for the same employee inside the batch
        batch_slip = self.Payslip.create({
            'name': 'Salary Slip - Duplicate Test Employee - October 2026 (Batch)',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.struct.id,
            'company_id': self.company.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': run.id,
            'state': 'draft',
        })

        # Recompute duplicate status
        self.Payslip._recompute_overlapping_duplicate_status()
        run._compute_duplicate_payslips()

        # Both payslips are aware of the conflict
        self.assertTrue(batch_slip.has_duplicate_payslip)
        self.assertTrue(existing_slip.has_duplicate_payslip)
        self.assertIn('Duplicate', batch_slip.payslip_warning or '')

        # Pay Run batch flags duplicate
        self.assertTrue(run.has_duplicate_payslips)
        self.assertEqual(run.duplicate_payslip_count, 1)

        # 3. action_batch_validate intercepts with duplicate warning wizard popup
        res = run.action_batch_validate()
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get('res_model'), 'hr.payslip.run.duplicate.wizard')
        wizard_id = res.get('res_id')
        self.assertTrue(wizard_id)

        wizard = self.env['hr.payslip.run.duplicate.wizard'].browse(wizard_id)
        self.assertEqual(wizard.duplicate_count, 1)

        # 4. Remove duplicate and validate
        wizard.action_remove_and_validate()
        self.assertEqual(run.state, 'confirmed')
        self.assertFalse(batch_slip.exists())
        self.assertFalse(existing_slip.has_duplicate_payslip)

    def test_02_standalone_payslip_triggers_duplicate_in_payrun_wizard(self):
        """
        Verify that when a standalone payslip exists for Nov 2026 (created via Payslips tab),
        running the Pay Run employee selection wizard generates a payslip in the batch
        and immediately flags it as Duplicate with warning ribbon and notification.
        """
        # 1. Create standalone payslip in Payslips tab (payslip_run_id = False)
        standalone_slip = self.Payslip.create({
            'name': 'Salary Slip - Duplicate Test Employee - November 2026',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.struct.id,
            'company_id': self.company.id,
            'date_from': date(2026, 11, 1),
            'date_to': date(2026, 11, 30),
            'state': 'draft',
        })
        self.assertFalse(standalone_slip.has_duplicate_payslip)

        # 2. Create Pay Run for November 2026
        run = self.PayRun.create({
            'name': 'November 2026 Pay Run',
            'company_id': self.company.id,
            'date_start': date(2026, 11, 1),
            'date_end': date(2026, 11, 30),
            'state': 'draft',
        })

        # 3. Wizard generates payslips for selected employee
        wizard = self.env['hr.payslip.employees'].with_context(
            active_id=run.id,
            active_model='hr.payslip.run'
        ).create({
            'employee_ids': [(6, 0, [self.employee.id])]
        })
        res = wizard.action_select()

        # Standalone slip should remain untouched in the Payslips tab
        self.assertFalse(standalone_slip.payslip_run_id)

        # Pay Run batch should have 1 new payslip and flag duplicate
        self.assertEqual(len(run.slip_ids), 1)
        batch_slip = run.slip_ids[0]
        self.assertNotEqual(batch_slip.id, standalone_slip.id)

        # Duplicate status checks
        self.assertTrue(batch_slip.has_duplicate_payslip)
        self.assertEqual(batch_slip.duplicate_payslip_id.id, standalone_slip.id)
        self.assertTrue(run.has_duplicate_payslips)
        self.assertEqual(run.duplicate_payslip_count, 1)
        self.assertIn('Duplicate', batch_slip.payslip_warning or '')

        # Action returned should be client warning notification
        self.assertEqual(res.get('type'), 'ir.actions.client')
        self.assertEqual(res.get('tag'), 'display_notification')

