# -*- coding: utf-8 -*-
from datetime import date

# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestForm138(TransactionCase):
    """Form 138 quarterly return: the quarters of a tax year, the deposited challans of each quarter
    and the text file (FH, BH, CD, DD records)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        kerala = cls.env['res.country.state'].search([('country_id.code', '=', 'IN'), ('code', '=', 'KL')], limit=1)
        cls.company = cls.env['res.company'].create({
            'name': 'Form138 Test Co',
            'street': 'Secretariate', 'city': 'Trivandrum', 'zip': '686518',
            'state_id': kerala.id, 'country_id': kerala.country_id.id, 'email': 'tds@example.com',
            'hds_in_tan': 'AWRG12345J', 'hds_in_company_pan': 'ACBFH2456H', 'hds_in_deductor_type': 'K',
            'hds_in_tds_responsible_name': 'HR Admin', 'hds_in_tds_responsible_email': 'hradmin@example.com',
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.fy = cls.env['tds.financial.year'].create({
            'name': 'Tax Year: 2098-99 (test)', 'code': '2098-2099',
            'start_date': date(2098, 4, 1), 'end_date': date(2099, 3, 31),
        })
        cls.structure = cls.env['hr.payroll.structure'].search([], limit=1)
        cls.rules = {code: cls.env['hr.salary.rule'].search([('code', '=', code)], limit=1)
                     for code in ('GROSS', 'NET', 'HDS_IN_TDS')}
        cls.Form = cls.env['hds.form.138']
        cls.forms = cls.Form._ensure_quarters(cls.fy, cls.company)

    _seq = 0

    def _payslip(self, name, gross, tds, paid_on, pan=False):
        TestForm138._seq += 1
        employee = self.env['hr.employee'].create({'name': name, 'company_id': self.company.id, 'hds_in_pan': pan})
        slip = self.env['hr.payslip'].create({
            'name': f'Slip {name}', 'employee_id': employee.id, 'struct_id': self.structure.id,
            'company_id': self.company.id, 'date_from': paid_on.replace(day=1), 'date_to': paid_on,
        })
        self.env['hr.payslip.line'].create([{
            'name': code, 'code': code, 'slip_id': slip.id, 'salary_rule_id': (self.rules[code] or self.rules['NET']).id,
            'employee_id': employee.id, 'contract_id': employee.version_id.id, 'amount': amount,
        } for code, amount in (('GROSS', gross), ('NET', gross - tds), ('HDS_IN_TDS', -tds))])
        slip.write({'state': 'paid', 'payment_date': paid_on})
        return slip

    def _done_challan(self, period_start, period_end, paid_date, slips, **vals):
        challan = self.env['hds.tds.challan'].create(dict({
            'company_id': self.company.id, 'date_from': period_start, 'date_to': period_end,
            'paid_date': paid_date, 'challan_number': '56780', 'bsr_code': '6789098',
        }, **vals))
        challan._add_payslips(slips)
        challan.action_done()
        return challan

    def _quarter(self, code):
        return self.forms.filtered(lambda form: form.quarter == code)

    def test_quarters_of_the_tax_year(self):
        self.assertEqual(len(self.forms), 4)
        expected = {
            'q1': (date(2098, 4, 1), date(2098, 6, 30), date(2098, 7, 31)),
            'q2': (date(2098, 7, 1), date(2098, 9, 30), date(2098, 10, 31)),
            'q3': (date(2098, 10, 1), date(2098, 12, 31), date(2099, 1, 31)),
            'q4': (date(2099, 1, 1), date(2099, 3, 31), date(2099, 5, 31)),
        }
        for code, (start, end, due) in expected.items():
            form = self._quarter(code)
            self.assertEqual((form.date_from, form.date_to, form.due_date), (start, end, due), code)
            self.assertEqual(form.name, f'Form 138 2098-2099 {code.upper()}')
        # Listed Q1, Q2, Q3, Q4 within a tax year, latest tax year first
        older_fy = self.env['tds.financial.year'].create({
            'name': 'Tax Year: 2096-97 (test)', 'code': '2096-2097',
            'start_date': date(2096, 4, 1), 'end_date': date(2097, 3, 31),
        })
        self.Form._ensure_quarters(older_fy, self.company)
        listed = self.Form.search([('company_id', '=', self.company.id)])
        self.assertEqual([(form.financial_year_id, form.quarter) for form in listed],
                         [(fy, code) for fy in (self.fy, older_fy) for code in ('q1', 'q2', 'q3', 'q4')])
        # Generating again creates nothing new
        self.assertEqual(self.Form._ensure_quarters(self.fy, self.company), self.forms)
        self.assertEqual(self.Form.search_count([('financial_year_id', '=', self.fy.id)]), 4)

    def test_challans_of_a_quarter(self):
        sept = self._done_challan(date(2098, 9, 1), date(2098, 9, 30), date(2098, 10, 3),
                                  self._payslip('Sept', 300000.0, 59859.43, date(2098, 9, 30)))
        draft = self.env['hds.tds.challan'].create({
            'company_id': self.company.id, 'date_from': date(2098, 8, 1), 'date_to': date(2098, 8, 31)})
        q2, q3 = self._quarter('q2'), self._quarter('q3')
        # The September challan (paid in October) belongs to Q2; draft challans are not part of a return
        self.assertEqual(q2.challan_ids, sept)
        self.assertNotIn(draft, q2.challan_ids)
        self.assertFalse(q3.challan_ids)
        self.assertEqual(q2.challan_count, 1)
        self.assertAlmostEqual(q2.tds_amount, 59859.43, places=2)
        self.assertEqual(q2.statement_line_ids, sept.line_ids)
        # The challan's Form 138 button opens its quarter
        self.assertEqual(sept.action_form_138()['res_id'], q2.id)

    def test_text_file(self):
        slip_a = self._payslip('Employee 2', 307714.05, 95885.95, date(2098, 11, 30))
        slip_b = self._payslip('Employee 3', 272066.67, 25133.33, date(2098, 11, 30), pan='ABCPE1234K')
        challan = self._done_challan(date(2098, 11, 1), date(2098, 11, 30), date(2098, 12, 3), slip_a | slip_b,
                                     interest_amount=400.0, penalty_amount=2000.0)
        q3 = self._quarter('q3')
        with self.assertRaises(UserError):  # only a Done return has a text file
            q3.action_generate_text_file()
        q3.action_done()
        q3.action_generate_text_file()
        self.assertEqual(q3.text_filename, '209899Q3.txt')
        lines = q3.text_file.content.decode().splitlines()
        records = [line.split('^') for line in lines]
        self.assertEqual([r[1] for r in records], ['FH', 'BH', 'CD', 'DD', 'DD'])
        self.assertEqual([r[0] for r in records], ['1', '2', '3', '4', '5'])
        self.assertEqual([len(r) for r in records], [18, 72, 30, 45, 45])

        fh, bh, cd, dd1, dd2 = records
        self.assertEqual(fh[2:4] + fh[6:10], ['SL1', 'R', 'D', 'AWRG12345J', '1', 'Odoo'])
        self.assertEqual(bh[2:5], ['1', '1', '138'])
        self.assertEqual(bh[12], 'AWRG12345J')
        self.assertEqual(bh[14:19], ['ACBFH2456H', '209900', '209899', 'Q3', 'Form138 Test Co'])
        self.assertEqual(bh[20], 'Secretariate')
        self.assertEqual(bh[22], 'Trivandrum')
        self.assertEqual(bh[25:28], ['16', '686518', 'tds@example.com'])
        self.assertEqual(bh[31:33], ['K', 'HR Admin'])
        self.assertEqual(bh[41], 'hradmin@example.com')
        self.assertEqual(bh[46], '%.2f' % challan.total_paid)
        self.assertEqual(bh[51], 'N')

        tds = slip_a._hds_in_challan_tds_amount() + slip_b._hds_in_challan_tds_amount()
        self.assertEqual(cd[2:6], ['1', '1', '2', 'N'])
        # Break-up: tax, surcharge, interest, penalty; they add up to the challan total
        self.assertEqual(cd[7:13], ['%.2f' % tds, '0.00', '400.00', '2000.00', '%.2f' % (tds + 2400.0), 'C'])
        self.assertAlmostEqual(sum(float(value) for value in cd[7:11]), float(cd[11]), places=2)
        self.assertEqual((cd[14], cd[16], cd[18]), ('6789098', '56780', '03122098'))
        self.assertEqual(cd[20:23], ['%.2f' % tds, '%.2f' % tds, '200'])

        by_name = {dd[8]: dd for dd in (dd1, dd2)}
        for slip, pan in ((slip_a, 'PANNOTAVBL'), (slip_b, 'ABCPE1234K')):
            dd = by_name[slip.employee_id.name]
            self.assertEqual(dd[2:6], ['1', '1', dd[4], 'O'])
            self.assertEqual(dd[7], pan)
            self.assertEqual((dd[14], dd[17], dd[31]), ('1002', 'Y', 'C'))
            self.assertEqual(dd[18], '30112098')
            self.assertEqual(dd[19], '%.2f' % slip.gross_wage)
            self.assertEqual(dd[23:25], ['%.2f' % slip._hds_in_challan_tds_amount()] * 2)
            self.assertEqual((dd[26], dd[28]), ('30112098', '03122098'))
        self.assertEqual(sorted([dd1[4], dd2[4]]), ['1', '2'])

    def test_done_needs_a_challan(self):
        q1 = self._quarter('q1')
        with self.assertRaises(UserError) as error:
            q1.action_done()
        self.assertIn('at least one challan', str(error.exception))
        self.assertEqual(q1.state, 'draft')
        # A return already Done without challans cannot produce a text file either
        q1.write({'state': 'done'})
        with self.assertRaises(UserError):
            q1.action_generate_text_file()
        self.assertFalse(q1.text_file)

    def test_earlier_regular_statement(self):
        from odoo.exceptions import ValidationError
        self._done_challan(date(2098, 7, 1), date(2098, 7, 31), date(2098, 8, 7),
                           self._payslip('Q2', 100000.0, 5000.0, date(2098, 7, 31)))
        self._done_challan(date(2098, 4, 1), date(2098, 4, 30), date(2098, 5, 7),
                           self._payslip('Q1', 100000.0, 5000.0, date(2098, 4, 30)))
        q2 = self._quarter('q2')
        with self.assertRaises(ValidationError):  # a token is the 15-digit receipt number
            with self.env.cr.savepoint():
                q2.write({'earlier_regular_statement': True, 'previous_token_number': '12345'})
        q2.write({'earlier_regular_statement': True})
        with self.assertRaises(UserError):  # ticked without its token number
            q2.action_done()
        q2.write({'previous_token_number': '123456789012345'})
        q2.action_done()
        with self.assertRaises(UserError):  # read-only once Done
            q2.write({'earlier_regular_statement': False})
        q2.action_generate_text_file()
        bh = q2.text_file.content.decode().splitlines()[1].split('^')
        self.assertEqual((bh[51], bh[52]), ('Y', '123456789012345'))
        self.assertEqual(len(bh), 72)
        # Without an earlier statement: N and no token
        q1 = self._quarter('q1')
        q1.action_done()
        q1.action_generate_text_file()
        bh = q1.text_file.content.decode().splitlines()[1].split('^')
        self.assertEqual((bh[51], bh[52]), ('N', ''))

    def test_missing_deductor_details_are_listed(self):
        self._done_challan(date(2098, 4, 1), date(2098, 4, 30), date(2098, 5, 7),
                           self._payslip('Q1', 100000.0, 5000.0, date(2098, 4, 30)))
        self.company.write({'hds_in_company_pan': False, 'hds_in_tds_responsible_name': False})
        q1 = self._quarter('q1')
        q1.action_done()
        with self.assertRaises(UserError) as error:
            q1.action_generate_text_file()
        self.assertIn('Company PAN', str(error.exception))
        self.assertIn('Responsible Person', str(error.exception))

    def test_done_locks_and_draft_clears_file(self):
        challan = self._done_challan(date(2098, 4, 1), date(2098, 4, 30), date(2098, 5, 7),
                                     self._payslip('Q1', 100000.0, 5000.0, date(2098, 4, 30)))
        q1 = self._quarter('q1')
        q1.action_done()
        q1.action_generate_text_file()
        with self.assertRaises(UserError):
            q1.write({'due_date': date(2098, 8, 15)})
        with self.assertRaises(UserError):
            q1.unlink()
        # A challan of a Done return cannot be reset, and no new challan can be deposited in it
        with self.assertRaises(UserError):
            challan.action_draft()
        with self.assertRaises(UserError):
            self._done_challan(date(2098, 5, 1), date(2098, 5, 31), date(2098, 6, 7),
                               self._payslip('Late', 100000.0, 5000.0, date(2098, 5, 31)))
        q1.action_draft()
        self.assertEqual(q1.state, 'draft')
        self.assertFalse(q1.text_file)
        challan.action_draft()
        self.assertEqual(challan.state, 'draft')

    def test_new_quarter_from_the_form(self):
        from odoo.exceptions import ValidationError
        from odoo.tests import Form
        today = date.today()
        form = Form(self.Form.with_company(self.company))
        # Defaults: the tax year and quarter of today
        if form.financial_year_id:
            self.assertTrue(form.financial_year_id.start_date <= today <= form.financial_year_id.end_date)
        self.assertEqual(form.quarter, 'q%d' % (((today.month - 4) % 12) // 3 + 1))
        form.financial_year_id = self.fy
        form.quarter = 'q2'
        self.assertEqual((form.date_from, form.date_to, form.due_date),
                         (date(2098, 7, 1), date(2098, 9, 30), date(2098, 10, 31)))
        # Q2 of this tax year already exists (setUpClass): a second one is refused
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                form.save()
        other_fy = self.env['tds.financial.year'].create({
            'name': 'Tax Year: 2097-98 (test)', 'code': '2097-2098',
            'start_date': date(2097, 4, 1), 'end_date': date(2098, 3, 31),
        })
        new = self.Form.create({'company_id': self.company.id, 'financial_year_id': other_fy.id, 'quarter': 'q4'})
        self.assertEqual((new.date_from, new.date_to, new.due_date), (date(2098, 1, 1), date(2098, 3, 31), date(2098, 5, 31)))
        self.assertEqual(new.name, 'Form 138 2097-2098 Q4')

    def test_generate_current_fy(self):
        today = date.today()
        fy = self.env['tds.financial.year'].search([('start_date', '<=', today), ('end_date', '>=', today)], limit=1)
        if not fy:
            fy = self.env['tds.financial.year'].create({
                'name': 'Tax Year (current test)', 'code': 'current-test',
                'start_date': date(today.year if today.month >= 4 else today.year - 1, 4, 1),
                'end_date': date(today.year + 1 if today.month >= 4 else today.year, 3, 31),
            })
        self.Form.with_company(self.company).action_generate_current_fy()
        self.assertEqual(self.Form.search_count([('financial_year_id', '=', fy.id), ('company_id', '=', self.company.id)]), 4)
