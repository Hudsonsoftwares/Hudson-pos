# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hds_dms_store_payslips = fields.Boolean(
        related='company_id.hds_dms_store_payslips',
        readonly=False,
    )

    def action_hds_dms_store_existing_payslips(self):
        """Queue the validated payslips of the company that are not in Documents yet."""
        self.ensure_one()
        slips = self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('done', 'paid')),
            ('hds_dms_state', '!=', 'stored'),
        ])
        slips._hds_dms_queue()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Store payslips in Documents"),
                'message': _("%(count)s payslip(s) queued: their PDFs are stored in the employee folders "
                             "within a few minutes.", count=len(slips)),
                'type': 'success',
                'sticky': False,
            },
        }
