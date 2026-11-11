# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HelpdeskManagementTicketTime(models.Model):
    _name = 'helpdesk.management.ticket.time'
    _description = 'Ticket Time Tracking'
    _order = 'date desc, id desc'
    
    ticket_id = fields.Many2one('helpdesk.management.ticket', string='Ticket', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', related='ticket_id.company_id', store=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, required=True)
    description = fields.Char(string='Description', required=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    start_time = fields.Datetime(string='Start')
    stop_time = fields.Datetime(string='Stop')
    duration = fields.Float(string='Duration (Hours)', required=True)

class HelpdeskManagementTicketRating(models.Model):
    _name = 'helpdesk.management.ticket.rating'
    _description = 'Ticket Rating'
    _order = 'date desc, id desc'
    
    ticket_id = fields.Many2one('helpdesk.management.ticket', string='Ticket', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', related='ticket_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='ticket_id.partner_id', store=True)
    user_id = fields.Many2one('res.users', string='Assigned to', related='ticket_id.user_id', store=True)
    team_id = fields.Many2one('helpdesk.management.team', string='Team', related='ticket_id.team_id', store=True)
    rating = fields.Selection([
        ('1', '1 Star'),
        ('2', '2 Stars'),
        ('3', '3 Stars'),
        ('4', '4 Stars'),
        ('5', '5 Stars')
    ], string='Rating', required=True)
    feedback = fields.Text(string='Feedback')
    date = fields.Datetime(string='Date', default=fields.Datetime.now)
