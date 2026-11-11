# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestHrSnapshot(common.TransactionCase):

    def setUp(self):
        super(TestHrSnapshot, self).setUp()
        self.Employee = self.env['hr.employee']
        self.Department = self.env['hr.department']
        self.Contract = self.env['hr.version']
        self.Payslip = self.env['hr.payslip']
        self.WorkedDays = self.env['hr.payslip.worked.days']

        # Setup base test records
        self.dept_engineering = self.Department.create({'name': 'Engineering'})
        self.dept_hr = self.Department.create({'name': 'Human Resources'})

        self.employee = self.Employee.create({
            'name': 'John Snapshot Tester',
            'identification_id': 'EMP1001',
            'department_id': self.dept_engineering.id,
            'hds_in_uan': '100000000001',
            'hds_in_pf_member_id': 'MH/BAN/0012345/000/0000101',
            'hds_in_epf_applicable': True,
            'hds_in_eps_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })

        self.contract = self.Contract.create({
            'name': 'John Contract',
            'employee_id': self.employee.id,
            'wage': 50000.0,
            'basic_salary': 30000.0,
            'hra': 10000.0,
            'da': 5000.0,
            'travel_allowance': 5000.0,
            'date_start': date(2026, 1, 1),
            'state': 'open',
        })

    def _create_payslip(self, date_from, date_to):
        payslip = self.Payslip.create({
            'name': f'Payslip for {self.employee.name}',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': date_from,
            'date_to': date_to,
        })
        # Add worked days lines
        self.WorkedDays.create({
            'name': 'Normal Working Days',
            'code': 'WORK100',
            'number_of_days': 22.0,
            'number_of_hours': 176.0,
            'contract_id': self.contract.id,
            'payslip_id': payslip.id,
        })
        self.WorkedDays.create({
            'name': 'Unpaid Leave Days',
            'code': 'UNPAID',
            'number_of_days': 2.0,
            'number_of_hours': 16.0,
            'contract_id': self.contract.id,
            'payslip_id': payslip.id,
        })
        return payslip

    def test_01_confirm_payslip_creates_linked_snapshot(self):
        """Test 1: Confirming a payslip creates exactly one bidirectional snapshot link."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        self.assertFalse(payslip.hds_snapshot_id)

        payslip.action_payslip_done()

        self.assertTrue(payslip.hds_snapshot_id, "Payslip should have an associated snapshot.")
        snapshot = payslip.hds_snapshot_id
        self.assertEqual(snapshot.payslip_id, payslip, "Snapshot should link back to payslip.")
        self.assertEqual(snapshot.employee_id, self.employee)
        self.assertEqual(snapshot.employee_code, 'EMP1001')
        self.assertEqual(snapshot.department, 'Engineering')
        self.assertEqual(snapshot.wage, 50000.0)
        self.assertEqual(snapshot.basic_salary, 30000.0)
        self.assertEqual(snapshot.hra, 10000.0)
        self.assertEqual(snapshot.working_days, 24.0)
        self.assertEqual(snapshot.paid_days, 22.0)
        self.assertEqual(snapshot.lop_days, 2.0)

    def test_02_basic_salary_change_post_confirmation(self):
        """Test 2: Changing basic salary post confirmation does not alter old snapshot."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        payslip.action_payslip_done()
        snapshot = payslip.hds_snapshot_id

        # Update live contract salary
        self.contract.write({'basic_salary': 40000.0, 'wage': 60000.0})

        self.assertEqual(snapshot.basic_salary, 30000.0, "Snapshot Basic Salary must stay at frozen value 30000.")
        self.assertEqual(snapshot.wage, 50000.0, "Snapshot Wage must stay at frozen value 50000.")

    def test_03_department_change_post_confirmation(self):
        """Test 3: Changing department post confirmation preserves original snapshot department."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        payslip.action_payslip_done()
        snapshot = payslip.hds_snapshot_id

        # Transfer employee to HR department
        self.employee.write({'department_id': self.dept_hr.id})

        self.assertEqual(snapshot.department, 'Engineering', "Snapshot department text must remain 'Engineering'.")

    def test_04_statutory_details_change_post_confirmation(self):
        """Test 4: Changing statutory fields preserves old snapshot values."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        payslip.action_payslip_done()
        snapshot = payslip.hds_snapshot_id

        # Update statutory fields on employee
        self.employee.write({
            'hds_in_uan': '999999999999',
            'hds_in_pf_member_id': 'NEW_PF_ID',
            'hds_in_pf_contribution_basis': 'actual_basic',
        })

        self.assertEqual(snapshot.uan, '100000000001')
        self.assertEqual(snapshot.pf_member_id, 'MH/BAN/0012345/000/0000101')
        self.assertIn('Statutory Wage Ceiling', snapshot.pf_wage_basis)

    def test_05_multi_period_payslips_with_salary_revision(self):
        """Test 5: July and August snapshots reflect period-specific values across salary changes."""
        july_payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        july_payslip.action_payslip_done()
        july_snapshot = july_payslip.hds_snapshot_id

        # Revise salary in August
        self.contract.write({'basic_salary': 35000.0, 'wage': 55000.0})

        aug_payslip = self._create_payslip(date(2026, 8, 1), date(2026, 8, 31))
        aug_payslip.action_payslip_done()
        aug_snapshot = aug_payslip.hds_snapshot_id

        self.assertNotEqual(july_snapshot.id, aug_snapshot.id)
        self.assertEqual(july_snapshot.basic_salary, 30000.0)
        self.assertEqual(aug_snapshot.basic_salary, 35000.0)
        self.assertEqual(july_snapshot.payroll_period, '07/2026')
        self.assertEqual(aug_snapshot.payroll_period, '08/2026')

    def test_06_archiving_employee_preserves_snapshot(self):
        """Test 6: Archiving or modifying employee after confirmation does not alter snapshot."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        payslip.action_payslip_done()
        snapshot = payslip.hds_snapshot_id

        self.employee.write({'active': False, 'name': 'Archived John'})

        self.assertTrue(snapshot.exists())
        self.assertEqual(snapshot.employee_code, 'EMP1001')
        self.assertEqual(snapshot.department, 'Engineering')

    def test_07_reconfirming_payslip_is_idempotent(self):
        """Test 7: Re-confirming an already done payslip does not duplicate or mutate snapshot."""
        payslip = self._create_payslip(date(2026, 7, 1), date(2026, 7, 31))
        payslip.action_payslip_done()
        initial_snapshot = payslip.hds_snapshot_id

        # Cancel and re-confirm
        payslip.action_payslip_cancel()
        payslip.action_payslip_done()

        self.assertEqual(payslip.hds_snapshot_id.id, initial_snapshot.id, "Snapshot ID should not change upon re-confirmation.")
        snapshots_count = self.env['hds.hr.snapshot'].search_count([('payslip_id', '=', payslip.id)])
        self.assertEqual(snapshots_count, 1, "Exactly one snapshot should exist for the payslip.")
