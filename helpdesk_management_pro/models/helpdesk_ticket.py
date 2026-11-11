# -*- coding: utf-8 -*-
import datetime
import random
import uuid
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, tools, _

_logger = logging.getLogger(__name__)

SLA_WARNING_SECONDS = 3600

class HelpdeskManagementTicket(models.Model):
    _name = 'helpdesk.management.ticket'
    _description = 'Helpdesk Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'priority desc, create_date desc'
    # Customers (read-only portal access) can reply on their tickets
    _mail_post_access = 'read'

    name = fields.Char(string='Ticket Number', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    subject = fields.Char(string='Subject', required=True, tracking=True)
    access_token = fields.Char('Security Token', copy=False, default=lambda self: str(uuid.uuid4()))
    access_url = fields.Char('Portal Access URL', compute='_compute_access_url', help='Customer Portal URL')
    
    # Customer Info
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    # Follow the customer like the standard helpdesk; still editable for tickets without contact
    partner_name = fields.Char(string='Customer Name', compute='_compute_partner_info', store=True, readonly=False)
    partner_email = fields.Char(string='Customer Email', compute='_compute_partner_info', store=True, readonly=False)
    partner_phone = fields.Char(string='Customer Phone', compute='_compute_partner_info', store=True, readonly=False)
    
    # Assignment
    team_id = fields.Many2one('helpdesk.management.team', string='Team', tracking=True, index=True, required=True, default=lambda self: self.env['helpdesk.management.team'].search([], limit=1).id)
    user_id = fields.Many2one('res.users', string='Assigned to', tracking=True, index=True)
    is_manually_assigned = fields.Boolean(string='Manually Assigned', default=False, tracking=True, copy=False)
    
    
    @api.depends('partner_id')
    def _compute_partner_info(self):
        # A new customer replaces the contact details of the previous one
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_name = ticket.partner_id.name
                ticket.partner_email = ticket.partner_id.email
                ticket.partner_phone = ticket.partner_id.phone

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category_id.team_id:
            self.team_id = self.category_id.team_id
    
    # Status
    def _default_stage_id(self):
        return self._get_team_first_stage(self._context.get('default_team_id')).id

    @api.model
    def _get_team_first_stage(self, team_id):
        Stage = self.env['helpdesk.management.stage']
        if team_id:
            stage = Stage.search(
                ['|', ('team_ids', '=', False), ('team_ids', 'in', [team_id])],
                order='sequence, id', limit=1
            )
            if stage:
                return stage
        return Stage.search([], order='sequence, id', limit=1)

    stage_id = fields.Many2one(
        'helpdesk.management.stage', string='Stage', tracking=True,
        domain="['|', ('team_ids', '=', False), ('team_ids', 'in', [team_id])]",
        group_expand='_read_group_stage_ids', copy=False,
        index=True, ondelete='restrict', required=True, default=_default_stage_id
    )

    @api.onchange('team_id')
    def _onchange_team_id_stage(self):
        if self.team_id:
            if self.stage_id and self.stage_id.team_ids and self.team_id not in self.stage_id.team_ids:
                new_stage = self.env['helpdesk.management.stage'].search(
                    ['|', ('team_ids', '=', False), ('team_ids', 'in', [self.team_id.id])],
                    order='sequence, id', limit=1
                )
                if new_stage:
                    self.stage_id = new_stage
    
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', default='0', tracking=True)

    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('blocked', 'Blocked'),
        ('waiting_customer', 'Waiting for Customer'),
        ('done', 'Ready for Next Stage')
    ], string='Kanban State', default='normal', tracking=True, copy=False)
    
    # Dates
    assign_date = fields.Datetime(string='Assign Date', copy=False, tracking=True, readonly=True)
    close_date = fields.Datetime(string='Close Date', copy=False, tracking=True, readonly=True)
    date_last_stage_update = fields.Datetime(string='Last Stage Update', copy=False, readonly=True, index=True,
                                             default=fields.Datetime.now)
    auto_close_reminder_sent = fields.Boolean(
        string='Auto-Close Reminder Sent',
        default=False,
        copy=False,
        help="Tracks if the reminder email before auto-closing has already been sent."
    )
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')

    # Categorization
    description = fields.Html(string='Description')
    tag_ids = fields.Many2many('helpdesk.management.tag', string='Tags')
    category_id = fields.Many2one('helpdesk.management.category', string='Category', tracking=True)
    source_id = fields.Many2one('helpdesk.management.source', string='Source', tracking=True)
    
    # SLA
    sla_status_ids = fields.One2many('helpdesk.management.sla.status', 'ticket_id', string='SLA Policies')
    # SLA tags displayed on the ticket (cancelled statuses are history only)
    sla_tag_ids = fields.Many2many('helpdesk.management.sla.status', string='SLA', compute='_compute_sla_tag_ids')

    @api.depends('sla_status_ids.status')
    def _compute_sla_tag_ids(self):
        for ticket in self:
            ticket.sla_tag_ids = ticket.sla_status_ids.filtered(lambda s: s.status != 'cancelled')

    # We still need sla_deadline and sla_status for the UI to represent the "current" state
    sla_deadline = fields.Datetime(string='SLA Deadline', compute='_compute_sla_deadline_status', store=True, tracking=True)
    sla_status = fields.Selection([
        ('on_track', 'On Track'),
        ('warning', 'Warning'),
        ('breached', 'Breached'),
        ('achieved', 'Achieved')
    ], string='SLA Status', compute='_compute_sla_deadline_status', store=True, tracking=True)
    
    @api.depends('sla_status_ids.deadline', 'sla_status_ids.status', 'sla_status_ids.is_paused')
    def _compute_sla_deadline_status(self):
        now = fields.Datetime.now()
        for ticket in self:
            ongoing = ticket.sla_status_ids.filtered(lambda s: s.status == 'ongoing')
            running = ongoing.filtered(lambda s: not s.is_paused and s.deadline)
            earliest = min(running, key=lambda s: s.deadline) if running else False
            ticket.sla_deadline = earliest.deadline if earliest else False

            # A single failed (or overdue) policy breaches the ticket, even if others are still running
            if any(s.status == 'failed' for s in ticket.sla_status_ids) or (earliest and now > earliest.deadline):
                ticket.sla_status = 'breached'
            elif earliest and (earliest.deadline - now).total_seconds() < SLA_WARNING_SECONDS:
                ticket.sla_status = 'warning'
            elif ongoing:
                # Running on time, or paused (excluded stage / waiting for customer)
                ticket.sla_status = 'on_track'
            elif any(s.status == 'reached' for s in ticket.sla_status_ids):
                ticket.sla_status = 'achieved'
            else:
                ticket.sla_status = False

    @api.model
    def _get_sla_failed_domain(self, now=None):
        """ Tickets having a failed SLA, evaluated on the SLA statuses at ``now``: an ongoing (not paused)
        policy past its deadline is already failed, without waiting for the SLA cron to refresh sla_status. """
        now = fields.Datetime.to_string(now or fields.Datetime.now())
        return [('sla_status_ids', 'any', [
            '|', ('status', '=', 'failed'),
            '&', '&', ('status', '=', 'ongoing'), ('is_paused', '=', False), ('deadline', '<', now),
        ])]

    def _handle_assign_sla_reach(self):
        """ Check and mark reaching for ongoing SLAs targeting ticket assignment """
        now = fields.Datetime.now()
        for ticket in self:
            if not ticket.user_id:
                continue
            assign_dt = ticket.assign_date or now
            for sla_status in ticket.sla_status_ids.filtered(lambda s: s.status == 'ongoing' and s.sla_id.target_type == 'assign'):
                if not sla_status._is_sla_expired():
                    sla_status.status = 'reached'
                    sla_status.reached_datetime = assign_dt
                else:
                    sla_status.status = 'failed'
                    sla_status.failed_datetime = assign_dt
                sla_status.is_paused = False
                sla_status.pause_start_time = False

    def _update_sla(self):
        """ Update SLA and deadline based on dynamic criteria matching. (Idempotent) """
        # pyrefly: ignore [missing-import]
        from odoo.tools.safe_eval import safe_eval
        
        now = fields.Datetime.now()
        
        for ticket in self:
            if not ticket.team_id or not ticket.team_id.use_sla:
                # Task 3.1: Cancel ongoing SLAs if team SLA is disabled
                for sla_status in ticket.sla_status_ids.filtered(lambda s: s.status == 'ongoing'):
                    sla_status.write({'status': 'cancelled'})
                continue
                
            all_slas = self.env['helpdesk.management.sla'].search([
                ('team_id', '=', ticket.team_id.id),
                ('active', '=', True)
            ])
            
            matching_slas = self.env['helpdesk.management.sla']
            for sla in all_slas:
                if not sla._matches_ticket(ticket):
                    continue

                domain = safe_eval(sla.domain or '[]')
                if domain:
                    ticket_domain = [('id', '=', ticket.id)] + domain
                    if not self.env['helpdesk.management.ticket'].search(ticket_domain):
                        continue
                matching_slas |= sla
            
            # 1. Create missing SLA statuses for matching policies
            existing_sla_statuses = ticket.sla_status_ids
            existing_sla_ids = existing_sla_statuses.mapped('sla_id')
            
            # A policy matching again (e.g. priority changed back) restarts its cancelled status,
            # the unique (ticket, policy) constraint preventing a new one
            reactivated_statuses = existing_sla_statuses.filtered(
                lambda s: s.status == 'cancelled' and s.sla_id in matching_slas)
            if reactivated_statuses:
                existing_sla_ids -= reactivated_statuses.sla_id
                reactivated_statuses.unlink()

            for sla in matching_slas:
                if sla not in existing_sla_ids:
                    # Task 3.2: Calculate deadline from ticket creation date
                    calendar = ticket.team_id.resource_calendar_id or ticket.company_id.resource_calendar_id or self.env.company.resource_calendar_id
                    start_date = ticket.create_date if (ticket.create_date and ticket.create_date <= now) else now
                    
                    if calendar and hasattr(calendar, 'plan_hours'):
                        deadline = calendar.plan_hours(sla.target_hours, day_dt=start_date, compute_leaves=True)
                    else:
                        deadline = start_date + datetime.timedelta(hours=sla.target_hours)
                        
                    # Task 3.4: Check if ticket is in an excluded stage or in waiting state
                    is_paused = bool(
                        (sla.exclude_stage_ids and ticket.stage_id in sla.exclude_stage_ids)
                        or ticket.kanban_state in ('waiting_customer', 'blocked')
                    )
                    
                    # Task 3.3: Target type check (reaching stage vs assign ticket)
                    status = 'ongoing'
                    reached_dt = False
                    failed_dt = False
                    
                    if sla.target_type == 'reaching_stage':
                        if ticket.stage_id == sla.stage_id:
                            is_paused = False
                            if not deadline or now <= deadline:
                                status = 'reached'
                                reached_dt = now
                            else:
                                status = 'failed'
                                failed_dt = now
                    elif sla.target_type == 'assign':
                        if ticket.user_id:
                            is_paused = False
                            assign_dt = ticket.assign_date or now
                            if not deadline or assign_dt <= deadline:
                                status = 'reached'
                                reached_dt = assign_dt
                            else:
                                status = 'failed'
                                failed_dt = assign_dt
                        
                    self.env['helpdesk.management.sla.status'].create({
                        'ticket_id': ticket.id,
                        'sla_id': sla.id,
                        'status': status,
                        'start_datetime': start_date,
                        'deadline': deadline,
                        'is_paused': is_paused,
                        'pause_start_time': now if is_paused else False,
                        'reached_datetime': reached_dt,
                        'failed_datetime': failed_dt,
                    })
                    
            # 2. Cancel ongoing SLA statuses that no longer match the criteria
            for sla_status in existing_sla_statuses.exists():
                if sla_status.status == 'ongoing' and sla_status.sla_id not in matching_slas:
                    sla_status.write({
                        'status': 'cancelled'
                    })

    # Time Tracking & Rating
    use_helpdesk_timesheet = fields.Boolean(related='team_id.use_helpdesk_timesheet', string='Timesheets Enabled')
    use_rating = fields.Boolean(related='team_id.use_rating', string='Ratings Enabled')
    time_ids = fields.One2many('helpdesk.management.ticket.time', 'ticket_id', string='Timesheets')
    total_time = fields.Float(string='Total Time', compute='_compute_total_time', store=True)
    ticket_rating_ids = fields.One2many('helpdesk.management.ticket.rating', 'ticket_id', string='Customer Ratings')
    average_rating = fields.Float(string='Average Rating', compute='_compute_average_rating', store=True)

    @api.depends('time_ids.duration')
    def _compute_total_time(self):
        for ticket in self:
            ticket.total_time = sum(ticket.time_ids.mapped('duration'))

    @api.depends('ticket_rating_ids.rating')
    def _compute_average_rating(self):
        for ticket in self:
            ratings = [int(r.rating) for r in ticket.ticket_rating_ids if r.rating]
            ticket.average_rating = sum(ratings) / len(ratings) if ratings else 0.0

    def _do_auto_assignment(self):
        """ Implement Odoo 19 auto-assignment logic """
        for ticket in self:
            if ticket.user_id or ticket.is_manually_assigned or not ticket.team_id.auto_assignment:
                continue
            
            team = ticket.team_id
            
            # Eligible users: Team Members or Fallback to Helpdesk Users
            eligible_users = team.member_ids
            if not eligible_users:
                helpdesk_group = self.env.ref('helpdesk_management_pro.group_helpdesk_user', raise_if_not_found=False)
                if helpdesk_group:
                    eligible_users = helpdesk_group.sudo().user_ids
            
            if not eligible_users:
                continue
                
            # Filter unavailable users
            available_users = self.env['res.users']
            now = fields.Datetime.now()
            for user in eligible_users:
                if not user.resource_ids:
                    available_users |= user
                    continue
                # Check leaves for this user's resource
                on_leave = self.env['resource.calendar.leaves'].sudo().search_count([
                    ('resource_id', 'in', user.resource_ids.ids),
                    ('date_from', '<=', now),
                    ('date_to', '>=', now)
                ])
                if not on_leave:
                    available_users |= user
            
            if not available_users:
                continue
                
            method = team.assignment_method
            # Workload is measured within the team, like the standard helpdesk
            count_domain = [('team_id', '=', team.id)]
            if method == 'tags':
                # Dispatch based on tags, then lowest open tickets among the matching users
                candidates = ticket.tag_ids.user_ids & available_users
                count_domain += [('stage_id.is_close', '=', False)]
            elif method == 'balanced':
                # Equal number of OPEN tickets
                candidates = available_users
                count_domain += [('stage_id.is_close', '=', False)]
            else:
                # 'random': equal number of TOTAL tickets
                candidates = available_users
            if not candidates:
                continue  # Leave unassigned if no tag match

            # Workload of the whole team, whatever the tickets visible to the user creating this one
            user_counts = self.env['helpdesk.management.ticket'].sudo()._read_group(
                count_domain + [('id', '!=', ticket.id), ('user_id', 'in', candidates.ids)],
                groupby=['user_id'],
                aggregates=['__count']
            )
            count_dict = {user.id: count for user, count in user_counts if user}
            best_user = min(candidates, key=lambda u: (count_dict.get(u.id, 0), u.id))
            ticket.with_context(helpdesk_auto_assign=True).write({'user_id': best_user.id})

        self._handle_assign_sla_reach()

    @api.constrains('name', 'company_id')
    def _check_name_unique(self):
        for ticket in self:
            if ticket.name and ticket.name != _('New'):
                domain = [
                    ('id', '!=', ticket.id),
                    ('name', '=', ticket.name),
                    ('company_id', '=', ticket.company_id.id),
                ]
                if self.search_count(domain) > 0:
                    from odoo.exceptions import ValidationError
                    raise ValidationError(_("Ticket reference '%s' already exists for company %s.", ticket.name, ticket.company_id.name))

    @api.model
    def website_form_input_filter(self, request, values):
        """ Website Form Builder hook ("Create a Ticket" action).

        Routes the ticket to the team chosen on the form (only teams accepting website
        tickets on this website, else the first one) and links the customer: the logged-in
        user, or the contact matching the email (created if needed).
        """
        Team = self.env['helpdesk.management.team'].sudo()
        website = self.env.website
        form_teams = Team.search([
            ('use_website_helpdesk_form', '=', True),
            ('website_id', 'in', [False, website.id]),
        ])
        team = form_teams.filtered(lambda t: t.id == values.get('team_id'))[:1] or form_teams[:1]
        if team:
            values['team_id'] = team.id
        else:
            values.pop('team_id', None)

        if not values.get('partner_id'):
            partner = self.env['res.partner']
            if not request.env.user._is_public():
                partner = request.env.user.partner_id
            else:
                email = tools.email_normalize(values.get('partner_email') or '')
                if email:
                    Partner = self.env['res.partner'].sudo()
                    partner = Partner.search([('email_normalized', '=', email)], limit=1) or Partner.create({
                        'name': values.get('partner_name') or email,
                        'email': values['partner_email'].strip(),
                        'phone': values.get('partner_phone'),
                    })
            if partner:
                values['partner_id'] = partner.id
                values.setdefault('partner_name', partner.name)
                values.setdefault('partner_email', partner.email)
                if partner.phone:
                    values.setdefault('partner_phone', partner.phone)

        values.setdefault('company_id', (team.company_id or website.company_id).id)
        return values

    @api.model_create_multi
    def create(self, vals_list):
        """ Create tickets and assign them according to the team's assignment method """
        now = fields.Datetime.now()
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company_id = vals.get('company_id') or self.env.company.id
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('helpdesk.management.ticket') or _('New')
            
            if not vals.get('team_id') and vals.get('category_id'):
                category = self.env['helpdesk.management.category'].browse(vals['category_id'])
                if category.team_id:
                    vals['team_id'] = category.team_id.id

            # Start in the first stage of the ticket's own team (website form, email alias, API, ...)
            team_id = vals.get('team_id') or self._context.get('default_team_id')
            if team_id and not vals.get('stage_id'):
                stage = self._get_team_first_stage(team_id)
                if stage:
                    vals['stage_id'] = stage.id

            if vals.get('user_id'):
                vals['is_manually_assigned'] = True
                if not vals.get('assign_date'):
                    vals['assign_date'] = now

        tickets = super().create(vals_list)
        # The customer follows the ticket, so that replies from the chatter reach them
        for ticket in tickets.filtered('partner_id'):
            ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        tickets._update_sla()
        tickets._do_auto_assignment()

        # Task 2.1: Configurable and predictable receipt policy
        for ticket in tickets:
            if ticket.team_id and not ticket.team_id.use_ticket_receipt:
                continue

            recipient_email = ticket.partner_email or (ticket.partner_id and ticket.partner_id.email)
            if not recipient_email:
                continue

            is_external_channel = (
                bool(ticket.source_id and ((ticket.source_id.name or '').lower() in ('website', 'email', 'portal') or getattr(ticket.source_id, 'code', '') in ('website', 'email', 'portal')))
                or bool(self.env.context.get('website_id'))
                or bool(self.env.context.get('default_source_id'))
                or bool(self.env.context.get('mail_create_nolog'))
            )
            is_internal_creator = (
                ticket.create_uid and ticket.partner_id and ticket.partner_id == ticket.create_uid.partner_id
            )
            if not is_external_channel and is_internal_creator:
                continue

            # Avoid duplicate receipt when stage template is already configured
            if ticket.stage_id and ticket.stage_id.template_id:
                continue

            template = (ticket.team_id and ticket.team_id.ticket_receipt_template_id) or self.env.ref(
                'helpdesk_management_pro.mail_template_ticket_receipt', raise_if_not_found=False
            )
            if template:
                ticket._send_ticket_template(template)

        return tickets

    def _send_ticket_template(self, template):
        """ Send a customer email logged in the chatter, as the standard helpdesk does for stage templates. """
        rating_template = self.env.ref('helpdesk_management_pro.mail_template_ticket_review', raise_if_not_found=False)
        queued = False
        for ticket in self:
            if not (ticket.partner_email or ticket.partner_id.email):
                continue
            # Rating requests only make sense when the team collects ratings
            if template == rating_template and not ticket.team_id.use_rating:
                continue
            # Queue the email instead of sending it at the end of the request: the user saving the ticket
            # must not wait for the SMTP server (up to its 60s timeout when it is slow or unreachable)
            ticket.with_context(mail_notify_force_send=False).message_post_with_source(
                template,
                subtype_xmlid='mail.mt_note',
                email_layout_xmlid='mail.mail_notification_light',
            )
            queued = True
        if queued:
            # Send the queue right away in the background (cron worker), not at the next hourly run
            mail_cron = self.env.ref('mail.ir_cron_mail_scheduler_action', raise_if_not_found=False)
            if mail_cron:
                mail_cron.sudo()._trigger()

    @api.model
    def _read_group_stage_ids(self, stages, domain, order=None):
        search_domain = []
        if self.env.context.get('default_team_id'):
            search_domain = ['|', ('team_ids', '=', False), ('team_ids', 'in', [self.env.context['default_team_id']])]
        return stages.search(search_domain, order=order)

    def write(self, vals):
        now = fields.Datetime.now()
        
        # Track manual assignment (automatic assignment goes through the same write)
        if 'user_id' in vals:
            vals['is_manually_assigned'] = bool(vals['user_id']) and not self.env.context.get('helpdesk_auto_assign')

        if 'team_id' in vals:
            vals['is_manually_assigned'] = False

        # Track old stage, kanban_state and partner for each ticket
        old_stage_map = {ticket.id: ticket.stage_id for ticket in self}
        old_kanban_state_map = {ticket.id: ticket.kanban_state for ticket in self}
        old_partner_map = {ticket.id: ticket.partner_id for ticket in self}
        old_team_map = {ticket.id: ticket.team_id for ticket in self}

        stage_changed = self.env['helpdesk.management.ticket']
        newly_closed = self.env['helpdesk.management.ticket']
        if 'stage_id' in vals:
            stage = self.env['helpdesk.management.stage'].browse(vals['stage_id'])
            stage_changed = self.filtered(lambda t: t.stage_id != stage)
            newly_closed = stage_changed.filtered(lambda t: not t.stage_id.is_close) if stage.is_close else newly_closed
            if not stage.is_close:
                vals['close_date'] = False
            # Moving forward resets the kanban state, like the standard helpdesk
            if stage_changed and 'kanban_state' not in vals:
                stage_changed.write({'kanban_state': 'normal'})
                old_kanban_state_map.update({t.id: t.kanban_state for t in stage_changed})
        newly_assigned = self.filtered(lambda t: not t.assign_date) if vals.get('user_id') and not vals.get('assign_date') else None

        res = super(HelpdeskManagementTicket, self).write(vals)

        # Per-ticket dates: keep the first assignment / closing date and the last stage change
        if newly_assigned:
            super(HelpdeskManagementTicket, newly_assigned).write({'assign_date': now})
        if newly_closed:
            super(HelpdeskManagementTicket, newly_closed).write({'close_date': now})
        if stage_changed:
            super(HelpdeskManagementTicket, stage_changed).write({
                'date_last_stage_update': now,
                'auto_close_reminder_sent': False,
            })

        if 'partner_id' in vals:
            for ticket in self.filtered(lambda t: t.partner_id and t.partner_id != old_partner_map[t.id]):
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)

        # Task 3.3: Reached check on assignment target SLAs
        if 'user_id' in vals and vals['user_id']:
            self._handle_assign_sla_reach()

        if 'stage_id' in vals or 'kanban_state' in vals:
            for ticket in self:
                old_stage = old_stage_map.get(ticket.id)
                old_kanban_state = old_kanban_state_map.get(ticket.id)
                new_stage = ticket.stage_id
                new_kanban_state = ticket.kanban_state

                # Task 2.2: Send stage email ONLY if ticket actually transitioned to a different stage
                if 'stage_id' in vals and old_stage and old_stage.id != ticket.stage_id.id:
                    if ticket.stage_id and ticket.stage_id.template_id:
                        ticket._send_ticket_template(ticket.stage_id.template_id)
                
                # Ticket moved back before the target stage: reopen reached SLAs
                if 'stage_id' in vals:
                    for sla_status in ticket.sla_status_ids.filtered(
                        lambda s: s.status == 'reached' and s.sla_id.target_type == 'reaching_stage'
                        and new_stage not in s.sla_id.exclude_stage_ids
                        and not s.sla_id._is_stage_reached(new_stage)
                    ):
                        sla_status.write({'status': 'ongoing', 'reached_datetime': False})

                # SLA stage reaching and pause/resume logic
                for sla_status in ticket.sla_status_ids.filtered(lambda s: s.status == 'ongoing'):
                    sla = sla_status.sla_id
                    calendar = sla_status._get_calendar()

                    # 1. Check if reached target stage (or a later one)
                    if sla.target_type == 'reaching_stage' and sla._is_stage_reached(new_stage):
                        if not sla_status._is_sla_expired():
                            sla_status.status = 'reached'
                            sla_status.reached_datetime = now
                        else:
                            sla_status.status = 'failed'
                            sla_status.failed_datetime = now
                        sla_status.is_paused = False
                        sla_status.pause_start_time = False
                        continue

                    # 2. Check pause condition (excluded stage or waiting state)
                    was_paused_condition = bool(
                        (old_stage and old_stage in sla.exclude_stage_ids)
                        or old_kanban_state in ('waiting_customer', 'blocked')
                    )
                    is_paused_now_condition = bool(
                        new_stage in sla.exclude_stage_ids
                        or new_kanban_state in ('waiting_customer', 'blocked')
                    )

                    # Resume if leaving paused condition
                    if sla_status.is_paused and not is_paused_now_condition:
                        if sla_status.pause_start_time:
                            if calendar and hasattr(calendar, 'get_work_hours_count'):
                                paused_working_hours = calendar.get_work_hours_count(sla_status.pause_start_time, now)
                                if sla_status.deadline and hasattr(calendar, 'plan_hours'):
                                    sla_status.deadline = calendar.plan_hours(paused_working_hours, day_dt=sla_status.deadline, compute_leaves=True)
                                sla_status.total_paused_working_hours += paused_working_hours
                            else:
                                paused_delta = now - sla_status.pause_start_time
                                if sla_status.deadline:
                                    sla_status.deadline += paused_delta
                        sla_status.is_paused = False
                        sla_status.pause_start_time = False

                    # Pause if entering paused condition
                    elif not sla_status.is_paused and is_paused_now_condition:
                        sla_status.is_paused = True
                        sla_status.pause_start_time = now

        relevant_fields = ['team_id', 'priority', 'stage_id', 'partner_id', 'tag_ids', 'kanban_state', 'company_id']
        if any(f in vals for f in relevant_fields):
            self._update_sla()
            
        # Like the standard helpdesk, tickets are dispatched when created or moved to another team,
        # not each time they are edited (an agent can unassign a ticket on purpose)
        if 'team_id' in vals:
            moved = self.filtered(lambda t: t.team_id != old_team_map[t.id])
            if 'stage_id' not in vals:
                for ticket in moved.filtered(lambda t: t.stage_id.team_ids and t.team_id not in t.stage_id.team_ids):
                    stage = self._get_team_first_stage(ticket.team_id.id)
                    if stage:
                        ticket.stage_id = stage
            if 'user_id' not in vals:
                moved._do_auto_assignment()

        return res

    def action_assign_to_me(self):
        self.write({'user_id': self.env.user.id})

    def action_reply(self):
        self.ensure_one()
        partner_ids = []
        if self.partner_id:
            partner_ids = [self.partner_id.id]
        elif self.partner_email:
            partner = self.env['res.partner'].search([('email', '=ilike', self.partner_email)], limit=1)
            if partner:
                partner_ids = [partner.id]

        comment_subtype = self.env.ref('mail.mt_comment', raise_if_not_found=False)
        return {
            'name': _('Reply to Customer'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': 'helpdesk.management.ticket',
                'default_res_id': self.id,
                'default_composition_mode': 'comment',
                'default_subtype_id': comment_subtype.id if comment_subtype else False,
                'default_subtype_xmlid': 'mail.mt_comment',
                'default_partner_ids': partner_ids,
                'default_subject': _("Re: %s - %s", self.name or '', self.subject or ''),
                'force_email': True,
            },
        }


    def message_new(self, msg_dict, custom_values=None):
        """ Overrides mail_thread message_new to route incoming emails to tickets """
        custom_values = dict(custom_values or {})
        if not custom_values.get('team_id') and self.env.context.get('default_team_id'):
            custom_values['team_id'] = self.env.context.get('default_team_id')
        # The customer is the sender (created if unknown), like the standard helpdesk
        if not msg_dict.get('author_id') and msg_dict.get('email_from'):
            author = self.env['mail.thread']._partner_find_from_emails_single([msg_dict['email_from']], no_create=False)
            msg_dict['author_id'] = author.id
        author = self.env['res.partner'].browse(msg_dict.get('author_id')).exists()
        email_name, email_normalized = tools.parse_contact_from_email(msg_dict.get('email_from') or '')
        defaults = {
            # 'name' is the ticket number: the email subject goes to the subject field
            'name': _('New'),
            'subject': msg_dict.get('subject') or _("No Subject"),
            'description': msg_dict.get('body'),
            'partner_id': author.id or False,
            'partner_name': author.name or email_name or email_normalized,
            'partner_email': author.email or email_normalized,
        }
        defaults.update(custom_values)
        return super(HelpdeskManagementTicket, self).message_new(msg_dict, defaults)

    def _mail_get_partner_fields(self, introspect_fields=False):
        return ['partner_id']

    def create_ticket_from_whatsapp(self, wa_data):
        """ Hook for WhatsApp integration to create tickets """
        try:
            subject = wa_data.get('subject') or 'WhatsApp Ticket'
            phone = wa_data.get('phone') or wa_data.get('partner_phone')
            partner_id = wa_data.get('partner_id')
            if not partner_id and phone:
                partner = self.env['res.partner'].search([('phone', '=', phone)], limit=1)
                if partner:
                    partner_id = partner.id

            vals = {
                'subject': subject,
                'description': wa_data.get('message') or wa_data.get('description', ''),
                'partner_phone': phone,
                'partner_name': wa_data.get('partner_name'),
                'partner_id': partner_id,
            }
            if wa_data.get('team_id'):
                vals['team_id'] = wa_data['team_id']
            return self.create({k: v for k, v in vals.items() if v is not None})
        except Exception as e:
            _logger.error("Failed to create ticket from whatsapp data: %s. Error: %s", wa_data, str(e))
            return self.env['helpdesk.management.ticket']

    @api.model
    def _cron_auto_close_tickets(self):
        teams = self.env['helpdesk.management.team'].search([('use_auto_close', '=', True)])
        now = fields.Datetime.now()
        _logger.info("Starting auto-close cron for %s teams.", len(teams))
        for team in teams:
            try:
                # One failing team must not abort the transaction of the others
                with self.env.cr.savepoint():
                    self._auto_close_team_tickets(team, now)
            except Exception as e:
                _logger.error("Failed to auto-close tickets for team %s: %s", team.name, str(e))

    @api.model
    def _auto_close_team_tickets(self, team, now):
        """ Remind, then close the tickets of the team without stage change for too long.
        Inactivity is measured from the last stage change like the standard helpdesk, not from
        write_date which any write (SLA cron, the reminder flag itself, ...) would reset. """
        if not team.auto_close_stage_id:
            return
        close_days = team.auto_close_ticket_days or 7
        reminder_days = team.auto_close_reminder_days or 2
        close_cutoff = now - datetime.timedelta(days=close_days)

        base_domain = [
            ('team_id', '=', team.id),
            ('stage_id.is_close', '=', False),
        ]
        if team.auto_close_in_stage_ids:
            base_domain.append(('stage_id', 'in', team.auto_close_in_stage_ids.ids))

        # Send the auto-close reminder email prior to closing
        if team.use_auto_close_reminder:
            template = team.auto_close_reminder_template_id or self.env.ref(
                'helpdesk_management_pro.mail_template_ticket_autoclose', raise_if_not_found=False
            )
            if template:
                reminder_cutoff = now - datetime.timedelta(days=max(close_days - reminder_days, 1))
                tickets_to_remind = self.search(base_domain + [
                    ('auto_close_reminder_sent', '=', False),
                    ('date_last_stage_update', '<', reminder_cutoff),
                    ('date_last_stage_update', '>=', close_cutoff),
                ])
                tickets_to_remind._send_ticket_template(template)
                tickets_to_remind.write({'auto_close_reminder_sent': True})
                if tickets_to_remind:
                    _logger.info("Sent auto-close reminder for %s tickets of team %s", len(tickets_to_remind), team.name)

        # Auto-close inactive tickets past threshold
        tickets_to_close = self.search(base_domain + [('date_last_stage_update', '<', close_cutoff)])
        if tickets_to_close:
            tickets_to_close.write({'stage_id': team.auto_close_stage_id.id})
            _logger.info("Auto-closed %s tickets for team %s", len(tickets_to_close), team.name)

    @api.model
    def _cron_update_sla_status(self):
        """ Fail the overdue SLAs and refresh the time-dependent SLA state (warning / breached) of the tickets. """
        now = fields.Datetime.now()
        ongoing_statuses = self.env['helpdesk.management.sla.status'].search([
            ('status', '=', 'ongoing'),
            ('is_paused', '=', False)
        ])
        expired = ongoing_statuses.filtered(lambda s: s._is_sla_expired())
        expired.write({'status': 'failed', 'failed_datetime': now})

        # sla_status also depends on the current time: recompute it as a stored compute, without
        # writing on the tickets (which would bump their write_date)
        tickets = ongoing_statuses.ticket_id
        for fname in ('sla_deadline', 'sla_status'):
            self.env.add_to_compute(self._fields[fname], tickets)
        tickets.flush_recordset(['sla_deadline', 'sla_status'])

    def _compute_access_url(self):
        for ticket in self:
            ticket.access_url = '/my/ticket/%s' % ticket.id

    def action_preview_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.access_url,
        }


