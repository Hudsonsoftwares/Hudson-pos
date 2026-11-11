# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo import SUPERUSER_ID
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPayslipDms(TransactionCase):
    """A validated payslip's PDF is stored in Employees / <employee> / Payroll / <tax year>."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.hds_dms_store_payslips = True
        cls.structure = cls.env.ref('hudson_payroll_base.structure_base')
        cls.employee = cls._employee('Payroll Dms Employee One', 'payroll.dms.one@example.com')
        cls.other = cls._employee('Payroll Dms Employee Two', 'payroll.dms.two@example.com')

    @classmethod
    def _employee(cls, name, login):
        user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': name, 'login': login, 'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        employee = cls.env['hr.employee'].create({'name': name, 'user_id': user.id, 'company_id': cls.company.id})
        vals = {'wage': 30000.0, 'basic_salary': 15000.0, 'date_version': date(2026, 1, 1),
                'struct_id': cls.structure.id}
        Version = cls.env['hr.version']
        if 'contract_date_start' in Version._fields:
            vals['contract_date_start'] = date(2026, 1, 1)
        if 'pay_by_attendance' in Version._fields:
            vals['pay_by_attendance'] = False
        employee.version_id.write(vals)
        return employee

    def _payslip(self, employee=None, start=date(2026, 10, 1), end=date(2026, 10, 31), compute=True):
        employee = employee or self.employee
        slip = self.env['hr.payslip'].create({
            'name': f'Dms {employee.name} {start}', 'employee_id': employee.id, 'company_id': self.company.id,
            'contract_id': employee.version_id.id, 'struct_id': self.structure.id,
            'date_from': start, 'date_to': end})
        if compute:
            slip.action_compute_sheet()
        return slip

    def _validate(self, slip):
        slip.action_payslip_done()
        self.assertEqual(slip.hds_dms_state, 'pending')
        self.env['hr.payslip']._cron_hds_dms_store_payslips()
        return slip.hds_dms_file_id

    def test_validated_payslip_is_stored_in_the_employee_folder(self):
        slip = self._payslip()
        dms_file = self._validate(slip)
        self.assertEqual(slip.hds_dms_state, 'stored', slip.hds_dms_error)
        self.assertEqual(dms_file.name, 'Payroll Dms Employee One - October 2026.pdf')
        self.assertEqual(dms_file.directory_id.name, '2026-27')
        self.assertEqual(dms_file.directory_id.parent_id.name, 'Payroll')
        self.assertEqual(dms_file.directory_id.parent_id.parent_id, self.employee.dms_directory_id)
        self.assertTrue(dms_file.with_context(bin_size=False).content, "The PDF is stored")
        self.assertEqual(dms_file.create_uid.id, SUPERUSER_ID, "Created by the system, not the validating user")

    def test_reset_to_draft_and_revalidate_replace_the_same_file(self):
        slip = self._payslip()
        dms_file = self._validate(slip)
        slip.action_payslip_draft()
        self.assertEqual(slip.hds_dms_state, 'none')
        self.assertTrue(dms_file.with_context(active_test=False).is_trashed, "Draft payslip: PDF in the Trash")
        slip.action_compute_sheet()
        self.assertEqual(self._validate(slip), dms_file, "Validated again: the same document is reused")
        self.assertFalse(dms_file.is_trashed)
        self.assertEqual(self.env['dms.file'].with_context(active_test=False).search_count(
            [('directory_id', '=', dms_file.directory_id.id)]), 1)

    def test_cancelled_payslip_moves_the_file_to_the_trash(self):
        slip = self._payslip()
        dms_file = self._validate(slip)
        slip.action_payslip_cancel()
        self.assertEqual(slip.hds_dms_state, 'none')
        self.assertTrue(dms_file.with_context(active_test=False).is_trashed)

    def test_two_payslips_of_a_month_get_distinct_names(self):
        first = self._payslip(start=date(2026, 10, 1), end=date(2026, 10, 15))
        second = self._payslip(start=date(2026, 10, 16), end=date(2026, 10, 31))
        names = {self._validate(first).name, self._validate(second).name}
        self.assertEqual(len(names), 2, names)

    def test_employee_without_folder_gets_one(self):
        self.employee.sudo().dms_directory_id = False
        slip = self._payslip()
        self._validate(slip)
        self.assertEqual(slip.hds_dms_state, 'stored', slip.hds_dms_error)
        self.assertTrue(self.employee.dms_directory_id)

    def test_failure_does_not_block_validation_and_is_retried(self):
        slip = self._payslip()
        with patch.object(type(slip), '_hds_dms_write_file', side_effect=ValueError("PDF engine unavailable")):
            slip.action_payslip_done()
            self.env['hr.payslip']._cron_hds_dms_store_payslips()
        self.assertEqual(slip.state, 'done', "The payslip is validated anyway")
        self.assertEqual(slip.hds_dms_state, 'failed')
        self.assertIn('PDF engine unavailable', slip.hds_dms_error)
        self.env['hr.payslip']._cron_hds_dms_store_payslips()
        self.assertEqual(slip.hds_dms_state, 'stored', slip.hds_dms_error)

    def test_store_existing_payslips(self):
        self.company.hds_dms_store_payslips = False
        slip = self._payslip()
        slip.action_payslip_done()
        self.assertEqual(slip.hds_dms_state, 'none', "Switched off: nothing is stored")
        self.company.hds_dms_store_payslips = True
        settings = self.env['res.config.settings'].create({})
        settings.action_hds_dms_store_existing_payslips()
        self.assertEqual(slip.hds_dms_state, 'pending')
        self.env['hr.payslip']._cron_hds_dms_store_payslips()
        self.assertEqual(slip.hds_dms_state, 'stored', slip.hds_dms_error)

    def test_employee_sees_own_payslips_only(self):
        own = self._validate(self._payslip())
        others = self._validate(self._payslip(employee=self.other))
        File = self.env['dms.file'].with_user(self.employee.user_id)
        self.assertIn(own, File.search([]), "The employee sees their own payslip")
        self.assertNotIn(others, File.search([]), "...but not a colleague's")
        self.assertNotIn(own, self.env['dms.file'].with_user(self.other.user_id).search([]))

    def test_pay_run_validation_stores_every_payslip(self):
        """Validating a pay run stores each employee's payslip in their own folder."""
        run = self.env['hr.payslip.run'].create({
            'name': 'Dms Pay Run October 2026', 'company_id': self.company.id,
            'date_start': date(2026, 10, 1), 'date_end': date(2026, 10, 31)})
        slips = self._payslip() | self._payslip(employee=self.other)
        slips.write({'payslip_run_id': run.id})
        run.with_context(skip_duplicate_check=True).action_batch_validate()
        self.assertEqual(set(slips.mapped('state')), {'done'})
        self.assertEqual(set(slips.mapped('hds_dms_state')), {'pending'})
        self.env['hr.payslip']._cron_hds_dms_store_payslips()
        for slip in slips:
            self.assertEqual(slip.hds_dms_state, 'stored', slip.hds_dms_error)
            self.assertEqual(slip.hds_dms_file_id.directory_id.parent_id.parent_id, slip.employee_id.dms_directory_id,
                             "Each payslip is stored in its own employee's folder")

    def test_tax_year_label(self):
        slip = self._payslip()
        self.assertEqual(slip._hds_dms_tax_year_label(), '2026-27')
        # A period no Tax Year covers yet (no 2025-26 here): April to March rule
        early = self._payslip(start=date(2026, 2, 1), end=date(2026, 2, 28), compute=False)
        self.assertEqual(early._hds_dms_tax_year_label(), '2025-26')
