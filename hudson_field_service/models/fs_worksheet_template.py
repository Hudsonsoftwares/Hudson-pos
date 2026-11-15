# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class FsWorksheetTemplate(models.Model):
    """Worksheet filled in by the technician on a field service job.

    The fields of the worksheet are defined on the template (text, checkbox,
    selection, signature..., grouped by separators), and filled in on the job.
    """
    _name = 'fs.worksheet.template'
    _description = 'Field Service Worksheet Template'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Leave empty to make the worksheet available to all companies.',
    )
    worksheet_definition = fields.PropertiesDefinition(
        string='Worksheet Fields',
        help='Fields the technicians fill out on the jobs using this worksheet.',
    )
    field_count = fields.Integer(string='Fields', compute='_compute_field_count')

    @api.model
    def _get_default_worksheet_definition(self, device=True, intervention=True, checks=True, sign_off=True):
        """Worksheet fields of the default template, by group (separator)."""
        definition = []
        if device:
            definition += [
                {'name': 'device', 'string': _('Device'), 'type': 'separator'},
                {'name': 'manufacturer_id', 'string': _('Manufacturer'), 'type': 'many2one', 'comodel': 'res.partner'},
                {'name': 'model', 'string': _('Model'), 'type': 'char'},
                {'name': 'serial_number', 'string': _('Serial Number'), 'type': 'char'},
            ]
        if intervention:
            definition += [
                {'name': 'intervention', 'string': _('Intervention'), 'type': 'separator'},
                {'name': 'intervention_type', 'string': _('Type'), 'type': 'selection', 'selection': [
                    ['installation', _('Installation')],
                    ['maintenance', _('Maintenance')],
                    ['repair', _('Repair')],
                    ['inspection', _('Inspection')],
                ]},
                {'name': 'intervention_description', 'string': _('Description'), 'type': 'text'},
            ]
        if checks:
            definition += [
                {'name': 'checks', 'string': _('Checks'), 'type': 'separator'},
                {'name': 'visual_inspection', 'string': _('Visual Inspection'), 'type': 'boolean'},
                {'name': 'function_test', 'string': _('Function Test'), 'type': 'boolean'},
                {'name': 'safety_test', 'string': _('Safety Test'), 'type': 'boolean'},
            ]
        if sign_off:
            definition += [
                {'name': 'sign_off', 'string': _('Sign-off'), 'type': 'separator'},
                {'name': 'sign_off_date', 'string': _('Date'), 'type': 'date'},
                {'name': 'technician_signature', 'string': _('Technician Signature'), 'type': 'signature'},
            ]
        return definition

    @api.depends('worksheet_definition')
    def _compute_field_count(self):
        for template in self:
            template.field_count = len([
                prop for prop in template.worksheet_definition or [] if prop.get('type') != 'separator'
            ])
