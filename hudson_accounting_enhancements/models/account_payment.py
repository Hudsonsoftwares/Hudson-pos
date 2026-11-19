from odoo import models, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _notify_invoices_payment_state(self):
        for payment in self:
            moves = (payment.reconciled_bill_ids | payment.reconciled_invoice_ids | payment.invoice_ids).filtered(
                lambda m: m.is_invoice(True) and m.state == 'posted'
            )
            extra_moves = self.env['account.move'].search([
                ('matched_payment_ids', 'in', payment.ids),
                ('state', '=', 'posted'),
            ])
            moves |= extra_moves.filtered(lambda m: m.is_invoice(True))

            # Also check moves linked through payment's move lines partial reconciliations
            if payment.move_id and payment.move_id.state == 'posted':
                lines = payment.move_id.line_ids
                counterpart_lines = lines.matched_debit_ids.debit_move_id | lines.matched_credit_ids.credit_move_id
                moves |= counterpart_lines.move_id.filtered(lambda m: m.is_invoice(True) and m.state == 'posted')

            if moves:
                moves.invalidate_recordset(['payment_state', 'status_in_payment', 'amount_residual'])
                moves._compute_payment_state()

    def _compute_state(self):
        super()._compute_state()
        self._notify_invoices_payment_state()

    def _compute_reconciliation_status(self):
        super()._compute_reconciliation_status()
        self._notify_invoices_payment_state()

    def write(self, vals):
        res = super().write(vals)
        if {'state', 'is_matched'} & set(vals.keys()):
            self._notify_invoices_payment_state()
        return res

