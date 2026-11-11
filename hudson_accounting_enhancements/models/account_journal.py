import ast
from odoo import models, api, _

class AccountJournal(models.Model):
    _inherit = "account.journal"

    def open_action(self):
        self.ensure_one()
        if self.type in ('bank', 'cash'):
            return self._hudson_open_transactions_view()
        return super(AccountJournal, self).open_action()

    def _hudson_open_transactions_view(self, apply_to_review_filter=False):
        """Open the Hudson transactions view, optionally with 'To Review' filter applied."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            'hudson_accounting_enhancements.action_hudson_bank_matching_tree'
        )

        action_context = action.get('context', {})
        if isinstance(action_context, str):
            action_context = ast.literal_eval(action_context)

        action['context'] = {
            **action_context,
            **self.env.context,
            'default_journal_id': self.id,
        }
        action['domain'] = [('journal_id', '=', self.id)]

        if apply_to_review_filter:
            action['context']['search_default_to_review'] = 1

        return action

    def om_action_open_bank_reconciliation(self, state='to_reconcile', st_line_id=False):
        """Override: redirect to Hudson transactions view with 'To Review' filter instead of OM reconciliation."""
        self.ensure_one()
        return self._hudson_open_transactions_view(apply_to_review_filter=True)

    def om_action_open_to_review(self):
        """Override: redirect to Hudson transactions view with 'To Review' filter."""
        self.ensure_one()
        return self._hudson_open_transactions_view(apply_to_review_filter=True)

    def om_action_new_transaction(self):
        """Override: redirect to Hudson transactions view with inline 'New Transaction' row open."""
        self.ensure_one()
        action = self._hudson_open_transactions_view()
        action['context']['show_new_transaction'] = True
        return action

    @api.model
    def get_account_dashboard_kpis(self):
        cards = super().get_account_dashboard_kpis()

        # Action for Expenses -> Profit and Loss
        pl_action = self.env.ref('hudson_accounting_enhancements.action_server_report_profit_and_loss', raise_if_not_found=False) \
            or self.env.ref('accounting_pdf_reports.action_account_report_pl', raise_if_not_found=False)

        # Action for Receivable -> Aged Receivable
        ar_action = self.env.ref('hudson_accounting_enhancements.action_server_aged_receivable', raise_if_not_found=False) \
            or self.env.ref('accounting_pdf_reports.action_account_aged_receivable', raise_if_not_found=False)

        # Action for Payable -> Aged Payable
        ap_action = self.env.ref('hudson_accounting_enhancements.action_server_aged_payable', raise_if_not_found=False) \
            or self.env.ref('accounting_pdf_reports.action_account_aged_payable', raise_if_not_found=False)

        # Action for Setup Your Invoice Layout
        invoice_layout_action = self.env.ref('account.action_base_document_layout_configurator', raise_if_not_found=False) \
            or self.env.ref('web.action_base_document_layout_configurator', raise_if_not_found=False)

        has_invoice_layout = False
        for card in cards:
            if card.get('id') == 'expenses' and not card.get('action_id') and pl_action:
                card['action_id'] = pl_action.id
            elif card.get('id') == 'receivable' and not card.get('action_id') and ar_action:
                card['action_id'] = ar_action.id
            elif card.get('id') == 'payable' and not card.get('action_id') and ap_action:
                card['action_id'] = ap_action.id
            elif card.get('id') == 'invoice_layout':
                has_invoice_layout = True

        if not has_invoice_layout and invoice_layout_action:
            cards.append({
                'id': 'invoice_layout',
                'name': self.env._('Setup Your Invoice Layout'),
                'is_invoice_layout_card': True,
                'image': '/web/static/img/mimetypes/document.svg',
                'action_id': invoice_layout_action.id,
            })

        return cards
