# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FieldServiceStage(models.Model):
    _name = 'field.service.stage'
    _description = 'Field Service Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    fold = fields.Boolean(
        string='Folded in Kanban',
        help='This stage is folded in the kanban view when there are no records in that stage to display.',
    )
    is_close = fields.Boolean(
        string='Closing Stage',
        help='Orders in this stage are considered as done/closed.',
    )
    color = fields.Integer(string='Color Index')
    description = fields.Text(string='Description', translate=True)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Always display all stages in kanban view."""
        return stages.search([], order=stages._order)
