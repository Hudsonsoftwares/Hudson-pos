# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import timedelta

class HelpdeskManagementSLA(models.Model):
    _name = 'helpdesk.management.sla'
    _description = 'Helpdesk SLA'
    _order = 'sequence, id'

    name = fields.Char(string='SLA Name', required=True)
    description = fields.Text('Description')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    team_id = fields.Many2one('helpdesk.management.team', string='Team', required=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority')
    tag_ids = fields.Many2many(
        'helpdesk.management.tag', 'helpdesk_management_sla_tag_rel', 'sla_id', 'tag_id', string='Tags',
        help="Only apply the SLA to tickets having all these tags.")
    partner_ids = fields.Many2many(
        'res.partner', 'helpdesk_management_sla_partner_rel', 'sla_id', 'partner_id', string='Customers',
        help="Only apply the SLA to tickets of these customers (or their contacts).")
    stage_id = fields.Many2one('helpdesk.management.stage', string='Target Stage', required=True)
    
    target_type = fields.Selection([
        ('reaching_stage', 'Reaching Stage'),
        ('assign', 'Assigning Ticket')
    ], string='Target Type', default='reaching_stage', required=True)
    
    target_hours = fields.Float(string='Target Time (Hours)', required=True)
    exclude_stage_ids = fields.Many2many('helpdesk.management.stage', string='Excluding Stages')
    
    res_model = fields.Char(default='helpdesk.management.ticket')
    domain = fields.Char(string='Tickets', default='[]')

    def _is_stage_reached(self, stage):
        """ A target stage is reached by the stage itself or any later stage (standard helpdesk behaviour).
        Excluded stages pause the SLA: they never count as reaching it, wherever they sit in the pipeline. """
        self.ensure_one()
        if not stage or stage in self.exclude_stage_ids:
            return False
        return stage == self.stage_id or stage.sequence > self.stage_id.sequence

    def _matches_ticket(self, ticket):
        """ Return True if this SLA policy applies to the given ticket. """
        self.ensure_one()
        if self.team_id != ticket.team_id:
            return False
        if self.company_id and ticket.company_id and self.company_id != ticket.company_id:
            return False
        if self.priority and self.priority != ticket.priority:
            return False
        if self.tag_ids and not self.tag_ids <= ticket.tag_ids:
            return False
        if self.partner_ids:
            partner = ticket.partner_id
            if not partner or not (partner | partner.commercial_partner_id) & self.partner_ids:
                return False
        # Target stage already passed: the policy no longer applies
        if ticket.stage_id and self.stage_id and ticket.stage_id != self.stage_id \
                and self.target_type == 'reaching_stage' and self._is_stage_reached(ticket.stage_id):
            return False
        return True

    @api.constrains('team_id', 'stage_id')
    def _check_stage_team(self):
        for sla in self:
            if sla.stage_id and sla.team_id:
                if sla.stage_id.team_ids and sla.team_id not in sla.stage_id.team_ids:
                    from odoo.exceptions import ValidationError
                    raise ValidationError("The selected target stage does not belong to the selected Helpdesk Team.")

    @api.constrains('stage_id', 'exclude_stage_ids')
    def _check_exclude_stages(self):
        for sla in self:
            if sla.stage_id and sla.stage_id in sla.exclude_stage_ids:
                from odoo.exceptions import ValidationError
                raise ValidationError("The target stage cannot be an excluding stage.")
