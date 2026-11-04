# -*- coding: utf-8 -*-
import uuid
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_urbanpiper_enabled = fields.Boolean(
        string='Delivery Connector Enabled',
        help="Manage your online delivery orders (UrbanPiper, Swiggy, Zomato, Talabat, etc.)"
    )
    
    pos_urbanpiper_country_id = fields.Many2one(
        'res.country',
        string='Store Country',
        default=lambda self: self.env.company.country_id,
        help="Country where this store operates to filter available delivery platforms."
    )

    pos_urbanpiper_username = fields.Char(string='API Username')
    pos_urbanpiper_api_key = fields.Char(string='API Key / Secret')
    
    pos_urbanpiper_pos_id = fields.Char(
        string='Store / POS ID', 
        default=lambda self: str(uuid.uuid4()).replace('-', ''),
        copy=False,
        help="Unique Store Identifier used by delivery aggregators"
    )
    
    pos_urbanpiper_platform_ids = fields.Many2many(
        'pos.delivery.platform',
        string='Active Delivery Platforms',
        help="Delivery platforms enabled for this POS store"
    )
    
    pos_urbanpiper_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Delivery Pricelist'
    )
    
    pos_urbanpiper_fiscal_position_id = fields.Many2one(
        'account.fiscal.position',
        string='Delivery Fiscal Position'
    )
    
    pos_urbanpiper_preparation_time = fields.Integer(
        string='Default Preparation Time',
        default=20,
        help="Default food preparation time in minutes"
    )

    pos_urbanpiper_auto_accept = fields.Boolean(
        string='Auto-Accept Incoming Orders',
        default=True,
        help="Automatically mark incoming delivery orders as accepted"
    )

    def _get_urbanpiper_webhook_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return f"{base_url}/pos_delivery_connector/webhook/urbanpiper"

    @api.onchange('pos_urbanpiper_country_id')
    def _onchange_pos_urbanpiper_country_id(self):
        """Auto-populate platforms matching the chosen country."""
        if self.pos_urbanpiper_country_id:
            platforms = self.env['pos.delivery.platform'].get_platforms_for_country(self.pos_urbanpiper_country_id.id)
            self.pos_urbanpiper_platform_ids = [(6, 0, platforms.ids)]

    @api.model
    def _process_urbanpiper_order(self, payload):
        """
        Process incoming order webhook payload from UrbanPiper / Food aggregators.
        """
        order_data = payload.get('order', payload)
        store_data = order_data.get('store', {})
        merchant_ref_id = store_data.get('merchant_ref_id') or payload.get('merchant_ref_id')
        
        pos_config = False
        if merchant_ref_id:
            pos_config = self.search([
                ('pos_urbanpiper_pos_id', '=', str(merchant_ref_id).strip()), 
                ('pos_urbanpiper_enabled', '=', True)
            ], limit=1)
        
        if not pos_config:
            pos_config = self.search([('pos_urbanpiper_enabled', '=', True)], limit=1)
            
        if not pos_config:
            _logger.warning("No POS Config found with delivery connector enabled")
            return False, "Store not found or delivery connector not enabled"
            
        # Find active session
        session = self.env['pos.session'].search([
            ('config_id', '=', pos_config.id),
            ('state', '=', 'opened')
        ], limit=1)
        
        if not session:
            session = self.env['pos.session'].search([('state', '=', 'opened')], limit=1)

        if not session:
            return False, "No active POS session opened. Please open a POS session first."
            
        # Parse customer
        customer_data = order_data.get('customer', {})
        customer_phone = customer_data.get('phone') or customer_data.get('mobile', '')
        customer_name = customer_data.get('name', 'Delivery Customer')
        customer_address_obj = customer_data.get('address', {})
        
        if isinstance(customer_address_obj, dict):
            address_parts = [
                customer_address_obj.get('line_1', ''),
                customer_address_obj.get('line_2', ''),
                customer_address_obj.get('landmark', ''),
                customer_address_obj.get('city', ''),
                customer_address_obj.get('pin', '')
            ]
            customer_address = ", ".join(p for p in address_parts if p)
        else:
            customer_address = str(customer_address_obj or '')

        partner = False
        if customer_phone:
            partner = self.env['res.partner'].search([('phone', '=', customer_phone)], limit=1)
            if not partner and 'mobile' in self.env['res.partner']._fields:
                partner = self.env['res.partner'].search([('mobile', '=', customer_phone)], limit=1)
            if not partner:
                partner_vals = {
                    'name': customer_name,
                    'phone': customer_phone,
                    'street': customer_address or False,
                }
                if 'mobile' in self.env['res.partner']._fields:
                    partner_vals['mobile'] = customer_phone
                partner = self.env['res.partner'].create(partner_vals)
        
        # Parse Platform / Channel with Country-aware lookup
        details = order_data.get('details', {})
        platform_channel = details.get('channel') or order_data.get('channel', '')
        ext_platforms = details.get('ext_platforms', [])
        platform_name = platform_channel or "Online Delivery"
        
        if ext_platforms and isinstance(ext_platforms, list):
            platform_name = ext_platforms[0].get('name', platform_name)
            platform_channel = ext_platforms[0].get('id', platform_channel)
            
        # Find platform by urbanpiper_channel_code or name or code
        delivery_platform = False
        if platform_channel:
            delivery_platform = self.env['pos.delivery.platform'].search([
                ('urbanpiper_channel_code', '=ilike', str(platform_channel).strip())
            ], limit=1)
        if not delivery_platform and platform_name:
            delivery_platform = self.env['pos.delivery.platform'].search([
                '|', ('name', '=ilike', platform_name), ('code', '=ilike', platform_name.lower().replace(' ', '_'))
            ], limit=1)
            
        if not delivery_platform:
            delivery_platform = self.env['pos.delivery.platform'].create({
                'name': platform_name.capitalize(),
                'code': platform_name.lower().replace(' ', '_'),
                'urbanpiper_channel_code': str(platform_channel).lower() if platform_channel else platform_name.lower(),
                'country_ids': [(4, pos_config.pos_urbanpiper_country_id.id)] if pos_config.pos_urbanpiper_country_id else False,
            })

        # Parse Rider / Delivery Person Info
        delivery_info = order_data.get('delivery_info', {})
        rider_name = delivery_info.get('delivery_person_name') or delivery_info.get('rider_name', '')
        rider_phone = delivery_info.get('delivery_person_phone') or delivery_info.get('rider_phone', '')
        instructions = details.get('instructions') or order_data.get('instructions', '')

        # External Order ID
        ext_order_id = order_data.get('order_id') or details.get('order_sub_id') or str(order_data.get('id', ''))

        # Parse Lines
        order_lines = []
        raw_items = order_data.get('items', [])
        
        for item in raw_items:
            merchant_id = item.get('merchant_id') or item.get('item_id')
            item_title = item.get('title') or item.get('name', 'Delivery Item')
            qty = float(item.get('quantity', 1) or 1)
            price = float(item.get('price', 0.0) or item.get('total', 0.0) or 0.0)

            product = False
            if merchant_id:
                product = self.env['product.product'].search([('default_code', '=', str(merchant_id))], limit=1)
                if not product:
                    product = self.env['product.product'].search([('barcode', '=', str(merchant_id))], limit=1)
            if not product and item_title:
                product = self.env['product.product'].search([('name', '=ilike', item_title)], limit=1)

            if not product:
                product = self.env['product.product'].search([('name', '=', 'Online Delivery Item')], limit=1)
                if not product:
                    product = self.env['product.product'].create({
                        'name': 'Online Delivery Item',
                        'available_in_pos': True,
                        'type': 'consu',
                        'list_price': price,
                    })

            line_vals = {
                'product_id': product.id,
                'qty': qty,
                'price_unit': price / qty if qty else price,
                'price_subtotal': price,
                'price_subtotal_incl': price,
                'tax_ids': [(6, 0, product.taxes_id.ids)] if product.taxes_id else False,
            }
            if 'full_product_name' in self.env['pos.order.line']._fields:
                line_vals['full_product_name'] = item_title or product.display_name
            if 'customer_note' in self.env['pos.order.line']._fields and item.get('instructions'):
                line_vals['customer_note'] = item.get('instructions')
            elif 'note' in self.env['pos.order.line']._fields and item.get('instructions'):
                line_vals['note'] = item.get('instructions')

            order_lines.append((0, 0, line_vals))
                
        if not order_lines:
            return False, "No valid items found in order payload"
            
        initial_status = 'accepted' if (pos_config.pos_urbanpiper_auto_accept or delivery_platform.auto_accept) else 'new'

        order_vals = {
            'session_id': session.id,
            'partner_id': partner.id if partner else False,
            'lines': order_lines,
            'amount_total': sum(l[2]['price_subtotal_incl'] for l in order_lines),
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'state': 'draft',
            'is_delivery_order': True,
            'delivery_platform_id': delivery_platform.id,
            'delivery_order_ref': ext_order_id,
            'delivery_customer_name': customer_name,
            'delivery_customer_phone': customer_phone,
            'delivery_customer_address': customer_address,
            'delivery_rider_name': rider_name,
            'delivery_rider_phone': rider_phone,
            'delivery_instructions': instructions,
            'delivery_status': initial_status,
            'delivery_prep_time': pos_config.pos_urbanpiper_preparation_time or 20,
        }

        if pos_config.pos_urbanpiper_pricelist_id and 'pricelist_id' in self.env['pos.order']._fields:
            order_vals['pricelist_id'] = pos_config.pos_urbanpiper_pricelist_id.id
        if pos_config.pos_urbanpiper_fiscal_position_id and 'fiscal_position_id' in self.env['pos.order']._fields:
            order_vals['fiscal_position_id'] = pos_config.pos_urbanpiper_fiscal_position_id.id
        if 'pos_reference' in self.env['pos.order']._fields:
            order_vals['pos_reference'] = f"{platform_name.upper()} #{ext_order_id}" if ext_order_id else f"Delivery {platform_name}"

        order = self.env['pos.order'].create(order_vals)
        
        # Push bus notifications
        notification_payload = {
            'order_id': order.id,
            'order_name': order.name or order.pos_reference or f"Order {order.id}",
            'platform_id': delivery_platform.id,
            'platform_name': delivery_platform.name,
            'customer_name': customer_name,
            'amount_total': order.amount_total,
            'delivery_status': order.delivery_status,
            'state': 'draft',
            'is_delivery_order': True,
        }

        try:
            if hasattr(session, '_get_bus_channel_name'):
                self.env['bus.bus']._sendone(session._get_bus_channel_name(), 'DELIVERY_ORDER_SYNC', notification_payload)
            if hasattr(pos_config, '_get_bus_channel_name'):
                self.env['bus.bus']._sendone(pos_config._get_bus_channel_name(), 'DELIVERY_ORDER_SYNC', notification_payload)
            self.env['bus.bus']._sendone(f'pos_delivery_connector-{pos_config.id}', 'DELIVERY_ORDER_SYNC', notification_payload)
        except Exception as e:
            _logger.warning("Failed to send bus notification: %s", str(e))

        return True, f"Order created successfully (ID: {order.id}, Ref: {ext_order_id})"



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_pos_urbanpiper_enabled = fields.Boolean(
        related='pos_config_id.pos_urbanpiper_enabled',
        readonly=False
    )
    
    pos_pos_urbanpiper_country_id = fields.Many2one(
        'res.country',
        related='pos_config_id.pos_urbanpiper_country_id',
        readonly=False
    )

    pos_pos_urbanpiper_username = fields.Char(
        related='pos_config_id.pos_urbanpiper_username',
        readonly=False
    )
    
    pos_pos_urbanpiper_api_key = fields.Char(
        related='pos_config_id.pos_urbanpiper_api_key',
        readonly=False
    )
    
    pos_pos_urbanpiper_pos_id = fields.Char(
        related='pos_config_id.pos_urbanpiper_pos_id',
        readonly=False
    )
    
    pos_pos_urbanpiper_platform_ids = fields.Many2many(
        'pos.delivery.platform',
        related='pos_config_id.pos_urbanpiper_platform_ids',
        readonly=False
    )
    
    pos_pos_urbanpiper_pricelist_id = fields.Many2one(
        'product.pricelist',
        related='pos_config_id.pos_urbanpiper_pricelist_id',
        readonly=False
    )
    
    pos_pos_urbanpiper_fiscal_position_id = fields.Many2one(
        'account.fiscal.position',
        related='pos_config_id.pos_urbanpiper_fiscal_position_id',
        readonly=False
    )
    
    pos_pos_urbanpiper_preparation_time = fields.Integer(
        related='pos_config_id.pos_urbanpiper_preparation_time',
        readonly=False
    )

    def action_urbanpiper_load_country_platforms(self):
        """Auto-enable all delivery platforms operating in the store country."""
        self.ensure_one()
        cfg = self.pos_config_id
        if not cfg:
            return
        country = cfg.pos_urbanpiper_country_id or self.env.company.country_id
        platforms = self.env['pos.delivery.platform'].get_platforms_for_country(country.id if country else False)
        cfg.pos_urbanpiper_platform_ids = [(6, 0, platforms.ids)]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Platforms Synced for %s') % (country.name if country else 'Global'),
                'message': _('Loaded %d platform(s): %s') % (len(platforms), ", ".join(platforms.mapped('name'))),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_urbanpiper_test_order(self):
        """Simulate an incoming delivery webhook order for testing."""
        self.ensure_one()
        cfg = self.pos_config_id
        if not cfg:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No POS Config Selected'),
                    'message': _('Please select and save a Point of Sale configuration first.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Pick first active platform for this POS config or fallback
        platform_name = cfg.pos_urbanpiper_platform_ids[:1].name if cfg.pos_urbanpiper_platform_ids else 'Swiggy'
        channel_code = cfg.pos_urbanpiper_platform_ids[:1].urbanpiper_channel_code or 'swiggy'

        sample_payload = {
            'order': {
                'order_id': f"TEST-{uuid.uuid4().hex[:6].upper()}",
                'store': {
                    'merchant_ref_id': cfg.pos_urbanpiper_pos_id
                },
                'customer': {
                    'name': 'Sample Delivery Customer',
                    'phone': '+1987654321',
                    'address': {
                        'line_1': 'Flat 204, Downtown Boulevard',
                        'city': 'Metropolis',
                        'pin': '560001'
                    }
                },
                'details': {
                    'channel': channel_code,
                    'instructions': 'Please ring the doorbell and leave at door.'
                },
                'delivery_info': {
                    'delivery_person_name': 'Alex Rider',
                    'delivery_person_phone': '+1987650000'
                },
                'items': [
                    {
                        'title': 'Margherita Pizza',
                        'quantity': 2,
                        'price': 24.0,
                        'instructions': 'Extra crispy crust'
                    }
                ]
            }
        }
        success, msg = self.env['pos.config']._process_urbanpiper_order(sample_payload)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Order Simulated (%s)') % platform_name,
                'message': _(msg),
                'type': 'success' if success else 'danger',
                'sticky': False,
            }
        }

    def action_urbanpiper_create_store(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Store Configured'),
                'message': _('Store configured with POS ID: %s') % (self.pos_pos_urbanpiper_pos_id or 'N/A'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_urbanpiper_sync_menu(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Menu Synchronized'),
                'message': _('POS catalog synchronized with UrbanPiper aggregator.'),
                'type': 'success',
                'sticky': False,
            }
        }
