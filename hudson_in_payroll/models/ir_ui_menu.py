# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        """
        Dynamically hides menus when features are disabled for the user's active company:
        - Labour Welfare Fund (LWF) menu under Indian Statutory when LWF is not enabled.
        - Leave Encashment Policies, My Requests, and Management menus when Leave Encashment is not enabled.
        """
        menus = super().load_menus(debug)
        try:
            company = self.env.company
        except Exception:
            company = False

        if not company:
            return menus

        menus_to_hide = []

        if hasattr(company, 'hds_in_enable_lwf') and not company.hds_in_enable_lwf:
            lwf_menu = self.env.ref('hudson_in_payroll.menu_lwf_state_rate', raise_if_not_found=False)
            if lwf_menu:
                menus_to_hide.append(lwf_menu)

        if hasattr(company, 'hds_in_enable_leave_encashment') and not company.hds_in_enable_leave_encashment:
            le_xmlids = [
                'hudson_in_payroll.menu_hds_leave_encashment_policy',
                'hudson_in_payroll.menu_hds_leave_encashment_policy_timeoff',
                'hudson_in_payroll.menu_hds_leave_encashment_request_my',
                'hudson_in_payroll.menu_hds_leave_encashment_request',
            ]
            for xmlid in le_xmlids:
                m = self.env.ref(xmlid, raise_if_not_found=False)
                if m:
                    menus_to_hide.append(m)

        if menus_to_hide:
            menus = dict(menus)
            for m in menus_to_hide:
                if m.id in menus:
                    parent_menu = m.parent_id
                    if parent_menu and parent_menu.id in menus:
                        p_dict = dict(menus[parent_menu.id])
                        p_dict['children'] = [c for c in p_dict.get('children', []) if c != m.id]
                        menus[parent_menu.id] = p_dict
                    menus.pop(m.id, None)

        return menus
