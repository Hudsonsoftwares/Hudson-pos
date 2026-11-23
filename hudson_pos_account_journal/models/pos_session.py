# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_session_closing_journal(self):
        """Journal that receives the session closing entries.

        Uses the POS config's "Point of Sale Journal" (journal_id). Falls back
        to the company's standard POS journal (code POSS), and finally to the
        stock closing journal if neither is a usable sale journal.
        """
        self.ensure_one()
        config = self.config_id
        journal = config.journal_id
        if not journal or journal.type != 'sale' or journal.company_id != self.company_id:
            journal = self.env['account.journal'].with_company(
                self.company_id,
            )._ensure_company_account_journal()
        return journal or config.closing_journal_id

    def _prepare_session_move_vals(self, orders):
        vals = super()._prepare_session_move_vals(orders)
        journal = self._get_session_closing_journal()
        if journal:
            vals['journal_id'] = journal.id
        return vals
