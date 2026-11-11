# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import http
# pyrefly: ignore[missing-import]
from odoo.http import request
# pyrefly: ignore[missing-import]
from werkzeug.exceptions import Forbidden


class HelpdeskForum(http.Controller):

    @http.route('/helpdesk/forum/post/<int:post_id>/create_ticket', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def forum_post_create_ticket(self, post_id, **kwargs):
        """ "Create Helpdesk Ticket" button of a forum question: create the ticket and open it in the backend. """
        if not request.env.user.has_group('helpdesk_management_pro.group_helpdesk_user'):
            raise Forbidden()
        post = request.env['forum.post'].browse(post_id).exists()
        if not post:
            raise request.not_found()
        ticket = post._helpdesk_create_ticket()
        return request.redirect(f'/odoo/helpdesk.management.ticket/{ticket.id}', local=True)
