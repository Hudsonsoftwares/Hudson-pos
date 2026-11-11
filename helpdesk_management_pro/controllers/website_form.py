# -*- coding: utf-8 -*-
from odoo.addons.website.controllers.form import WebsiteForm


class HelpdeskManagementWebsiteForm(WebsiteForm):
    """ Website Form Builder "Create a Ticket" action.

    Tickets go through the standard form pipeline (field whitelist, custom fields appended
    to the description, attachments, success page). Customer and team resolution happen in
    ``helpdesk.management.ticket.website_form_input_filter``.
    """

    def insert_record(self, request, model_sudo, values, custom, meta=None):
        if model_sudo.model != 'helpdesk.management.ticket':
            return super().insert_record(request, model_sudo, values, custom, meta=meta)
        ticket_id = super().insert_record(request, model_sudo, values, custom, meta=meta)
        if ticket_id:
            ticket = request.env['helpdesk.management.ticket'].sudo().browse(ticket_id)
            request.session['ticket_number'] = ticket.name
            request.session['ticket_id'] = ticket.id
        return ticket_id
