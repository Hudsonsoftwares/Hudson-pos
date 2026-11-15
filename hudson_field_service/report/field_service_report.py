# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class ReportFieldServiceAnalysis(models.Model):
    _name = 'report.field.service.analysis'
    _description = 'Field Service Analysis Report'
    _auto = False
    _order = 'date_planned desc'

    name = fields.Char(string='Reference', readonly=True)
    title = fields.Char(string='Title', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Technician', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)
    stage_id = fields.Many2one('field.service.stage', string='Stage', readonly=True)
    state = fields.Selection([
        ('new', 'New'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('paused', 'Paused'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', readonly=True)
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', readonly=True)
    date_planned = fields.Datetime(string='Planned Date', readonly=True)
    date_start = fields.Datetime(string='Start Date', readonly=True)
    date_end = fields.Datetime(string='End Date', readonly=True)
    date_deadline = fields.Date(string='Deadline', readonly=True)
    duration_planned = fields.Float(string='Planned Duration (h)', readonly=True, aggregator='avg')
    duration_actual = fields.Float(string='Actual Duration (h)', readonly=True, aggregator='avg')
    total_products_amount = fields.Float(string='Products Amount', readonly=True, aggregator='sum')
    total_time_spent = fields.Float(string='Time Spent (h)', readonly=True, aggregator='sum')
    nbr = fields.Integer(string='# of Orders', readonly=True, aggregator='sum')
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    invoice_status = fields.Selection([
        ('not_invoiced', 'Not Invoiced'),
        ('invoiced', 'Invoiced'),
    ], string='Invoice Status', readonly=True)
    tag_ids = fields.Many2many('field.service.tag', readonly=True)
    has_project = fields.Boolean(string='Has Project', readonly=True)

    def _select(self):
        return """
            SELECT
                o.id AS id,
                o.name AS name,
                o.title AS title,
                o.partner_id AS partner_id,
                o.employee_id AS employee_id,
                o.project_id AS project_id,
                o.stage_id AS stage_id,
                o.state AS state,
                o.priority AS priority,
                o.date_planned AS date_planned,
                o.date_start AS date_start,
                o.date_end AS date_end,
                o.date_deadline AS date_deadline,
                o.duration_planned AS duration_planned,
                o.duration_actual AS duration_actual,
                o.total_products_amount AS total_products_amount,
                o.total_time_spent AS total_time_spent,
                1 AS nbr,
                o.company_id AS company_id,
                o.invoice_status AS invoice_status,
                CASE WHEN o.project_id IS NOT NULL THEN true ELSE false END AS has_project
        """

    def _from(self):
        return """
            FROM field_service_order o
        """

    def _where(self):
        return """
            WHERE o.active = true
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
            )
        """ % (self._table, self._select(), self._from(), self._where()))
