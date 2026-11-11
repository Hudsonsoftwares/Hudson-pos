# -*- coding: utf-8 -*-
from odoo.tests import common
from odoo.exceptions import ValidationError, UserError
from psycopg2 import IntegrityError


class TestHrRuleParameter(common.TransactionCase):

    def setUp(self):
        super(TestHrRuleParameter, self).setUp()
        self.RuleParam = self.env['hr.rule.parameter']
        self.RuleParamValue = self.env['hr.rule.parameter.value']

    def test_01_effective_dated_resolution(self):
        """Test historical vs future effective-dated parameter retrieval for EPF Rate."""
        epf_param = self.RuleParam.search([('code', '=', 'hds_in_epf_rate')], limit=1)
        self.assertTrue(epf_param, "EPF Rate parameter hds_in_epf_rate must exist.")

        # Query before 2014-09-01
        past_val = epf_param._get_parameter_value(date='2010-01-01')
        self.assertFalse(past_val, "No parameter value should resolve prior to the initial effective date.")

        # Query on 2026-04-01
        current_val = epf_param._get_parameter_value(date='2026-04-01')
        self.assertEqual(current_val, "12", "Current EPF rate value should resolve to '12'.")

        # Add future effective date version (13% effective 2028-04-01)
        self.RuleParamValue.create({
            'parameter_id': epf_param.id,
            'date_from': '2028-04-01',
            'parameter_value': '13',
            'description': 'Future statutory rate change test'
        })

        # Query on 2027-12-31 should resolve 12%
        val_2027 = epf_param._get_parameter_value(date='2027-12-31')
        self.assertEqual(val_2027, "12", "EPF rate on 2027-12-31 should remain 12%.")

        # Query on 2028-04-01 should resolve 13%
        val_2028 = epf_param._get_parameter_value(date='2028-04-01')
        self.assertEqual(val_2028, "13", "EPF rate on 2028-04-01 should resolve to 13%.")

    def test_02_shared_helper_get_pf_parameter(self):
        """Test shared helper method get_pf_parameter with constant keys and decimals."""
        epf_rate = self.RuleParam.get_pf_parameter('EPF_RATE', date='2026-04-01', as_decimal=True)
        self.assertAlmostEqual(epf_rate, 0.12, places=4, msg="EPF_RATE as decimal should be 0.12")

        eps_rate = self.RuleParam.get_pf_parameter('EPS_RATE', date='2026-04-01', as_decimal=True)
        self.assertAlmostEqual(eps_rate, 0.0833, places=4, msg="EPS_RATE as decimal should be 0.0833")

        pf_ceiling = self.RuleParam.get_pf_parameter('PF_WAGE_CEILING', date='2026-04-01')
        self.assertEqual(pf_ceiling, 25000.0, "PF_WAGE_CEILING should resolve to 25000.0")

        edli_rate = self.RuleParam.get_pf_parameter('EDLI_RATE', date='2026-04-01', as_decimal=True)
        self.assertAlmostEqual(edli_rate, 0.005, places=4, msg="EDLI_RATE as decimal should be 0.005")

        edli_admin = self.RuleParam.get_pf_parameter('EDLI_ADMIN_RATE', date='2026-04-01', as_decimal=True)
        self.assertEqual(edli_admin, 0.0, "EDLI_ADMIN_RATE as decimal should be 0.0")

    def test_03_edli_rate_has_version_before_activation(self):
        """Assert hds_in_edli_rate has at least one valid effective version."""
        edli_param = self.RuleParam.search([('code', '=', 'hds_in_edli_rate')], limit=1)
        self.assertTrue(edli_param, "EDLI rate parameter hds_in_edli_rate must exist.")
        self.assertTrue(
            len(edli_param.parameter_version_ids) > 0,
            "hds_in_edli_rate must have at least one effective version before EDLI salary rules can activate."
        )

    def test_04_duplicate_date_from_constraint(self):
        """Test validation constraint preventing duplicate date_from entries for the same parameter."""
        epf_param = self.RuleParam.search([('code', '=', 'hds_in_epf_rate')], limit=1)
        with self.assertRaises((ValidationError, IntegrityError)):
            with self.env.cr.savepoint():
                self.RuleParamValue.create({
                    'parameter_id': epf_param.id,
                    'date_from': '2014-09-01',  # Duplicate date_from
                    'parameter_value': '14',
                })
                self.RuleParamValue.flush_model()
