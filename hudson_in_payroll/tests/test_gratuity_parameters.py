# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestGratuityParameters(TransactionCase):

    def setUp(self):
        super(TestGratuityParameters, self).setUp()
        self.Param = self.env['hr.rule.parameter']

    def test_01_gratuity_days_multiplier_parameter(self):
        """Test lookup of Gratuity Days Multiplier (15 days)."""
        days_mult = self.Param._get_parameter_value('hds_in_gratuity_days_multiplier', Date.today())
        self.assertEqual(float(days_mult), 15.0)

    def test_02_gratuity_month_divisor_parameter(self):
        """Test lookup of Gratuity Month Divisor (26 days)."""
        month_div = self.Param._get_parameter_value('hds_in_gratuity_month_divisor', Date.today())
        self.assertEqual(float(month_div), 26.0)

    def test_03_gratuity_min_service_years_parameter(self):
        """Test lookup of Minimum Service Years (5 years)."""
        min_years = self.Param._get_parameter_value('hds_in_gratuity_min_service_years', Date.today())
        self.assertEqual(float(min_years), 5.0)

    def test_04_gratuity_statutory_ceiling_parameter(self):
        """Test lookup of Statutory Gratuity Ceiling (INR 2,000,000)."""
        ceiling = self.Param._get_parameter_value('hds_in_gratuity_statutory_ceiling', Date.today())
        self.assertEqual(float(ceiling), 2000000.0)
