# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestKitchenMenuVisibility(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Test Kitchen Manufacturing Co',
            'kitchen_mode': True,
        })
        cls.routing_group = cls.env.ref('mrp.group_mrp_routings')
        cls.group_user = cls.env.ref('base.group_user')
        cls.mrp_manager_group = cls.env.ref('mrp.group_mrp_manager')
        cls.menu_kitchen_label = cls.env.ref('hudson_kitchen_terms.menu_kitchen_label')
        cls.menu_mrp_config = cls.env.ref('mrp.menu_mrp_configuration')

        cls.user = cls.env['res.users'].create({
            'name': 'Kitchen MRP User',
            'login': 'kitchen_mrp_user_test',
            'email': 'kitchen_mrp_user@test.com',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
            'group_ids': [(6, 0, [cls.group_user.id, cls.mrp_manager_group.id, cls.routing_group.id])],
        })

    def setUp(self):
        super().setUp()
        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company.id]))

    def _clear_caches(self):
        self.env.invalidate_all()
        for c in ('default', 'groups'):
            try:
                self.env.transaction.invalidate_ormcache(c)
            except Exception:
                pass

    def _get_visible_menu_ids(self, user=None):
        self._clear_caches()
        target_user = user or self.user
        return self.env['ir.ui.menu'].with_user(target_user).with_context(
            allowed_company_ids=[target_user.company_id.id]
        )._visible_menu_ids()

    def _get_loaded_menus(self, user=None):
        self._clear_caches()
        target_user = user or self.user
        return self.env['ir.ui.menu'].with_user(target_user).with_context(
            allowed_company_ids=[target_user.company_id.id]
        ).load_menus(False)

    def test_01_menu_visible_when_kitchen_task_enabled(self):
        """When the kitchen task group/checkbox is enabled, Kitchen Labels menu is visible in MRP configuration."""
        self.company.kitchen_mode = True
        self.user.write({'group_ids': [(4, self.routing_group.id)]})

        visible_ids = self._get_visible_menu_ids()
        self.assertIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen Labels menu must be visible in _visible_menu_ids when kitchen task is enabled."
        )

        loaded_menus = self._get_loaded_menus()
        self.assertIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Kitchen Labels menu must be present in load_menus when kitchen task is enabled."
        )
        config_menu_id = self.menu_mrp_config.id
        if config_menu_id in loaded_menus:
            self.assertIn(
                self.menu_kitchen_label.id,
                loaded_menus[config_menu_id].get('children', []),
                "Kitchen Labels menu must be listed under Manufacturing Configuration children."
            )

    def test_02_menu_not_visible_when_kitchen_task_disabled(self):
        """When the kitchen task group/checkbox is disabled, Kitchen Labels menu is removed from MRP configuration."""
        self.company.kitchen_mode = True
        self.user.write({'group_ids': [(3, self.routing_group.id)]})
        # Also ensure not implied by group_user
        if self.routing_group in self.group_user.implied_ids:
            self.group_user.write({'implied_ids': [(3, self.routing_group.id)]})

        visible_ids = self._get_visible_menu_ids()
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen Labels menu must NOT be visible in _visible_menu_ids when kitchen task is disabled."
        )

        loaded_menus = self._get_loaded_menus()
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Kitchen Labels menu must NOT be present in load_menus when kitchen task is disabled."
        )
        config_menu_id = self.menu_mrp_config.id
        if config_menu_id in loaded_menus:
            self.assertNotIn(
                self.menu_kitchen_label.id,
                loaded_menus[config_menu_id].get('children', []),
                "Kitchen Labels menu must NOT be listed under Manufacturing Configuration children when disabled."
            )

    def test_03_state_transitions_via_res_config_settings(self):
        """Automated test verifying state transitions: enabled -> disabled -> re-enabled via res.config.settings."""
        self.company.kitchen_mode = True
        admin_user = self.env.ref('base.user_admin')
        admin_user.write({
            'company_id': self.company.id,
            'company_ids': [(4, self.company.id)],
        })

        # 1. Enable via res.config.settings group_mrp_routings
        settings = self.env['res.config.settings'].with_user(admin_user).create({
            'group_mrp_routings': True,
        })
        settings.execute()
        self.env.invalidate_all()

        visible_ids = self._get_visible_menu_ids(admin_user)
        self.assertIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen label must be visible after enabling group_mrp_routings via settings."
        )

        # 2. Disable via res.config.settings group_mrp_routings
        settings = self.env['res.config.settings'].with_user(admin_user).create({
            'group_mrp_routings': False,
        })
        settings.execute()
        self.env.invalidate_all()

        visible_ids = self._get_visible_menu_ids(admin_user)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen label must NOT be visible after disabling group_mrp_routings via settings."
        )

        loaded_menus = self._get_loaded_menus(admin_user)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Kitchen label must NOT be in load_menus after disabling group_mrp_routings."
        )

        # 3. Re-enable via res.config.settings kitchen_task alias
        settings = self.env['res.config.settings'].with_user(admin_user).create({
            'kitchen_task': True,
        })
        settings.execute()
        self.env.invalidate_all()

        visible_ids = self._get_visible_menu_ids(admin_user)
        self.assertIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen label must be visible after re-enabling kitchen_task via settings."
        )

        # 4. Disable via res.config.settings kitchen_task alias
        settings = self.env['res.config.settings'].with_user(admin_user).create({
            'kitchen_task': False,
        })
        settings.execute()
        self.env.invalidate_all()

        visible_ids = self._get_visible_menu_ids(admin_user)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen label must NOT be visible after disabling kitchen_task via settings."
        )

    def test_04_company_kitchen_task_property(self):
        """Verify company.kitchen_task property controls routings group and menu visibility."""
        self.company.kitchen_mode = True

        self.company.kitchen_task = True
        self.assertTrue(self.company.kitchen_task, "kitchen_task must read True when enabled.")
        self.user.write({'group_ids': [(4, self.routing_group.id)]})
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(),
            "Kitchen label must be visible when company.kitchen_task is True."
        )

        self.company.kitchen_task = False
        self.assertFalse(self.company.kitchen_task, "kitchen_task must read False when disabled.")
        # Notice: user still has routing_group in group_ids, but menu must still NOT be visible!
        self.assertNotIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(),
            "Kitchen label must NOT be visible when company.kitchen_task is False, even if user has direct routing group."
        )
        self.assertNotIn(
            self.menu_kitchen_label.id,
            self._get_loaded_menus(),
            "Kitchen label must NOT be in load_menus when company.kitchen_task is False."
        )

    def test_05_kitchen_mode_disabled_hides_menu(self):
        """When Kitchen Mode is disabled for the company, kitchen label is removed from configuration menu."""
        self.user.write({'group_ids': [(4, self.routing_group.id)]})

        # When kitchen_mode is True:
        self.company.kitchen_mode = True
        self.company.kitchen_task = True
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(),
            "Kitchen label must be visible when both kitchen_mode and kitchen_task are enabled."
        )

        # When kitchen_mode is False:
        self.company.kitchen_mode = False
        self.assertNotIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(),
            "Kitchen label must NOT be visible when kitchen_mode is False."
        )
        self.assertNotIn(
            self.menu_kitchen_label.id,
            self._get_loaded_menus(),
            "Kitchen label must NOT be in load_menus when kitchen_mode is False."
        )

    def test_06_admin_user_respects_kitchen_task_checkbox(self):
        """Even administrator users (base.group_system) do not see Kitchen Labels if kitchen tasks are disabled."""
        admin_user = self.env.ref('base.user_admin')
        admin_user.write({
            'company_id': self.company.id,
            'company_ids': [(4, self.company.id)],
        })
        self.company.kitchen_mode = True

        # Disable routings
        settings = self.env['res.config.settings'].with_user(admin_user).create({
            'group_mrp_routings': False,
        })
        settings.execute()

        visible_ids = self._get_visible_menu_ids(admin_user)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Admin user must NOT see Kitchen Labels when kitchen task is disabled."
        )

        loaded_menus = self._get_loaded_menus(admin_user)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Admin user must NOT see Kitchen Labels in load_menus when kitchen task is disabled."
        )

    def test_07_multi_company_isolation(self):
        """Multi-company test: Kitchen label visibility in company A does not leak into company B."""
        company_b = self.env['res.company'].create({
            'name': 'Company B No Kitchen',
            'kitchen_mode': False,
        })
        self.company.kitchen_mode = True
        self.company.kitchen_task = True
        self.user.write({'company_ids': [(4, company_b.id)]})

        # When company A is active (kitchen_mode=True, routing enabled):
        visible_a = self.env['ir.ui.menu'].with_user(self.user).with_context(
            allowed_company_ids=[self.company.id]
        )._visible_menu_ids()
        self.assertIn(self.menu_kitchen_label.id, visible_a)

        # When company B is active (kitchen_mode=False):
        visible_b = self.env['ir.ui.menu'].with_user(self.user).with_context(
            allowed_company_ids=[company_b.id]
        )._visible_menu_ids()
        self.assertNotIn(self.menu_kitchen_label.id, visible_b)

    def test_08_direct_group_user_respects_kitchen_task_disabled(self):
        """User with direct mrp.group_mrp_routings assignment must NOT see Kitchen Labels when kitchen_task is False."""
        self.company.kitchen_mode = True
        self.company.kitchen_task = False
        user_direct = self.env['res.users'].create({
            'name': 'Direct Group User',
            'login': 'direct_grp_user_test',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [self.group_user.id, self.mrp_manager_group.id, self.routing_group.id])],
        })

        visible_ids = self._get_visible_menu_ids(user_direct)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Kitchen label menu must NOT be visible even if user has direct routing group when kitchen task is disabled."
        )

        loaded_menus = self._get_loaded_menus(user_direct)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Kitchen label menu must NOT be in load_menus even if user has direct routing group when kitchen task is disabled."
        )

        # When kitchen task is enabled again, user with direct group must see it
        self.company.kitchen_task = True
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(user_direct),
            "Kitchen label menu must be visible when kitchen task is re-enabled for direct group user."
        )
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_loaded_menus(user_direct),
            "Kitchen label menu must be present in load_menus when kitchen task is re-enabled for direct group user."
        )

    def test_09_superuser_respects_kitchen_task_disabled(self):
        """Superuser (user_root) must NOT see Kitchen Labels when kitchen task checkbox is disabled."""
        self.company.kitchen_mode = True
        self.company.kitchen_task = False
        superuser = self.env.ref('base.user_root')

        visible_ids = self._get_visible_menu_ids(superuser)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            visible_ids,
            "Superuser must NOT see Kitchen Labels when kitchen task is disabled."
        )

        loaded_menus = self._get_loaded_menus(superuser)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_menus,
            "Superuser must NOT see Kitchen Labels in load_menus when kitchen task is disabled."
        )

        # When kitchen task is enabled again, superuser must see it
        self.company.kitchen_task = True
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_visible_menu_ids(superuser),
            "Superuser must see Kitchen Labels when kitchen task is enabled."
        )
        self.assertIn(
            self.menu_kitchen_label.id,
            self._get_loaded_menus(superuser),
            "Superuser must see Kitchen Labels in load_menus when kitchen task is enabled."
        )

    def test_10_multi_company_active_switch(self):
        """Switching active company context dynamically determines Kitchen Labels visibility in both directions without cache clear."""
        company_active = self.env['res.company'].create({
            'name': 'Company Active Kitchen',
            'kitchen_mode': True,
        })
        company_inactive = self.env['res.company'].create({
            'name': 'Company Inactive Kitchen',
            'kitchen_mode': False,
        })
        self.company.kitchen_task = True
        multi_user = self.env['res.users'].create({
            'name': 'Multi Company MRP User',
            'login': 'multi_co_mrp_user_test',
            'company_id': company_active.id,
            'company_ids': [(6, 0, [company_active.id, company_inactive.id])],
            'group_ids': [(6, 0, [self.group_user.id, self.mrp_manager_group.id, self.routing_group.id])],
        })

        # 1. Start from Inactive company: hidden
        loaded_inactive = self.env['ir.ui.menu'].with_user(multi_user).with_context(
            allowed_company_ids=[company_inactive.id]
        ).load_menus(False)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_inactive,
            "Kitchen label must NOT be present when active company has kitchen mode disabled."
        )
        if self.menu_mrp_config.id in loaded_inactive:
            self.assertNotIn(
                self.menu_kitchen_label.id,
                loaded_inactive[self.menu_mrp_config.id].get('children', []),
                "Kitchen label must NOT be in MRP config children when active company has kitchen mode disabled."
            )

        # 2. Switch to Company Active WITHOUT manual cache clear: must be visible!
        loaded_active = self.env['ir.ui.menu'].with_user(multi_user).with_context(
            allowed_company_ids=[company_active.id]
        ).load_menus(False)
        self.assertIn(
            self.menu_kitchen_label.id,
            loaded_active,
            "Kitchen label must be present when active company has kitchen mode and kitchen tasks enabled."
        )
        if self.menu_mrp_config.id in loaded_active:
            self.assertIn(
                self.menu_kitchen_label.id,
                loaded_active[self.menu_mrp_config.id].get('children', []),
                "Kitchen label must be in MRP config children when active company has kitchen mode enabled."
            )

        # 3. Switch back to Company Inactive WITHOUT manual cache clear: must be hidden!
        loaded_inactive_2 = self.env['ir.ui.menu'].with_user(multi_user).with_context(
            allowed_company_ids=[company_inactive.id]
        ).load_menus(False)
        self.assertNotIn(
            self.menu_kitchen_label.id,
            loaded_inactive_2,
            "Kitchen label must NOT be present when active company has kitchen mode disabled on return switch."
        )
        if self.menu_mrp_config.id in loaded_inactive_2:
            self.assertNotIn(
                self.menu_kitchen_label.id,
                loaded_inactive_2[self.menu_mrp_config.id].get('children', []),
                "Kitchen label must NOT be in MRP config children on return switch to inactive company."
            )
