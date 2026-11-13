# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.exceptions import UserError

class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config):
        """Append appointment.type and appointment.booking to the loaded POS data models when booking is enabled."""
        models_list = super()._load_pos_data_models(config)
        if config.use_booking:
            for model_name in ('appointment.type', 'appointment.booking'):
                if model_name not in models_list:
                    models_list.append(model_name)
        return models_list

    def _create_session_account_move(self, orders):
        if not orders:
            return self.env['account.move']

        # Prevent 'Even magicians can't post nothing!' UserError when a session
        # has $0 / zero-revenue orders without accounting payments or postable invoice lines.
        lines = orders.with_context(hide_combo_title=True)._prepare_account_move_line_data()
        payments = orders._prepare_account_move_line_data_for_payments()
        has_postable_lines = any(
            l.get('account.move.line', {}).get('display_type') not in ('line_section', 'line_subsection', 'line_note')
            for l in lines
        )
        if not has_postable_lines and not payments:
            return self.env['account.move']

        try:
            return super()._create_session_account_move(orders)
        except UserError as e:
            if "Even magicians can't post nothing!" in str(e):
                return self.env['account.move']
            raise
