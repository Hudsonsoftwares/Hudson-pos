# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPayRunSendEmail(TransactionCase):
    """Pay run 'Send by Email': each employee receives their own validated / paid payslip, with the
    payslip template and its PDF, logged in the payslip's chatter."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'Payslip Email Test Co', 'email': 'payroll@example.com'})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id], mail_notrack=True))
        cls.structure = cls.env['hr.payroll.structure'].search([], limit=1)
        cls.payrun = cls.env['hr.payslip.run'].create({
            'name': 'Email Run', 'company_id': cls.company.id,
            'date_start': date(2026, 9, 1), 'date_end': date(2026, 9, 30),
        })

    def _slip(self, name, email, state):
        employee = self.env['hr.employee'].create({'name': name, 'company_id': self.company.id, 'work_email': email})
        return self.env['hr.payslip'].create({
            'name': f'Slip {name}', 'employee_id': employee.id, 'struct_id': self.structure.id,
            'company_id': self.company.id, 'payslip_run_id': self.payrun.id,
            'date_from': date(2026, 9, 1), 'date_to': date(2026, 9, 30), 'state': state,
        })

    def _emails(self, slip):
        return self.env['mail.message'].search([
            ('model', '=', 'hr.payslip'), ('res_id', '=', slip.id), ('message_type', '=', 'comment'),
        ])

    def test_each_employee_gets_their_own_payslip(self):
        paid = self._slip('Paid Employee', 'paid.employee@example.com', 'paid')
        validated = self._slip('Validated Employee', 'validated.employee@example.com', 'done')
        draft = self._slip('Draft Employee', 'draft.employee@example.com', 'draft')
        no_email = self._slip('No Email Employee', False, 'paid')
        self.payrun.state = 'paid'

        result = self.payrun.action_send_payslips_email()

        for slip in (paid, validated):
            messages = self._emails(slip)
            self.assertEqual(len(messages), 1, slip.name)
            # Sent only to that employee, with one PDF of that payslip
            self.assertEqual(messages.partner_ids, slip.employee_id.work_contact_id)
            self.assertEqual(len(messages.attachment_ids), 1)
            self.assertIn(slip.employee_id.name, messages.subject)
        self.assertNotEqual(self._emails(paid).attachment_ids, self._emails(validated).attachment_ids)
        self.assertFalse(self._emails(draft))
        self.assertFalse(self._emails(no_email))
        self.assertIn('No Email Employee', result['params']['message'])
        self.assertEqual(result['params']['type'], 'warning')

    def test_nothing_to_send(self):
        self._slip('Only Draft', 'only.draft@example.com', 'draft')
        with self.assertRaises(UserError):
            self.payrun.action_send_payslips_email()
