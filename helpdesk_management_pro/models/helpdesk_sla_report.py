# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models, tools
# pyrefly: ignore [missing-import]
from odoo.tools import SQL


class HelpdeskManagementSLAReport(models.Model):
    """ SLA Status Analysis: one line per ticket and SLA policy, like the standard helpdesk SLA report.
    The status is evaluated when the report is read, so an overdue SLA is reported as failed
    without waiting for the SLA cron. """
    _name = 'helpdesk.management.sla.report'
    _description = 'SLA Status Analysis'
    _auto = False
    _order = 'ticket_create_date desc'
    _rec_name = 'ticket_id'

    ticket_id = fields.Many2one('helpdesk.management.ticket', string='Ticket', readonly=True)
    sla_id = fields.Many2one('helpdesk.management.sla', string='SLA Policy', readonly=True)
    sla_stage_id = fields.Many2one('helpdesk.management.stage', string='SLA Target Stage', readonly=True)
    team_id = fields.Many2one('helpdesk.management.team', string='Team', readonly=True)
    stage_id = fields.Many2one('helpdesk.management.stage', string='Ticket Stage', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned to', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', readonly=True)
    ticket_create_date = fields.Datetime(string='Ticket Created On', readonly=True)
    ticket_closed = fields.Boolean(string='Ticket Closed', readonly=True)
    deadline = fields.Datetime(string='SLA Deadline', readonly=True)
    reached_datetime = fields.Datetime(string='SLA Reached On', readonly=True)
    status = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('reached', 'Success'),
        ('failed', 'Failed'),
    ], string='SLA Status', readonly=True)
    is_paused = fields.Boolean(string='Paused', readonly=True)
    success_rate = fields.Float(string='SLA Success (%)', aggregator='avg', readonly=True,
                                help="Share of finished SLAs reached on time. Ongoing SLAs are not counted.")
    exceeded_hours = fields.Float(string='Exceeded Hours', aggregator='avg', readonly=True,
                                  help="Hours past the deadline for failed SLAs.")

    def _select(self):
        return SQL("""
            s.id AS id,
            s.ticket_id AS ticket_id,
            s.sla_id AS sla_id,
            sla.stage_id AS sla_stage_id,
            t.team_id AS team_id,
            t.stage_id AS stage_id,
            t.user_id AS user_id,
            t.partner_id AS partner_id,
            t.company_id AS company_id,
            t.priority AS priority,
            t.create_date AS ticket_create_date,
            COALESCE(ts.is_close, FALSE) AS ticket_closed,
            s.deadline AS deadline,
            s.reached_datetime AS reached_datetime,
            s.is_paused AS is_paused,
            %(status)s AS status,
            CASE %(status)s
                WHEN 'reached' THEN 100.0
                WHEN 'failed' THEN 0.0
            END AS success_rate,
            CASE WHEN %(status)s = 'failed' AND s.deadline IS NOT NULL THEN
                GREATEST(EXTRACT(EPOCH FROM (
                    COALESCE(s.reached_datetime, s.failed_datetime, NOW() AT TIME ZONE 'UTC') - s.deadline
                )) / 3600.0, 0)
            END AS exceeded_hours
        """, status=self._status_expression())

    def _status_expression(self):
        # Ongoing SLAs past their deadline are already failed, unless the timer is paused
        return SQL("""(CASE
            WHEN s.status IN ('reached', 'failed') THEN s.status
            WHEN NOT s.is_paused AND s.deadline < NOW() AT TIME ZONE 'UTC' THEN 'failed'
            ELSE 'ongoing'
        END)""")

    def _from(self):
        return SQL("""
            helpdesk_management_sla_status s
            JOIN helpdesk_management_ticket t ON t.id = s.ticket_id
            JOIN helpdesk_management_sla sla ON sla.id = s.sla_id
            LEFT JOIN helpdesk_management_stage ts ON ts.id = t.stage_id
        """)

    def _where(self):
        return SQL("s.status != 'cancelled' AND t.active")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL(
            "CREATE OR REPLACE VIEW %s AS (SELECT %s FROM %s WHERE %s)",
            SQL.identifier(self._table),
            self._select(),
            self._from(),
            self._where(),
        ))
