# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestPayRunPayment(TransactionCase):
    """Only validated payslips may be paid; cancelled ones are skipped, draft ones block payment."""

    @classmethod
    def _gc_filestore(cls):
        # Override Windows filestore temp file GC assertion
        pass

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False) \
            or self.env['hr.payroll.structure'].search([], limit=1)
        PartnerBank = self.env['res.partner.bank']
        self.company_bank = PartnerBank.create({
            'acc_number': 'PAYRUN-CO-BANK-001',
            'account_number': 'PAYRUN-CO-BANK-001',
            'partner_id': self.company.partner_id.id,
            'company_id': self.company.id,
        })

        self.employees = self.env['hr.employee']
        for idx, name in enumerate(('Pay Validated', 'Pay Cancelled', 'Pay Draft'), start=1):
            emp = self.env['hr.employee'].create({'name': name, 'company_id': self.company.id})
            emp.version_id.write({
                'wage': 30000.0,
                'struct_id': self.struct.id,
                'contract_date_start': date(2026, 1, 1),
            })
            emp.bank_account_id = PartnerBank.create({
                'acc_number': 'PAYRUN-EMP-%03d' % idx,
                'partner_id': emp.work_contact_id.id,
                'company_id': self.company.id,
            })
            self.employees |= emp

        self.run = self.env['hr.payslip.run'].create({
            'name': 'Oct 2026 Payment Test',
            'company_id': self.company.id,
            'company_bank_id': self.company_bank.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        self.slips = self.env['hr.payslip']
        for emp in self.employees:
            slip = self.env['hr.payslip'].create({
                'name': 'Slip %s' % emp.name,
                'employee_id': emp.id,
                'contract_id': emp.version_id.id,
                'struct_id': self.struct.id,
                'date_from': date(2026, 10, 1),
                'date_to': date(2026, 10, 31),
                'payslip_run_id': self.run.id,
            })
            slip.action_compute_sheet()
            self.slips |= slip
        self.slip_done, self.slip_cancel, self.slip_draft = self.slips
        self.slip_done.action_payslip_done()
        self.slip_cancel.action_payslip_cancel()

    def _pay_wizard(self):
        return self.env['hr.payslip.run.pay.wizard'].with_context(
            active_id=self.run.id, active_model='hr.payslip.run',
        ).create({
            'payslip_run_id': self.run.id,
            'mode': 'advice',
            'company_bank_id': self.company_bank.id,
        })

    def test_01_draft_slip_blocks_payment(self):
        with self.assertRaises(UserError):
            self._pay_wizard().action_mark_paid()
        with self.assertRaises(UserError):
            self.run.action_pay_payrun()
        self.assertEqual(self.slip_draft.state, 'draft')
        self.assertEqual(self.slip_cancel.state, 'cancel')
        self.assertEqual(self.slip_done.state, 'done')
        self.assertNotEqual(self.run.state, 'paid')

    def test_02_mark_paid_skips_cancelled_slips(self):
        self.slip_draft.action_payslip_done()
        self._pay_wizard().action_mark_paid()

        self.assertEqual(self.slip_done.state, 'paid')
        self.assertEqual(self.slip_draft.state, 'paid')
        self.assertEqual(self.slip_cancel.state, 'cancel', "Cancelled payslip must never become paid")
        self.assertFalse(self.slip_cancel.paid)
        self.assertEqual(self.run.state, 'paid')
        advice_slips = self.run.advice_id.line_ids.mapped('payslip_id')
        self.assertNotIn(self.slip_cancel, advice_slips, "Cancelled payslip must not be in the bank advice")
        self.assertEqual(advice_slips, self.slip_done | self.slip_draft)

    def test_03_pay_button_skips_cancelled_slips(self):
        self.slip_draft.action_payslip_done()
        self.run.action_pay_payrun()
        self.assertEqual(self.slip_cancel.state, 'cancel')
        self.assertEqual((self.slip_done | self.slip_draft).mapped('state'), ['paid', 'paid'])
        self.assertEqual(self.run.state, 'paid')

    def test_05_run_totals_exclude_cancelled_slips(self):
        """Gross/net/basic/cost, payslip count, department summary and 'all done' ignore cancelled slips."""
        active = self.slip_done | self.slip_draft
        self.assertTrue(self.slip_cancel.net_wage, "Cancelled slip still carries amounts")
        self.run._compute_department_summaries()

        self.assertAlmostEqual(self.run.gross_wage_total, sum(active.mapped('gross_wage')))
        self.assertAlmostEqual(self.run.net_wage_total, sum(active.mapped('net_wage')))
        self.assertAlmostEqual(self.run.basic_wage_total, sum(active.mapped('basic_wage')))
        self.assertEqual(self.run.payslip_count, 2)
        self.assertEqual(sum(self.run.dep_summary_ids.mapped('employee_count')), 2)
        self.assertAlmostEqual(sum(self.run.dep_summary_ids.mapped('net_total')), sum(active.mapped('net_wage')))

        self.slip_draft.action_payslip_done()
        self.assertTrue(self.run.slips_all_done, "A cancelled slip must not block 'all payslips validated'")

    def test_06_cancelling_a_slip_updates_run_totals(self):
        """Totals refresh immediately when a payslip is cancelled or reset to draft."""
        net_before = self.run.net_wage_total
        draft_net = self.slip_draft.net_wage
        self.slip_draft.action_payslip_cancel()
        self.assertAlmostEqual(self.run.net_wage_total, net_before - draft_net)
        self.assertEqual(self.run.payslip_count, 1)
        self.assertEqual(sum(self.run.dep_summary_ids.mapped('employee_count')), 1)

        self.slip_draft.action_payslip_draft()
        self.assertAlmostEqual(self.run.net_wage_total, net_before)
        self.assertEqual(sum(self.run.dep_summary_ids.mapped('employee_count')), 2)

    def test_07_revert_paid_keeps_cancelled_slips_cancelled(self):
        """Revert Paid only turns paid slips back to validated; cancelled slips stay cancelled."""
        self.slip_draft.action_payslip_done()
        self._pay_wizard().action_mark_paid()
        self.assertEqual(self.run.state, 'paid')
        self.assertEqual(self.run.advice_id.state, 'confirmed')
        net_paid = self.run.net_wage_total

        self.run.action_revert_paid()

        self.assertEqual(self.run.state, 'confirmed')
        self.assertEqual(self.slip_cancel.state, 'cancel', "Cancelled payslip must not be revived")
        self.assertEqual((self.slip_done | self.slip_draft).mapped('state'), ['done', 'done'])
        self.assertFalse(any((self.slip_done | self.slip_draft).mapped('paid')))
        self.assertEqual(self.run.payslip_count, 2)
        self.assertAlmostEqual(self.run.net_wage_total, net_paid, msg="Totals must not change on revert")
        self.assertEqual(self.run.advice_id.state, 'draft', "Advice must be reopened when payment is reverted")

    def test_08_revert_paid_leaves_draft_slips_untouched(self):
        """A draft payslip inside a paid run (e.g. added later) must not become validated on revert."""
        self.slip_draft.action_payslip_done()
        self._pay_wizard().action_mark_paid()
        late_emp = self.env['hr.employee'].create({'name': 'Pay Late Joiner', 'company_id': self.company.id})
        late_emp.version_id.write({
            'wage': 30000.0,
            'struct_id': self.struct.id,
            'contract_date_start': date(2026, 1, 1),
        })
        late_slip = self.env['hr.payslip'].create({
            'name': 'Late draft slip',
            'employee_id': late_emp.id,
            'contract_id': late_emp.version_id.id,
            'struct_id': self.struct.id,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
            'payslip_run_id': self.run.id,
        })

        self.run.action_revert_paid()

        self.assertEqual(late_slip.state, 'draft', "Draft payslip must not be marked as validated")
        self.assertEqual(self.slip_cancel.state, 'cancel')

    def test_09_validate_reports_failures_and_keeps_run_draft(self):
        """A payslip that cannot be validated is reported and the run stays in Draft until it is fixed."""
        contract = self.slip_draft.contract_id
        contract.sudo().contract_date_end = date(2026, 9, 30)
        self.slip_draft._compute_contract_status()
        self.assertTrue(self.slip_draft.has_no_running_contract)

        res = self.run.action_batch_validate()

        self.assertIsInstance(res, dict, "Validation failures must be reported to the user")
        self.assertEqual(res.get('tag'), 'display_notification')
        self.assertIn(self.slip_draft.employee_id.name, res['params']['message'])
        self.assertIn('No running contract', res['params']['message'])
        self.assertEqual(self.run.state, 'draft', "Run must not be confirmed while a payslip failed")
        self.assertEqual(self.slip_draft.state, 'draft')
        self.assertEqual(self.slip_done.state, 'done', "Already validated payslips are kept")
        self.assertEqual(self.slip_cancel.state, 'cancel')

        # Fix the contract and validate again: only the remaining draft is processed and the run is confirmed
        contract.sudo().contract_date_end = False
        self.slip_draft._compute_contract_status()
        self.assertTrue(self.run.action_batch_validate())
        self.assertEqual(self.slip_draft.state, 'done')
        self.assertEqual(self.run.state, 'confirmed')

    def test_10_validate_empty_run_is_refused(self):
        """A pay run without payslips (or only cancelled ones) cannot be confirmed."""
        empty_run = self.env['hr.payslip.run'].create({
            'name': 'Empty run',
            'company_id': self.company.id,
            'date_start': date(2026, 11, 1),
            'date_end': date(2026, 11, 30),
        })
        with self.assertRaises(UserError):
            empty_run.action_batch_validate()
        self.assertEqual(empty_run.state, 'draft')

    def test_11_payment_advice_excel_layout(self):
        """Excel advice: company name/bank account on top, one row per paid employee, SUM total."""
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not available")
        import io

        self.slip_draft.action_payslip_done()
        self.employees[0].bank_account_id.bank_bic = 'HDFC0001234'
        advice = self._pay_wizard()._ensure_payment_advice()
        action = advice.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/web/content/')[1].split('?')[0]))
        sheet = openpyxl.load_workbook(io.BytesIO(attachment.raw)).active

        self.assertEqual(sheet['A1'].value, "Company Name : %s" % self.company.name)
        self.assertEqual(sheet['A2'].value, "Company Bank Account : PAYRUN-CO-BANK-001")
        self.assertEqual(
            [sheet.cell(row=3, column=c).value for c in range(1, 7)],
            ["Sl No.", "Name Of Employee", "C/D", "Bank Account No.", "IFSC Code", "By Salary"],
        )

        paid_slips = self.slip_done | self.slip_draft
        self.assertEqual(len(advice.line_ids), 2, "Cancelled payslip must not be in the advice")
        for offset, line in enumerate(advice.line_ids):
            row = 4 + offset
            self.assertEqual(sheet.cell(row=row, column=1).value, offset + 1)
            self.assertEqual(sheet.cell(row=row, column=2).value, line.employee_id.name)
            self.assertEqual(sheet.cell(row=row, column=3).value, 'C')
            self.assertEqual(sheet.cell(row=row, column=4).value, line.acc_number, "Account number kept as text")
            self.assertAlmostEqual(sheet.cell(row=row, column=6).value, line.net_amount)
        self.assertIn(self.employees[0].bank_account_id.acc_number, [sheet['D4'].value, sheet['D5'].value])
        self.assertIn('HDFC0001234', [sheet['E4'].value, sheet['E5'].value], "IFSC taken from the BIC/SWIFT field")

        # Total two rows below the last employee, as a SUM formula over the amounts
        self.assertEqual(sheet['E8'].value, "Total:")
        self.assertEqual(sheet['F8'].value, "=SUM(F4:F5)")
        self.assertIn(self.company.currency_id.symbol, sheet['F4'].number_format)
        self.assertAlmostEqual(sum(paid_slips.mapped('net_wage')), advice.total_amount)

    def test_12_enet_rtgs_csv_layout(self):
        """HDFC ENet RTGS CSV: 28 bank columns, values taken from employee, bank account and advice."""
        import csv
        import io

        self.slip_draft.action_payslip_done()
        emp = self.employees[0]
        emp.work_email = 'pay.validated@example.com'
        emp.bank_account_id.write({'bank_bic': 'HDFC0001234', 'bank_name': 'HDFC Bank'})

        wizard = self._pay_wizard()
        wizard.write({'mode': 'enet', 'payment_method': 'enet_rtgs'})
        action = wizard.action_create_enet()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/web/content/')[1].split('?')[0]))
        rows = list(csv.reader(io.StringIO(attachment.raw.decode('utf-8-sig'))))
        advice = self.run.advice_id

        self.assertEqual(rows[0], [
            'Transaction Type', 'Beneficiary Code', 'Beneficiary Account Number', 'Amount', 'Beneficiary Name',
            'Drawee Location', 'DD Printing Location', 'Beneficiary Address 1', 'Beneficiary Address 2',
            'Beneficiary Address 3', 'Beneficiary Address 4', 'Beneficiary Address 5',
            'Instruction Reference Number', 'Customer Reference Number', 'Payment Details 1', 'Payment Details 2',
            'Payment Details 3', 'Payment Details 4', 'Payment Details 5', 'Payment Details 6', 'Payment Details 7',
            'Cheque Number', 'Value Date', 'MICR Number', 'IFSC Code', 'Beneficiary Bank Name',
            'Beneficiary Bank Branch Name', 'Beneficiary Email ID',
        ])
        self.assertEqual(len(rows), 1 + len(advice.line_ids), "One row per paid employee (cancelled excluded)")
        header = rows[0]
        by_name = {r[header.index('Beneficiary Name')]: r for r in rows[1:]}
        row = by_name[emp.name]
        line = advice.line_ids.filtered(lambda l: l.employee_id == emp)

        self.assertEqual(row[header.index('Transaction Type')], 'RTGS')
        self.assertIn(row[header.index('Beneficiary Code')], ('1', '2'))
        self.assertEqual(row[header.index('Beneficiary Account Number')], emp.bank_account_id.acc_number)
        self.assertEqual(float(row[header.index('Amount')]), round(line.net_amount, 2))
        self.assertNotIn(',', row[header.index('Amount')])
        self.assertEqual(row[header.index('Customer Reference Number')], advice._get_customer_reference_number())
        self.assertTrue(row[header.index('Customer Reference Number')].startswith('PAYORDER/OUT/'))
        self.assertEqual(row[header.index('Value Date')], advice.date.strftime('%d/%m/%Y'))
        self.assertEqual(row[header.index('IFSC Code')], 'HDFC0001234')
        self.assertEqual(row[header.index('Beneficiary Bank Name')], '')
        self.assertEqual(row[header.index('Beneficiary Bank Branch Name')], '')
        self.assertEqual(row[header.index('Beneficiary Email ID')], 'pay.validated@example.com')
        for blank in ('Drawee Location', 'Beneficiary Address 1', 'Payment Details 1', 'Cheque Number', 'MICR Number', 'Beneficiary Bank Name', 'Beneficiary Bank Branch Name'):
            self.assertEqual(row[header.index(blank)], '')

        Advice = self.env['hudson.payroll.payment.advice']
        self.assertEqual(Advice._format_enet_amount(10945.0), '10945')
        self.assertEqual(Advice._format_enet_amount(268171.67), '268171.67')
        self.assertEqual(Advice._format_enet_amount(1000.5), '1000.5')

    def test_13_payment_advice_pdf_letter(self):
        """PDF advice: letter with period, company account, one row per employee, total and amount in words."""
        self.slip_draft.action_payslip_done()
        self.employees[0].bank_account_id.bank_bic = 'HDFC0001234'
        advice = self._pay_wizard()._ensure_payment_advice()

        html = self.env['ir.actions.report']._render_qweb_html(
            'hudson_payroll_base.report_payment_advice_document', advice.ids)[0].decode()

        self.assertEqual(advice.get_period_label(), "1 October 2026 to 31 October 2026")
        self.assertIn("Payment Advice from 1 October 2026 to 31 October 2026", html)
        self.assertIn("from account number PAYRUN-CO-BANK-001", html)
        for line in advice.line_ids:
            self.assertIn(line.employee_id.name, html)
            self.assertIn(line.acc_number, html)
        self.assertNotIn(self.slip_cancel.employee_id.name, html, "Cancelled payslip not in the advice")
        self.assertIn("HDFC0001234", html)
        self.assertIn("Total Amount: %s" % advice.get_amount_in_words(), html)
        self.assertIn("For %s" % self.company.name, html)
        self.assertTrue(advice.get_amount_in_words())

    def test_04_single_unvalidated_payslip_cannot_be_paid(self):
        with self.assertRaises(UserError):
            self.slip_draft.action_payslip_paid()
        with self.assertRaises(UserError):
            self.slip_cancel.action_payslip_paid()
        self.assertEqual(self.slip_draft.state, 'draft')
        self.assertEqual(self.slip_cancel.state, 'cancel')

    def test_14_bank_csv_layout(self):
        """CSV mode: Odoo Online columns, values from the advice, payslip and employee bank (BIC = IFSC)."""
        import csv
        import io
        from odoo import fields

        self.slip_draft.action_payslip_done()
        emp = self.employees[0]
        emp.bank_account_id.write({'bank_bic': 'HDFC0001234'})

        wizard = self._pay_wizard()
        wizard.write({'mode': 'csv'})
        action = wizard.action_create_csv()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/web/content/')[1].split('?')[0]))
        rows = list(csv.reader(io.StringIO(attachment.raw.decode('utf-8-sig'))))
        advice = self.run.advice_id

        self.assertEqual(rows[0], [
            'Sequence', 'Payment Date', 'Report Date', 'Payment Period',
            'Employee name', 'Bank account', 'IFSC', 'Amount to pay',
        ])
        self.assertEqual(len(rows), 1 + len(advice.line_ids))
        self.assertEqual([r[0] for r in rows[1:]], [str(i) for i in range(1, len(advice.line_ids) + 1)])
        row = next(r for r in rows[1:] if r[4] == emp.name)
        line = advice.line_ids.filtered(lambda l: l.employee_id == emp)
        slip = line.payslip_id

        self.assertEqual(row[1], advice.date.strftime('%d/%m/%Y'))
        self.assertEqual(row[2], fields.Date.context_today(advice).strftime('%d/%m/%Y'))
        self.assertEqual(row[3], '%s - %s' % (slip.date_from.strftime('%d/%m/%Y'), slip.date_to.strftime('%d/%m/%Y')))
        self.assertEqual(row[5], emp.bank_account_id.acc_number)
        self.assertEqual(row[6], 'HDFC0001234')
        self.assertEqual(row[7], f"{line.net_amount:,.2f}")
