# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosDeliveryConnectorController(http.Controller):

    @http.route('/pos_delivery_connector/webhook/urbanpiper', type='http', auth="public", methods=['POST'], csrf=False)
    def urbanpiper_webhook(self, **post):
        """
        Endpoint to receive UrbanPiper / Aggregator order webhooks.
        """
        _logger.info("Received UrbanPiper Webhook Request")
        
        try:
            raw_body = request.httprequest.data
            if not raw_body:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Empty payload'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )
            
            data = json.loads(raw_body.decode('utf-8') if isinstance(raw_body, bytes) else raw_body)
            _logger.debug("UrbanPiper Webhook Data: %s", data)

            # Process the order payload
            success, message = request.env['pos.config'].sudo()._process_urbanpiper_order(data)
            
            if not success:
                _logger.warning("UrbanPiper order processing failed: %s", message)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': message}),
                    headers={'Content-Type': 'application/json'},
                    status=422
                )

            _logger.info("UrbanPiper order processed successfully: %s", message)
            return request.make_response(
                json.dumps({'status': 'success', 'message': message}),
                headers={'Content-Type': 'application/json'},
                status=200
            )
            
        except json.JSONDecodeError:
            _logger.error("Invalid JSON received on UrbanPiper webhook")
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Invalid JSON format'}),
                headers={'Content-Type': 'application/json'},
                status=400
            )
        except Exception as e:
            _logger.exception("Error processing UrbanPiper webhook: %s", str(e))
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    @http.route('/pos_delivery_connector/webhook/order_status', type='http', auth="public", methods=['POST'], csrf=False)
    def update_order_status_webhook(self, **post):
        """
        Endpoint to update status of an existing delivery order (e.g. rider assigned, delivered, cancelled).
        """
        try:
            raw_body = request.httprequest.data
            data = json.loads(raw_body.decode('utf-8') if isinstance(raw_body, bytes) else raw_body)
            
            order_ref = data.get('order_id') or data.get('order_ref')
            new_status = data.get('status') # accepted, preparing, ready, dispatched, delivered, cancelled
            
            if not order_ref:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Missing order_id'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            order = request.env['pos.order'].sudo().search([
                ('delivery_order_ref', '=', str(order_ref).strip())
            ], limit=1)

            if not order:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': f'Order {order_ref} not found'}),
                    headers={'Content-Type': 'application/json'},
                    status=404
                )

            update_vals = {}
            if new_status and new_status in ['new', 'accepted', 'preparing', 'ready', 'dispatched', 'delivered', 'cancelled']:
                update_vals['delivery_status'] = new_status
            
            if data.get('rider_name'):
                update_vals['delivery_rider_name'] = data.get('rider_name')
            if data.get('rider_phone'):
                update_vals['delivery_rider_phone'] = data.get('rider_phone')

            if update_vals:
                order.write(update_vals)
                
            return request.make_response(
                json.dumps({'status': 'success', 'message': 'Order status updated'}),
                headers={'Content-Type': 'application/json'},
                status=200
            )
        except Exception as e:
            _logger.exception("Error updating order status: %s", str(e))
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    @http.route('/pos_delivery_connector/api/platforms', type='json', auth="user", methods=['POST'])
    def get_platforms(self):
        platforms = request.env['pos.delivery.platform'].search_read(
            [], ['id', 'name', 'code', 'sequence', 'color', 'auto_accept']
        )
        return platforms
