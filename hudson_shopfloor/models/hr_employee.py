# -*- coding: utf-8 -*-
from odoo import models, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def check_shopfloor_pin(self, employee_id, pin):
        employee = self.sudo().browse(employee_id)
        if not employee.exists():
            return False

        emp_pin = (employee.pin or '').strip()
        input_pin = (str(pin) if pin is not None else '').strip()

        # If employee has no pin, allow empty pin login
        if not emp_pin and not input_pin:
            return True

        return emp_pin == input_pin
