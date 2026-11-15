# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployeePublic(models.Model):
    """The planning roles of employees are public: users without HR rights
    (technicians, planners) read employees, e.g. the resource of a shift, and
    Odoo refuses to read fields of hr.employee missing from its public model."""
    _inherit = 'hr.employee.public'

    planning_role_ids = fields.Many2many(related='employee_id.planning_role_ids', readonly=True)
    default_planning_role_id = fields.Many2one(related='employee_id.default_planning_role_id', readonly=True)
