# -*- coding: utf-8 -*-
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestUAEPayStructures(common.TransactionCase):
    """Test UAE Pay Standalone Structures, Structure Types, and Isolation."""

    def setUp(self):
        super(TestUAEPayStructures, self).setUp()
        self.struct_monthly = self.env.ref('hudson_ae_payroll.structure_ae_monthly', raise_if_not_found=False)
        self.struct_instant = self.env.ref('hudson_ae_payroll.structure_ae_instant', raise_if_not_found=False)
        self.struct_base = self.env.ref('hr_payroll_community.structure_base', raise_if_not_found=False)
        self.struct_type_ae = self.env.ref('hudson_ae_payroll.structure_type_ae_employee', raise_if_not_found=False)

    def test_01_uae_structures_exist_and_standalone(self):
        """Verify both UAE Pay Structures exist as standalone structures (parent_id = False)."""
        self.assertTrue(self.struct_monthly, "United Arab Emirates: Monthly Pay structure must exist")
        self.assertTrue(self.struct_instant, "United Arab Emirates: Instant Pay structure must exist")
        self.assertEqual(self.struct_monthly.name, 'United Arab Emirates: Monthly Pay')
        self.assertEqual(self.struct_instant.name, 'United Arab Emirates: Instant Pay')
        self.assertEqual(self.struct_monthly.code, 'UAE_MONTHLY')
        self.assertEqual(self.struct_instant.code, 'UAE_INSTANT')
        self.assertFalse(self.struct_monthly.parent_id, "UAE Monthly Pay must be a standalone structure (parent_id = False)")
        self.assertFalse(self.struct_instant.parent_id, "UAE Instant Pay must be a standalone structure (parent_id = False)")

    def test_02_uae_root_is_absent(self):
        """Verify obsolete UAE_ROOT structure is absent or removed."""
        root = self.env['hr.payroll.structure'].search([('code', '=', 'UAE_ROOT')])
        self.assertFalse(root, "UAE_ROOT structure must not exist in database")

    def test_03_base_structure_unmodified(self):
        """Verify structure_base is not polluted by UAE structures."""
        if self.struct_base:
            self.assertNotIn(self.struct_monthly, self.struct_base.children_ids)
            self.assertNotIn(self.struct_instant, self.struct_base.children_ids)

    def test_04_uae_structure_type_links(self):
        """Verify UAE Structure Type properties, default structure, and linked structures."""
        self.assertTrue(self.struct_type_ae, "United Arab Emirates Employee Structure type must exist")
        self.assertEqual(self.struct_type_ae.name, "United Arab Emirates Employee Structure")
        self.assertEqual(self.struct_type_ae.country_id.code, "AE")
        self.assertEqual(self.struct_type_ae.schedule_pay, "monthly")
        self.assertEqual(self.struct_type_ae.wage_type, "monthly")
        self.assertEqual(self.struct_type_ae.default_struct_id.id, self.struct_monthly.id, "Monthly Pay must be the default pay structure")
        self.assertEqual(self.struct_monthly.type_id.id, self.struct_type_ae.id)
        self.assertEqual(self.struct_instant.type_id.id, self.struct_type_ae.id)
        self.assertIn(self.struct_monthly, self.struct_type_ae.struct_ids)
        self.assertIn(self.struct_instant, self.struct_type_ae.struct_ids)

    def test_05_contract_structure_type_onchange(self):
        """Verify selecting structure_type_id on contract defaults struct_id and scheduled pay."""
        contract = self.env['hr.version'].new({
            'name': 'Test UAE Contract',
            'structure_type_id': self.struct_type_ae.id,
        })
        contract._onchange_structure_type_id()
        self.assertEqual(contract.struct_id.id, self.struct_monthly.id)
        self.assertEqual(contract.schedule_pay, 'monthly')

    def test_06_uae_salary_rules_wired(self):
        """Verify UAE Monthly and Instant structures have rules cleanly wired."""
        if not self.struct_monthly or not self.struct_instant:
            return
        monthly_rule_codes = self.struct_monthly.rule_ids.mapped('code')
        # Check generic rules reused
        self.assertIn('BASIC', monthly_rule_codes)
        self.assertIn('HRA', monthly_rule_codes)
        self.assertIn('Travel', monthly_rule_codes)
        self.assertIn('GROSS', monthly_rule_codes)
        self.assertIn('NET', monthly_rule_codes)
        # Check missing UAE rules wired
        self.assertIn('HOUALLOWINP', monthly_rule_codes)
        self.assertIn('CONVALLOWINP', monthly_rule_codes)
        self.assertIn('MEDALLOWINP', monthly_rule_codes)
        self.assertIn('ANNUALPASSALLOWINP', monthly_rule_codes)
        self.assertIn('OVERTIMEALLOWINP', monthly_rule_codes)
        self.assertIn('OTALL', monthly_rule_codes)
        self.assertIn('LEAVEENCASHINP', monthly_rule_codes)
        self.assertIn('AIRFARE_ALLOWANCE', monthly_rule_codes)
        self.assertIn('REIMBURSEMENT', monthly_rule_codes)
        self.assertIn('BONUS', monthly_rule_codes)
        self.assertIn('DEDUCTION', monthly_rule_codes)
        self.assertIn('ADVREC', monthly_rule_codes)
        self.assertIn('SIEC', monthly_rule_codes)
        self.assertIn('SICC', monthly_rule_codes)
        self.assertIn('NETCOST', monthly_rule_codes)
        # Check settlement rules
        instant_rule_codes = self.struct_instant.rule_ids.mapped('code')
        self.assertIn('EOS', instant_rule_codes)
        self.assertIn('ALEA', instant_rule_codes)
        self.assertIn('ALPPOUT', instant_rule_codes)
        self.assertIn('NET', instant_rule_codes)

