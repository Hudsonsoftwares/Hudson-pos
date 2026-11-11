# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError

class HudsonAttendanceMapReprocessWizard(models.TransientModel):
    _name = 'hudson.attendance.map.reprocess.wizard'
    _description = 'Map and Reprocess Unmapped Punches'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Odoo Employee',
        required=True,
    )

    def action_map_and_reprocess(self):
        active_ids = self.env.context.get('active_ids')
        if not active_ids:
            return

        punches = self.env['hudson.attendance.raw.punch'].browse(active_ids)
        unmapped_punches = punches.filtered(lambda p: p.state == 'unmapped')
        if not unmapped_punches:
            raise UserError(_("No unmapped punches were selected."))

        # Group by (device_id, employee_code) to create mappings
        mappings_to_create = {}
        for punch in unmapped_punches:
            key = (punch.device_id.id or False, punch.employee_code)
            if key not in mappings_to_create:
                mappings_to_create[key] = punch

        mapping_model = self.env['hudson.attendance.employee.mapping']
        
        for (device_id, employee_code), punch in mappings_to_create.items():
            # Check if mapping already exists
            existing = mapping_model.search([
                ('device_id', '=', device_id),
                ('external_employee_code', '=', employee_code)
            ], limit=1)
            if not existing:
                mapping_model.create({
                    'device_id': device_id,
                    'external_employee_code': employee_code,
                    'employee_id': self.employee_id.id,
                })
            else:
                existing.write({'employee_id': self.employee_id.id})

        # Reprocess all unmapped punches for these codes
        devices = unmapped_punches.mapped('device_id')
        codes = unmapped_punches.mapped('employee_code')
        
        all_unmapped = self.env['hudson.attendance.raw.punch'].search([
            ('state', '=', 'unmapped'),
            ('device_id', 'in', devices.ids + [False]),
            ('employee_code', 'in', codes)
        ])
        
        # Reset state to 'new' and process
        all_unmapped.write({'state': 'new', 'error_message': False})
        all_unmapped._process_punch()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reprocessing Complete'),
                'message': _('Mappings created and punches have been reprocessed.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
