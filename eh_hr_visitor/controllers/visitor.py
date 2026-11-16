# -*- encoding: utf-8 -*-
"""Visitor sign-in / sign-out endpoints for the front-desk kiosk.

Authenticated by the same kiosk device token issued by the base module
pairing flow, so the same reception tablet can serve both employee
attendance (via the face kiosk) and visitor sign-in. The visitor
themselves is not authenticated; the device is.
"""
import base64
import json

# pyrefly: ignore [missing-import]
from odoo import _, fields, http
import logging
from functools import wraps

# pyrefly: ignore [missing-import]
from odoo.http import request

_logger = logging.getLogger(__name__)

KIOSK_PHOTO_FILENAME = 'visitor.png'
PREREG_PHOTO_FILENAME = 'visitor_photo.jpg'
AGREEMENT_PDF_FILENAME = 'Agreements_%s.pdf'

def catch_json_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _logger.exception("Error in JSON route")
            return _json_response({'error': 'An internal error occurred.'}, status=500)
    return wrapper

def _process_visitor_files(data, purpose):
    if purpose.nda_required and not data.get('nda_accepted'):
        return {'error': 'NDA acceptance required'}, None

    digital_signature_b64 = data.get('digital_signature_b64')
    digital_signature = False
    if purpose.nda_required and not digital_signature_b64:
        return {'error': 'Signature is required'}, None
    if digital_signature_b64:
        try:
            if digital_signature_b64.startswith('data:'):
                digital_signature_b64 = digital_signature_b64.split(',', 1)[1]
            digital_signature = base64.b64encode(base64.b64decode(digital_signature_b64))
        except Exception:
            _logger.exception("Error decoding digital signature")

    photo_b64 = data.get('photo_b64')
    photo_data = False
    photo_filename = False
    if photo_b64:
        try:
            if photo_b64.startswith('data:'):
                photo_b64 = photo_b64.split(',', 1)[1]
            photo_data = base64.b64encode(base64.b64decode(photo_b64))
            photo_filename = KIOSK_PHOTO_FILENAME
        except Exception:
            return {'error': 'photo_b64 is not valid base64'}, None

    return None, {
        'digital_signature': digital_signature,
        'photo': photo_data,
        'photo_filename': photo_filename,
    }


def _client_ip():
    return request.httprequest.headers.get('X-Real-IP') \
        or request.httprequest.headers.get('X-Forwarded-For', '').split(',')[0].strip() \
        or request.httprequest.remote_addr


def _client_user_agent():
    return request.httprequest.headers.get('User-Agent', '')[:255]


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )


def _get_device_by_token(token):
    if not token:
        return None
    Device = request.env['eh.hr.kiosk.terminal'].sudo()
    return Device.search([
        ('device_token', '=', token),
        ('active', '=', True),
    ], limit=1)


def _throttled(scope, key, limit):
    """Return a 429 JSON response if the caller is over budget, else None."""
    if not request.env['eh.hr.rate.limit'].sudo().hit(scope, key, limit):
        return _json_response({'error': 'rate_limited'}, status=429)
    return None


class EhHrVisitorController(http.Controller):

    @http.route('/eh_hr/visitor/<string:site_code>', type='http', auth='public', methods=['GET'], csrf=False)
    def visitor_shell(self, site_code, **kwargs):
        Site = request.env['eh.hr.kiosk.site'].sudo()
        site = Site.search([('code', '=', site_code), ('active', '=', True)], limit=1)
        return request.render('eh_hr_visitor.visitor_kiosk_shell', {
            'site_code': site_code,
            'site_found': bool(site),
            'site_name': site.name if site else '',
        })

    @http.route('/eh_hr/visitor/bootstrap', type='http', auth='public', methods=['GET'], csrf=False)
    @catch_json_error
    def bootstrap(self, **kwargs):
        """Return purposes, NDA defaults, and host autocomplete data for
        the site bound to the calling device token."""
        token = request.httprequest.headers.get('X-EH-Kiosk-Token')
        throttled = _throttled('visitor.bootstrap', token or _client_ip(), 60)
        if throttled:
            return throttled
        device = _get_device_by_token(token)
        if not device:
            return _json_response({'error': 'unauthorized'}, status=401)

        company = device.company_id
        Purpose = request.env['eh.hr.visitor.purpose'].sudo()
        purposes = Purpose.search([
            '|',
            ('company_id', '=', company.id),
            ('company_id', '=', False),
            ('active', '=', True),
        ])

        # Hosts are NOT dumped here. Returning the whole employee directory to
        # any device-token holder is a bulk-PII leak. The shell instead calls
        # /eh_hr/visitor/host_search with a typed query, which is throttled and
        # capped, so only the few names the visitor actually types are exposed.
        return _json_response({
            'site_code': device.site_id.code,
            'site_name': device.site_id.name,
            'purposes': [
                {
                    'id': p.id,
                    'name': p.name,
                    'nda_required': p.nda_required,
                    'photo_required': p.photo_required,
                }
                for p in purposes
            ],
            'hosts': [],
            'host_search': True,
            'nda_text': company.eh_hr_visitor_nda_text or '',
            'visitor_agreement_text': company.eh_hr_visitor_visitor_agreement_text or '',
            'safety_declaration_text': company.eh_hr_visitor_safety_declaration_text or '',
            'privacy_consent_text': company.eh_hr_visitor_privacy_consent_text or '',
            'photo_consent_text': company.eh_hr_visitor_photo_consent_text or '',
        })

    @http.route('/eh_hr/visitor/host_search', type='http', auth='public', methods=['GET'], csrf=False)
    @catch_json_error
    def host_search(self, **kwargs):
        """Typeahead host lookup. Requires a query of at least two characters
        and returns at most ten matches (id + name only), scoped to the
        device's company and throttled, so the directory cannot be bulk-pulled."""
        token = request.httprequest.headers.get('X-EH-Kiosk-Token')
        throttled = _throttled('visitor.host_search', token or _client_ip(), 60)
        if throttled:
            return throttled
        device = _get_device_by_token(token)
        if not device:
            return _json_response({'error': 'unauthorized'}, status=401)
        query = (kwargs.get('q') or '').strip()
        if len(query) < 2:
            return _json_response({'hosts': []})
        hosts = request.env['hr.employee'].sudo().search([
            ('company_id', '=', device.company_id.id),
            ('active', '=', True),
            ('name', 'ilike', query),
        ], limit=10, order='name')
        return _json_response({
            'hosts': [{'id': h.id, 'name': h.name} for h in hosts],
        })

    @http.route('/eh_hr/visitor/sign_in', type='http', auth='public', methods=['POST'], csrf=False)
    @catch_json_error
    def sign_in(self, **kwargs):
        token = request.httprequest.headers.get('X-EH-Kiosk-Token')
        throttled = _throttled('visitor.sign_in', token or _client_ip(), 30)
        if throttled:
            return throttled
        device = _get_device_by_token(token)
        if not device:
            return _json_response({'error': 'unauthorized'}, status=401)

        try:
            data = json.loads(request.httprequest.data)
        except (ValueError, TypeError):
            return _json_response({'error': 'invalid body'}, status=400)

        name = (data.get('name') or '').strip()
        host_id = data.get('host_id')
        purpose_id = data.get('purpose_id')
        if not name:
            return _json_response({'error': 'name is required'}, status=400)
        if not host_id:
            return _json_response({'error': 'host_id is required'}, status=400)
        if not purpose_id:
            return _json_response({'error': 'purpose_id is required'}, status=400)

        try:
            host_id = int(host_id)
            purpose_id = int(purpose_id)
        except (TypeError, ValueError):
            return _json_response({'error': 'host_id and purpose_id must be integers'}, status=400)

        Employee = request.env['hr.employee'].sudo()
        host = Employee.browse(host_id).exists()
        if not host or host.company_id != device.company_id:
            return _json_response({'error': 'host not found'}, status=404)

        Purpose = request.env['eh.hr.visitor.purpose'].sudo()
        purpose = Purpose.browse(purpose_id).exists()
        if not purpose:
            return _json_response({'error': 'purpose not found'}, status=404)

        err, files_data = _process_visitor_files(data, purpose)
        if err:
            return _json_response(err, status=400)

        Visitor = request.env['eh.hr.visitor'].sudo()
        visitor = Visitor.create({
            'name': name,
            'visitor_company': (data.get('visitor_company') or '').strip() or False,
            'visitor_email': (data.get('visitor_email') or '').strip() or False,
            'visitor_phone': (data.get('visitor_phone') or '').strip() or False,
            'host_employee_id': host.id,
            'purpose_id': purpose.id,
            'site_id': device.site_id.id,
            'device_id': device.id,
            'nda_required': bool(purpose.nda_required),
            'nda_accepted': bool(data.get('nda_accepted')),
            'nda_text': device.company_id.eh_hr_visitor_nda_text if purpose.nda_required else False,
            'digital_signature': files_data['digital_signature'],
            'photo': files_data['photo'],
            'photo_filename': files_data['photo_filename'],
            'company_id': device.company_id.id,
            'drink_id': int(data.get('drink_id')) if data.get('drink_id') else False,
        })
        visitor.action_sign_in()

        request.env['eh.hr.kiosk.event'].sudo().log(
            'attendance_in',
            device_id=device.id,
            ref_model='eh.hr.visitor',
            ref_id=visitor.id,
            ip_address=_client_ip(),
            notes='Visitor sign-in: %s for %s' % (visitor.name, host.name),
            company_id=device.company_id.id,
        )

        return _json_response({
            'ok': True,
            'visitor_id': visitor.id,
            'visit_number': visitor.visit_number,
            'host_name': host.name,
        })

    @http.route('/eh_hr/visitor/sign_out', type='http', auth='public', methods=['POST'], csrf=False)
    @catch_json_error
    def sign_out(self, **kwargs):
        token = request.httprequest.headers.get('X-EH-Kiosk-Token')
        throttled = _throttled('visitor.sign_out', token or _client_ip(), 30)
        if throttled:
            return throttled
        device = _get_device_by_token(token)
        if not device:
            return _json_response({'error': 'unauthorized'}, status=401)

        try:
            data = json.loads(request.httprequest.data)
        except (ValueError, TypeError):
            return _json_response({'error': 'invalid body'}, status=400)

        visit_number = (data.get('visit_number') or '').strip()
        if not visit_number:
            return _json_response({'error': 'visit_number is required'}, status=400)

        Visitor = request.env['eh.hr.visitor'].sudo()
        visitor = Visitor.search([
            ('visit_number', '=', visit_number),
            ('company_id', '=', device.company_id.id),
            ('state', '=', 'signed_in'),
        ], limit=1)
        if not visitor:
            return _json_response({'ok': False, 'reason': 'not_found_or_already_signed_out'}, status=200)

        visitor.action_sign_out()

        request.env['eh.hr.kiosk.event'].sudo().log(
            'attendance_out',
            device_id=device.id,
            ref_model='eh.hr.visitor',
            ref_id=visitor.id,
            ip_address=_client_ip(),
            notes='Visitor sign-out: %s' % visitor.name,
            company_id=device.company_id.id,
        )

        return _json_response({
            'ok': True,
            'visit_number': visitor.visit_number,
            'visitor_name': visitor.name,
            'duration_minutes': visitor.duration_minutes,
        })

    @http.route('/fd/kiosk/<string:kiosk_token>', type='http', auth='public', methods=['GET'], csrf=False)
    def fd_visitor_shell(self, kiosk_token, **kwargs):
        Station = request.env['eh.hr.visitor.station'].sudo()
        station = Station.search([('kiosk_token', '=', kiosk_token), ('active', '=', True)], limit=1)
        if not station:
            return request.not_found()
        return request.render('eh_hr_visitor.frontdesk_kiosk_shell', {
            'station_token': kiosk_token,
            'station_name': station.name,
            'theme': station.theme or 'light',
        })

    @http.route('/fd/kiosk/bootstrap/<string:kiosk_token>', type='http', auth='public', methods=['GET'], csrf=False)
    @catch_json_error
    def fd_bootstrap(self, kiosk_token, **kwargs):
        throttled = _throttled('visitor.fd_bootstrap', kiosk_token or _client_ip(), 60)
        if throttled:
            return throttled
        station = request.env['eh.hr.visitor.station'].sudo().search([('kiosk_token', '=', kiosk_token), ('active', '=', True)], limit=1)
        if not station:
            return _json_response({'error': 'unauthorized'}, status=401)

        company = station.company_id
        Purpose = request.env['eh.hr.visitor.purpose'].sudo()
        purposes = Purpose.search([
            '|',
            ('company_id', '=', company.id),
            ('company_id', '=', False),
            ('active', '=', True),
        ])

        drinks = []
        if station.offer_drinks:
            drinks = [{'id': d.id, 'name': d.name} for d in station.drink_ids if d.active]

        return _json_response({
            'station_token': station.kiosk_token,
            'station_name': station.name,
            'company_name': company.name,
            'host_selection': station.host_selection,
            'authenticate_guest': station.authenticate_guest,
            'field_email': station.field_email,
            'field_phone': station.field_phone,
            'field_organization': station.field_organization,
            'self_checkin': station.self_checkin,
            'offer_drinks': station.offer_drinks,
            'drinks': drinks,
            'purposes': [
                {
                    'id': p.id,
                    'name': p.name,
                    'nda_required': p.nda_required,
                    'photo_required': p.photo_required,
                }
                for p in purposes
            ],
            'nda_text': company.eh_hr_visitor_nda_text or '',
            'visitor_agreement_text': company.eh_hr_visitor_visitor_agreement_text or '',
            'safety_declaration_text': company.eh_hr_visitor_safety_declaration_text or '',
            'privacy_consent_text': company.eh_hr_visitor_privacy_consent_text or '',
            'photo_consent_text': company.eh_hr_visitor_photo_consent_text or '',
            'side_message': station.side_message or '',
        })

    @http.route('/fd/kiosk/host_search/<string:kiosk_token>', type='http', auth='public', methods=['GET'], csrf=False)
    @catch_json_error
    def fd_host_search(self, kiosk_token, **kwargs):
        throttled = _throttled('visitor.fd_host_search', kiosk_token or _client_ip(), 60)
        if throttled:
            return throttled
        station = request.env['eh.hr.visitor.station'].sudo().search([('kiosk_token', '=', kiosk_token), ('active', '=', True)], limit=1)
        if not station:
            return _json_response({'error': 'unauthorized'}, status=401)

        query = (kwargs.get('q') or '').strip()
        if len(query) < 2:
            return _json_response({'hosts': []})

        domain = [('company_id', '=', station.company_id.id), ('active', '=', True), ('name', 'ilike', query)]
        if station.allowed_host_employee_ids:
            domain.append(('id', 'in', station.allowed_host_employee_ids.ids))

        hosts = request.env['hr.employee'].sudo().search(domain, limit=10, order='name')
        return _json_response({
            'hosts': [{'id': h.id, 'name': h.name} for h in hosts],
        })

    @http.route('/fd/kiosk/sign_in/<string:kiosk_token>', type='http', auth='public', methods=['POST'], csrf=False)
    @catch_json_error
    def fd_sign_in(self, kiosk_token, **kwargs):
        throttled = _throttled('visitor.fd_sign_in', kiosk_token or _client_ip(), 30)
        if throttled:
            return throttled
        station = request.env['eh.hr.visitor.station'].sudo().search([('kiosk_token', '=', kiosk_token), ('active', '=', True)], limit=1)
        if not station:
            return _json_response({'error': 'unauthorized'}, status=401)

        try:
            data = json.loads(request.httprequest.data)
        except (ValueError, TypeError):
            return _json_response({'error': 'invalid body'}, status=400)

        name = (data.get('name') or '').strip()
        transaction_id = data.get('transaction_id')
        
        if transaction_id:
            existing = request.env['eh.hr.visitor'].sudo().search([('registration_token', '=', transaction_id)], limit=1)
            if existing:
                return _json_response({
                    'ok': True,
                    'visitor_id': existing.id,
                    'visit_number': existing.visit_number,
                    'host_name': existing.host_employee_id.name,
                })

        if not name:
            return _json_response({'error': 'name is required'}, status=400)

        host_id = data.get('host_id')
        if not station.host_selection:
            if station.default_host_employee_id:
                host_id = station.default_host_employee_id.id
            else:
                return _json_response({'error': 'No default host configured.'}, status=400)

        if not host_id:
            return _json_response({'error': 'host_id is required'}, status=400)
            
        purpose_id = data.get('purpose_id')
        if not purpose_id:
            return _json_response({'error': 'purpose_id is required'}, status=400)

        try:
            host_id = int(host_id)
            purpose_id = int(purpose_id)
        except (TypeError, ValueError):
            return _json_response({'error': 'host_id and purpose_id must be integers'}, status=400)

        Employee = request.env['hr.employee'].sudo()
        host = Employee.browse(host_id).exists()
        if not host or host.company_id != station.company_id:
            return _json_response({'error': 'host not found'}, status=404)

        Purpose = request.env['eh.hr.visitor.purpose'].sudo()
        purpose = Purpose.browse(purpose_id).exists()
        if not purpose:
            return _json_response({'error': 'purpose not found'}, status=404)

        err, files_data = _process_visitor_files(data, purpose)
        if err:
            return _json_response(err, status=400)

        drink_id = False
        if station.offer_drinks and data.get('drink_id'):
            try:
                drink_id = int(data.get('drink_id'))
            except ValueError:
                pass

        Visitor = request.env['eh.hr.visitor'].sudo()
        visitor = Visitor.create({
            'name': name,
            'visitor_company': (data.get('visitor_company') or '').strip() or False,
            'visitor_email': (data.get('visitor_email') or '').strip() or False,
            'visitor_phone': (data.get('visitor_phone') or '').strip() or False,
            'host_employee_id': host.id,
            'purpose_id': purpose.id,
            'station_id': station.id,
            'drink_id': drink_id,
            'nda_required': bool(purpose.nda_required),
            'nda_accepted': bool(data.get('nda_accepted')),
            'nda_text': station.company_id.eh_hr_visitor_nda_text if purpose.nda_required else False,
            'digital_signature': files_data['digital_signature'],
            'photo': files_data['photo'],
            'photo_filename': files_data['photo_filename'],
            'company_id': station.company_id.id,
            'registration_token': transaction_id,
        })
        visitor.action_sign_in()

        try:
            request.env['eh.hr.kiosk.event'].sudo().log(
                'attendance_in',
                device_id=False,
                ref_model='eh.hr.visitor',
                ref_id=visitor.id,
                ip_address=_client_ip(),
                notes='Visitor sign-in (Frontdesk): %s for %s' % (visitor.name, host.name),
                company_id=station.company_id.id,
            )
        except Exception:
            _logger.exception("Error logging frontdesk kiosk event")

        return _json_response({
            'ok': True,
            'visitor_id': visitor.id,
            'visit_number': visitor.visit_number,
            'host_name': host.name,
        })

    @http.route('/visitor/register/<string:token>', type='http', auth='public', website=True, csrf=True)
    def visitor_preregister(self, token, **kwargs):
        Visitor = request.env['eh.hr.visitor'].sudo()
        visitor = Visitor.search([('registration_token', '=', token), ('state', 'in', ['invitation_sent', 'confirmed'])], limit=1)
        if not visitor:
            return request.not_found()

        if visitor.state == 'confirmed':
            return request.render('eh_hr_visitor.visitor_preregistration_form', {
                'visitor': visitor,
                'company': visitor.company_id,
                'error': False,
                'success': True,
                'message': 'Your registration has already been completed.',
            })

        if request.httprequest.method == 'GET':
            return request.render('eh_hr_visitor.visitor_preregistration_form', {
                'visitor': visitor,
                'company': visitor.company_id,
                'error': False,
                'success': False,
            })

        if request.httprequest.method == 'POST':
            try:
                # Update visitor record with form data
                update_vals = {
                    'name': kwargs.get('name'),
                    'visitor_company': kwargs.get('visitor_company'),
                    'visitor_email': kwargs.get('visitor_email'),
                    'visitor_phone': kwargs.get('visitor_phone'),
                    'designation': kwargs.get('designation'),
                    'visitor_address': kwargs.get('visitor_address'),
                    'visitor_city': kwargs.get('visitor_city'),
                    'visitor_country': kwargs.get('visitor_country'),
                    'identity_type': kwargs.get('identity_type'),
                    'identity_number': kwargs.get('identity_number'),
                    'emergency_contact_name': kwargs.get('emergency_contact_name'),
                    'emergency_contact_number': kwargs.get('emergency_contact_number'),

                    'accept_privacy_policy': bool(kwargs.get('accept_privacy_policy')),
                    'registration_type': 'pre-registered',
                }
                
                if visitor.nda_required and kwargs.get('nda_accepted'):
                    update_vals['nda_accepted'] = True
                    update_vals['nda_text'] = visitor.company_id.eh_hr_visitor_nda_text
                    
                if visitor.visitor_agreement_required and kwargs.get('visitor_agreement_accepted'):
                    update_vals['visitor_agreement_accepted'] = True
                    update_vals['visitor_agreement_text'] = visitor.company_id.eh_hr_visitor_visitor_agreement_text
                    
                if visitor.safety_declaration_required and kwargs.get('safety_declaration_accepted'):
                    update_vals['safety_declaration_accepted'] = True
                    update_vals['safety_declaration_text'] = visitor.company_id.eh_hr_visitor_safety_declaration_text
                    
                if visitor.privacy_consent_required and kwargs.get('accept_privacy_policy'):
                    update_vals['privacy_consent_text'] = visitor.company_id.eh_hr_visitor_privacy_consent_text
                    
                if 'identity_proof' in request.params:
                    upload = request.params['identity_proof']
                    if upload:
                        upload.seek(0, 2)
                        if upload.tell() > 5 * 1024 * 1024:
                            raise Exception("Identity proof file size exceeds 5MB limit.")
                        upload.seek(0)
                        if upload.mimetype not in ['image/jpeg', 'image/png', 'application/pdf']:
                            raise Exception("Invalid file type for identity proof.")
                        update_vals['identity_proof'] = base64.b64encode(upload.read())
                        
                if 'photo' in request.params:
                    upload_photo = request.params['photo']
                    if upload_photo:
                        upload_photo.seek(0, 2)
                        if upload_photo.tell() > 5 * 1024 * 1024:
                            raise Exception("Photo file size exceeds 5MB limit.")
                        upload_photo.seek(0)
                        if upload_photo.mimetype not in ['image/jpeg', 'image/png']:
                            raise Exception("Invalid file type for photo.")
                        update_vals['photo'] = base64.b64encode(upload_photo.read())
                        update_vals['photo_filename'] = PREREG_PHOTO_FILENAME
                        
                digital_signature_b64 = kwargs.get('digital_signature_b64')
                if digital_signature_b64:
                    try:
                        if digital_signature_b64.startswith('data:'):
                            digital_signature_b64 = digital_signature_b64.split(',', 1)[1]
                        update_vals['digital_signature'] = base64.b64encode(base64.b64decode(digital_signature_b64))
                    except Exception:
                        pass

                update_vals['state'] = 'confirmed'
                visitor.write(update_vals)
                
                if visitor.agreement_status == 'completed' and visitor.digital_signature:
                    try:
                        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf('eh_hr_visitor.report_visitor_agreement', visitor.ids)
                        visitor.write({
                            'signed_pdf': base64.b64encode(pdf),
                            'signed_pdf_filename': AGREEMENT_PDF_FILENAME % visitor.visit_number
                        })
                    except Exception:
                        _logger.exception("Error generating PDF for visitor %s", visitor.visit_number)
                
                # Generate QR Code
                visitor._generate_qr_code()
                
                # Send confirmation email to visitor
                template_conf = request.env.ref('eh_hr_visitor.email_template_visitor_confirmation', raise_if_not_found=False)
                if template_conf:
                    template_conf.send_mail(visitor.id, force_send=True, email_values={'email_to': visitor.visitor_email})
                    
                # Send notification email to host
                template_host = request.env.ref('eh_hr_visitor.email_template_visitor_preregistration_host_notification', raise_if_not_found=False)
                if template_host:
                    template_host.send_mail(visitor.id, force_send=True, email_values={'email_to': visitor.host_employee_id.work_email})

                return request.render('eh_hr_visitor.visitor_preregistration_form', {
                    'visitor': visitor,
                    'company': visitor.company_id,
                    'error': False,
                    'success': True,
                })
            except Exception as e:
                _logger.exception("Error during visitor pre-registration")
                return request.render('eh_hr_visitor.visitor_preregistration_form', {
                    'visitor': visitor,
                    'company': visitor.company_id,
                    'error': "An error occurred while saving your registration. Please verify your details or contact your host.",
                    'success': False,
                })

    @http.route('/eh_hr/visitor/scanner_embed', type='http', auth='user')
    def scanner_embed(self, **kwargs):
        return request.render('eh_hr_visitor.visitor_qr_scanner_embed')
