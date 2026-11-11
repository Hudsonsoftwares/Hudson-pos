from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import SQL

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    hudson_deferred_start_date = fields.Date(string='Deferred Start Date')
    hudson_deferred_end_date = fields.Date(string='Deferred End Date')

    @api.constrains('hudson_deferred_start_date', 'hudson_deferred_end_date')
    def _check_hudson_deferred_dates(self):
        for line in self:
            if line.hudson_deferred_start_date and line.hudson_deferred_end_date:
                if line.hudson_deferred_start_date > line.hudson_deferred_end_date:
                    raise ValidationError("Deferred Start Date cannot be after Deferred End Date.")

    def action_hudson_manual_reconcile(self):
        """Action for the manual Reconcile button on the custom Reconcile view."""
        return self.reconcile()

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        query = super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)
        
        match_amount = self.env.context.get('hudson_match_amount')
        match_partner_id = self.env.context.get('hudson_match_partner_id')
        
        # Safely extract float from match_amount
        if isinstance(match_amount, dict):
            match_amount = match_amount.get('value') or match_amount.get('amount') or match_amount.get('id')
        elif isinstance(match_amount, (list, tuple)) and match_amount:
            match_amount = match_amount[0]
        try:
            match_amount = float(match_amount) if match_amount is not None and match_amount is not False else None
        except (ValueError, TypeError):
            match_amount = None

        # Safely extract int from match_partner_id
        if isinstance(match_partner_id, dict):
            match_partner_id = match_partner_id.get('id')
        elif isinstance(match_partner_id, (list, tuple)) and match_partner_id:
            match_partner_id = match_partner_id[0]
        try:
            match_partner_id = int(match_partner_id) if match_partner_id else None
        except (ValueError, TypeError):
            match_partner_id = None
        
        if match_amount is not None or match_partner_id:
            alias = self._table
            order_terms = []
            conditions = []
            
            if match_amount is not None and match_partner_id:
                conditions.append(
                    SQL("(ABS(%s.amount_residual - %s) < 0.005 AND %s.partner_id = %s) THEN 1",
                        SQL.identifier(alias), match_amount, SQL.identifier(alias), match_partner_id)
                )
            if match_amount is not None:
                conditions.append(
                    SQL("ABS(%s.amount_residual - %s) < 0.005 THEN 2",
                        SQL.identifier(alias), match_amount)
                )
                conditions.append(
                    SQL("ABS(ABS(%s.amount_residual) - ABS(%s)) < 0.005 THEN 3",
                        SQL.identifier(alias), match_amount)
                )
            if match_partner_id:
                conditions.append(
                    SQL("%s.partner_id = %s THEN 4",
                        SQL.identifier(alias), match_partner_id)
                )
                
            if conditions:
                sql_when = SQL(" WHEN ").join(conditions)
                case_order = SQL("CASE WHEN %s ELSE 5 END", sql_when)
                order_terms.append(case_order)
                
            if query.order:
                order_terms.append(query.order)
            else:
                order_terms.append(SQL("%s.date DESC, %s.id DESC", SQL.identifier(alias), SQL.identifier(alias)))
                
            query.order = SQL(", ").join(order_terms)
            
        return query
