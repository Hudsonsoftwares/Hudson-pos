# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_enable_qr_self_join = fields.Boolean(
        related='pos_config_id.enable_qr_self_join', readonly=False)
    pos_qr_join_url = fields.Char(related='pos_config_id.qr_join_url')
    pos_qr_code_image = fields.Binary(related='pos_config_id.qr_code_image')
    pos_qr_code_outdated = fields.Boolean(related='pos_config_id.qr_code_outdated')
    pos_waitlist_minutes_per_party = fields.Integer(
        related='pos_config_id.waitlist_minutes_per_party', readonly=False)
    pos_waitlist_max_party_size = fields.Integer(
        related='pos_config_id.waitlist_max_party_size', readonly=False)

    def _qr_pos_config(self):
        self.ensure_one()
        # Persist a just-ticked "Enable QR Self Join" before acting on it.
        if self.pos_config_id.enable_qr_self_join != self.pos_enable_qr_self_join:
            self.pos_config_id.enable_qr_self_join = self.pos_enable_qr_self_join
        return self.pos_config_id

    def action_generate_qr_code(self):
        return self._qr_pos_config().action_generate_qr_code()

    def action_download_qr_code(self):
        return self._qr_pos_config().action_download_qr_code()

    def action_print_qr_code(self):
        return self._qr_pos_config().action_print_qr_code()
