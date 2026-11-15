# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from datetime import UTC
from zoneinfo import ZoneInfo

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Same table as fs.planning.role.resource_ids: the roles of the employee.
    planning_role_ids = fields.Many2many(
        'fs.planning.role',
        'fs_planning_role_employee_rel',
        'employee_id',
        'role_id',
        string='Roles',
        help='Roles the employee can be planned for.',
    )
    default_planning_role_id = fields.Many2one(
        'fs.planning.role',
        string='Default Role',
        ondelete='set null',
        help='Role set on the shifts assigned to the employee. '
             'Empty: the first of their roles.',
    )

    @api.onchange('default_planning_role_id')
    def _onchange_default_planning_role_id(self):
        if self.default_planning_role_id and self.default_planning_role_id not in self.planning_role_ids:
            self.planning_role_ids |= self.default_planning_role_id

    @api.onchange('planning_role_ids')
    def _onchange_planning_role_ids(self):
        if self.default_planning_role_id not in self.planning_role_ids:
            self.default_planning_role_id = self.planning_role_ids[:1]

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._add_default_planning_role()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if 'default_planning_role_id' in vals:
            self._add_default_planning_role()
        return res

    def _add_default_planning_role(self):
        """The default role is one of the roles of the employee."""
        for employee in self.filtered('default_planning_role_id'):
            if employee.default_planning_role_id not in employee.planning_role_ids:
                employee.planning_role_ids = [(4, employee.default_planning_role_id.id)]

    def _get_default_planning_role(self):
        """Role of the shifts assigned to the employee."""
        self.ensure_one()
        return self.default_planning_role_id or self.planning_role_ids.sorted()[:1]

    def _is_available_for_slot(self, slot):
        """Whether the employee works during the shift (working schedule and
        time off), used by Auto Plan. Overlapping shifts are checked on write."""
        self.ensure_one()
        calendar = self.resource_calendar_id
        if not calendar:
            return True
        start = slot.date_start.replace(tzinfo=UTC)
        end = slot.date_end.replace(tzinfo=UTC)
        # Odoo 20: the timezone is the resource's (no more on the calendar)
        tz = ZoneInfo(self.tz or self.env.user.tz or 'UTC')
        intervals = calendar._work_intervals_batch(start, end, resources_per_tz={tz: self.resource_id})[self.resource_id.id]
        worked = sum((stop - begin).total_seconds() for begin, stop, _record in intervals)
        # Working at least half of the shift.
        return worked * 2 >= (end - start).total_seconds() - slot.break_hours * 3600
