# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import pytz

from odoo import api, fields, models


class FsScheduleReport(models.AbstractModel):
    """PDF of the schedule as shown: same period, filters and grouping.

    The shifts come from ``get_schedule_view_data``, so the PDF follows the
    access rules (employees only print their own planning).
    """
    _name = 'report.hudson_planning.report_fs_schedule'
    _description = 'Planning Schedule Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        Slot = self.env['fs.planning.slot']
        schedule = Slot.get_schedule_view_data(
            data.get('domain') or [], data.get('group_by') or [], data['date_from'], data['date_to'])
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def local_time(dt):
            return pytz.utc.localize(dt).astimezone(tz).strftime('%H:%M')

        columns = [{
            'label': col['label'],
            'start': fields.Datetime.to_datetime(col['start']),
            'end': fields.Datetime.to_datetime(col['end']),
            'is_weekend': col.get('is_weekend'),
        } for col in data.get('columns') or []]

        rows = []
        for row in schedule['rows']:
            slots = sorted((s for s in schedule['slots'] if s['row_key'] == row['key']), key=lambda s: s['date_start'])
            rows.append({
                # With two group bys: the header of a group (e.g. a role)
                'is_group': row.get('type') == 'group',
                'name': row['name'],
                'job_title': row.get('job_title'),
                'planned_hours': row.get('planned_hours') or 0.0,
                'capacity_hours': row.get('capacity_hours'),
                'cells': [[{
                    'time': '%s - %s' % (local_time(s['date_start']), local_time(s['date_end'])),
                    'label': s.get('label') or '',
                    'draft': s['state'] == 'draft',
                    'is_job': s.get('is_job'),
                } for s in slots if s['date_start'] < col['end'] and s['date_end'] > col['start']] for col in columns],
            })
        return {
            'doc_ids': docids,
            'doc_model': 'fs.planning.slot',
            'docs': Slot.browse(),
            'title': data.get('title') or '',
            'columns': columns,
            'rows': rows,
        }
