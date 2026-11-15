# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FsShiftTemplate(models.Model):
    _name = 'fs.shift.template'
    _description = 'Shift Template'
    _order = 'sequence, start_time, role_id'

    # Kept for templates created before names were computed; the label shown
    # everywhere is the display name ("8:00 AM - 5:00 PM Role").
    name = fields.Char(string='Name')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    start_time = fields.Float(string='Start Hour', required=True, default=8.0)
    end_time = fields.Float(string='End Hour', required=True, default=17.0)
    duration_days = fields.Integer(
        string='Days',
        required=True,
        default=1,
        help='Number of days the shift spans.',
    )
    duration = fields.Float(
        string='Duration',
        compute='_compute_duration',
        store=True,
        help='Total duration of the shift, in hours.',
    )
    role_id = fields.Many2one(
        'fs.planning.role',
        string='Role',
        ondelete='restrict',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        ondelete='set null',
    )
    task_id = fields.Many2one(
        'project.task',
        string='Task',
        ondelete='set null',
        domain="[('project_id', '=?', project_id)]",
    )
    hours_display = fields.Char(string='Hours', compute='_compute_hours_display')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Leave empty to make the template visible to all companies.',
    )

    _check_duration_days = models.Constraint(
        'CHECK(duration_days > 0)',
        'The span of a shift template must be at least one day.',
    )

    @api.constrains('start_time', 'end_time')
    def _check_time_range(self):
        for template in self:
            if not 0 <= template.start_time < 24:
                raise ValidationError(_('The start hour must be between 0:00 and 23:59.'))
            if not 0 <= template.end_time < 24:
                raise ValidationError(_('The end hour must be between 0:00 and 23:59.'))

    @api.depends('start_time', 'end_time', 'duration_days')
    def _compute_duration(self):
        for template in self:
            end = template.end_time if template.end_time > template.start_time else template.end_time + 24.0
            template.duration = (end - template.start_time) + 24.0 * (max(template.duration_days, 1) - 1)

    @api.depends('start_time', 'end_time')
    def _compute_hours_display(self):
        # e.g. "8:00 - 12:00"
        for template in self:
            template.hours_display = '%s - %s' % (
                self._format_hour(template.start_time, minutes=True),
                self._format_hour(template.end_time, minutes=True),
            )

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.task_id.project_id != self.project_id:
            self.task_id = False

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id.project_id:
            self.project_id = self.task_id.project_id

    @api.depends('start_time', 'end_time', 'duration_days', 'role_id')
    def _compute_display_name(self):
        # e.g. "9 - 17", "22 - 6 (2 days span)", "8 - 12 Management"
        for template in self:
            parts = [f'{self._format_hour(template.start_time)} - {self._format_hour(template.end_time)}']
            span = template._get_span_days()
            if span > 1:
                parts.append(_('(%s days span)', span))
            if template.role_id:
                parts.append(template.role_id.name)
            template.display_name = ' '.join(parts)

    @api.model
    def _format_hour(self, hour, minutes=False):
        hours, mins = divmod(round(hour * 60), 60)
        if minutes or mins:
            return f'{hours % 24}:{mins:02d}'
        return f'{hours % 24}'

    def _get_span_days(self):
        """Number of calendar days the shift touches (a night shift spans two)."""
        self.ensure_one()
        return max(self.duration_days, 1) + (1 if self.end_time <= self.start_time else 0)

    def _get_interval(self, day, tz, calendar=None):
        """Return the UTC (start, end) of the template applied on ``day`` in ``tz``.

        The span counts working days of ``calendar`` (the resource's working
        schedule): a 2 working days shift starting on Friday ends on Monday.
        """
        self.ensure_one()
        start_h, start_m = divmod(round(self.start_time * 60), 60)
        end_h, end_m = divmod(round(self.end_time * 60), 60)
        start = tz.localize(datetime.combine(day, time(start_h % 24, start_m)))
        end_day = self._add_working_days(day, max(self.duration_days, 1) - 1, calendar)
        end = tz.localize(datetime.combine(end_day, time(end_h % 24, end_m)))
        if end <= start:
            end += timedelta(days=1)
        return (
            start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _add_working_days(self, day, count, calendar=None):
        """The day ``count`` working days after ``day`` (calendar days without schedule)."""
        work_days = set(calendar.attendance_ids.mapped('dayofweek')) if calendar else set()
        while count > 0:
            day += timedelta(days=1)
            if not work_days or str(day.weekday()) in work_days:
                count -= 1
        return day
