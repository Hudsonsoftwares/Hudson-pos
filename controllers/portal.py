# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import http, _
# pyrefly: ignore [missing-import]
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
# pyrefly: ignore [missing-import]
from odoo.http import request

class AppointmentPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'appointment_count':
            return 'appointment.booking', [
                ('partner_id', '=', request.env.user.partner_id.id),
                ('state', 'not in', ['draft', 'pending_payment', 'cancelled'])
            ], 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @http.route(['/my/appointments', '/my/appointments/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_appointments(self, page=1, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        AppointmentBooking = request.env['appointment.booking'].sudo()

        domain = [
            ('partner_id', '=', request.env.user.partner_id.id),
            ('state', 'not in', ['draft', 'pending_payment', 'cancelled'])
        ]
        
        searchbar_sortings = {
            'date': {'label': _('Date'), 'order': 'start_datetime desc'},
            'type': {'label': _('Type'), 'order': 'appointment_type_id'},
            'state': {'label': _('Status'), 'order': 'state'},
        }
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        appointment_count = AppointmentBooking.search_count(domain)
        
        pager = portal_pager(
            url="/my/appointments",
            url_args={'sortby': sortby},
            total=appointment_count,
            page=page,
            step=self._items_per_page
        )
        
        appointments = AppointmentBooking.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'appointments': appointments,
            'page_name': 'appointment',
            'pager': pager,
            'default_url': '/my/appointments',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render("appointment.portal_my_appointments", values)

    @http.route(['/my/appointment/<int:booking_id>'], type='http', auth="user", website=True)
    def portal_my_appointment_detail(self, booking_id, **kw):
        booking = request.env['appointment.booking'].sudo().browse(booking_id)
        if not booking.exists() or booking.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my/appointments')
            
        values = self._prepare_portal_layout_values()
        
        import pytz
        tz = pytz.timezone(booking.appointment_type_id.appointment_tz or 'UTC')
        start_dt = booking.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).replace(tzinfo=None)
        
        values.update({
            'booking': booking,
            'start_dt': start_dt,
            'page_name': 'appointment',
        })
        return request.render("appointment.portal_my_appointment_detail", values)
