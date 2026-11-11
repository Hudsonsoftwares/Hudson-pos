# -*- coding: utf-8 -*-
import ast
import datetime

import pytz
# pyrefly: ignore[missing-import]
from odoo import _, api, fields, models
# pyrefly: ignore[missing-import]
from odoo.fields import Domain

class HelpdeskManagementTeam(models.Model):
    _name = 'helpdesk.management.team'
    _description = 'Helpdesk Team'
    _order = 'sequence, name, id'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'mail.alias.mixin', 'image.mixin', 'website.published.mixin']

    def _compute_website_url(self):
        for team in self:
            team.website_url = f"/helpdesk/{self.env['ir.http']._slug(team)}" if team.id else '/helpdesk'

    name = fields.Char(string='Team Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Assignment
    user_id = fields.Many2one('res.users', string='Team Leader')
    member_ids = fields.Many2many('res.users', string='Team Members')
    
    assignment_method = fields.Selection([
        ('random', 'Each user is assigned an equal number of tickets'),
        ('balanced', 'Each user has an equal number of open tickets'),
        ('tags', 'Dispatch tickets based on tags')
    ], string='Assignment Method', default='random', required=True)
    
    # Options
    use_alias = fields.Boolean(string='Email Alias')
    use_ticket_receipt = fields.Boolean(string='Send Receipt Email', default=True, help='Send an automated acknowledgment email when a new customer ticket is created.')
    ticket_receipt_template_id = fields.Many2one('mail.template', string='Receipt Email Template', domain=[('model', '=', 'helpdesk.management.ticket')])
    
    # Visibility & Assignment
    visibility_member_type = fields.Selection([
        ('internal', 'Invited internal users (private)'),
        ('company', 'All internal users (company)'),
        ('portal', 'Invited portal users and all internal users (public)')
    ], string='Visibility Member Type', default='portal')
    visibility = fields.Selection([
        ('invited', 'Invited internal users'),
        ('all', 'All internal users'),
        ('public', 'Public and internal users')
    ], string='Visibility', compute='_compute_visibility', inverse='_inverse_visibility', store=False)

    def _compute_visibility(self):
        mapping = {'internal': 'invited', 'company': 'all', 'portal': 'public'}
        for team in self:
            team.visibility = mapping.get(team.visibility_member_type, 'public')

    def _inverse_visibility(self):
        inv_mapping = {'invited': 'internal', 'all': 'company', 'public': 'portal'}
        for team in self:
            if team.visibility:
                team.visibility_member_type = inv_mapping.get(team.visibility, 'portal')
    follower_ids = fields.Many2many('res.users', relation='helpdesk_team_follower_rel', column1='team_id', column2='user_id', string='Team Followers')
    auto_assignment = fields.Boolean('Automatic Assignment')
    
    # Channels
    use_livechat = fields.Boolean('Live Chat')
    
    # Help Center
    use_website_helpdesk_form = fields.Boolean('Website Form')
    website_id = fields.Many2one('website', string='Website')
    @api.model
    def _get_help_center_feature_fields(self):
        """ Boolean fields enabling a help center feature. Extended by optional integrations (e.g. Forum, eLearning, Knowledge). """
        return ['use_website_helpdesk_form']

    @api.model
    def _get_help_center_teams(self, website=None):
        """ Teams exposed on the help center of the given website. """
        domain = Domain.OR(Domain(fname, '=', True) for fname in self._get_help_center_feature_fields())
        if website:
            domain &= Domain('website_id', 'in', [False, website.id])
        return self.sudo().search(domain)

    def _get_help_center_content(self):
        """ Content shared by these teams. Extended by optional integrations (e.g. Forum, eLearning, Knowledge). """
        return {
            'forums': self.env['forum.forum'] if 'forum.forum' in self.env else [],
            'courses': self.env['slide.channel'] if 'slide.channel' in self.env else [],
            'show_forum': False,
            'show_elearning': False,
            'form_teams': self.filtered('use_website_helpdesk_form'),
        }
    
    # Track & Bill Time
    use_helpdesk_timesheet = fields.Boolean('Timesheets')
    use_helpdesk_sale_timesheet = fields.Boolean('Time Billing')
    
    # Performance
    use_sla = fields.Boolean('SLA Policies', default=True)
    use_rating = fields.Boolean('Customer Ratings')
    resource_calendar_id = fields.Many2one('resource.calendar', 'Working Hours', default=lambda self: self.env.company.resource_calendar_id)
    # Self-Service
    
    # After Sales
    use_closure_by_customer = fields.Boolean('Closure by Customers')
    use_auto_close = fields.Boolean('Automatic Closing')
    auto_close_ticket_days = fields.Integer('After', default=7)
    auto_close_stage_id = fields.Many2one('helpdesk.management.stage', string='Move to Stage')
    auto_close_in_stage_ids = fields.Many2many('helpdesk.management.stage', relation='helpdesk_team_auto_close_stage_rel', column1='team_id', column2='stage_id', string='In Stages')
    use_auto_close_reminder = fields.Boolean('Auto-Close Reminder')
    auto_close_reminder_template_id = fields.Many2one(
        'mail.template',
        string='Email Template',
        domain=[('model', '=', 'helpdesk.management.ticket')],
        default=lambda self: self.env.ref('helpdesk_management_pro.mail_template_ticket_autoclose', raise_if_not_found=False)
    )
    auto_close_reminder_days = fields.Integer('Send', default=2)
    
    # After-Sales
    use_credit_notes = fields.Boolean('Refunds')
    use_coupons = fields.Boolean('Coupons')
    use_product_replacements = fields.Boolean('Replacements')
    use_fsm = fields.Boolean('Field Service')
    use_gift_cards = fields.Boolean('Gift Cards')
    use_product_returns = fields.Boolean('Returns')
    use_product_repairs = fields.Boolean('Repairs')
    
    ticket_ids = fields.One2many('helpdesk.management.ticket', 'team_id', string='Tickets')
    
    # Counts for dashboard
    ticket_count = fields.Integer(compute='_compute_ticket_count')
    open_ticket_count = fields.Integer(compute='_compute_ticket_count')
    unassigned_count = fields.Integer(compute='_compute_ticket_count')
    urgent_ticket_count = fields.Integer(compute='_compute_ticket_count')
    failed_ticket_count = fields.Integer(compute='_compute_ticket_count')
    closed_ticket_count = fields.Integer(compute='_compute_ticket_count')
    sla_success_rate = fields.Float(compute='_compute_ticket_metrics')
    average_rating = fields.Float(compute='_compute_ticket_metrics')
    sla_policy_count = fields.Integer(compute='_compute_sla_policy_count', string="SLA Policies Count")
    
    @api.depends()
    def _compute_sla_policy_count(self):
        for team in self:
            team.sla_policy_count = self.env['helpdesk.management.sla'].search_count([('team_id', '=', team.id)])

    @api.depends('ticket_ids', 'ticket_ids.stage_id', 'ticket_ids.stage_id.is_close', 'ticket_ids.user_id', 'ticket_ids.priority',
                 'ticket_ids.sla_status_ids.status', 'ticket_ids.sla_status_ids.deadline', 'ticket_ids.sla_status_ids.is_paused')
    def _compute_ticket_count(self):
        for team in self:
            team.ticket_count = 0
            team.open_ticket_count = 0
            team.unassigned_count = 0
            team.urgent_ticket_count = 0
            team.failed_ticket_count = 0
            team.closed_ticket_count = 0

        if not self.ids:
            return

        Ticket = self.env['helpdesk.management.ticket']
        ticket_data = Ticket._read_group(
            [('team_id', 'in', self.ids)],
            groupby=['team_id', 'stage_id', 'user_id', 'priority'],
            aggregates=['__count']
        )
        # Failed SLAs are evaluated now, the stored sla_status being only refreshed by the SLA cron
        failed_data = dict(Ticket._read_group(
            [('team_id', 'in', self.ids), ('stage_id.is_close', '=', False)] + Ticket._get_sla_failed_domain(),
            groupby=['team_id'],
            aggregates=['__count']
        ))
        for team in self:
            team.failed_ticket_count = failed_data.get(team._origin, 0)

        for team, stage, user, priority, count in ticket_data:
            if not team:
                continue
            
            team_rec = self.filtered(lambda t: t.id == team.id)
            if not team_rec:
                continue
            
            team_rec.ticket_count += count
            
            is_close = stage.is_close if stage else False
            if is_close:
                team_rec.closed_ticket_count += count
            else:
                team_rec.open_ticket_count += count
                if not user:
                    team_rec.unassigned_count += count
                if priority in ('2', '3'):
                    team_rec.urgent_ticket_count += count

    @api.depends('ticket_ids.sla_status_ids.status', 'ticket_ids.sla_status_ids.deadline', 'ticket_ids.stage_id.is_close',
                 'ticket_ids.ticket_rating_ids.rating')
    def _compute_ticket_metrics(self):
        for team in self:
            team.sla_success_rate = 0.0
            team.average_rating = 0.0

        if not self.ids:
            return

        Ticket = self.env['helpdesk.management.ticket']
        # Only closed tickets under SLA count towards the success rate; they succeed when no policy failed
        sla_domain = [('team_id', 'in', self.ids), ('stage_id.is_close', '=', True),
                      ('sla_status_ids', 'any', [('status', '!=', 'cancelled')])]
        total_data = dict(Ticket._read_group(sla_domain, groupby=['team_id'], aggregates=['__count']))
        failed_data = dict(Ticket._read_group(
            sla_domain + Ticket._get_sla_failed_domain(), groupby=['team_id'], aggregates=['__count']))
        team_sla_stats = {}
        for team in self:
            total = total_data.get(team._origin, 0)
            team_sla_stats[team.id] = {'total': total, 'achieved': total - failed_data.get(team._origin, 0)}
                
        rating_data = self.env['helpdesk.management.ticket.rating']._read_group(
            [('team_id', 'in', self.ids)],
            groupby=['team_id', 'rating'],
            aggregates=['__count']
        )
        
        team_ratings = {t.id: {'sum': 0.0, 'count': 0} for t in self}
        for team, rating, count in rating_data:
            if not team or team.id not in team_ratings:
                continue
            rating_val = int(rating or 0)
            team_ratings[team.id]['sum'] += (rating_val * count)
            team_ratings[team.id]['count'] += count

        for team in self:
            t_stats = team_sla_stats[team.id]
            if t_stats['total'] > 0:
                team.sla_success_rate = round((t_stats['achieved'] / t_stats['total']) * 100, 2)
            else:
                team.sla_success_rate = 100.0 if team.closed_ticket_count > 0 else 0.0
                
            r_stats = team_ratings[team.id]
            if r_stats['count'] > 0:
                team.average_rating = round(r_stats['sum'] / r_stats['count'], 1)

    alias_email = fields.Char(string='Team Alias Email', compute='_compute_alias_email')

    @api.depends('alias_name', 'alias_domain_id')
    def _compute_alias_email(self):
        for team in self:
            if team.alias_name:
                domain = team.alias_domain_id.name if team.alias_domain_id else (
                    self.env.company.alias_domain_id.name if hasattr(self.env.company, 'alias_domain_id') and self.env.company.alias_domain_id else False
                )
                if not domain:
                    domain = self.env['ir.config_parameter'].sudo().get_param('mail.catchall.domain')
                team.alias_email = f"{team.alias_name}@{domain}" if domain else False
            else:
                team.alias_email = False

    def action_open_team_settings(self):
        """ Open the settings (form) of this team, e.g. from its dashboard card. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('helpdesk_management_pro.helpdesk_management_pro_view_team_form').id, 'form')],
            'target': 'current',
        }

    def action_view_tickets(self):
        """ Open the tickets of this team, titled with the team name so the breadcrumb shows which team it is. """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'helpdesk_management_pro.helpdesk_management_pro_action_team_tickets')
        action.update({
            'name': self.display_name,
            'display_name': self.display_name,
            'domain': [('team_id', '=', self.id)],
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        })
        return action

    def action_view_open_tickets(self):
        self.ensure_one()
        return {
            'name': _('%s: Open Tickets', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'kanban,list,form',
            'domain': ['&', ('team_id', '=', self.id), '|', ('stage_id', '=', False), ('stage_id.is_close', '=', False)],
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        }

    def action_view_unassigned_tickets(self):
        self.ensure_one()
        return {
            'name': _('%s: Unassigned Tickets', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'kanban,list,form',
            'domain': ['&', '&', ('team_id', '=', self.id), ('user_id', '=', False), '|', ('stage_id', '=', False), ('stage_id.is_close', '=', False)],
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        }

    def action_view_urgent_tickets(self):
        self.ensure_one()
        return {
            'name': _('%s: Urgent Tickets', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'kanban,list,form',
            'domain': ['&', '&', ('team_id', '=', self.id), ('priority', 'in', ['2', '3']), '|', ('stage_id', '=', False), ('stage_id.is_close', '=', False)],
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        }

    def action_view_failed_tickets(self):
        self.ensure_one()
        return {
            'name': _('%s: Failed SLA Tickets', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'kanban,list,form',
            'domain': [('team_id', '=', self.id), ('stage_id.is_close', '=', False)]
                      + self.env['helpdesk.management.ticket']._get_sla_failed_domain(),
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        }

    def action_view_closed_tickets(self):
        self.ensure_one()
        return {
            'name': _('%s: Closed Tickets', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'kanban,list,form',
            'domain': ['&', ('team_id', '=', self.id), ('stage_id.is_close', '=', True)],
            'context': {'default_team_id': self.id, 'search_default_team_id': self.id},
        }

    @api.model
    def _get_dashboard_periods(self):
        """ Start of today and of the last 7 days (today included), in the user's timezone, as UTC datetimes. """
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        local_today = pytz.utc.localize(fields.Datetime.now()).astimezone(tz).replace(
            hour=0, minute=0, second=0, microsecond=0)
        to_utc = lambda dt: tz.normalize(dt).astimezone(pytz.utc).replace(tzinfo=None)
        return to_utc(local_today), to_utc(local_today - datetime.timedelta(days=6))

    @api.model
    def get_dashboard_metrics(self):
        """ Figures of the "My Tickets" / "My Performance" dashboard: the tickets assigned to the current user,
        like the standard dashboard. ``domains`` are the exact domains counted, used to open the matching lists. """
        Ticket = self.env['helpdesk.management.ticket']
        now = fields.Datetime.now()
        allowed_companies = self.env.companies.ids or [self.env.company.id]
        my_domain = ['|', ('company_id', '=', False), ('company_id', 'in', allowed_companies),
                     ('user_id', '=', self.env.uid)]
        open_domain = my_domain + [('stage_id.is_close', '=', False)]
        failed_domain = open_domain + Ticket._get_sla_failed_domain(now)
        today, last_7_days = self._get_dashboard_periods()
        closed_today_domain = my_domain + [('stage_id.is_close', '=', True), ('close_date', '>=', today)]
        closed_7d_domain = my_domain + [('stage_id.is_close', '=', True), ('close_date', '>=', last_7_days)]

        # --- My Tickets: open tickets per priority, failed SLAs evaluated now
        open_counts = dict(Ticket._read_group(open_domain, groupby=['priority'], aggregates=['__count']))
        failed_counts = dict(Ticket._read_group(failed_domain, groupby=['priority'], aggregates=['__count']))

        # Average age of the open tickets (all of them, whatever their creation date)
        open_tickets = Ticket.search_fetch(open_domain, ['create_date', 'priority'])

        def _avg_open_seconds(tickets):
            ages = [(now - t.create_date).total_seconds() for t in tickets if t.create_date]
            return sum(ages) / len(ages) if ages else 0

        def _fmt_duration(sec):
            if not sec or sec <= 0:
                return "0h"
            total_min = int(sec // 60)
            h = total_min // 60
            m = total_min % 60
            if h > 0 and m > 0:
                return f"{h}h {m}m"
            elif h > 0:
                return f"{h}h"
            elif m > 0:
                return f"{m}m"
            return "0h"

        # --- My Performance: closed tickets, SLA success (closed tickets under SLA without failed policy), ratings
        def _sla_success(closed_domain):
            sla_domain = closed_domain + [('sla_status_ids', 'any', [('status', '!=', 'cancelled')])]
            total = Ticket.search_count(sla_domain)
            if not total:
                return None
            failed = Ticket.search_count(sla_domain + Ticket._get_sla_failed_domain(now))
            return (total - failed) / total * 100

        def _avg_rating(since):
            groups = self.env['helpdesk.management.ticket.rating']._read_group(
                my_domain + [('date', '>=', since)], groupby=['rating'], aggregates=['__count'])
            count = sum(c for _r, c in groups)
            return sum(int(r or 0) * c for r, c in groups) / count if count else None

        today_closed = Ticket.search_count(closed_today_domain)
        last_7_closed = Ticket.search_count(closed_7d_domain)
        sla_today = _sla_success(closed_today_domain)
        sla_7d = _sla_success(closed_7d_domain)
        rating_today = _avg_rating(today)
        rating_7d = _avg_rating(last_7_days)
        my_failed = sum(failed_counts.values())

        return {
            'my_tickets': sum(open_counts.values()),
            'high_priority': open_counts.get('2', 0),
            'urgent': open_counts.get('3', 0),
            'open_tickets': sum(open_counts.values()),
            'avg_open_hours': _fmt_duration(_avg_open_seconds(open_tickets)),
            'hp_avg_open_hours': _fmt_duration(_avg_open_seconds(open_tickets.filtered(lambda t: t.priority == '2'))),
            'urg_avg_open_hours': _fmt_duration(_avg_open_seconds(open_tickets.filtered(lambda t: t.priority == '3'))),
            'failed_tickets': my_failed,
            'hp_failed_tickets': failed_counts.get('2', 0),
            'urg_failed_tickets': failed_counts.get('3', 0),

            'closed_tickets': today_closed,
            'sla_success_rate': f"{round(sla_today)}%" if sla_today is not None else "0%",
            'sla_success_rate_7d': f"{sla_7d:.2f} %" if sla_7d is not None else "0.00 %",
            'average_rating': f"{round(rating_today, 1)}" if rating_today is not None else "/",
            'average_rating_7d': f"{round(rating_7d, 1)} / 5" if rating_7d is not None else "/",
            'today': today_closed,
            # Daily average over the last 7 days
            'avg_last_7_days': round(last_7_closed / 7.0, 1),
            # Raw figures compared to the daily targets (None: no data, nothing to compare)
            'performance': {
                'closed_today': today_closed,
                'closed_7d': round(last_7_closed / 7.0, 1),
                'success_today': sla_today,
                'success_7d': sla_7d,
                'rating_today': rating_today,
                'rating_7d': rating_7d,
            },

            # Daily targets of the current user (0 = not set)
            **self._get_dashboard_targets(),

            'domains': {
                'open': open_domain,
                'high_priority': open_domain + [('priority', '=', '2')],
                'urgent': open_domain + [('priority', '=', '3')],
                'failed': failed_domain,
                'hp_failed': failed_domain + [('priority', '=', '2')],
                'urg_failed': failed_domain + [('priority', '=', '3')],
                'closed_today': [self._json_leaf(leaf) for leaf in closed_today_domain],
                'closed_7d': [self._json_leaf(leaf) for leaf in closed_7d_domain],
                'closed': my_domain + [('stage_id.is_close', '=', True)],
            },
        }

    # Dashboard target key -> (res.users field, max value)
    _DASHBOARD_TARGETS = {
        'closed': ('helpdesk_target_closed', None),
        'success': ('helpdesk_target_success', 100.0),
        'rating': ('helpdesk_target_rating', 5.0),
    }

    @api.model
    def _get_dashboard_targets(self):
        user = self.env.user.sudo()
        return {
            'target_closed': user.helpdesk_target_closed,
            'target_success': user.helpdesk_target_success,
            'target_rating': user.helpdesk_target_rating,
        }

    @api.model
    def set_dashboard_target(self, target, value):
        """ Save a daily target of the current user's dashboard. Returns the stored value. """
        if target not in self._DASHBOARD_TARGETS:
            raise ValueError(f"Unknown dashboard target: {target}")
        fname, maximum = self._DASHBOARD_TARGETS[target]
        value = max(float(value or 0), 0.0)
        if maximum is not None:
            value = min(value, maximum)
        if target == 'closed':
            value = int(value)
        # sudo: users may not write their own res.users fields by default; only the current user is written
        self.env.user.sudo().write({fname: value})
        return value

    @api.model
    def _json_leaf(self, leaf):
        """ Domain leaf sent to the web client: datetimes as server strings. """
        if isinstance(leaf, tuple) and isinstance(leaf[2], datetime.datetime):
            return (leaf[0], leaf[1], fields.Datetime.to_string(leaf[2]))
        return leaf

    def _alias_get_creation_values(self):
        values = super(HelpdeskManagementTeam, self)._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get_id('helpdesk.management.ticket')
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['team_id'] = self.id
        return values
