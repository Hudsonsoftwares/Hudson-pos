from odoo import models, api

class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials._hudson_sync_payment_and_invoice_states()
        return partials

    def unlink(self):
        lines = self.debit_move_id | self.credit_move_id
        moves = lines.move_id
        affected_moves = moves.filtered(lambda m: m.is_invoice(True))
        affected_payments = self.env['account.payment'].search([
            '|', '|',
            ('move_id', 'in', moves.ids),
            ('reconciled_bill_ids', 'in', affected_moves.ids),
            ('reconciled_invoice_ids', 'in', affected_moves.ids),
        ]) | affected_moves.matched_payment_ids

        res = super().unlink()

        if affected_payments:
            affected_payments.invalidate_recordset(['state', 'is_matched', 'is_reconciled'])
            affected_payments._compute_state()
            affected_payments._compute_reconciliation_status()
            affected_moves |= affected_payments.reconciled_bill_ids | affected_payments.reconciled_invoice_ids

        if affected_moves:
            affected_moves.invalidate_recordset(['payment_state', 'status_in_payment', 'amount_residual'])
            affected_moves._compute_payment_state()

        return res

    def _hudson_sync_payment_and_invoice_states(self):
        lines = self.debit_move_id | self.credit_move_id
        moves = lines.move_id
        invoices = moves.filtered(lambda m: m.is_invoice(True))

        payments = self.env['account.payment'].search([
            '|', '|',
            ('move_id', 'in', moves.ids),
            ('reconciled_bill_ids', 'in', invoices.ids),
            ('reconciled_invoice_ids', 'in', invoices.ids),
        ]) | invoices.matched_payment_ids

        if payments:
            payments.invalidate_recordset(['state', 'is_matched', 'is_reconciled'])
            payments._compute_state()
            payments._compute_reconciliation_status()
            invoices |= payments.reconciled_bill_ids | payments.reconciled_invoice_ids

        if invoices:
            invoices.invalidate_recordset(['payment_state', 'status_in_payment', 'amount_residual'])
            invoices._compute_payment_state()

