# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

class HelpdeskManagementSLAStatus(models.Model):
    _name = 'helpdesk.management.sla.status'
    _description = 'Helpdesk SLA Status'
    _order = 'deadline asc, id asc'

    ticket_id = fields.Many2one('helpdesk.management.ticket', string='Ticket', required=True, ondelete='cascade', index=True)
    sla_id = fields.Many2one('helpdesk.management.sla', string='SLA Policy', required=True, ondelete='restrict', index=True)
    team_id = fields.Many2one(related='ticket_id.team_id', store=True, index=True)
    
    status = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('reached', 'Reached'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='ongoing', required=True, index=True)
    
    start_datetime = fields.Datetime(string='Start Date', required=True)
    deadline = fields.Datetime(string='Deadline', index=True)
    reached_datetime = fields.Datetime(string='Reached Date')
    failed_datetime = fields.Datetime(string='Failed Date')
    
    is_paused = fields.Boolean(string='Is Paused', default=False)
    pause_start_time = fields.Datetime(string='Pause Start Time')
    total_paused_working_hours = fields.Float(string='Total Paused Working Hours', default=0.0)
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    color = fields.Integer(compute='_compute_color')

    @api.depends('sla_id.name')
    def _compute_display_name(self):
        for status in self:
            status.display_name = status.sla_id.name

    @api.depends('status', 'deadline')
    def _compute_color(self):
        """ Same colors as the standard SLA tags: red when failed, green when reached. """
        now = fields.Datetime.now()
        for status in self:
            if status.status == 'failed' or (status.status == 'ongoing' and status.deadline and status.deadline < now):
                status.color = 1
            elif status.status == 'reached':
                status.color = 10
            else:
                status.color = 0

    @api.constrains('ticket_id', 'sla_id')
    def _check_unique_ticket_sla(self):
        for status in self:
            domain = [
                ('id', '!=', status.id),
                ('ticket_id', '=', status.ticket_id.id),
                ('sla_id', '=', status.sla_id.id),
            ]
            if self.search_count(domain) > 0:
                # pyrefly: ignore[missing-import]
                from odoo.exceptions import ValidationError
                raise ValidationError("A ticket can only have one SLA Status per SLA Policy!")
    
    def _get_calendar(self):
        self.ensure_one()
        return self.team_id.resource_calendar_id or self.company_id.resource_calendar_id or self.env.company.resource_calendar_id
        
    def _is_sla_expired(self):
        self.ensure_one()
        if not self.deadline:
            return False
        return fields.Datetime.now() > self.deadline
