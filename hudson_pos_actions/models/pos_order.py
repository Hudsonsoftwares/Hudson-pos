# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def save_customer_note_from_pos(self, order_vals):
        """Persists customer note on existing draft pos.order or customer."""
        uuid = order_vals.get('uuid')
        note = order_vals.get('note', '')
        partner_id = order_vals.get('partner_id')

        if uuid:
            pos_order = self.search([('uuid', '=', uuid), ('state', '=', 'draft')], limit=1)
            if pos_order:
                pos_order.write({'general_customer_note': note})

        if partner_id and order_vals.get('save_to_partner'):
            partner = self.env['res.partner'].browse(partner_id)
            if partner.exists():
                partner.write({'comment': note})

        return {'success': True}

    @api.model
    def validate_code_from_pos(self, code, config_id=False):
        """Validates a coupon/promo/discount code from POS."""
        if not code:
            return {'valid': False, 'message': _("Please enter a code.")}
        code = str(code).strip()

        # 1. Check loyalty cards if model exists
        if 'loyalty.card' in self.env:
            card = self.env['loyalty.card'].search([('code', '=', code)], limit=1)
            if card:
                if not card.program_id.active:
                    return {'valid': False, 'message': _("This loyalty program is inactive.")}
                if card.expiration_date and card.expiration_date < fields.Date.today():
                    return {'valid': False, 'message': _("This card has expired.")}
                if card.points <= 0 and card.program_id.program_type != 'coupons':
                    return {'valid': False, 'message': _("This card has no remaining balance/points.")}
                return {
                    'valid': True,
                    'type': 'loyalty_card',
                    'program_name': card.program_id.name,
                    'points': card.points,
                    'message': _("Valid %s code! Balance: %s", card.program_id.name, card.points),
                }

        # 2. Check loyalty rules (promotion codes)
        if 'loyalty.rule' in self.env:
            rule = self.env['loyalty.rule'].search([('code', '=', code)], limit=1)
            if rule:
                if not rule.program_id.active:
                    return {'valid': False, 'message': _("This promotion is inactive.")}
                return {
                    'valid': True,
                    'type': 'loyalty_rule',
                    'program_name': rule.program_id.name,
                    'message': _("Valid promotion code for %s!", rule.program_id.name),
                }

        return {'valid': False, 'message': _("Invalid or expired code (%s).", code)}

    @api.model
    def create_sale_quotation_from_pos(self, order_data):
        """Creates a quotation (sale.order) in draft state from POS cart lines."""
        partner_id = order_data.get('partner_id')
        if not partner_id:
            return {'success': False, 'message': _("Please select a Customer first before saving as quotation.")}

        lines_data = order_data.get('lines', [])
        if not lines_data:
            return {'success': False, 'message': _("Cannot create quotation from an empty cart.")}

        order_lines = []
        for l in lines_data:
            product_id = l.get('product_id')
            qty = float(l.get('qty', 1.0))
            price_unit = float(l.get('price_unit', 0.0))
            discount = float(l.get('discount', 0.0))
            order_lines.append((0, 0, {
                'product_id': product_id,
                'product_uom_qty': qty,
                'price_unit': price_unit,
                'discount': discount,
            }))

        company_id = order_data.get('company_id') or self.env.company.id
        pricelist_id = order_data.get('pricelist_id')
        so_vals = {
            'partner_id': partner_id,
            'company_id': company_id,
            'order_line': order_lines,
            'origin': _("POS: %s", order_data.get('pos_reference', 'Cart')),
        }
        if pricelist_id:
            so_vals['pricelist_id'] = pricelist_id

        sale_order = self.env['sale.order'].create(so_vals)
        return {
            'success': True,
            'order_id': sale_order.id,
            'order_name': sale_order.name,
            'message': _("Quotation %s created successfully in Sales!", sale_order.name),
        }

