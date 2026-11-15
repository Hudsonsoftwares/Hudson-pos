import secrets
import time

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq, email_normalize, str2bool
from odoo.tools.misc import hmac as hmac_tool

from odoo.addons.dms_enterprise_features.controllers.portal import DMSPortal


class _SignatureRefused(Exception):
    """Rolls back the copy made for a share link visitor when signing fails."""


def _identity_key(req_id):
    return f'hudson_sign_identity_{req_id}'


# Extra authentication "By Email": one-time code, kept (hashed) in the signer's session
OTP_VALIDITY = 10 * 60
OTP_RESEND_DELAY = 30
OTP_MAX_ATTEMPTS = 5


def _otp_key(req_id):
    return f'hudson_sign_otp_{req_id}'


def _otp_hash(req_id, email, code):
    return hmac_tool(request.env(su=True), 'hudson_sign_otp', f'{req_id}:{email}:{code}')


def _mask_email(email):
    local, _sep, domain = email.partition('@')
    return f"{local[:1]}{'*' * max(len(local) - 1, 3)}@{domain}"


class HudsonSignPortal(DMSPortal):

    @staticmethod
    def _get_token_request(req_id, access_token):
        signature_req = request.env['dms.file.signature.request'].sudo().browse(req_id).exists()
        if not signature_req or not access_token or not consteq(signature_req.access_token or '', access_token):
            return None
        return signature_req

    @http.route()
    def portal_dms_signature_token(self, req_id, access_token, **kw):
        signature_req = self._get_token_request(req_id, access_token)
        sign_request = signature_req and signature_req.hudson_request_id
        if sign_request and signature_req.state != 'signed' and sign_request.state == 'canceled':
            return request.render('hudson_sign.sign_request_unavailable', {
                'signature_req': signature_req,
                'is_shared': sign_request.is_shared,
            })
        if signature_req and signature_req._get_blocking_requests():
            return self._render_waiting_page(signature_req, access_token)
        return super().portal_dms_signature_token(req_id, access_token, **kw)

    @http.route()
    def portal_my_dms_signature_detail(self, req_id, access_token=None, **kw):
        signature_req = request.env['dms.file.signature.request'].sudo().browse(req_id).exists()
        allowed = signature_req and (
            (access_token and consteq(signature_req.access_token or '', access_token))
            or signature_req.recipient_id == request.env.user)
        if allowed and signature_req._get_blocking_requests():
            return self._render_waiting_page(signature_req, access_token or signature_req.access_token)
        return super().portal_my_dms_signature_detail(req_id, access_token=access_token, **kw)

    @staticmethod
    def _render_waiting_page(signature_req, access_token):
        """Not this signer's turn: the document with the areas of the earlier signers, read-only."""
        blocking = signature_req._get_blocking_requests()
        return request.render("dms_enterprise_features.portal_signature_page", {
            'signature_req': signature_req,
            'access_token': access_token,
            'page_name': 'dms_signature',
            'hs_waiting_for': blocking,
            'hs_display_items': blocking.item_ids,
        })

    @http.route()
    def portal_my_dms_signature_accept(self, req_id, items_data=None, access_token=None, **kw):
        signature_req = self._get_token_request(req_id, access_token)
        sign_request = signature_req and signature_req.hudson_request_id
        own_req = signature_req or request.env['dms.file.signature.request'].sudo().browse(req_id).exists().filtered(
            lambda r: r.recipient_id == request.env.user)
        blocking = own_req and own_req._get_blocking_requests()
        if blocking:
            return {'error': _("%s must sign before you.", ", ".join(blocking.recipient_id.mapped('name')))}
        if not (sign_request and sign_request.is_shared):
            if own_req and not self._otp_verified(own_req):
                return {'error': _("Please verify your email address with the code we sent you before signing.")}
            result = super().portal_my_dms_signature_accept(req_id, items_data=items_data, access_token=access_token, **kw)
            if own_req:
                self._otp_log(own_req, own_req, result)
            return self._finalize_result(signature_req, result)

        # Share link: the visitor signs a copy of their own, the link stays usable for others
        # Given in the "Final Validation" step of the page, kept in the session
        identity = request.session.get(_identity_key(req_id)) or {}
        name = (kw.pop('signer_name', None) or identity.get('name') or '').strip()
        email = email_normalize(kw.pop('signer_email', None) or identity.get('email') or '')
        if not name or not email:
            return {'error': _("Please enter your name and a valid email address.")}
        if not self._otp_verified(signature_req):
            return {'error': _("Please verify your email address with the code we sent you before signing.")}
        try:
            # A refused signature (e.g. a missing field) must not leave its copy behind
            with request.env.cr.savepoint():
                Partner = request.env['res.partner'].sudo()
                partner = Partner.search([('email', '=ilike', email)], limit=1) or Partner.create({'name': name, 'email': email})
                new_req, item_map = sign_request._create_from_share(partner)
                items_data = {
                    str(item_map[int(item_id)]): data
                    for item_id, data in (items_data or {}).items()
                    if int(item_id) in item_map
                }
                result = super().portal_my_dms_signature_accept(
                    new_req.id, items_data=items_data, access_token=new_req.access_token, **kw)
                if isinstance(result, dict) and result.get('error'):
                    raise _SignatureRefused(result)
        except _SignatureRefused as e:
            return e.args[0]
        except UserError as e:
            return {'error': str(e)}
        self._otp_log(signature_req, new_req, result)
        request.session.pop(_identity_key(req_id), None)
        return self._finalize_result(new_req, result)

    # ------------------------------------------------------------------
    # Extra authentication "By Email"
    # ------------------------------------------------------------------

    @staticmethod
    def _otp_email(signature_req):
        """Address the one-time code is sent to; None when no code is needed,
        False when it is not known yet (share link before "Final Validation")."""
        if not signature_req.hudson_email_otp or signature_req.state == 'signed':
            return None
        if signature_req.hudson_request_id.is_shared:
            return (request.session.get(_identity_key(signature_req.id)) or {}).get('email') or False
        if request.session.uid and signature_req.recipient_id.id == request.session.uid:
            return None  # logged in as the signer
        recipient = signature_req.recipient_id
        return email_normalize(recipient.email or recipient.partner_id.email or '') or False

    def _otp_verified(self, signature_req):
        email = self._otp_email(signature_req)
        if email is None:
            return True
        otp = request.session.get(_otp_key(signature_req.id)) or {}
        return bool(email and otp.get('verified') and otp.get('email') == email)

    def _otp_log(self, verified_req, signed_req, result):
        """Keep track of the verification on the signed document."""
        otp = request.session.get(_otp_key(verified_req.id)) if verified_req else None
        if not (otp and otp.get('verified')) or not isinstance(result, dict) or result.get('error'):
            return
        request.session.pop(_otp_key(verified_req.id), None)
        group = signed_req.sudo().hudson_request_id
        if group:
            group.message_post(body=_(
                "%(name)s verified their email address %(email)s with a one-time code before signing (IP: %(ip)s).",
                name=signed_req.sudo().recipient_id.name, email=otp['email'],
                ip=request.httprequest.remote_addr or '-'))

    @http.route(['/hudson_sign/otp/send/<int:req_id>'], type='jsonrpc', auth='public', website=True)
    def hudson_sign_otp_send(self, req_id, access_token=None, **kw):
        signature_req = self._get_token_request(req_id, access_token)
        if not signature_req or signature_req.state == 'signed':
            return {'error': _("Invalid Request.")}
        email = self._otp_email(signature_req)
        if email is None or self._otp_verified(signature_req):
            return {'success': True, 'verified': True}
        if not email:
            if signature_req.hudson_request_id.is_shared:
                return {'error': _("Please enter your name and email first.")}
            return {'error': _("No email address is known for this signer. Please contact the sender.")}
        now = time.time()
        otp = request.session.get(_otp_key(req_id)) or {}
        if otp.get('email') == email and now - otp.get('sent_at', 0) < OTP_RESEND_DELAY:
            return {'error': _("A code was just sent to %s. Please wait a few seconds before asking for a new one.",
                               _mask_email(email))}
        code = f"{secrets.randbelow(10 ** 6):06d}"
        signature_req._hudson_send_otp_email(email, code, OTP_VALIDITY // 60)
        request.session[_otp_key(req_id)] = {
            'email': email,
            'hash': _otp_hash(req_id, email, code),
            'expires': now + OTP_VALIDITY,
            'sent_at': now,
            'attempts': 0,
            'verified': False,
        }
        return {'success': True, 'email': _mask_email(email)}

    @http.route(['/hudson_sign/otp/verify/<int:req_id>'], type='jsonrpc', auth='public', website=True)
    def hudson_sign_otp_verify(self, req_id, access_token=None, code=None, **kw):
        signature_req = self._get_token_request(req_id, access_token)
        if not signature_req or signature_req.state == 'signed':
            return {'error': _("Invalid Request.")}
        email = self._otp_email(signature_req)
        if email is None:
            return {'success': True}
        otp = dict(request.session.get(_otp_key(req_id)) or {})
        if not email or otp.get('email') != email:
            return {'error': _("Please ask for a new code.")}
        if time.time() > otp.get('expires', 0):
            return {'error': _("This code has expired. Please ask for a new one.")}
        if otp.get('attempts', 0) >= OTP_MAX_ATTEMPTS:
            return {'error': _("Too many wrong codes. Please ask for a new one.")}
        code = ''.join((code or '').split())
        if not consteq(_otp_hash(req_id, email, code), otp.get('hash', '')):
            otp['attempts'] = otp.get('attempts', 0) + 1
            request.session[_otp_key(req_id)] = otp
            left = OTP_MAX_ATTEMPTS - otp['attempts']
            if not left:
                return {'error': _("Too many wrong codes. Please ask for a new one.")}
            return {'error': _("Wrong code. %s attempt(s) left.", left)}
        otp['verified'] = True
        request.session[_otp_key(req_id)] = otp
        return {'success': True}

    @staticmethod
    def _finalize_result(signature_req, result):
        """Information for the "It's signed!" dialog, and the "Redirect Link" of the template."""
        if not (signature_req and isinstance(result, dict)) or result.get('error') or result.get('next_signer_url'):
            return result
        signature_req = signature_req.sudo()
        if signature_req.state == 'signed':
            result['hs_download_url'] = f"/dms/signature/{signature_req.id}/{signature_req.access_token}/pdf"
        group = signature_req.hudson_request_id
        others = group.request_ids if group else signature_req
        result['hs_all_signed'] = all(req.state == 'signed' for req in others)
        template = signature_req.template_id
        if template and template.redirect_url:
            url = template.redirect_url.strip()
            if '://' not in url and not url.startswith('/'):
                url = 'https://' + url
            result['redirect_url'] = url
        return result

    @http.route(['/hudson_sign/identify/<int:req_id>'], type='jsonrpc', auth='public', website=True)
    def hudson_sign_identify(self, req_id, access_token=None, signer_name=None, signer_email=None, **kw):
        """Share link: remember who is signing, before "Complete & Sign" posts the fields."""
        signature_req = self._get_token_request(req_id, access_token)
        if not signature_req or not signature_req.hudson_request_id.is_shared:
            return {'error': _("Invalid Request.")}
        name = (signer_name or '').strip()
        email = email_normalize(signer_email or '')
        if not name or not email:
            return {'error': _("Please enter your name and a valid email address.")}
        request.session[_identity_key(req_id)] = {'name': name, 'email': email}
        if (request.session.get(_otp_key(req_id)) or {}).get('email') != email:
            # Another address: its code has to be verified again
            request.session.pop(_otp_key(req_id), None)
        return {'success': True}

    @http.route(['/hudson_sign/decline/<int:req_id>'], type='jsonrpc', auth='public', website=True)
    def hudson_sign_decline(self, req_id, access_token=None, reason=None, signer_name=None, signer_email=None, **kw):
        signature_req = self._get_token_request(req_id, access_token)
        if not signature_req or signature_req.state == 'signed':
            return {'error': _("Invalid Request.")}
        reason = (reason or '').strip()
        if not reason:
            return {'error': _("Please provide a reason for refusal.")}
        sign_request = signature_req.hudson_request_id
        if sign_request.is_shared:
            name = (signer_name or '').strip()
            email = email_normalize(signer_email or '')
            if not name or not email:
                return {'error': _("Please enter your name and a valid email address.")}
        else:
            recipient = signature_req.recipient_id
            name, email = recipient.name, recipient.email
        if sign_request:
            if sign_request.state == 'canceled':
                return {'error': _("This signature request has been canceled.")}
            sign_request._notify_refusal(name, email, reason)
        else:
            signature_req.message_post(body=_("%(name)s declined to sign: %(reason)s", name=name, reason=reason))
        return {'success': True}

    @http.route(['/hudson_sign/terms/<int:company_id>'], type='http', auth='public', website=True)
    def hudson_sign_terms(self, company_id, **kw):
        """Sign settings: "Terms as Web Page", linked from the signature request emails."""
        params = request.env['ir.config_parameter'].sudo()
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or not str2bool(params.get_param('hudson_sign.use_terms') or 'False'):
            return request.not_found()
        return request.render('hudson_sign.sign_terms_page', {'company': company})
