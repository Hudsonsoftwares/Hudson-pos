# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPayslipJournalEntry(TransactionCase):
    """A validated payslip gets a draft journal entry on the company's payroll accounts: gross salary
    and employer contributions as expenses, each deduction / contribution and the net salary as
    payables. Posted entries are reversed when the payslip is cancelled."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Payroll Accounting Test Co', 'country_id': cls.env.ref('base.in').id})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.env['account.chart.template'].try_loading('in', cls.company, install_demo=False)
        cls.structure = cls.env['hr.payroll.structure'].search([], limit=1)
        cls.rules = {rule.code: rule for rule in cls.env['hr.salary.rule'].search([])}

    def _payslip(self, name='Accounting Employee'):
        employee = self.env['hr.employee'].create({'name': name, 'company_id': self.company.id,
                                                   'work_email': 'acc.employee@example.com'})
        slip = self.env['hr.payslip'].create({
            'name': f'Slip {name}', 'employee_id': employee.id, 'struct_id': self.structure.id,
            'company_id': self.company.id, 'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31),
        })
        # Gross 9,600: PT 175, PF 1,152, ESIC 72, LWF 25, TDS 500 -> net 7,676
        # Employer: EPF 1,152, ESIC 312, LWF 75
        amounts = [('BASIC', 9600.0), ('GROSS', 9600.0), ('PT', -175.0), ('EPF', -1152.0), ('ESIC_EE', -72.0),
                   ('LWF_EE', -25.0), ('HDS_IN_TDS', -500.0), ('EMPLOYER_EPF', 1152.0), ('ESIC_ER', 312.0),
                   ('LWF_ER', 75.0), ('NET', 7676.0)]
        self.env['hr.payslip.line'].create([{
            'name': self.rules[code].name, 'code': code, 'slip_id': slip.id, 'salary_rule_id': self.rules[code].id,
            'employee_id': employee.id, 'contract_id': employee.version_id.id, 'amount': value,
        } for code, value in amounts if code in self.rules])
        return slip

    def _balances(self, move):
        balances = {}
        for line in move.line_ids:
            balances[line.account_id] = round(balances.get(line.account_id, 0.0) + line.debit - line.credit, 2)
        return balances

    def _account(self, key):
        return self.company[f'hds_payroll_account_{key}_id']

    def test_accounts_mapped_to_the_indian_chart(self):
        """Loading the Indian chart maps the payroll accounts to its payroll accounts."""
        for key, xmlid in (('salary_expense', 'p2101'), ('employer_expense', 'p2101'), ('net_payable', 'p300010'),
                           ('tds', 'p300019'), ('pf_employee', 'p300007'), ('pf_employer', 'p300008'),
                           ('pf_admin', 'p300008'), ('esic_employee', 'p300014'), ('esic_employer', 'p300015'),
                           ('pt', 'p300012'), ('lwf_employee', 'p300016'), ('lwf_employer', 'p300017')):
            self.assertEqual(self._account(key), self.env.ref(f'account.{self.company.id}_{xmlid}'), key)
        # Other deductions have no chart account: created when needed; chosen accounts are kept
        self.assertFalse(self._account('other_deductions'))
        custom = self.env['account.account'].create({'code': '399999', 'name': 'Custom TDS', 'account_type': 'liability_current',
                                                     'company_ids': [(6, 0, self.company.ids)]})
        self.company.hds_payroll_account_tds_id = custom
        accounts = self.company._hds_get_payroll_accounts()
        self.assertEqual(accounts['tds'], custom)
        self.assertTrue(accounts['other_deductions'])
        # Opening the settings shows them filled in
        settings = self.env['res.config.settings'].with_company(self.company).create({})
        self.assertEqual(settings.hds_payroll_account_net_payable_id, self._account('net_payable'))

    def test_validated_payslip_gets_a_draft_entry(self):
        slip = self._payslip()
        slip.write({'state': 'done'})
        move = slip.move_id
        self.assertTrue(move)
        self.assertEqual(move.state, 'draft')
        self.assertEqual(slip.move_state, 'draft')
        self.assertEqual(move.journal_id.code, 'SAL')
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)
        balances = self._balances(move)
        employer = slip.hds_in_total_employer_statutory if 'hds_in_total_employer_statutory' in slip._fields else 0.0
        # Salary Expense carries the gross and (as in the Indian chart) the employer contributions
        self.assertAlmostEqual(balances[self._account('salary_expense')], 9600.0 + employer, places=2)
        self.assertEqual(balances[self._account('tds')], -500.0)
        self.assertEqual(balances[self._account('pt')], -175.0)
        self.assertEqual(balances[self._account('pf_employee')], -1152.0)
        self.assertEqual(balances[self._account('esic_employee')], -72.0)
        self.assertEqual(balances[self._account('lwf_employee')], -25.0)
        self.assertEqual(balances[self._account('net_payable')], -7676.0)
        net_line = move.line_ids.filtered(lambda line: line.account_id == self._account('net_payable'))
        self.assertEqual(net_line.partner_id, slip.employee_id.work_contact_id)
        # One entry per payslip; the smart button opens it
        slip._create_account_move()
        self.assertEqual(slip.move_id, move)
        self.assertEqual(slip.action_open_account_move()['res_id'], move.id)

    def test_post_and_cancel_reverses(self):
        slip = self._payslip()
        slip.write({'state': 'done'})
        move = slip.move_id
        move.action_post()
        self.assertEqual(slip.move_state, 'posted')
        slip.action_payslip_cancel()
        self.assertFalse(slip.move_id)
        self.assertEqual(move.state, 'posted')
        reversal = self.env['account.move'].search([('reversed_entry_id', '=', move.id)])
        self.assertEqual(len(reversal), 1)
        self.assertEqual(reversal.state, 'posted')

    def test_cancel_deletes_draft_entry(self):
        slip = self._payslip()
        slip.write({'state': 'done'})
        move = slip.move_id
        slip.action_payslip_cancel()
        self.assertFalse(move.exists())

    def test_payroll_accounts_are_created_once(self):
        accounts = self.company._hds_get_payroll_accounts()
        self.assertEqual(len(accounts), 13)
        self.assertEqual(self.company._hds_get_payroll_accounts(), accounts)
        # A company without the Indian chart gets every account created, each with a unique code
        company = self.env['res.company'].create({'name': 'Generic Chart Co'})
        self.env['account.account'].create({'code': '210100', 'name': 'Something Else', 'account_type': 'expense',
                                            'company_ids': [(6, 0, company.ids)]})
        created = company._hds_get_payroll_accounts()
        codes = [account.code for account in created.values()]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(created['salary_expense'].name, 'Salary Expense')
        self.assertNotEqual(created['salary_expense'].code, '210100')

    def test_company_without_chart_gets_no_entry(self):
        company = self.env['res.company'].create({'name': 'No Chart Co'})
        employee = self.env['hr.employee'].create({'name': 'No Chart Employee', 'company_id': company.id})
        slip = self.env['hr.payslip'].with_company(company).create({
            'name': 'No chart slip', 'employee_id': employee.id, 'struct_id': self.structure.id,
            'company_id': company.id, 'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31),
        })
        slip.with_company(company).write({'state': 'done'})
        self.assertFalse(slip.move_id)
        self.assertTrue(slip.message_ids.filtered(lambda m: 'no chart of accounts' in (m.body or '')))


@tagged('post_install', '-at_install')
class TestPayRunJournalEntry(TestPayslipJournalEntry):
    """Pay run: one entry per payslip, or one consolidated entry when Batch Accounting Entries is on;
    cancelling one payslip only removes / reverses its own amounts."""

    def _run(self, count=2):
        run = self.env['hr.payslip.run'].create({
            'name': 'Accounting Run', 'company_id': self.company.id,
            'date_start': date(2026, 10, 1), 'date_end': date(2026, 10, 31)})
        slips = self.env['hr.payslip']
        for index in range(count):
            slip = self._payslip(f'Run Employee {index}')
            slip.payslip_run_id = run
            slips |= slip
        return run, slips

    def test_one_entry_per_payslip_by_default(self):
        self.company.payrun_accounting = False
        run, slips = self._run()
        slips.write({'state': 'done'})
        self.assertEqual(len(slips.move_id), 2)
        self.assertEqual(run.move_count, 2)
        action = run.action_open_account_moves()
        self.assertEqual(action['domain'], [('id', 'in', slips.move_id.ids)])
        # Journal Entries list (no Upload / Tax Excluded / Amount Due / Due Date)
        self.assertEqual(action['views'][0], (self.env.ref('hudson_payroll_account.view_move_tree_payroll').id, 'list'))

    def test_consolidated_entry(self):
        self.company.payrun_accounting = True
        run, slips = self._run()
        for slip in slips:  # validated one by one, as the pay run does
            slip.write({'state': 'done'})
        move = slips.move_id
        self.assertEqual(len(move), 1)
        self.assertEqual(move.ref, run.name)
        self.assertEqual(move.state, 'draft')
        self.assertEqual(run.move_count, 1)
        self.assertEqual(run.hds_move_status, 'Draft')
        self.assertEqual(run.action_open_account_moves()['res_id'], move.id)
        self.assertEqual(run.action_open_draft_journal_entry()['res_id'], move.id)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)
        self.assertEqual(move.line_ids.hds_payslip_id, slips)
        self.assertEqual(self._balances(move)[self._account('net_payable')], -7676.0 * 2)
        # Cancelling one payslip of the draft entry removes only its journal items
        slips[0].action_payslip_cancel()
        self.assertTrue(move.exists())
        self.assertEqual(move.line_ids.hds_payslip_id, slips[1])
        self.assertEqual(self._balances(move)[self._account('net_payable')], -7676.0)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)

    def test_consolidated_posted_entry_reversed_per_payslip(self):
        self.company.payrun_accounting = True
        run, slips = self._run()
        slips.write({'state': 'done'})
        move = slips.move_id
        move.action_post()
        self.assertEqual(run.hds_move_status, 'Posted')
        slips[0].action_payslip_cancel()
        self.assertEqual(move.state, 'posted')
        reversal = self.env['account.move'].search([('line_ids.hds_payslip_id', '=', slips[0].id), ('id', '!=', move.id)])
        self.assertEqual(len(reversal), 1)
        self.assertEqual(reversal.state, 'posted')
        # The reversal cancels exactly that payslip's amounts
        self.assertEqual(self._balances(reversal)[self._account('net_payable')], 7676.0)
        self.assertEqual(slips[1].move_id, move)
