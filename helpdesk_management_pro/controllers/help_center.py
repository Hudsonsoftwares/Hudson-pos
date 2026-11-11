# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class HelpdeskHelpCenter(http.Controller):

    _search_limit = 10

    @http.route(['/helpdesk', '/helpdesk/help_center', '/help', '/helpcenter', '/helpdesk_ticket'], type='http', auth="public", website=True, sitemap=True)
    def helpdesk_help_center(self, search=None, **kwargs):
        teams = request.env['helpdesk.management.team']._get_help_center_teams(request.env.website)
        return self._render_help_center(teams, search=search)

    @http.route(['/helpdesk/<string:team_slug>'], type='http', auth="public", website=True, sitemap=False)
    def helpdesk_team_help_center(self, team_slug, search=None, **kwargs):
        # Teams are not readable by visitors: resolve the slug among the teams exposed on this website
        team_id = request.env['ir.http']._unslug(team_slug)[1]
        teams = request.env['helpdesk.management.team']._get_help_center_teams(request.env.website)
        team = teams.filtered(lambda t: t.id == team_id)
        if not team:
            raise request.not_found()
        return self._render_help_center(team, search=search, team=team)

    def _render_help_center(self, teams, search=None, team=None):
        content = teams._get_help_center_content()
        search_results = self._search_help_center(content, search) if search else {}
        values = dict(
            content,
            page_name='help_center',
            team=team,
            search=search,
            search_results=search_results,
            has_results=any(search_results.values()),
            submit_url='/helpdesk/submit?team_id=%s' % team.id if team else '/helpdesk/submit',
        )
        return request.render("helpdesk_management_pro.helpdesk_landing_page", values)

    def _search_help_center(self, content, search):
        """ Search the forums and courses linked to the help center teams.
        Extended by optional integrations (e.g. Knowledge) to add their own result types. """
        results = {'posts': [], 'slides': []}
        if content['forums']:
            results['posts'] = request.env['forum.post'].sudo().search([
                ('forum_id', 'in', content['forums'].ids),
                ('parent_id', '=', False),
                ('state', '=', 'active'),
                '|', ('name', 'ilike', search), ('content', 'ilike', search),
            ], limit=self._search_limit)
        if content['courses']:
            results['slides'] = request.env['slide.slide'].sudo().search([
                ('channel_id', 'in', content['courses'].ids),
                ('website_published', '=', True),
                ('is_category', '=', False),
                '|', ('name', 'ilike', search), ('description', 'ilike', search),
            ], limit=self._search_limit)
        return results
