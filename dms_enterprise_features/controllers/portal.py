import base64
import time
from odoo import http, _
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError
from odoo.tools import human_size
from .directory_download import extract_file_raw_bytes

class DMSPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'dms_directory_count':
            return 'dms.directory', [('company_id', 'in', [False] + request.env.companies.ids)], 'read'
        if counter == 'dms_document_count':
            return 'dms.file', [('is_trashed', '=', False), ('active', '=', True), ('company_id', 'in', [False] + request.env.companies.ids)], 'read'
        if counter == 'dms_signature_count':
            return 'dms.file.signature.request', [('recipient_id', '=', request.env.user.id), ('state', '!=', 'signed'), ('company_id', 'in', [False] + request.env.companies.ids)], 'read'
        if hasattr(super(), '_prepare_portal_counter_values'):
            return super()._prepare_portal_counter_values(counter)
        return False, False, False

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters) if hasattr(super(), '_prepare_home_portal_values') else {}
        user = request.env.user
        company_domain = [('company_id', 'in', [False] + request.env.companies.ids)]

        if 'dms_directory_count' in counters:
            own_root_ids = request.env['dms.directory']._get_own_root_directories()
            values['dms_directory_count'] = len(own_root_ids)

        if 'dms_document_count' in counters:
            values['dms_document_count'] = request.env['dms.file'].search_count([
                ('is_trashed', '=', False),
                ('active', '=', True),
            ] + company_domain)

        if 'dms_signature_count' in counters:
            values['dms_signature_count'] = request.env['dms.file.signature.request'].search_count([
                ('recipient_id', '=', user.id),
                ('state', 'in', ['sent', 'draft']),
            ] + company_domain)

        return values

    @http.route(["/my/dms"], type="http", auth="user", website=True)
    def portal_my_dms(self, sortby=None, filterby=None, search=None, search_in="name", **kw):
        values = self._prepare_portal_layout_values()
        user = request.env.user
        is_admin = request.env.is_admin() or user.has_group('base.group_system') or user.has_group('dms.group_dms_manager')
        company_domain = [] if is_admin else [('company_id', 'in', [False] + request.env.companies.ids)]

        searchbar_sortings = {
            'name': {'label': _('Name'), 'order': 'name asc'},
            'date': {'label': _('Last update'), 'order': 'write_date desc'},
        }
        if not sortby or sortby not in searchbar_sortings:
            sortby = 'name'
        sort_order = searchbar_sortings[sortby]['order']

        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search in Name')},
        }

        # Root directories accessible to this user
        if is_admin:
            dir_domain = [
                ('parent_id', '=', False),
                ('is_hidden', '=', False),
                ('is_trashed', '=', False),
            ]
        else:
            own_root_ids = request.env['dms.directory']._get_own_root_directories()
            dir_domain = [
                ('id', 'in', own_root_ids),
                ('is_hidden', '=', False),
                ('is_trashed', '=', False),
            ] + company_domain

        if search and search_in == 'name':
            dir_domain.append(('name', 'ilike', search))

        directories = request.env['dms.directory'].search(dir_domain, order=sort_order)
        request.session['my_dms_folder_history'] = directories.ids

        # Files located at root (directory_id is False)
        file_domain = [
            ('directory_id', '=', False),
            ('is_hidden', '=', False),
            ('is_trashed', '=', False),
            ('active', '=', True),
        ] + company_domain

        if search and search_in == 'name':
            file_domain.append(('name', 'ilike', search))

        root_files = request.env['dms.file'].search(file_domain, order=sort_order)

        # Count total accessible files
        total_files_count = request.env['dms.file'].search_count([
            ('is_trashed', '=', False),
            ('active', '=', True),
        ] + company_domain)

        # Pending signatures mapping
        pending_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', '=', user.id),
            ('state', 'in', ['sent', 'draft']),
        ])
        sig_map = {}
        for s in pending_sigs:
            if s.revision_id and s.revision_id.file_id:
                sig_map[s.revision_id.file_id.id] = s

        # Signed files set
        signed_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', 'in', [user.id, user.partner_id.id]),
            ('state', '=', 'signed'),
        ])
        signed_file_ids = {s.revision_id.file_id.id for s in signed_sigs if s.revision_id and s.revision_id.file_id}

        values.update({
            'dms_directories': directories,
            'dms_files': root_files,
            'dms_directory': False,
            'dms_parent_categories': [],
            'total_files_count': total_files_count,
            'sig_map': sig_map,
            'signed_file_ids': signed_file_ids,
            'page_name': 'dms_directory',
            'default_url': '/my/dms',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'sortby': sortby,
            'filterby': filterby,
            'breadcrumbs_searchbar': True,
            'is_admin': is_admin,
            'access_token': None,
        })
        return request.render("dms_enterprise_features.portal_my_dms", values)

    @http.route(
        ["/my/dms/directory/<int:dms_directory_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_dms_directory(
        self,
        dms_directory_id=False,
        sortby=None,
        filterby=None,
        search=None,
        search_in="name",
        access_token=None,
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        user = request.env.user
        is_admin = request.env.is_admin() or user.has_group('base.group_system') or user.has_group('dms.group_dms_manager')
        company_domain = [] if is_admin else [('company_id', 'in', [False] + request.env.companies.ids)]

        directory = request.env['dms.directory'].browse(dms_directory_id)
        if not directory.exists() or directory.is_trashed or directory.is_hidden:
            return request.redirect("/my/dms")

        # Multi-company verification
        if not is_admin and directory.company_id and directory.company_id not in request.env.companies:
            return request.redirect("/my/dms")

        # Access check
        if access_token:
            if not directory.check_access_token(access_token):
                return request.redirect("/my/dms")
        else:
            if not is_admin and not directory.permission_read:
                return request.redirect("/my/dms")

        searchbar_sortings = {
            'name': {'label': _('Name'), 'order': 'name asc'},
            'date': {'label': _('Last update'), 'order': 'write_date desc'},
        }
        if not sortby or sortby not in searchbar_sortings:
            sortby = 'name'
        sort_order = searchbar_sortings[sortby]['order']

        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search in Name')},
        }

        # Subdirectories
        sub_domain = [
            ('parent_id', '=', directory.id),
            ('is_hidden', '=', False),
            ('is_trashed', '=', False),
        ] + company_domain
        if search and search_in == 'name':
            sub_domain.append(('name', 'ilike', search))

        subdirectories = request.env['dms.directory'].search(sub_domain, order=sort_order)

        # Files in this directory
        file_domain = [
            ('directory_id', '=', directory.id),
            ('is_hidden', '=', False),
            ('is_trashed', '=', False),
            ('active', '=', True),
        ] + company_domain
        if search and search_in == 'name':
            file_domain.append(('name', 'ilike', search))

        files = request.env['dms.file'].search(file_domain, order=sort_order)

        # Pending signatures mapping
        pending_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', '=', user.id),
            ('state', 'in', ['sent', 'draft']),
        ])
        sig_map = {}
        for s in pending_sigs:
            if s.revision_id and s.revision_id.file_id:
                sig_map[s.revision_id.file_id.id] = s

        # Signed files set
        signed_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', 'in', [user.id, user.partner_id.id]),
            ('state', '=', 'signed'),
        ])
        signed_file_ids = {s.revision_id.file_id.id for s in signed_sigs if s.revision_id and s.revision_id.file_id}

        parent_categories = directory.sudo()._get_parent_categories(access_token)

        values.update({
            'dms_directory': directory,
            'dms_directories': subdirectories,
            'dms_files': files,
            'dms_parent_categories': parent_categories,
            'sig_map': sig_map,
            'signed_file_ids': signed_file_ids,
            'page_name': 'dms_directory',
            'default_url': f'/my/dms/directory/{directory.id}',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'sortby': sortby,
            'filterby': filterby,
            'breadcrumbs_searchbar': True,
            'is_admin': is_admin,
            'access_token': access_token,
        })
        return request.render("dms_enterprise_features.portal_my_dms", values)

    @http.route(
        ["/my/dms/file/<int:dms_file_id>/download"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_dms_file_download(self, dms_file_id, access_token=None, **kw):
        file_rec = request.env['dms.file'].browse(dms_file_id)
        if not file_rec.exists() or file_rec.is_trashed or not file_rec.active:
            return request.not_found()

        user = request.env.user
        is_admin = request.env.is_admin() or user.has_group('base.group_system') or user.has_group('dms.group_dms_manager')

        # Multi-company verification
        if not is_admin and file_rec.company_id and not user._is_public():
            if file_rec.company_id not in request.env.companies:
                return request.not_found()

        # Permission verification
        if access_token:
            if not file_rec.check_access_token(access_token):
                return request.not_found()
        else:
            if user._is_public():
                return request.redirect(f"/web/login?redirect=/my/dms/file/{dms_file_id}/download")
            if not is_admin and not file_rec.permission_read and not file_rec.permission_download:
                return request.not_found()

        content_bytes = extract_file_raw_bytes(file_rec)
        filename = file_rec.name or f"document_{file_rec.id}"
        mimetype = file_rec.mimetype or "application/octet-stream"
        headers = [
            ("Content-Type", mimetype),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(content_bytes, headers)

    @http.route(
        ["/my/dms/file/<int:dms_file_id>/view"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_dms_file_view(self, dms_file_id, access_token=None, **kw):
        file_rec = request.env['dms.file'].browse(dms_file_id)
        if not file_rec.exists() or file_rec.is_trashed or not file_rec.active:
            return request.not_found()

        user = request.env.user
        is_admin = not user._is_public() and (request.env.is_admin() or user.has_group('base.group_system') or user.has_group('dms.group_dms_manager'))

        # Multi-company verification
        if not is_admin and file_rec.company_id and not user._is_public():
            if file_rec.company_id not in request.env.companies:
                return request.not_found()

        # Permission verification
        if access_token:
            if not file_rec.check_access_token(access_token):
                return request.not_found()
        else:
            if user._is_public():
                return request.redirect(f"/web/login?redirect=/my/dms/file/{dms_file_id}/view")
            if not is_admin and not file_rec.permission_read and not file_rec.permission_view:
                return request.not_found()

        # If user has a pending signature request on this file, redirect directly to signature request!
        if not user._is_public():
            pending_sig = request.env['dms.file.signature.request'].sudo().search([
                ('revision_id.file_id', '=', file_rec.id),
                ('recipient_id', '=', user.id),
                ('state', 'in', ['sent', 'draft']),
            ], limit=1)
            if pending_sig:
                return request.redirect(pending_sig.get_portal_url())

        # Directly stream document content inline in the browser
        content_bytes = extract_file_raw_bytes(file_rec)
        filename = (file_rec.current_revision_id.file_name if file_rec.current_revision_id else False) or file_rec.name or f"document_{file_rec.id}"
        mimetype = (file_rec.mimetype or '').lower()
        fname_lower = filename.lower()

        if fname_lower.endswith('.pdf') or mimetype == 'application/pdf':
            mimetype = 'application/pdf'
        elif fname_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')) or mimetype.startswith('image/'):
            if fname_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')):
                ext = fname_lower.split('.')[-1]
                mimetype = f'image/{ext if ext != "jpg" else "jpeg"}'
        elif not mimetype or mimetype in ('application/octet-stream', 'binary/octet-stream'):
            from odoo.tools.mimetypes import guess_mimetype
            mimetype = guess_mimetype(content_bytes) or 'application/octet-stream'

        headers = [
            ('Content-Type', mimetype),
            ('Content-Disposition', f'inline; filename="{filename}"'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'public, max-age=3600'),
        ]
        return request.make_response(content_bytes, headers)

    @http.route(['/my/dms/documents', '/my/dms/documents/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_dms_documents(self, page=1, filterby=None, search=None, search_in="name", **kw):
        values = self._prepare_portal_layout_values()
        user = request.env.user
        is_admin = request.env.is_admin() or user.has_group('base.group_system') or user.has_group('dms.group_dms_manager')
        company_domain = [] if is_admin else [('company_id', 'in', [False] + request.env.companies.ids)]

        domain = [
            ('is_trashed', '=', False),
            ('active', '=', True),
        ] + company_domain

        if search and search_in == 'name':
            domain.append(('name', 'ilike', search))

        if filterby == 'pending_sig':
            sig_files = request.env['dms.file.signature.request'].sudo().search([
                ('recipient_id', '=', user.id),
                ('state', 'in', ['sent', 'draft']),
            ]).mapped('revision_id.file_id').ids
            domain.append(('id', 'in', sig_files or [0]))
        elif filterby == 'owned':
            domain.append(('document_owner_id', '=', user.id))
        elif filterby == 'shared':
            domain.append(('document_owner_id', '!=', user.id))

        files = request.env['dms.file'].search(domain, order='write_date desc')

        pending_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', '=', user.id),
            ('state', 'in', ['sent', 'draft']),
        ])
        sig_map = {}
        for s in pending_sigs:
            if s.revision_id and s.revision_id.file_id:
                sig_map[s.revision_id.file_id.id] = s

        # Signed files set
        signed_sigs = request.env['dms.file.signature.request'].sudo().search([
            ('recipient_id', 'in', [user.id, user.partner_id.id]),
            ('state', '=', 'signed'),
        ])
        signed_file_ids = {s.revision_id.file_id.id for s in signed_sigs if s.revision_id and s.revision_id.file_id}

        values.update({
            'files': files,
            'sig_map': sig_map,
            'signed_file_ids': signed_file_ids,
            'page_name': 'dms_documents',
            'default_url': '/my/dms/documents',
            'filterby': filterby,
            'search': search,
            'search_in': search_in,
            'breadcrumbs_searchbar': True,
            'is_admin': is_admin,
        })
        return request.render("dms_enterprise_features.portal_my_dms_documents", values)

    @http.route(['/my/dms/signatures', '/my/dms/signatures/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_dms_signatures(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        company_domain = [('company_id', 'in', [False] + request.env.companies.ids)]
        domain = [
            ('recipient_id', '=', request.env.user.id),
            ('state', 'in', ['sent', 'draft']),
        ] + company_domain
        
        signatures = request.env['dms.file.signature.request'].search(domain)
        request.session['my_signatures_history'] = signatures.ids[:100]

        values.update({
            'signatures': signatures,
            'page_name': 'dms_signature',
            'default_url': '/my/dms/signatures',
        })
        return request.render("dms_enterprise_features.portal_my_dms_signatures", values)

    @http.route(['/dms/signature/<int:req_id>/<string:access_token>'], type='http', auth="public", website=True)
    def portal_dms_signature_token(self, req_id, access_token, **kw):
        """Public route for signers clicking the email link (no login required)."""
        signature_req = request.env['dms.file.signature.request'].sudo().browse(req_id)
        if not signature_req.exists() or signature_req.access_token != access_token:
            # If user is logged in, find their latest pending signature or redirect to signatures list
            if not request.env.user._is_public():
                latest_sig = request.env['dms.file.signature.request'].sudo().search([
                    ('recipient_id', '=', request.env.user.id),
                    ('state', 'in', ['sent', 'draft'])
                ], order='id desc', limit=1)
                if latest_sig:
                    return request.redirect(f'/dms/signature/{latest_sig.id}/{latest_sig.access_token}')
                return request.redirect('/my/dms/signatures')
            return request.not_found()
        values = {
            'signature_req': signature_req,
            'access_token': access_token,
            'page_name': 'dms_signature',
        }
        return request.render("dms_enterprise_features.portal_signature_page", values)

    @http.route(['/my/dms/signature/<int:req_id>'], type='http', auth="public", website=True)
    def portal_my_dms_signature_detail(self, req_id, access_token=None, **kw):
        try:
            signature_req = self._document_check_access('dms.file.signature.request', req_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not access_token and signature_req.recipient_id != request.env.user:
            return request.redirect('/my')

        values = {
            'signature_req': signature_req,
            'access_token': access_token or signature_req.access_token or '',
            'page_name': 'dms_signature',
        }
        return request.render("dms_enterprise_features.portal_signature_page", values)


    @http.route(['/dms/signature/<int:req_id>/pdf', '/dms/signature/<int:req_id>/<string:access_token>/pdf'], type='http', auth="public", website=True)
    def portal_dms_signature_pdf(self, req_id, access_token=None, **kw):
        """Serve the PDF content directly for public or authenticated signers."""
        token = access_token or kw.get('access_token')
        signature_req = request.env['dms.file.signature.request'].sudo().browse(req_id)
        if not signature_req.exists():
            return request.not_found()

        # Authorization: token match, or logged-in recipient, or internal user
        is_authorized = False
        if token and signature_req.access_token == token:
            is_authorized = True
        elif not request.env.user._is_public():
            if (signature_req.recipient_id == request.env.user or 
                    request.env.user.has_group('dms.group_dms_user') or 
                    request.env.is_admin()):
                is_authorized = True

        if not is_authorized:
            return request.not_found()

        # Get PDF content: if signed, pdf_content is the signed PDF; otherwise clean revision content for signer
        if signature_req.state == 'signed':
            raw_field = signature_req.pdf_content or (signature_req.revision_id and signature_req.revision_id.content)
        else:
            raw_field = (signature_req.revision_id and signature_req.revision_id.content) or signature_req.pdf_content
        if not raw_field:
            return request.not_found()

        # Extract raw binary bytes safely (handling bytes, BinaryValueAttachment, and base64 strings)
        content = None
        if hasattr(raw_field, '__bytes__') or isinstance(raw_field, (bytes, bytearray)):
            raw_bytes = bytes(raw_field)
            if raw_bytes.startswith(b'%PDF'):
                content = raw_bytes
            else:
                try:
                    decoded = base64.b64decode(raw_bytes)
                    content = decoded if decoded.startswith(b'%PDF') else raw_bytes
                except Exception:
                    content = raw_bytes
        elif isinstance(raw_field, str):
            try:
                content = base64.b64decode(raw_field.encode('ascii'))
            except Exception:
                content = raw_field.encode('utf-8')

        if not content:
            return request.not_found()

        filename = (signature_req.revision_id and (signature_req.revision_id.file_name or signature_req.revision_id.file_id.name)) or f"document_{signature_req.id}.pdf"
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'inline; filename="{filename}"'),
            ('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
        ]
        return request.make_response(content, headers)

    @http.route(['/my/dms/signature/<int:req_id>/accept'], type='json', auth="public", website=True)
    def portal_my_dms_signature_accept(self, req_id, items_data=None, access_token=None, **kw):
        try:
            signature_req = self._document_check_access('dms.file.signature.request', req_id, access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid Request.')}

        if not items_data:
            return {'error': _('Missing form data.')}

        try:
            for item_id, data in items_data.items():
                item = request.env['dms.file.signature.item'].sudo().browse(int(item_id))
                if item.request_id.id != signature_req.id:
                    continue
                
                vals = {'state': 'completed'}
                if 'value_text' in data:
                    vals['value_text'] = data['value_text']
                if 'value_bool' in data:
                    vals['value_bool'] = data['value_bool']
                if 'value_image' in data:
                    # expects base64 string without data prefix
                    vals['value_image'] = data['value_image'].split(',')[1] if ',' in data['value_image'] else data['value_image']
                    
                item.write(vals)
                
            signature_req.sudo().action_apply_signature()
        except Exception as e:
            return {'error': str(e)}

        return_url = kw.get('return_url') or request.params.get('return_url')
        if return_url:
            redirect_url = return_url
        elif not request.env.user._is_public():
            file_id = signature_req.revision_id and signature_req.revision_id.file_id and signature_req.revision_id.file_id.id
            if file_id:
                redirect_url = f"/web#id={file_id}&model=dms.file&view_type=form"
            else:
                redirect_url = "/web#action=dms.action_dms_file"
        else:
            redirect_url = signature_req.get_portal_url()

        result = {
            'force_refresh': True,
            'redirect_url': redirect_url,
        }

        # Check for sequential "Sign Now" handoff
        if signature_req.is_sign_now:
            next_req = request.env['dms.file.signature.request'].sudo().search([
                ('revision_id', '=', signature_req.revision_id.id),
                ('state', '=', 'sent'),
                ('is_sign_now', '=', True),
                ('id', '!=', signature_req.id)
            ], order='id asc', limit=1)
            
            if next_req:
                result['next_signer_url'] = next_req.get_portal_url()
                result['next_signer_name'] = next_req.recipient_id.name

        return result

    def _check_file_access(self, file_rec):
        """
        Determines (has_access, can_replace) based on share settings,
        ensuring link permissions, group permissions, and viewer/editor rules
        are strictly respected like in Enterprise.
        """
        if not file_rec or not file_rec.exists() or file_rec.is_trashed or not file_rec.active:
            return False, False

        user = request.env.user
        link_access = file_rec.share_link_access or 'none'

        # 1. When accessed via link, if link is explicitly set to 'viewer':
        # The link is strictly a Viewer link. can_replace is ALWAYS False!
        if link_access == 'viewer':
            return True, False

        # 2. When accessed via link, if link is explicitly set to 'editor':
        if link_access == 'editor':
            return True, not file_rec.is_locked

        # 3. link_access == 'none' (No public link access)
        if user._is_public():
            return False, False

        # Logged-in users: effective DMS permissions (inherited folder
        # permissions + explicit file lines + owner), same as the backend.
        perms = file_rec._dms_effective_permissions(user)
        if perms['edit'] or perms['rename'] or perms['move']:
            return True, not file_rec.is_locked
        if perms['view'] or perms['download']:
            return True, False

        # Document owner or DMS manager
        if file_rec.document_owner_id == user or file_rec.create_uid == user or user.has_group('dms.group_dms_manager'):
            return True, not file_rec.is_locked

        # Check internal users setting
        if file_rec.share_internal_access == 'editor':
            return True, not file_rec.is_locked
        elif file_rec.share_internal_access == 'viewer':
            return True, False

        return False, False

    # ── File Sharing Public Routes ─────────────────────────────────────────

    @http.route(['/dms/share/file/<string:access_token>'], type='http', auth="public", website=True)
    def portal_share_file_view(self, access_token, **kw):
        file_rec = request.env['dms.file'].sudo().search([('access_token', '=', access_token)], limit=1)
        has_access, can_replace = self._check_file_access(file_rec)
        if not has_access:
            return request.render("dms_enterprise_features.portal_share_file_page", {
                'has_access': False,
                'file': None,
                'res_company': request.env.company,
                'db_name': request.env.cr.dbname,
            })

        user = request.env.user
        is_locked = file_rec.is_locked
        locked_by_name = file_rec.locked_by.name if file_rec.locked_by else 'another user'

        size_bytes = file_rec.size or 0
        formatted_size = human_size(size_bytes) if size_bytes else '0 B'
        file_timestamp = int(file_rec.write_date.timestamp()) if file_rec.write_date else int(time.time())

        filename = (file_rec.current_revision_id.file_name if file_rec.current_revision_id else False) or file_rec.name or "document"
        mimetype = (file_rec.mimetype or '').lower()
        fname_lower = filename.lower()
        is_pdf = (mimetype == 'application/pdf' or fname_lower.endswith('.pdf'))
        is_image = (mimetype.startswith('image/') or fname_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')))
        is_video = (mimetype.startswith('video/') or fname_lower.endswith(('.mp4', '.webm', '.ogg', '.mov')))
        is_audio = (mimetype.startswith('audio/') or fname_lower.endswith(('.mp3', '.wav', '.ogg', '.m4a')))
        is_previewable = is_pdf or is_image or is_video or is_audio

        is_public = bool(user._is_public())
        user_name = user.name if not is_public else ''
        csrf_token = request.csrf_token() if request else ''

        company = file_rec.company_id or (request.env.company if request else False)
        company_logo_uri = None
        if company:
            try:
                from odoo.tools.image import image_data_uri
                if company.logo:
                    company_logo_uri = image_data_uri(company.logo)
            except Exception:
                company_logo_uri = None

        if request and request.session and not request.session.db:
            request.session.db = request.env.cr.dbname

        values = {
            'has_access': has_access,
            'can_replace': can_replace,
            'is_locked': is_locked,
            'locked_by': locked_by_name,
            'file': file_rec,
            'access_token': access_token,
            'formatted_file_size': formatted_size,
            'file_timestamp': file_timestamp,
            'res_company': company,
            'company_logo_uri': company_logo_uri,
            'upload_success': kw.get('upload_success') == '1',
            'is_pdf': is_pdf,
            'is_image': is_image,
            'is_video': is_video,
            'is_audio': is_audio,
            'is_previewable': is_previewable,
            'is_public': is_public,
            'user_name': user_name,
            'csrf_token': csrf_token,
            'db_name': request.env.cr.dbname,
        }
        return request.render("dms_enterprise_features.portal_share_file_page", values)

    @http.route(['/dms/share/file/<string:access_token>/download'], type='http', auth="public", website=True)
    def portal_share_file_download(self, access_token, **kw):
        file_rec = request.env['dms.file'].sudo().search([('access_token', '=', access_token)], limit=1)
        has_access, _ = self._check_file_access(file_rec)
        if not has_access:
            return request.not_found()

        content = self._extract_file_raw_content(file_rec)
        filename = (file_rec.current_revision_id.file_name if file_rec.current_revision_id else False) or file_rec.name or "document"
        mimetype = file_rec.mimetype or 'application/octet-stream'

        headers = [
            ('Content-Type', mimetype),
            ('Content-Disposition', content_disposition(filename)),
            ('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
        ]
        return request.make_response(content, headers)

    def _extract_file_raw_content(self, file_rec):
        if not file_rec:
            return b""
        val = False
        if file_rec.current_revision_id and file_rec.current_revision_id.content:
            val = file_rec.current_revision_id.content
        elif file_rec.content:
            val = file_rec.content

        if not val:
            if hasattr(file_rec, 'content_file') and file_rec.content_file:
                val = file_rec.content_file
            elif hasattr(file_rec, 'content_binary') and file_rec.content_binary:
                val = file_rec.content_binary
            elif hasattr(file_rec, 'attachment_id') and file_rec.attachment_id:
                val = file_rec.attachment_id.raw or file_rec.attachment_id.datas

        if not val:
            return b""

        # Odoo 20 BinaryValueAttachment / BinaryValue
        if hasattr(val, 'open'):
            try:
                return bytes(val)
            except Exception:
                pass
        if hasattr(val, 'content'):
            c = val.content
            if isinstance(c, (bytes, bytearray)):
                return bytes(c)
            val = c

        if isinstance(val, (bytes, bytearray)):
            raw = bytes(val)
            if raw.startswith((b'%PDF', b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'PK\x03\x04', b'\x1f\x8b', b'RIFF')):
                return raw
            try:
                decoded = base64.b64decode(raw, validate=True)
                if decoded:
                    return decoded
            except Exception:
                pass
            return raw

        if isinstance(val, str):
            try:
                return base64.b64decode(val.encode('ascii'))
            except Exception:
                return val.encode('utf-8')

        try:
            return bytes(val)
        except Exception:
            return b""

    @http.route(['/dms/share/file/<string:access_token>/preview'], type='http', auth="public", website=True)
    def portal_share_file_preview(self, access_token, **kw):
        file_rec = request.env['dms.file'].sudo().search([('access_token', '=', access_token)], limit=1)
        has_access, _ = self._check_file_access(file_rec)
        if not has_access:
            return request.not_found()

        content = self._extract_file_raw_content(file_rec)
        filename = (file_rec.current_revision_id.file_name if file_rec.current_revision_id else False) or file_rec.name or "document"
        mimetype = (file_rec.mimetype or '').lower()
        fname_lower = filename.lower()

        if fname_lower.endswith('.pdf') or mimetype == 'application/pdf':
            mimetype = 'application/pdf'
        elif fname_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')) or mimetype.startswith('image/'):
            if fname_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')):
                ext = fname_lower.split('.')[-1]
                mimetype = f'image/{ext if ext != "jpg" else "jpeg"}'
        elif not mimetype or mimetype in ('application/octet-stream', 'binary/octet-stream'):
            from odoo.tools.mimetypes import guess_mimetype
            mimetype = guess_mimetype(content) or 'application/octet-stream'

        headers = [
            ('Content-Type', mimetype),
            ('Content-Disposition', f'inline; filename="{filename}"'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
        ]
        return request.make_response(content, headers)

    @http.route(['/dms/share/file/<string:access_token>/replace'], type='http', auth="public", methods=['POST'], website=True, csrf=True)
    def portal_share_file_replace(self, access_token, **post):
        file_rec = request.env['dms.file'].sudo().search([('access_token', '=', access_token)], limit=1)
        has_access, can_replace = self._check_file_access(file_rec)
        if not has_access or not can_replace or file_rec.is_locked:
            return request.not_found()

        replacement_file = post.get('replacement_file')
        if replacement_file:
            data = replacement_file.read()
            b64_content = base64.b64encode(data).decode('utf-8')
            new_filename = replacement_file.filename or file_rec.name
            user_label = request.env.user.name if not request.env.user._is_public() else "Public User"
            file_rec.with_context(
                revision_comment=f"Replaced via shared link ({user_label})"
            ).write({
                'content': b64_content,
                'name': new_filename,
            })

        return request.redirect(f'/dms/share/file/{access_token}?db={request.env.cr.dbname}&upload_success=1')

