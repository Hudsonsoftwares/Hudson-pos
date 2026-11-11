# -*- coding: utf-8 -*-
from datetime import date

# pyrefly: ignore [missing-import]
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTdsRecalculationMonths(TransactionCase):
    """Recalculation From Month and Distribution Months of a tax year stay in step:
    the distribution months are the payroll months from the chosen month to March."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fy = cls.env['tds.financial.year'].create({
            'name': 'Tax Year: 2099-00 (test)',
            'code': '2099-2100-test',
            'start_date': date(2099, 4, 1),
            'end_date': date(2100, 3, 31),
        })

    def test_choosing_month_sets_distribution_months(self):
        expected = {'4': 12, '5': 11, '6': 10, '7': 9, '8': 8, '9': 7, '10': 6, '11': 5,
                    '12': 4, '1': 3, '2': 2, '3': 1}
        with Form(self.fy) as form:
            for month, months in expected.items():
                form.tds_recalculation_from_month = month
                self.assertEqual(form.tds_recalculation_distribution_months, months, month)
                self.assertEqual(form.tds_recalculation_from_month, month)
            form.tds_recalculation_from_month = '12'
        self.assertEqual(self.fy.tds_recalculation_distribution_months, 4)

    def test_distribution_months_still_set_month(self):
        self.fy.write({'tds_recalculation_distribution_months': 4})
        self.assertEqual(self.fy.tds_recalculation_from_month, '12')

    def test_month_written_from_code_sets_distribution_months(self):
        self.fy.write({'tds_recalculation_from_month': '12'})
        self.assertEqual(self.fy.tds_recalculation_distribution_months, 4)
        self.fy.write({'tds_recalculation_from_month': '1'})
        self.assertEqual(self.fy.tds_recalculation_distribution_months, 3)
