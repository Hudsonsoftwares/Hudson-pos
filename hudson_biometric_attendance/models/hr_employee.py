# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    biometric_code = fields.Char(
        string='Biometric/Attendance Code',
        help='Unique identifier mapped to the biometric device or raw punch employee code.',
        index=True,
        copy=False,
    )

    @api.constrains('biometric_code')
    def _check_biometric_code_uniqueness(self):
        for employee in self:
            if employee.biometric_code:
                # Search for other employees with the same biometric code
                domain = [
                    ('biometric_code', '=', employee.biometric_code),
                    ('id', '!=', employee.id)
                ]
                duplicate = self.search(domain, limit=1)
                if duplicate:
                    raise ValidationError(_(
                        'The Biometric/Attendance Code "%s" is already assigned to employee %s.'
                    ) % (employee.biometric_code, duplicate.name))
