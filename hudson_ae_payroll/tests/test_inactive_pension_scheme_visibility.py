# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tests import Form


@tagged('post_install', '-at_install', 'TestInactivePensionSchemeVisibility')
class TestInactivePensionSchemeVisibility(TransactionCase):
    """
    Test suite for Inactive / Archived Pension Scheme Visibility:
    1. Inactive schemes remain visible in master views (action context active_test=False).
    2. Active/Inactive status is clearly derived.
    3. Inactive schemes are excluded from new employee selections.
    4. Existing employees already assigned to an archived scheme retain and display it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PensionScheme = cls.env['uae.pension.scheme']
        cls.Employee = cls.env['hr.employee']
        cls.Country = cls.env['res.country']

        cls.uae = cls.Country.search([('code', '=', 'AE')], limit=1)
        cls.legacy = cls.PensionScheme.with_context(active_test=False).search([('code', '=', 'legacy')], limit=1)
        cls.new_law = cls.PensionScheme.with_context(active_test=False).search([('code', '=', 'new_law')], limit=1)
        # In this visibility test suite, ensure all active schemes are permitted for env.company
        cls.env.company.uae_pension_scheme_ids = [(5, 0, 0)]

    def test_01_inactive_scheme_visible_with_active_test_false(self):
        """Archived schemes must remain visible when active_test=False (as in the action context)."""
        test_scheme = self.PensionScheme.create({
            'name': 'Test Obsolete Scheme',
            'code': 'test_obsolete',
            'active': False,
        })
        self.assertEqual(test_scheme.status, 'inactive')
        self.assertIn('(Inactive)', test_scheme.display_name)

        # Querying with active_test=False (action context) returns it
        schemes = self.PensionScheme.with_context(active_test=False).search([('id', '=', test_scheme.id)])
        self.assertEqual(len(schemes), 1, "Inactive scheme must be returned when active_test=False.")

        # Default query without active_test=False excludes it
        schemes_default = self.PensionScheme.search([('id', '=', test_scheme.id)])
        self.assertEqual(len(schemes_default), 0, "Default search without active_test=False excludes archived schemes.")

    def test_02_status_field_and_display_name(self):
        """Active scheme has status 'active', inactive scheme has status 'inactive'."""
        active_scheme = self.PensionScheme.create({
            'name': 'Active Test Scheme',
            'code': 'active_test',
            'active': True,
        })
        self.assertEqual(active_scheme.status, 'active')
        self.assertEqual(active_scheme.display_name, 'Active Test Scheme')

        active_scheme.active = False
        self.assertEqual(active_scheme.status, 'inactive')
        self.assertIn('(Inactive)', active_scheme.display_name)

    def test_03_inactive_scheme_rejected_on_new_employee(self):
        """New employee creation cannot select an inactive scheme."""
        archived_scheme = self.PensionScheme.create({
            'name': 'Archived Scheme 1970',
            'code': 'archived_1970',
            'active': False,
        })

        with self.assertRaises(ValidationError) as ctx:
            self.Employee.create({
                'name': 'New UAE National Employee',
                'country_id': self.uae.id,
                'uae_pension_scheme_id': archived_scheme.id,
            })
        self.assertIn("Cannot assign an inactive or archived Pension Scheme", str(ctx.exception))

    def test_04_inactive_scheme_rejected_on_existing_employee_reassignment(self):
        """Existing employee cannot be updated to assign an inactive scheme."""
        active_scheme = self.PensionScheme.create({
            'name': 'Active Cohort Scheme',
            'code': 'active_cohort',
            'active': True,
        })
        archived_scheme = self.PensionScheme.create({
            'name': 'Archived Cohort Scheme',
            'code': 'archived_cohort',
            'active': False,
        })

        emp = self.Employee.create({
            'name': 'Existing UAE Employee',
            'country_id': self.uae.id,
            'uae_pension_scheme_id': active_scheme.id,
        })
        self.assertEqual(emp.uae_pension_scheme_id, active_scheme)

        # Attempt to change to archived scheme
        with self.assertRaises(ValidationError) as ctx:
            emp.write({'uae_pension_scheme_id': archived_scheme.id})
        self.assertIn("Cannot assign an inactive or archived Pension Scheme", str(ctx.exception))

    def test_05_existing_employee_already_linked_continues_displaying_after_archival(self):
        """
        Historical/Audit integrity:
        An employee assigned to a scheme while it was active continues displaying
        their assigned scheme even after that scheme is archived/inactive.
        """
        target_scheme = self.PensionScheme.create({
            'name': 'Historic Cohort Scheme',
            'code': 'historic_cohort',
            'active': True,
        })

        emp = self.Employee.create({
            'name': 'Grandfathered UAE Employee',
            'country_id': self.uae.id,
            'uae_pension_scheme_id': target_scheme.id,
        })
        self.assertEqual(emp.uae_pension_scheme_id, target_scheme)

        # Now archive the scheme
        target_scheme.active = False
        self.assertFalse(target_scheme.active)

        # Re-read employee: scheme must NOT be lost or cleared
        emp.invalidate_recordset()
        self.assertTrue(emp.uae_pension_scheme_id, "Employee must still be linked to the archived scheme.")
        self.assertEqual(emp.uae_pension_scheme_id.id, target_scheme.id)
        self.assertEqual(emp.uae_pension_scheme_id.name, 'Historic Cohort Scheme')

        # Updating other fields on the employee must succeed without validation error
        emp.write({'job_title': 'Senior UAE Officer'})
        self.assertEqual(emp.job_title, 'Senior UAE Officer')
        self.assertEqual(emp.uae_pension_scheme_id.id, target_scheme.id)

    def test_06_form_view_simulation_for_historical_employee(self):
        """Simulate UI form interaction: historical scheme displays on employee form."""
        old_scheme = self.PensionScheme.create({
            'name': 'Old Law Scheme',
            'code': 'old_law',
            'active': True,
        })

        emp = self.Employee.create({
            'name': 'Audited Employee',
            'country_id': self.uae.id,
            'uae_pension_scheme_id': old_scheme.id,
        })

        # Archive the scheme
        old_scheme.active = False

        # Open in Form
        with Form(emp) as emp_form:
            # The field should retain its value and not be cleared
            self.assertEqual(emp_form.uae_pension_scheme_id, old_scheme)
            emp_form.job_title = "Audit Officer"

        self.assertEqual(emp.uae_pension_scheme_id, old_scheme)
        self.assertEqual(emp.job_title, "Audit Officer")
