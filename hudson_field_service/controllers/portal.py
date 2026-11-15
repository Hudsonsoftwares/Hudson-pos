# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import base64
from odoo import http, fields, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError

class FieldServicePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'field_service_count' in counters:
            field_service_count = request.env['field.service.order'].search_count([])
            values['field_service_count'] = field_service_count
        return values

    @http.route(['/my/field_service', '/my/field_service/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_field_services(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        FieldService = request.env['field.service.order']
        domain = []

        searchbar_sortings = {
            'date': {'label': _('Date'), 'order': 'create_date desc'},
            'name': {'label': _('Reference'), 'order': 'name'},
        }
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # count for pager
        order_count = FieldService.search_count(domain)
        # make pager
        pager = portal_pager(
            url="/my/field_service",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=order_count,
            page=page,
            step=self._items_per_page
        )
        # search the count to display, according to the pager data
        orders = FieldService.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'orders': orders,
            'page_name': 'field_service',
            'pager': pager,
            'default_url': '/my/field_service',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render("hudson_field_service.portal_my_field_services", values)

    @http.route(['/my/field_service/<int:order_id>'], type='http', auth="public", website=True)
    def portal_my_field_service_order(self, order_id=None, access_token=None, **kw):
        try:
            order_sudo = self._document_check_access('field.service.order', order_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._field_service_order_get_page_view_values(order_sudo, access_token, **kw)
        return request.render("hudson_field_service.portal_my_field_service_order", values)

    @http.route(['/my/field_service/<int:order_id>/accept'], type='json', auth="public", website=True)
    def portal_my_field_service_order_accept(self, order_id, access_token=None, name=None, signature=None):
        try:
            order_sudo = self._document_check_access('field.service.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid order.')}

        # Settings > Customer Report
        if not order_sudo._fs_feature('fs_customer_signature'):
            return {'error': _('Online signature is not available.')}
        if not signature:
            return {'error': _('Signature is missing.')}
        # The customer signs from the link they received: never a technician
        # or any other employee on the customer's behalf.
        if request.env.user._is_internal():
            return {'error': _('The report must be signed by the customer, from the link sent to them by email.')}

        order_sudo.with_context(fs_customer_signing=True).write({
            'customer_signature': signature,
            'customer_signed_by': name,
            'customer_signed_date': fields.Datetime.now(),
        })
        
        # Generate the PDF and attach it to the order
        pdf_content, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf('hudson_field_service.action_report_field_service_order', [order_sudo.id])
        
        attachment = request.env['ir.attachment'].sudo().create({
            'name': f"{order_sudo.name}_signed_report.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'field.service.order',
            'res_id': order_sudo.id,
            'mimetype': 'application/pdf',
        })
        order_sudo.message_post(
            body=_("The report was signed by %s.", name or order_sudo.partner_id.name),
            attachment_ids=attachment.ids,
        )

        return {
            'force_refresh': True,
            'redirect_url': order_sudo.get_portal_url(),
        }

    # The portal is the customer's view of the job. Technicians work from the
    # job in the backend (timer, products, photos, completion, report), where
    # the publication, billing and delivery rules apply: the former technician
    # actions of the portal lead there.
    @http.route([
        '/my/field_service/<int:order_id>/timer/<string:action>',
        '/my/field_service/<int:order_id>/add_product',
        '/my/field_service/<int:order_id>/add_photo',
        '/my/field_service/<int:order_id>/complete',
        '/my/field_service/<int:order_id>/send_report',
    ], type='http', auth="user", website=True)
    def portal_my_field_service_technician_action(self, order_id, access_token=None, **kw):
        try:
            order_sudo = self._document_check_access('field.service.order', order_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        slot = order_sudo.planning_slot_ids.filtered(
            lambda s: s.resource_id.user_id == request.env.user)[:1] or order_sudo.planning_slot_ids[:1]
        if slot:
            return request.redirect(f'/odoo/fs.planning.slot/{slot.id}')
        return request.redirect(f'/odoo/field.service.order/{order_sudo.id}')

    def _field_service_order_get_page_view_values(self, order, access_token, **kwargs):
        # Customer view only (also for the "Customer Preview" of the technician)
        is_technician = False

        values = {
            'page_name': 'field_service',
            'order': order,
            'report_type': 'html',
            'is_technician': is_technician,
            'can_sign': not request.env.user._is_internal(),
        }
        # Chatter values (object, token...) of portal.message_thread
        values = self._get_page_view_values(order, access_token, values, 'my_field_service_history', bool(access_token), **kwargs)
        
        if kwargs.get('error'):
            values['error'] = kwargs['error']
        if kwargs.get('warning'):
            values['warning'] = kwargs['warning']
        if kwargs.get('success'):
            values['success'] = kwargs['success']

        return values
