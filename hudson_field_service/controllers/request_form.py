# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import _, http
from odoo.http import request


class FieldServiceRequestForm(http.Controller):
    """Settings > Website Form: customers request an intervention online."""

    def _form_enabled(self):
        return request.env['ir.config_parameter'].sudo().get_bool('hudson_field_service.fs_website_form', True)

    @http.route('/field-service/request', type='http', auth='public', methods=['GET'], sitemap=True)
    def request_form(self, **kw):
        if not self._form_enabled():
            raise request.not_found()
        return request.render('hudson_field_service.fs_request_form', {'values': {}, 'error': False})

    @http.route('/field-service/request', type='http', auth='public', methods=['POST'])
    def request_form_submit(self, name='', email='', phone='', address='', title='', description='', **kw):
        if not self._form_enabled():
            raise request.not_found()
        values = {'name': name.strip(), 'email': email.strip(), 'phone': phone.strip(),
                  'address': address.strip(), 'title': title.strip(), 'description': description.strip()}
        if not (values['name'] and values['email'] and values['address'] and values['title']):
            return request.render('hudson_field_service.fs_request_form', {
                'values': values,
                'error': _('Please fill in your name, email, address and the service needed.'),
            })
        env = request.env(su=True)
        partner = env['res.partner'].search([('email', '=ilike', values['email'])], limit=1)
        if not partner:
            partner = env['res.partner'].create({
                'name': values['name'],
                'email': values['email'],
                'phone': values['phone'],
                'street': values['address'],
            })
        order = env['field.service.order'].create({
            'title': values['title'],
            'partner_id': partner.id,
            'partner_phone': values['phone'] or partner.phone,
            'partner_address': values['address'],
            'description': values['description'] and f"<p>{values['description']}</p>",
            # The request is planned by a dispatcher: no technician yet.
            'employee_id': False,
        })
        order.message_post(body=_("Intervention requested online by %s.", values['name']))
        return request.render('hudson_field_service.fs_request_form_thanks', {'order': order})
