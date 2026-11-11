# -*- coding: utf-8 -*-
from odoo import fields, http, _
from odoo.http import request, Response
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

def _is_request_bound():
    try:
        return bool(request and request.env)
    except RuntimeError:
        return False

def get_ticket_partner(name, email):
    """ Link the ticket to the logged-in customer, or to the contact matching the email (created if needed). """
    if not request.env.user._is_public():
        return request.env.user.partner_id
    if not email:
        return request.env['res.partner']
    Partner = request.env['res.partner'].sudo()
    partner = Partner.search([('email', '=ilike', email.strip())], limit=1)
    if not partner:
        partner = Partner.create({'name': name or email, 'email': email.strip()})
    return partner


class HelpdeskManagementPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'ticket_count' in counters:
            ticket_count = request.env['helpdesk.management.ticket'].search_count(
                self._prepare_tickets_domain(request.env.user.partner_id))
            values['ticket_count'] = ticket_count
        return values

    def _prepare_tickets_domain(self, partner):
        """ Tickets of the customer and the ones they follow (e.g. tickets of a colleague they were added to). """
        return ['|', ('partner_id', '=', partner.id), ('message_partner_ids', 'in', [partner.id])]

    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_tickets(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        Ticket = request.env['helpdesk.management.ticket']
        
        domain = self._prepare_tickets_domain(partner)
        ticket_count = Ticket.search_count(domain)
        
        pager = portal_pager(
            url="/my/tickets",
            total=ticket_count,
            page=page,
            step=self._items_per_page
        )
        
        tickets = Ticket.search(domain, limit=self._items_per_page, offset=pager['offset'])
        
        values.update({
            'tickets': tickets,
            'page_name': 'ticket',
            'pager': pager,
            'default_url': '/my/tickets',
        })
        return request.render("helpdesk_management_pro.portal_my_tickets", values)

    def _get_request_env(self):
        if getattr(self, '_test_env', None):
            return self._test_env, self._test_env.user
        try:
            return request.env, request.env.user
        except RuntimeError:
            return None, None

    def _can_access_ticket(self, ticket, user, access_token=None):
        if not ticket or not ticket.exists():
            return False
        if access_token and ticket.access_token == access_token:
            return True
        if user and hasattr(user, '_is_public') and not user._is_public():
            if user.partner_id == ticket.partner_id or user.partner_id in ticket.message_partner_ids:
                return True
            # Helpdesk users previewing the customer page ("Preview" action): their own access rights apply
            if user._is_internal() and ticket.with_user(user).has_access('read'):
                return True
        return False

    @http.route(['/my/ticket/<int:ticket_id>'], type='http', auth="public", website=True)
    def portal_my_ticket_detail(self, ticket_id=None, access_token=None, **kw):
        env, user = self._get_request_env()
        ticket = env['helpdesk.management.ticket'].sudo().browse(ticket_id)
        token = access_token or kw.get('access_token')
        if not self._can_access_ticket(ticket, user, token):
            return request.redirect('/my')
        
        values = {
            'ticket': ticket,
            'page_name': 'ticket',
            'token': token,
        }
        # Standard portal values of the chatter (portal.message_thread): object, token, pid / hash, record pager
        values = self._get_page_view_values(ticket, token, values, 'my_tickets_history', False, **kw)
        return request.render("helpdesk_management_pro.portal_ticket_page", values)

    @http.route(['/my/ticket/<int:ticket_id>/close'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_ticket_close(self, ticket_id=None, access_token=None, **kw):
        env, user = self._get_request_env()
        ticket = env['helpdesk.management.ticket'].sudo().browse(ticket_id)
        token = access_token or kw.get('access_token')
        if not self._can_access_ticket(ticket, user, token):
            return request.redirect('/my') if _is_request_bound() else Response("Access Denied", status=403)

        if ticket.team_id.use_closure_by_customer and not ticket.stage_id.is_close:
            closed_stage = ticket.team_id.auto_close_stage_id or env['helpdesk.management.stage'].sudo().search([
                ('is_close', '=', True),
                '|', ('team_ids', '=', False), ('team_ids', 'in', [ticket.team_id.id])
            ], limit=1)
            if not closed_stage:
                closed_stage = env['helpdesk.management.stage'].sudo().search([('is_close', '=', True)], limit=1)

            if closed_stage:
                ticket.write({'stage_id': closed_stage.id})
                ticket.message_post(
                    body=_("Ticket closed by the customer via portal."),
                    subtype_xmlid='mail.mt_comment',
                )
        redirect_url = '/my/ticket/%s' % ticket.id
        if token:
            redirect_url += '?access_token=%s' % token
        return request.redirect(redirect_url) if _is_request_bound() else Response("Redirect", status=302, headers=[('Location', redirect_url)])

    def _get_form_teams(self):
        """ Teams accepting tickets through the website form of the current website. """
        return request.env['helpdesk.management.team']._get_help_center_teams(request.env.website).filtered('use_website_helpdesk_form')

    def _get_ticket_partner(self, name, email):
        return get_ticket_partner(name, email)

    @http.route(['/helpdesk/submit'], type='http', auth="public", website=True)
    def helpdesk_submit(self, team_id=None, **kwargs):
        teams = self._get_form_teams()
        if not teams:
            raise request.not_found()
        selected_team = teams.filtered(lambda t: str(t.id) == str(team_id))[:1] or teams[:1]
        categories = request.env['helpdesk.management.category'].sudo().search([])
        return request.render("helpdesk_management_pro.helpdesk_submit_ticket", {
            'categories': categories,
            'teams': teams,
            'selected_team': selected_team,
        })

    @http.route(['/helpdesk/submit/process'], type='http', auth="public", methods=['POST'], website=True)
    def helpdesk_submit_process(self, **kwargs):
        teams = self._get_form_teams()
        team = teams.filtered(lambda t: str(t.id) == str(kwargs.get('team_id')))[:1] or teams[:1]
        if not team:
            raise request.not_found()
        partner = self._get_ticket_partner(kwargs.get('name'), kwargs.get('email'))
        vals = {
            'team_id': team.id,
            'subject': kwargs.get('subject') or _('Website Ticket'),
            'description': kwargs.get('description'),
            'category_id': int(kwargs['category_id']) if (kwargs.get('category_id') or '').isdigit() else False,
            'partner_name': kwargs.get('name') or partner.name,
            'partner_email': kwargs.get('email') or partner.email,
            'partner_id': partner.id or False,
        }
        ticket = request.env['helpdesk.management.ticket'].sudo().create(vals)
        return request.redirect('/helpdesk/submit/success?ticket=%s' % ticket.name)

    @http.route(['/helpdesk/submit/success'], type='http', auth="public", website=True)
    def helpdesk_submit_success(self, **kwargs):
        return request.render("helpdesk_management_pro.helpdesk_submit_success", {
            'ticket_name': kwargs.get('ticket'),
        })

    @http.route(['/helpdesk/rating/<int:ticket_id>/<string:token>/<int:rating>'], type='http', auth="public", website=True)
    def helpdesk_rating(self, ticket_id, token, rating, **kwargs):
        env, user = self._get_request_env()
        ticket = env['helpdesk.management.ticket'].sudo().browse(ticket_id)
        if not ticket.exists() or ticket.access_token != token:
            return request.not_found() if _is_request_bound() else Response("Not Found", status=404)
            
        # Task 5.2: Gate on team.use_rating
        if ticket.team_id and not ticket.team_id.use_rating:
            return request.not_found() if _is_request_bound() else Response("Not Found", status=404)
            
        if rating not in (1, 3, 5):
            rating = 3
            
        # Prevent duplicate ratings by updating existing rating
        existing_rating = env['helpdesk.management.ticket.rating'].sudo().search([
            ('ticket_id', '=', ticket.id)
        ], limit=1)
        if existing_rating:
            existing_rating.write({
                'rating': str(rating),
                # Dated when given, so the dashboard counts it in the right period
                'date': fields.Datetime.now(),
                'feedback': kwargs.get('feedback') or existing_rating.feedback or 'Rating updated via link.'
            })
        else:
            env['helpdesk.management.ticket.rating'].sudo().create({
                'ticket_id': ticket.id,
                'rating': str(rating),
                'feedback': kwargs.get('feedback') or 'Rating provided via email link.'
            })
        
        if _is_request_bound():
            return request.render("helpdesk_management_pro.helpdesk_rating_success", {
                'ticket': ticket,
                'rating': rating,
            })
        return Response("Rating Recorded", status=200)
