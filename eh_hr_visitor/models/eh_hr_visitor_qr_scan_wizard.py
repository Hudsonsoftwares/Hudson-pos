# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EhHrVisitorQrScanWizard(models.TransientModel):
    _name = 'eh.hr.visitor.qr.scan.wizard'
    _description = 'Simulate QR Scan Wizard'

    scan_input = fields.Char(string='Scan Input')
    visitor_id = fields.Many2one('eh.hr.visitor', string='Visitor')

    @api.onchange('scan_input')
    def _onchange_scan_input(self):
        if self.scan_input:
            visitor = self.env['eh.hr.visitor'].search([('visit_number', '=', self.scan_input)], limit=1)
            if visitor:
                self.visitor_id = visitor.id

    def action_process_scan(self):
        self.ensure_one()
        visitor = self.visitor_id
        if not visitor and self.scan_input:
            visitor = self.env['eh.hr.visitor'].search([('visit_number', '=', self.scan_input)], limit=1)
        
        if not visitor:
            raise ValidationError(_("No visitor found for this QR code or visit number."))

        if visitor.state not in ['pending', 'confirmed', 'invitation_sent']:
            raise ValidationError(_("Visitor %s is not in a valid state to register arrival. Current state: %s") % (visitor.name, visitor.state))

        visitor.write({'state': 'arrived'})
        visitor.message_post(body=_("Visitor scanned QR pass and is marked as Arrived at reception."))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Visitor Reception',
            'res_model': 'eh.hr.visitor',
            'res_id': visitor.id,
            'view_mode': 'form',
            'target': 'current',
        }
