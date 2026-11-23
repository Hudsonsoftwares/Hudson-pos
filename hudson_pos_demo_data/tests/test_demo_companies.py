# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.hudson_pos_demo_data.models.demo_company_setup_suite import (
    load_company_setup_suite_demo_data,
)
from odoo.addons.hudson_pos_demo_data.models.demo_hr_people_suite import (
    load_hr_people_suite_demo_data,
)


@tagged('post_install', '-at_install', 'hudson_demo_companies')
class TestDemoCompanies(TransactionCase):

    @classmethod
    def _gc_filestore(cls):
        """Override Windows filestore temp file GC to prevent permission error."""
        pass

    def setUp(self):
        super().setUp()
        self.Company = self.env['res.company'].sudo()
        self.User = self.env['res.users'].sudo()
        # Ensure company setup and HR people suites have loaded
        load_company_setup_suite_demo_data(self.env)
        if 'hr.employee' in self.env and 'hr.leave' in self.env:
            try:
                load_hr_people_suite_demo_data(self.env)
            except Exception:
                pass

    def test_01_three_default_companies_exist(self):
        """Verify that at least 3 default companies exist with valid XML IDs (R2)."""
        companies = self.Company.search([])
        self.assertGreaterEqual(len(companies), 3, "Expected at least 3 default companies")

        c1 = self.env.ref('base.main_company')
        self.assertEqual(c1.name, 'Resto Cafe Solutions', "Company 1 name should be Resto Cafe Solutions")
        rc_c1 = self.env.ref('hudson_pos_demo_data.rc_company_1', raise_if_not_found=False)
        self.assertTrue(rc_c1 and rc_c1.exists(), "XML ID hudson_pos_demo_data.rc_company_1 must exist")
        self.assertEqual(rc_c1.id, c1.id, "rc_company_1 should point to base.main_company")

        india = self.env.ref('base.in', raise_if_not_found=False)
        if india:
            self.assertEqual(c1.country_id, india, "Company 1 country should be India")

        c2 = self.env.ref('hudson_pos_demo_data.rc_company_2', raise_if_not_found=False)
        self.assertTrue(c2 and c2.exists(), "Company 2 (rc_company_2) must exist")
        self.assertTrue(c2.active, "Company 2 must be active")

        c3 = self.env.ref('hudson_pos_demo_data.rc_company_3', raise_if_not_found=False)
        self.assertTrue(c3 and c3.exists(), "Company 3 (rc_company_3) must exist")
        self.assertTrue(c3.active, "Company 3 must be active")

    def test_02_multi_company_user_access(self):
        """Verify internal users have access to all 3 companies with Company 1 default (R2)."""
        c1 = self.env.ref('base.main_company')
        c2 = self.env.ref('hudson_pos_demo_data.rc_company_2')
        c3 = self.env.ref('hudson_pos_demo_data.rc_company_3')
        target_company_ids = {c1.id, c2.id, c3.id}

        internal_users = self.User.search([('share', '=', False)])
        self.assertTrue(len(internal_users) > 0, "Expected at least one internal user")

        for user in internal_users:
            self.assertEqual(user.company_id, c1, f"User {user.login} default company must be Company 1")
            self.assertTrue(
                target_company_ids.issubset(set(user.company_ids.ids)),
                f"User {user.login} must have access to all 3 default companies"
            )

        # Multi-company group should be enabled
        group_mc = self.env.ref('base.group_multi_company', raise_if_not_found=False)
        if group_mc:
            admin_user = self.env.ref('base.user_admin')
            self.assertTrue(admin_user.has_group('base.group_multi_company'), "Admin user must belong to group_multi_company")

    def test_03_time_off_global_and_new_company_creation(self):
        """Verify time off demo data is global and new company creation never blocks (R1)."""
        WET = self.env['hr.work.entry.type'].sudo()
        custom_codes = ['RC_CL', 'RC_SL', 'RC_EL', 'RC_FL', 'RC_UL', 'RC_CO']
        custom_wets = WET.search([('code', 'in', custom_codes)])

        for wet in custom_wets:
            self.assertFalse(wet.country_id, f"Work entry type {wet.code} must be global (country_id=False)")

        c1 = self.env.ref('base.main_company')
        india = self.env.ref('base.in', raise_if_not_found=False)

        # 1. Create a 4th new company with India country
        c4_vals = {
            'name': 'Hudson Test Sibling India',
            'currency_id': c1.currency_id.id,
        }
        if india:
            c4_vals['country_id'] = india.id
        c4 = self.Company.create(c4_vals)
        self.assertTrue(c4.exists(), "New company creation with India country must succeed")

        # 2. Create a 5th new company with no country
        c5 = self.Company.create({
            'name': 'Hudson Test Sibling Global',
            'currency_id': c1.currency_id.id,
            'country_id': False,
        })
        self.assertTrue(c5.exists(), "New company creation without country must succeed")

        # 3. Change country on new company
        if india:
            c5.write({'country_id': india.id})
            self.assertEqual(c5.country_id, india, "Updating company country should succeed without ValidationError")

        # 4. Verify _check_country_change_holidays passes on Company 1
        c1._check_country_change_holidays()

    def test_04_operational_data_isolation(self):
        """Verify operational demo data is focused on Company 1 and isolated from Company 2 (R2)."""
        c1 = self.env.ref('base.main_company')
        c2 = self.env.ref('hudson_pos_demo_data.rc_company_2')
        admin = self.env.ref('base.user_admin')

        # Company 2 context
        env_c2 = self.env(user=admin, su=False, context={'allowed_company_ids': [c2.id]})

        if 'sale.order' in self.env:
            c1_orders = self.env['sale.order'].search([('company_id', '=', c1.id)])
            self.assertGreater(len(c1_orders), 0, "Company 1 should contain sales orders")
            c2_orders = env_c2['sale.order'].search([])
            self.assertEqual(len(c2_orders), 0, "Company 2 should not have transactional demo sales orders")

        if 'pos.config' in self.env:
            c1_pos = self.env['pos.config'].search([('company_id', '=', c1.id)])
            self.assertGreater(len(c1_pos), 0, "Company 1 should contain POS configurations")
            c2_pos = env_c2['pos.config'].search([])
            self.assertEqual(len(c2_pos), 0, "Company 2 should not have operational POS configurations")

    def test_05_sister_company_warehouses(self):
        """Verify default warehouses are provisioned for sister companies if stock installed (R2)."""
        if 'stock.warehouse' in self.env:
            Warehouse = self.env['stock.warehouse'].sudo()
            c2 = self.env.ref('hudson_pos_demo_data.rc_company_2')
            c3 = self.env.ref('hudson_pos_demo_data.rc_company_3')

            wh2 = Warehouse.search([('company_id', '=', c2.id)], limit=1)
            self.assertTrue(wh2 and wh2.exists(), "Warehouse must be provisioned for Company 2")

            wh3 = Warehouse.search([('company_id', '=', c3.id)], limit=1)
            self.assertTrue(wh3 and wh3.exists(), "Warehouse must be provisioned for Company 3")

    def test_06_public_holidays_multi_company(self):
        """Verify public holidays exist for all default companies (R1)."""
        if 'resource.calendar.leaves' in self.env:
            Holiday = self.env['resource.calendar.leaves'].sudo()
            c1 = self.env.ref('base.main_company')
            c2 = self.env.ref('hudson_pos_demo_data.rc_company_2')
            c3 = self.env.ref('hudson_pos_demo_data.rc_company_3')

            for comp in (c1, c2, c3):
                holidays = Holiday.search([('company_id', '=', comp.id)])
                self.assertGreater(len(holidays), 0, f"Expected public holidays for company {comp.name}")
