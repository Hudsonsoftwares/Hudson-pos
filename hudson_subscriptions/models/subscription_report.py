# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools


class SaleSubscriptionReport(models.Model):
    _name = 'sale.subscription.report'
    _description = 'Subscription Analysis & MRR Report'
    _auto = False
    _order = 'start_date desc, partner_id'

    order_id = fields.Many2one('sale.order', string='Subscription Order', readonly=True)
    name = fields.Char(string='Order Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    plan_id = fields.Many2one('sale.subscription.plan', string='Recurring Plan', readonly=True)
    close_reason_id = fields.Many2one('sale.subscription.close.reason', string='Close Reason', readonly=True)
    subscription_state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('3_progress', 'In Progress'),
        ('4_paused', 'Paused'),
        ('5_renew', 'To Renew'),
        ('5_renewed', 'Renewed'),
        ('6_churn', 'Churned'),
        ('7_upsell', 'Upsell'),
    ], string='Subscription Status', readonly=True)

    start_date = fields.Date(string='Start Date', readonly=True)
    next_invoice_date = fields.Date(string='Next Invoice Date', readonly=True)
    end_date = fields.Date(string='End Date', readonly=True)
    close_date = fields.Date(string='Close Date', readonly=True)

    recurring_total = fields.Monetary(string='Recurring Total', readonly=True)
    recurring_monthly = fields.Monetary(string='Monthly Recurring Revenue (MRR)', readonly=True)
    recurring_yearly = fields.Monetary(string='Annual Run Rate (ARR)', readonly=True)
    mrr_change = fields.Monetary(string='MRR Change', readonly=True)
    mrr_new = fields.Monetary(string='New MRR', readonly=True)
    mrr_expansion = fields.Monetary(string='Expansion / Upsell MRR', readonly=True)
    mrr_churn = fields.Monetary(string='Churned MRR', readonly=True)
    subscription_count = fields.Integer(string='Subscription Count', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE or REPLACE VIEW {self._table} AS (
                SELECT
                    so.id AS id,
                    so.id AS order_id,
                    so.name AS name,
                    so.partner_id AS partner_id,
                    so.user_id AS user_id,
                    so.team_id AS team_id,
                    so.company_id AS company_id,
                    so.currency_id AS currency_id,
                    so.plan_id AS plan_id,
                    so.close_reason_id AS close_reason_id,
                    so.subscription_state AS subscription_state,
                    so.start_date AS start_date,
                    so.next_invoice_date AS next_invoice_date,
                    so.end_date AS end_date,
                    so.close_date AS close_date,
                    COALESCE(so.recurring_total, 0.0) AS recurring_total,
                    COALESCE(so.recurring_monthly, 0.0) AS recurring_monthly,
                    COALESCE(so.recurring_monthly, 0.0) * 12.0 AS recurring_yearly,
                    COALESCE(so.mrr_change, 0.0) AS mrr_change,
                    CASE 
                        WHEN so.origin_order_id IS NULL AND so.subscription_state != '6_churn' THEN COALESCE(so.recurring_monthly, 0.0)
                        ELSE 0.0
                    END AS mrr_new,
                    CASE 
                        WHEN so.origin_order_id IS NOT NULL AND so.mrr_change > 0 THEN so.mrr_change
                        ELSE 0.0
                    END AS mrr_expansion,
                    CASE 
                        WHEN so.subscription_state = '6_churn' THEN COALESCE(so.recurring_monthly, 0.0)
                        ELSE 0.0
                    END AS mrr_churn,
                    1 AS subscription_count
                FROM sale_order so
                WHERE so.is_subscription = true
            )
        """)
