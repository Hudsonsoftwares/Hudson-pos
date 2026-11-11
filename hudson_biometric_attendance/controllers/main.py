# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class HudsonAttendanceWebhookController(http.Controller):

    @http.route('/hudson_attendance/webhook/<string:device_uuid>', type='json', auth='public', methods=['POST'], csrf=False)
    def receive_webhook(self, device_uuid, **kwargs):
        # 1. Resolve Device
        device = request.env['hudson.attendance.device'].sudo().search([('uuid', '=', device_uuid)], limit=1)
        if not device:
            return {"status": "error", "message": "Invalid device UUID"}

        # 2. Authenticate
        token = request.httprequest.headers.get('X-API-Token')
        if not device.verify_webhook_token(token):
            return {"status": "error", "message": "Unauthorized: Invalid API Token"}

        # 3. Read Raw Payload
        payload_data = request.httprequest.get_data()
        payload_size = len(payload_data)
        source_ip = request.httprequest.remote_addr

        try:
            payload = json.loads(payload_data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            request.env['hudson.attendance.webhook.log'].sudo().create({
                'device_id': device.id,
                'source_ip': source_ip,
                'payload_size': payload_size,
                'payload': payload_data.decode('utf-8', errors='ignore'),
                'result': 'failed',
                'error_message': f"Invalid JSON payload: {str(e)}"
            })
            return {"status": "error", "message": "Invalid JSON payload"}

        # 4. Extract records list from payload
        records = []
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            found_list = False
            for val in payload.values():
                if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                    records = val
                    found_list = True
                    break
            if not found_list:
                records = [payload]
        else:
            records = [payload]

        # 5. Load field mappings for the device
        mappings = request.env['hudson.attendance.field.mapping'].sudo().search([('device_id', '=', device.id)])
        mapping_dict = {m.target_field: m for m in mappings}

        if not mappings:
            err_msg = "No field mappings configured for this device."
            request.env['hudson.attendance.webhook.log'].sudo().create({
                'device_id': device.id,
                'source_ip': source_ip,
                'payload_size': payload_size,
                'payload': json.dumps(payload),
                'result': 'failed',
                'error_message': err_msg
            })
            return {"status": "error", "message": err_msg}

        # Helper to resolve dot notation path
        def get_by_path(data, path):
            if not path:
                return None
            parts = path.split('.')
            val = data
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                elif isinstance(val, list):
                    try:
                        val = val[int(part)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
            return val

        processed_count = 0
        failed_count = 0

        for rec in records:
            extracted = {}
            for target_field, m in mapping_dict.items():
                val = get_by_path(rec, m.src_path)
                
                # Apply value mapping for punch_type
                if target_field == 'punch_type' and val is not None:
                    str_val = str(val).strip()
                    val_map = m.value_mapping_ids.filtered(lambda vm: vm.src_value == str_val)
                    if val_map:
                        val = val_map[0].target_value
                    else:
                        val = str_val.lower()

                extracted[target_field] = val

            # Check if required fields are present
            if not extracted.get('employee_code') or not extracted.get('punch_time') or not extracted.get('punch_type'):
                failed_count += 1
                continue

            # Create Raw Punch record
            try:
                raw_punch = request.env['hudson.attendance.raw.punch'].sudo().create({
                    'device_id': device.id,
                    'employee_code': str(extracted['employee_code']),
                    'punch_time': extracted['punch_time'],
                    'punch_type': extracted['punch_type'],
                    'external_uid': str(extracted['external_uid']) if extracted.get('external_uid') else False,
                })
                raw_punch._process_punch()
                processed_count += 1
            except (ValidationError, UserError, ValueError, TypeError, Exception) as e:
                _logger.exception("Failed to insert/process webhook raw punch for employee %s: %s", extracted.get('employee_code'), e)
                failed_count += 1

        result_msg = f"Processed: {processed_count}, Failed/Skipped: {failed_count}"
        request.env['hudson.attendance.webhook.log'].sudo().create({
            'device_id': device.id,
            'source_ip': source_ip,
            'payload_size': payload_size,
            'payload': json.dumps(payload),
            'result': 'success' if processed_count > 0 else 'failed',
            'error_message': result_msg
        })

        return {
            "status": "success",
            "message": result_msg,
            "processed": processed_count,
            "failed": failed_count
        }
