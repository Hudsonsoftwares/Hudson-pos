# -*- coding: utf-8 -*-
from datetime import date

from dateutil.relativedelta import relativedelta

# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTdsChallan(TransactionCase):
    """TDS challan: imports the paid payslips of its period that have TDS, sums their TDS,
    locks when deposited and protects the payslips it covers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Own company: the tests do not depend on the challans / Form 138 of the database
        cls.company = cls.env['res.company'].create({'name': 'TDS Challan Test Co'})
        cls.other_company = cls.env['res.company'].create({'name': 'TDS Challan Other Co'})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id, cls.other_company.id]))
        cls.structure = cls.env['hr.payroll.structure'].search([], limit=1)
        cls.tds_rule = cls.env['hr.salary.rule'].search([('code', '=', 'HDS_IN_TDS')], limit=1)
        cls.net_rule = cls.env['hr.salary.rule'].search([('code', '=', 'NET')], limit=1) or cls.tds_rule
        cls.Challan = cls.env['hds.tds.challan']

    _pan_seq = 0

    def _payslip(self, name, tds, paid_on, company=None, state='paid', period=None):
        # Salary period: the month of `period`, by default the month in which the payslip is paid
        company = company or self.company
        period_start = (period or paid_on).replace(day=1)
        TestTdsChallan._pan_seq += 1
        pan = 'ZQTST%04dZ' % TestTdsChallan._pan_seq
        employee = self.env['hr.employee'].create({'name': name, 'company_id': company.id, 'hds_in_pan': pan})
        slip = self.env['hr.payslip'].create({
            'name': f'Slip {name}',
            'employee_id': employee.id,
            'struct_id': self.structure.id,
            'company_id': company.id,
            'date_from': period_start,
            'date_to': period_start + relativedelta(months=1, days=-1),
        })
        lines = [('NET', self.net_rule, 50000.0)]
        if tds:
            lines.append(('HDS_IN_TDS', self.tds_rule, -tds))
        self.env['hr.payslip.line'].create([{
            'name': code, 'code': code, 'slip_id': slip.id, 'salary_rule_id': rule.id,
            'employee_id': employee.id, 'contract_id': employee.version_id.id, 'amount': amount,
        } for code, rule, amount in lines])
        slip.write({'state': state, 'payment_date': paid_on})
        return slip

    def _challan(self, **vals):
        return self.Challan.create(dict({'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31)}, **vals))

    def test_import_only_paid_payslips_of_the_period_with_tds(self):
        in_period = self._payslip('In Period', 1500.0, date(2026, 10, 5))
        no_tds = self._payslip('No TDS', 0.0, date(2026, 10, 5))
        before = self._payslip('Paid Before', 900.0, date(2026, 9, 30))
        not_paid = self._payslip('Validated Only', 700.0, date(2026, 10, 5), state='done')
        other_company = self._payslip('Other Company', 800.0, date(2026, 10, 5), company=self.other_company)
        challan = self._challan()

        importable = challan._get_importable_payslips()
        self.assertIn(in_period, importable)
        for slip in (no_tds, before, not_paid, other_company):
            self.assertNotIn(slip, importable, slip.name)

        action = challan.action_import_payslips()
        self.assertEqual(action['res_model'], 'hr.payslip')
        self.assertIn(in_period.id, action['domain'][0][2])

        with self.assertRaises(UserError):
            challan._add_payslips(before)
        in_period.with_context(hds_tds_challan_id=challan.id).action_hds_add_to_tds_challan()
        self.assertEqual(challan.line_ids.payslip_id, in_period)
        self.assertEqual(challan.line_ids.pan, in_period.employee_id.hds_in_pan)
        self.assertTrue(challan.line_ids.pan)
        self.assertEqual(challan.line_ids.paid_date, date(2026, 10, 5))

        # A payslip is deposited once: not importable in another challan
        self.assertNotIn(in_period, self._challan()._get_importable_payslips())
        with self.assertRaises((UserError, ValidationError)):
            self._challan()._add_payslips(in_period)

    def test_salary_period_decides_the_challan(self):
        # April salary marked paid on 31 October: imported in the April challan, not in October's
        april = self._payslip('April Late', 1200.0, date(2026, 10, 31), period=date(2026, 4, 1))
        april_challan = self._challan(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        self.assertIn(april, april_challan._get_importable_payslips())
        self.assertNotIn(april, self._challan()._get_importable_payslips())
        april_challan._add_payslips(april)
        self.assertEqual(april_challan.line_ids.paid_date, date(2026, 10, 31))
        april_challan.write({'challan_number': '12345', 'bsr_code': '1234567'})
        april_challan.action_done()
        self.assertEqual(april_challan.state, 'done')

    def test_amounts(self):
        slips = self._payslip('A', 1500.0, date(2026, 10, 5)) | self._payslip('B', 2500.5, date(2026, 10, 20))
        challan = self._challan(penalty_amount=100.0, interest_amount=50.25)
        challan._add_payslips(slips)
        self.assertAlmostEqual(challan.tds_amount, 4000.5, places=2)
        self.assertAlmostEqual(challan.total_paid, 4150.75, places=2)
        self.assertEqual(challan.line_count, 2)
        challan.line_ids[0].unlink()
        self.assertEqual(challan.line_count, 1)
        self.assertAlmostEqual(challan.total_paid, challan.tds_amount + 150.25, places=2)

    def test_done_lock_and_reset(self):
        slip = self._payslip('Done', 1000.0, date(2026, 10, 5))
        challan = self._challan()
        challan._add_payslips(slip)
        with self.assertRaises(UserError):  # bank references missing
            challan.action_done()
        challan.write({'challan_number': '12345', 'bsr_code': '1234567'})
        challan.action_done()
        self.assertEqual(challan.state, 'done')
        with self.assertRaises(UserError):
            challan.write({'penalty_amount': 10.0})
        with self.assertRaises(UserError):
            challan.line_ids.unlink()
        with self.assertRaises(UserError):
            challan.unlink()
        with self.assertRaises(UserError):
            challan.action_import_payslips()
        challan.action_draft()
        self.assertEqual(challan.state, 'draft')

    def test_bank_reference_formats(self):
        with self.assertRaises(ValidationError):
            self._challan(challan_number='12A45')
        with self.assertRaises(ValidationError):
            self._challan(bsr_code='123456')
        with self.assertRaises(ValidationError):
            self._challan(date_from=date(2026, 10, 31), date_to=date(2026, 10, 1))

    def test_payslip_in_done_challan_is_protected(self):
        slip = self._payslip('Protected', 1000.0, date(2026, 10, 5))
        challan = self._challan(challan_number='12345', bsr_code='1234567')
        challan._add_payslips(slip)
        challan.action_done()
        with self.assertRaises(UserError):
            slip.action_payslip_cancel()
        with self.assertRaises(UserError):
            slip.unlink()
        self.assertEqual(slip.state, 'paid')

    def test_payslip_cancelled_leaves_draft_challan(self):
        slip = self._payslip('Released', 1000.0, date(2026, 10, 5))
        challan = self._challan()
        challan._add_payslips(slip)
        slip.action_payslip_cancel()
        self.assertFalse(challan.line_ids)
        self.assertEqual(challan.tds_amount, 0.0)

    def test_revert_paid_leaves_draft_challan_and_is_blocked_when_done(self):
        draft_slip = self._payslip('Reverted', 1000.0, date(2026, 10, 5))
        draft_challan = self._challan()
        draft_challan._add_payslips(draft_slip)
        draft_slip.write({'paid': False, 'state': 'done'})  # pay run "Revert Paid"
        self.assertFalse(draft_challan.line_ids)

        done_slip = self._payslip('Deposited', 1000.0, date(2026, 10, 5))
        done_challan = self._challan(challan_number='12345', bsr_code='1234567')
        done_challan._add_payslips(done_slip)
        done_challan.action_done()
        with self.assertRaises(UserError):
            done_slip.write({'paid': False, 'state': 'done'})
        with self.assertRaises(UserError):
            done_slip.write({'payment_date': date(2026, 12, 25)})
        done_slip.write({'payment_date': date(2026, 10, 5)})  # unchanged date is fine
        self.assertEqual(done_challan.line_ids.paid_date, date(2026, 10, 5))

    def test_refunds_and_duplicates_are_not_imported(self):
        refund = self._payslip('Refund', 1000.0, date(2026, 10, 5))
        refund.credit_note = True
        duplicate = self._payslip('Duplicate', 1000.0, date(2026, 10, 5))
        self.env.cr.execute("UPDATE hr_payslip SET has_duplicate_payslip = TRUE WHERE id = %s", (duplicate.id,))
        duplicate.invalidate_recordset(['has_duplicate_payslip'])
        importable = self._challan()._get_importable_payslips()
        self.assertNotIn(refund, importable)
        self.assertNotIn(duplicate, importable)

    def test_default_period_and_current_tax_year(self):
        challan = self.Challan.create({})
        self.assertEqual(challan.date_from.day, 1)
        self.assertEqual(challan.date_to.month, challan.date_from.month)
        self.assertLess(challan.date_to, date.today().replace(day=1))
        fy = challan.financial_year_id
        if fy:
            self.assertTrue(fy.start_date <= challan.date_from <= fy.end_date)

    def test_marking_paid_records_payment_date(self):
        slip = self._payslip('Marked Paid', 1000.0, date(2026, 1, 1), state='done')
        slip.with_context(hds_payment_date=date(2026, 10, 7)).action_payslip_paid()
        self.assertEqual(slip.state, 'paid')
        self.assertEqual(slip.payment_date, date(2026, 10, 7))
