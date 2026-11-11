# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


class PayrollWorkLocationService:
    """
    Domain Service for determining an employee's statutory work state.
    Provides a centralized, 3-tier resolution chain reusable across all state-wise
    statutory compliance engines (LWF, Professional Tax, Minimum Wages, S&E).

    Lookup Priority:
    1. employee.address_id.state_id                    (Direct employee work address partner state - Primary)
    2. employee.work_location_id.address_id.state_id  (Physical work location partner state - Secondary)
    3. employee.company_id.partner_id.state_id        (Registered company legal partner state - Fallback)
    """

    def __init__(self, env):
        self.env = env

    def get_work_state(self, employee):
        """
        Resolves the statutory state (res.country.state recordset) for a given employee.

        :param employee: hr.employee recordset (single record)
        :return: res.country.state recordset or False
        """
        if not employee:
            return False

        # 1. Specific Work Location Partner State (if different from generic company partner)
        company = employee.company_id or self.env.company
        company_partner = company.partner_id if company else False

        if employee.work_location_id and employee.work_location_id.address_id:
            wl_partner = employee.work_location_id.address_id
            if wl_partner != company_partner and wl_partner.state_id:
                return wl_partner.state_id

        # 2. Specific Employee Work Address (if different from default company address)
        if employee.address_id and employee.address_id != company_partner and employee.address_id.state_id:
            return employee.address_id.state_id

        # 3. Employee Private State (from Private Information / Employee Form)
        if getattr(employee, 'private_state_id', False):
            return employee.private_state_id

        # 4. Work Location Partner State (even if default company partner)
        if employee.work_location_id and employee.work_location_id.address_id and employee.work_location_id.address_id.state_id:
            return employee.work_location_id.address_id.state_id

        # 5. Work Address Partner State
        if employee.address_id and employee.address_id.state_id:
            return employee.address_id.state_id

        # 6. Fallback: Registered Company Partner State
        if company_partner and company_partner.state_id:
            return company_partner.state_id

        _logger.warning("Statutory work state could not be resolved for employee %s (ID: %s)", employee.name, employee.id)
        return False
