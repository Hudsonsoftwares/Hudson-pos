# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta
import datetime
import pytz


class FsShiftTemplateApplyWizard(models.TransientModel):
    _name = 'fs.shift.template.apply.wizard'
    _description = 'Apply Shift Templates'

    date_start = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    date_end = fields.Date(string='End Date', required=True)
    role_id = fields.Many2one('fs.planning.role', string='Role', help='Select a role to filter the employees.')
    role_employee_ids = fields.Many2many(related='role_id.resource_ids', string='Role Employees')
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        domain="[('id', 'in', role_employee_ids)]",
        help='Select specific employees to apply this template to. If left empty, it will apply to all employees in the selected role.'
    )
    template_ids = fields.Many2many('fs.shift.template', string='Templates to Apply', required=True)

    # Days of week selection
    work_on_monday = fields.Boolean(string='Monday', default=True)
    work_on_tuesday = fields.Boolean(string='Tuesday', default=True)
    work_on_wednesday = fields.Boolean(string='Wednesday', default=True)
    work_on_thursday = fields.Boolean(string='Thursday', default=True)
    work_on_friday = fields.Boolean(string='Friday', default=True)
    work_on_saturday = fields.Boolean(string='Saturday', default=True)
    work_on_sunday = fields.Boolean(string='Sunday', default=False)

    def action_apply(self):
        self.ensure_one()
        if self.date_end < self.date_start:
            raise UserError(_('End date cannot be before start date.'))
        if not self.template_ids:
            raise UserError(_('Please select at least one shift template.'))

        # Find resources
        if self.employee_ids:
            employees = self.employee_ids
        else:
            domain = [('active', '=', True)]
            if self.role_id:
                domain = [('id', 'in', self.role_id.resource_ids.ids)]
            employees = self.env['hr.employee'].search(domain)
        
        if not employees:
            raise UserError(_('No active resources found for the selected criteria.'))

        slots_to_create = []
        current_date = self.date_start
        
        # Loop through days
        while current_date <= self.date_end:
            # Check if this day of week is selected
            weekday = current_date.weekday()
            if weekday == 0 and not self.work_on_monday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 1 and not self.work_on_tuesday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 2 and not self.work_on_wednesday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 3 and not self.work_on_thursday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 4 and not self.work_on_friday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 5 and not self.work_on_saturday:
                current_date += timedelta(days=1)
                continue
            elif weekday == 6 and not self.work_on_sunday:
                current_date += timedelta(days=1)
                continue

            # Loop through employees
            for employee in employees:
                # Retrieve timezone explicitly to prevent mismatched shift times
                tz_name = employee.tz or self.env.context.get('tz') or self.env.user.tz
                if not tz_name:
                    raise UserError(_(
                        "Timezone is not configured for employee '%s' or your user account. "
                        "Please set your Timezone in your Preferences to generate shifts correctly."
                    ) % employee.name)
                
                emp_tz = pytz.timezone(tz_name)
                
                # Apply each template
                for template in self.template_ids:
                    dt_start, dt_end = template._get_interval(current_date, emp_tz, employee.resource_calendar_id)
                    slots_to_create.append({
                        'resource_id': employee.id,
                        'role_id': template.role_id.id,
                        'project_id': template.project_id.id,
                        'task_id': template.task_id.id,
                        'shift_template_id': template.id,
                        'date_start': dt_start,
                        'date_end': dt_end,
                        'state': 'draft',
                    })
            current_date += timedelta(days=1)
            
        if not self.env.context.get('force_generate'):
            warnings = []
            new_hours = {}
            for slot in slots_to_create:
                emp_id = slot['resource_id']
                dur = (slot['date_end'] - slot['date_start']).total_seconds() / 3600.0
                week_key = (emp_id, slot['date_start'].isocalendar()[0], slot['date_start'].isocalendar()[1])
                new_hours[week_key] = new_hours.get(week_key, 0) + dur

            if new_hours:
                employees_dict = {emp.id: emp for emp in employees}
                for week_key, added_hours in new_hours.items():
                    emp_id, year, week = week_key
                    emp = employees_dict[emp_id]
                    limit = emp.resource_calendar_id.hours_per_week or 40.0
                    first_day = datetime.date.fromisocalendar(year, week, 1)
                    last_day = datetime.date.fromisocalendar(year, week, 7)
                    
                    domain = [
                        ('resource_id', '=', emp_id),
                        ('date_start', '>=', datetime.datetime.combine(first_day, datetime.time.min)),
                        ('date_end', '<=', datetime.datetime.combine(last_day, datetime.time.max))
                    ]
                    existing_slots = self.env['fs.planning.slot'].search(domain)
                    existing_hours = sum((s.date_end - s.date_start).total_seconds() / 3600.0 for s in existing_slots)
                    
                    total = existing_hours + added_hours
                    if total > limit:
                        warnings.append(f"• {emp.name} (Week {week}): {total:.1f} hrs exceeds {limit:.1f} hrs limit.")

            # Check for overlaps
            for slot in slots_to_create:
                emp_id = slot['resource_id']
                emp_name = employees_dict[emp_id].name if emp_id in employees_dict else "Unknown Employee"
                
                domain_overlap = [
                    ('resource_id', '=', emp_id),
                    ('date_start', '<', slot['date_end']),
                    ('date_end', '>', slot['date_start'])
                ]
                overlapping = self.env['fs.planning.slot'].search(domain_overlap, limit=1)
                if overlapping:
                    warnings.append(f"• {emp_name}: New shift ({slot['date_start'].strftime('%Y-%m-%d %H:%M')} to {slot['date_end'].strftime('%H:%M')}) overlaps with existing shift ({overlapping.date_start.strftime('%Y-%m-%d %H:%M')} to {overlapping.date_end.strftime('%H:%M')}).")
            
            if warnings:
                msg = "The following conflicts were detected:\n\n" + "\n".join(warnings) + "\n\nDo you want to proceed anyway?"
                wizard = self.env['fs.shift.confirm.wizard'].create({
                    'warning_message': msg,
                    'apply_wizard_id': self.id
                })
                return {
                    'name': 'Confirm Shift Generation',
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'fs.shift.confirm.wizard',
                    'res_id': wizard.id,
                    'target': 'new'
                }

        slots = self.env['fs.planning.slot'].create(slots_to_create)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Shifts Generated'),
                'message': _('Successfully created %s shifts! You can view and edit them in the "All Shifts" menu.', len(slots_to_create)),
                'type': 'success',
                'sticky': False,
            }
        }
