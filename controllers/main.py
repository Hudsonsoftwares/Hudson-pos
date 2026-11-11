# pyrefly: ignore [missing-import]
from odoo import http
# pyrefly: ignore [missing-import]
from odoo.http import request

class AppointmentController(http.Controller):

    @http.route(['/book/<string:token>'], type='http', auth='public', website=True)
    def book_appointment(self, token, **kwargs):
        # Look up the invite by token (short_code or access_token)
        invite = request.env['appointment.invite'].sudo().search([
            '|', ('short_code', '=', token), ('access_token', '=', token)
        ], limit=1)
        
        if not invite or not invite.appointment_type_ids:
            return request.redirect('/?error=invalid_token')
            
        # If there's only one appointment type, redirect directly to it
        if len(invite.appointment_type_ids) == 1:
            return request.redirect(f'/appointment/{invite.appointment_type_ids[0].id}?invite_token={invite.access_token}')
            
        # If there are multiple, redirect to the first one for now
        # (Standard Odoo handles multiple by showing a list, but we'll simplify here since they usually just share one or can pick the first)
        return request.redirect(f'/appointment/{invite.appointment_type_ids[0].id}?invite_token={invite.access_token}')
        
    @http.route(['/appointment'], type='http', auth='public', website=True)
    def appointment_index(self, **kwargs):
        appointment_types = request.env['appointment.type'].sudo().search([('is_published', '=', True)])
        return request.render('appointment.appointment_type_index', {
            'appointment_types': appointment_types,
        })

    @http.route(['/appointment/<model("appointment.type"):appointment_type>'], type='http', auth='public', website=True)
    def appointment_preview(self, appointment_type, **kwargs):
        import calendar
        from datetime import date, datetime, timedelta
        
        preview = kwargs.get('preview') == 'True'
        invite_token = kwargs.get('invite_token')
        
        # Country Validation
        if appointment_type.country_ids:
            user_country_id = False
            if request.env.user and request.env.user.id != request.env.ref('base.public_user').id:
                user_country_id = request.env.user.partner_id.country_id.id
            elif hasattr(request, 'geoip') and request.geoip.get('country_code'):
                country = request.env['res.country'].sudo().search([('code', '=', request.geoip.country_code)], limit=1)
                if country:
                    user_country_id = country.id
            
            if user_country_id not in appointment_type.country_ids.ids:
                return request.render('appointment.appointment_invalid_country', {
                    'appointment_type': appointment_type
                })
        
        # Determine the selected date
        date_str = kwargs.get('date')
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = date.today()
        else:
            selected_date = date.today()
            
        try:
            selected_party_size = int(kwargs.get('party_size', 1))
        except ValueError:
            selected_party_size = 1
            
        current_date = date.today()
        month, year = selected_date.month, selected_date.year
        
        # Calculate available days of week from backend configuration
        available_dows = set()
        
        emp_dows = set()
        if appointment_type.employee_schedule:
            staff_user_id = kwargs.get('staff_user_id')
            allowed_user_ids = appointment_type.sudo().user_ids.ids
            user_ids_to_check = allowed_user_ids
            if staff_user_id:
                try:
                    staff_user_id = int(staff_user_id)
                    if staff_user_id in allowed_user_ids:
                        user_ids_to_check = [staff_user_id]
                except ValueError:
                    pass
                    
            employees = request.env['hr.employee'].sudo().search([('user_id', 'in', user_ids_to_check)])
            calendars = employees.mapped('resource_calendar_id')
            attendances = calendars.mapped('attendance_ids')
            for att in attendances:
                emp_dows.add(str(att.dayofweek))
                
        custom_dows = set()
        if appointment_type.availability_ids:
            for avail in appointment_type.availability_ids:
                custom_dows.add(avail.day_of_week)
                
        if appointment_type.employee_schedule and appointment_type.availability_ids:
            available_dows = emp_dows.intersection(custom_dows)
        elif appointment_type.employee_schedule:
            available_dows = emp_dows
        elif appointment_type.availability_ids:
            available_dows = custom_dows
                
        # Get closing days securely
        closing_days = request.env['appointment.closing.day'].sudo().search([
            '|',
            ('appointment_type_ids', '=', False),
            ('appointment_type_ids', 'in', [appointment_type.id])
        ])
        closed_dates = set()
        for cd in closing_days:
            if cd.closing_type == 'appointments' and cd.appointment_type_ids and appointment_type.id not in cd.appointment_type_ids.ids:
                continue
            if cd.start_datetime and cd.end_datetime:
                start_d = cd.start_datetime.date()
                end_d = cd.end_datetime.date()
                delta = end_d - start_d
                for i in range(delta.days + 1):
                    closed_dates.add(start_d + timedelta(days=i))
                    
        # Add full-day employee leaves to closed_dates
        if appointment_type.employee_schedule:
            # We already computed 'employees' in the previous block if employee_schedule is True
            try:
                if employees:
                    import logging
                    _logger = logging.getLogger(__name__)
                    from datetime import datetime
                    # Only look at leaves roughly in the window we care about
                    month_start_dt = datetime(year, month, 1)
                    leaves = request.env['resource.calendar.leaves'].sudo().search([
                        ('resource_id', 'in', [False] + employees.mapped('resource_id').ids),
                        ('date_from', '<', str(current_date + timedelta(days=60))),
                        ('date_to', '>', str(month_start_dt - timedelta(days=15)))
                    ])
                    for lv in leaves:
                        # Find the employee this leave belongs to
                        emp = employees.filtered(lambda e: e.resource_id.id == lv.resource_id.id)
                        
                        is_full_day = False
                        if not emp:
                            # It's a global leave (e.g. public holiday) - affects everyone
                            if (lv.date_to - lv.date_from).total_seconds() >= 7 * 3600:
                                is_full_day = True
                        else:
                            # It's a specific employee leave
                            # Only block the entire calendar day if we are only looking at ONE employee
                            if len(employees) == 1 and emp.resource_calendar_id:
                                day_of_week = str(lv.date_from.weekday())
                                atts = emp.resource_calendar_id.attendance_ids.filtered(lambda a: str(a.dayofweek) == day_of_week)
                                if atts:
                                    work_hours = sum([a.hour_to - a.hour_from for a in atts])
                                    if (lv.date_to - lv.date_from).total_seconds() >= (work_hours - 1.0) * 3600:
                                        is_full_day = True
                                        
                        if is_full_day:
                            start_d = lv.date_from.date()
                            end_d = lv.date_to.date()
                            delta = end_d - start_d
                            for i in range(delta.days + 1):
                                closed_dates.add(start_d + timedelta(days=i))
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Error calculating closed dates from leaves: %s", str(e))
                
        cal = calendar.Calendar(firstweekday=6) # Sunday first
        month_days = cal.monthdatescalendar(year, month)
        
        max_date = current_date + timedelta(days=appointment_type.max_schedule_days or 15)
        
        month_grid = []
        for week in month_days:
            week_data = []
            for d in week:
                dow_str = str(d.weekday())
                is_available = dow_str in available_dows if (appointment_type.availability_ids or appointment_type.employee_schedule) else True
                is_past = d < current_date
                is_closed = d in closed_dates
                is_too_far = d > max_date
                
                week_data.append({
                    'date_str': d.strftime('%Y-%m-%d'),
                    'day': d.day,
                    'is_current_month': d.month == month,
                    'is_today': d == current_date,
                    'is_selected': d == selected_date,
                    'is_available': is_available and not is_past and not is_closed and not is_too_far,
                    'is_past': is_past or is_too_far,
                    'is_weekend': d.isoweekday() in [6, 7] # Sat or Sun
                })
            month_grid.append(week_data)
            
        max_date = current_date + timedelta(days=appointment_type.max_schedule_days or 15)
        
        # Generate time slots for the selected date
        slots = []
        if selected_date not in closed_dates and current_date <= selected_date <= max_date:
            selected_dow_str = str(selected_date.weekday())
            
            # Fetch existing bookings for the selected date to filter slots
            import pytz
            from datetime import datetime as dt, time as dt_time, timedelta as td
            tz = pytz.timezone(appointment_type.appointment_tz or 'UTC')
            
            selected_day_start_local = tz.localize(dt.combine(selected_date, dt_time.min))
            selected_day_end_local = tz.localize(dt.combine(selected_date, dt_time.max))
            start_utc = selected_day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
            end_utc = selected_day_end_local.astimezone(pytz.UTC).replace(tzinfo=None)
            
            search_start = start_utc - td(hours=appointment_type.appointment_duration)
            search_end = end_utc + td(hours=24)
            
            # 15-minute hold logic: only pending payments from the last 15 minutes block slots
            time_limit = (dt.utcnow() - td(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            
            domain = [
                ('start_datetime', '<=', search_end),
                ('end_datetime', '>=', search_start),
                '|',
                    ('state', 'in', ['confirmed', 'checked_in']),
                    '&', ('state', '=', 'pending_payment'), ('create_date', '>=', time_limit)
            ]
            existing_bookings = request.env['appointment.booking'].sudo().search(domain)
            
            # Fetch staff user if passed
            staff_user_id = kwargs.get('staff_user_id')
            if staff_user_id:
                try:
                    staff_user_id = int(staff_user_id)
                    if staff_user_id not in appointment_type.sudo().user_ids.ids:
                        staff_user_id = False
                except ValueError:
                    staff_user_id = False
            
            utc_now = dt.utcnow()
            
            day_avails = []
            employee_data = {}
            if appointment_type.employee_schedule:
                employees = request.env['hr.employee'].sudo().search([('user_id', 'in', appointment_type.user_ids.ids)])
                min_start_h, max_end_h = 24.0, 0.0
                
                # BATCH FETCH LEAVES
                all_resource_ids = employees.mapped('resource_id').ids
                all_leaves = request.env['resource.calendar.leaves'].sudo().search([
                    ('resource_id', 'in', all_resource_ids + [False]),
                    ('date_from', '<', end_utc),
                    ('date_to', '>', start_utc)
                ])
                
                # PRE-GROUP LEAVES
                global_leaves = all_leaves.filtered(lambda l: not l.resource_id)
                leaves_by_resource = {r_id: global_leaves for r_id in all_resource_ids}
                for l in all_leaves.filtered(lambda l: l.resource_id):
                    leaves_by_resource[l.resource_id.id] = leaves_by_resource.get(l.resource_id.id, global_leaves) | l
                
                for emp in employees:
                    emp_calendar = emp.resource_calendar_id
                    if not emp_calendar:
                        continue
                        
                    attendances = emp_calendar.attendance_ids.filtered(lambda a: str(a.dayofweek) == selected_dow_str)
                    if attendances:
                        min_start_h = min(min_start_h, min(attendances.mapped('hour_from')))
                        max_end_h = max(max_end_h, max(attendances.mapped('hour_to')))
                        
                    leaves = leaves_by_resource.get(emp.resource_id.id, global_leaves)
                    
                    if emp.user_id.id in employee_data:
                        employee_data[emp.user_id.id]['attendances'] |= attendances
                        employee_data[emp.user_id.id]['leaves'] |= leaves
                    else:
                        employee_data[emp.user_id.id] = {'attendances': attendances, 'leaves': leaves}
                    
                if min_start_h < 24.0:
                    day_avails = [type('Avail', (object,), {'start_time': min_start_h, 'end_time': max_end_h})]
            else:
                if appointment_type.availability_ids:
                    day_avails = appointment_type.availability_ids.filtered(lambda a: a.day_of_week == selected_dow_str)
                    
            if day_avails:
                for avail in day_avails:
                    start_h = int(avail.start_time)
                    start_m = int(round((avail.start_time - start_h) * 60))
                    end_h = int(avail.end_time)
                    end_m = int(round((avail.end_time - end_h) * 60))
                    
                    # Generate slots every 30 mins
                    current_h, current_m = start_h, start_m
                    while current_h < end_h or (current_h == end_h and current_m < end_m):
                        time_str = f"{current_h:02d}:{current_m:02d}"
                        ampm = "am" if current_h < 12 else "pm"
                        display_h = current_h if current_h <= 12 else current_h - 12
                        if display_h == 0: display_h = 12
                        display_str = f"{display_h}:{current_m:02d} {ampm}"
                        
                        # Check availability
                        local_slot_start = tz.localize(dt.combine(selected_date, dt_time(current_h, current_m)))
                        slot_start_utc = local_slot_start.astimezone(pytz.UTC).replace(tzinfo=None)
                        slot_end_utc = slot_start_utc + td(hours=appointment_type.appointment_duration)
                        
                        available_users_for_slot = []
                        if slot_start_utc <= utc_now:
                            is_available = False
                        else:
                            if appointment_type.booking_target == 'users':
                                users_to_check = appointment_type.sudo().user_ids
                                if staff_user_id:
                                    users_to_check = users_to_check.filtered(lambda u: u.id == staff_user_id)
                                    
                                for u in users_to_check:
                                    u_avail = True
                                    if appointment_type.employee_schedule:
                                        emp_data = employee_data.get(u.id)
                                        if not emp_data:
                                            u_avail = False
                                        else:
                                            local_start_float = current_h + current_m / 60.0
                                            local_end_float = local_start_float + appointment_type.appointment_duration
                                            
                                            working = False
                                            for att in emp_data['attendances']:
                                                if att.hour_from <= local_start_float + 0.001 and att.hour_to >= local_end_float - 0.001:
                                                    working = True
                                                    break
                                            if not working:
                                                u_avail = False
                                                
                                            if u_avail and emp_data['leaves']:
                                                for leave in emp_data['leaves']:
                                                    if leave.date_from < slot_end_utc and leave.date_to > slot_start_utc:
                                                        u_avail = False
                                                        break
                                                        
                                            if u_avail and appointment_type.availability_ids:
                                                custom_avails = appointment_type.availability_ids.filtered(lambda a: a.day_of_week == selected_dow_str)
                                                slot_custom_valid = False
                                                for cav in custom_avails:
                                                    if cav.start_time <= local_start_float + 0.001 and cav.end_time >= local_end_float - 0.001:
                                                        slot_custom_valid = True
                                                        break
                                                if not slot_custom_valid:
                                                    u_avail = False
                                                        
                                    if u_avail:
                                        # Check user overlapping bookings
                                        user_bookings = existing_bookings.filtered(lambda b: b.staff_user_id.id == u.id)
                                        overlapping_party_size = sum(b.party_size for b in user_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                                        
                                        user_cap = u.capacity if hasattr(u, 'capacity') else appointment_type.capacity
                                        if overlapping_party_size + selected_party_size > user_cap:
                                            if not appointment_type.group_booking:
                                                u_avail = False
                                            elif overlapping_party_size + selected_party_size > user_cap:
                                                u_avail = False
                                                
                                        if u_avail and hasattr(u, 'capacity') and selected_party_size > u.capacity:
                                            u_avail = False
                                                
                                    if u_avail:
                                        available_users_for_slot.append(u)
                                        
                                is_available = len(available_users_for_slot) > 0
                            else:
                                resources_to_check = appointment_type.sudo().resource_ids
                                if staff_user_id:
                                    resources_to_check = resources_to_check.filtered(lambda r: r.id == staff_user_id)
                                    
                                for r in resources_to_check:
                                    r_avail = True
                                    resource_bookings = existing_bookings.filtered(lambda b: r.id in b.resource_ids.ids)
                                    overlapping_party_size = sum(b.party_size for b in resource_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                                    
                                    avail_cap = 0
                                    if overlapping_party_size > 0 and not (getattr(r, 'shareable', False) or appointment_type.group_booking):
                                        r_avail = False
                                    else:
                                        avail_cap = r.capacity - overlapping_party_size
                                        
                                    linked_r = getattr(r, 'linked_resource_id', False)
                                    if r_avail and linked_r:
                                        linked_bookings = existing_bookings.filtered(lambda b: linked_r.id in b.resource_ids.ids)
                                        linked_overlap = sum(b.party_size for b in linked_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                                        if linked_overlap > 0 and not (getattr(linked_r, 'shareable', False) or appointment_type.group_booking):
                                            r_avail = False
                                        else:
                                            avail_cap += linked_r.capacity - linked_overlap
                                            
                                    if r_avail and selected_party_size > avail_cap:
                                        r_avail = False
                                        
                                    if r_avail:
                                        available_users_for_slot.append(r)
                                        
                                is_available = len(available_users_for_slot) > 0
                        
                        slots.append({
                            'time': display_str,
                            'val': time_str,
                            'available': is_available,
                            'available_users': [{'id': u.id, 'name': u.name, 'capacity': getattr(u, 'capacity', 1)} for u in available_users_for_slot]
                        })
                        
                        interval_mins = int(round(appointment_type.slot_interval * 60))
                        if interval_mins <= 0:
                            interval_mins = 30 # fallback
                            
                        current_m += interval_mins
                        while current_m >= 60:
                            current_m -= 60
                            current_h += 1
            else:
                # Default slots if no availability configured: 9am to 12pm, 2pm to 5pm
                default_times = []
                interval_mins = int(round(appointment_type.slot_interval * 60))
                if interval_mins <= 0: interval_mins = 60
                
                for period_start, period_end in [(9, 17)]:
                    cur_h, cur_m = period_start, 0
                    while cur_h < period_end or (cur_h == period_end and cur_m == 0):
                        ampm = "am" if cur_h < 12 else "pm"
                        display_h = cur_h if cur_h <= 12 else cur_h - 12
                        if display_h == 0: display_h = 12
                        display_str = f"{display_h}:{cur_m:02d} {ampm}"
                        time_str = f"{cur_h:02d}:{cur_m:02d}"
                        default_times.append((display_str, time_str, cur_h, cur_m))
                        
                        cur_m += interval_mins
                        while cur_m >= 60:
                            cur_m -= 60
                            cur_h += 1
                            
                for display_str, time_str, h, m in default_times:
                    local_slot_start = tz.localize(dt.combine(selected_date, dt_time(h, m)))
                    slot_start_utc = local_slot_start.astimezone(pytz.UTC).replace(tzinfo=None)
                    slot_end_utc = slot_start_utc + td(hours=appointment_type.appointment_duration)
                    
                    available_users_for_slot = []
                    
                    if appointment_type.booking_target == 'users':
                        users_to_check = appointment_type.sudo().user_ids
                        if kwargs.get('staff_user_id'):
                            try:
                                staff_user_id = int(kwargs.get('staff_user_id'))
                                users_to_check = users_to_check.filtered(lambda u: u.id == staff_user_id)
                            except ValueError:
                                pass
                                
                        for u in users_to_check:
                            user_bookings = existing_bookings.filtered(lambda b: b.staff_user_id.id == u.id)
                            overlapping_party_size = sum(b.party_size for b in user_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                            
                            u_avail = True
                            if overlapping_party_size + selected_party_size > (u.capacity if hasattr(u, 'capacity') else appointment_type.capacity):
                                if not appointment_type.group_booking:
                                    u_avail = False
                                elif overlapping_party_size + selected_party_size > (u.capacity if hasattr(u, 'capacity') else appointment_type.capacity):
                                    u_avail = False
                                    
                            if u_avail and hasattr(u, 'capacity') and selected_party_size > u.capacity:
                                u_avail = False
                                
                            if u_avail:
                                available_users_for_slot.append(u)
                                
                        is_available = len(available_users_for_slot) > 0
                    else:
                        resources_to_check = appointment_type.sudo().resource_ids
                        if kwargs.get('staff_user_id'):
                            try:
                                staff_user_id = int(kwargs.get('staff_user_id'))
                                resources_to_check = resources_to_check.filtered(lambda r: r.id == staff_user_id)
                            except ValueError:
                                pass
                                
                        for r in resources_to_check:
                            resource_bookings = existing_bookings.filtered(lambda b: r.id in b.resource_ids.ids)
                            overlapping_party_size = sum(b.party_size for b in resource_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                            
                            r_avail = True
                            avail_cap = 0
                            if overlapping_party_size > 0 and not (getattr(r, 'shareable', False) or appointment_type.group_booking):
                                r_avail = False
                            else:
                                avail_cap = r.capacity - overlapping_party_size
                                
                            linked_r = getattr(r, 'linked_resource_id', False)
                            if r_avail and linked_r:
                                linked_bookings = existing_bookings.filtered(lambda b: linked_r.id in b.resource_ids.ids)
                                linked_overlap = sum(b.party_size for b in linked_bookings if b.start_datetime < slot_end_utc and b.end_datetime > slot_start_utc)
                                if linked_overlap > 0 and not (getattr(linked_r, 'shareable', False) or appointment_type.group_booking):
                                    r_avail = False
                                else:
                                    avail_cap += linked_r.capacity - linked_overlap
                                    
                            if r_avail and selected_party_size > avail_cap:
                                r_avail = False
                                
                            if r_avail:
                                available_users_for_slot.append(r)
                                
                        is_available = len(available_users_for_slot) > 0

                    if slot_start_utc <= utc_now:
                        is_available = False
                            
                    slots.append({
                        'time': display_str,
                        'val': time_str,
                        'available': is_available,
                        'available_users': [{'id': u.id, 'name': u.name, 'capacity': getattr(u, 'capacity', 1)} for u in available_users_for_slot]
                    })
            
        # Available party sizes
        if appointment_type.booking_target == 'resources' and appointment_type.resource_ids:
            # If a specific resource is selected, use its capacity. Otherwise use the max of all resources.
            requested_id = kwargs.get('staff_user_id')
            if requested_id:
                try:
                    requested_id = int(requested_id)
                    res = appointment_type.resource_ids.filtered(lambda r: r.id == requested_id)
                    max_cap = res.capacity if res else max(appointment_type.resource_ids.mapped('capacity'))
                except ValueError:
                    max_cap = max(appointment_type.resource_ids.mapped('capacity'))
            else:
                max_cap = max(appointment_type.resource_ids.mapped('capacity'))
            party_sizes = list(range(1, (max_cap or 1) + 1))
        else:
            party_sizes = list(range(1, (appointment_type.capacity or 1) + 1))
        
        # Check for existing booking
        existing_booking = False
        if request.env.user and request.env.user.id != request.env.ref('base.public_user').id:
            existing_booking = request.env['appointment.booking'].sudo().search([
                ('appointment_type_id', '=', appointment_type.id),
                ('partner_id', '=', request.env.user.partner_id.id),
                ('start_datetime', '>=', datetime.now())
            ], order='start_datetime asc', limit=1)
            
        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year
            
        if month == 1:
            prev_month = 12
            prev_year = year - 1
        else:
            prev_month = month - 1
            prev_year = year
            
        next_month_date = date(next_year, next_month, 1).strftime('%Y-%m-%d')
        prev_month_date = date(prev_year, prev_month, 1).strftime('%Y-%m-%d')
        
        values = {
            'appointment_type': appointment_type,
            'main_object': appointment_type,
            'preview': preview,
            'state': kwargs.get('state'),
            'month_grid': month_grid,
            'slots': slots,
            'party_sizes': party_sizes,
            'month_name': calendar.month_name[month],
            'year': year,
            'selected_date': selected_date.strftime('%Y-%m-%d'),
            'selected_party_size': selected_party_size,
            'prev_month_date': prev_month_date,
            'next_month_date': next_month_date,
            'existing_booking': existing_booking,
            'invite_token': invite_token,
            'staff_user_id': kwargs.get('staff_user_id'),
            'users_possible': (
                appointment_type.sudo().user_ids.filtered(lambda u: getattr(u, 'capacity', 1) >= selected_party_size)
                if appointment_type.booking_target == 'users'
                else appointment_type.sudo().resource_ids.filtered(lambda r: r.capacity >= selected_party_size or (getattr(r, 'linked_resource_id', False) and r.capacity + r.linked_resource_id.capacity >= selected_party_size))
            ),
            'assign_method': appointment_type.assign_method,
            'schedule_based_on': appointment_type.schedule_based_on,
            'has_multiple_targets': appointment_type.has_multiple_targets,
        }
        
        return request.render('appointment.appointment_preview', values)

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/info'], type='http', auth='public', website=True, methods=['POST'])
    def appointment_info(self, appointment_type, **kwargs):
        from datetime import datetime
        
        date_str = kwargs.get('date')
        time_str = kwargs.get('time')
        party_size = kwargs.get('party_size', 1)
        
        if not date_str or not time_str:
            return request.redirect(f'/appointment/{appointment_type.id}?error=missing_datetime')
            
        try:
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return request.redirect(f'/appointment/{appointment_type.id}?error=invalid_datetime')
            
        values = {
            'appointment_type': appointment_type,
            'selected_date': date_str,
            'selected_time': time_str,
            'party_size': party_size,
            'start_dt': start_dt,
            'user': request.env.user if request.env.user.id != request.env.ref('base.public_user').id else None,
            'invite_token': kwargs.get('invite_token'),
        }
        return request.render('appointment.appointment_info', values)

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/submit'], type='http', auth='public', website=True, methods=['POST'])
    def appointment_submit(self, appointment_type, **kwargs):
        from datetime import datetime, timedelta
        
        date_str = kwargs.get('date')
        time_str = kwargs.get('time')
        name = kwargs.get('name')
        email = kwargs.get('email')
        phone = kwargs.get('phone')
        party_size = kwargs.get('party_size', 1)
        
        if not date_str or not time_str or not name or not email:
            return request.redirect(f'/appointment/{appointment_type.id}?error=missing_fields')
            
        try:
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            import pytz
            tz = pytz.timezone(appointment_type.appointment_tz or 'UTC')
            start_dt_local = tz.localize(start_dt)
            start_dt_utc = start_dt_local.astimezone(pytz.UTC).replace(tzinfo=None)
            end_dt_utc = start_dt_utc + timedelta(hours=appointment_type.appointment_duration)
        except ValueError:
            return request.redirect(f'/appointment/{appointment_type.id}?error=invalid_datetime')
            
        # Get or create partner
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('email', '=', email)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'email': email,
                'phone': phone,
            })
            
        # Extract custom questions
        answers_dict = {}
        for key, val in kwargs.items():
            if key.startswith('question_') and val:
                try:
                    q_id_str = key.replace('question_', '').split('_')[0]
                    q_id = int(q_id_str)
                    if q_id not in answers_dict:
                        answers_dict[q_id] = []
                    answers_dict[q_id].append(str(val))
                except ValueError:
                    continue
                    
        answer_vals_list = []
        for q_id, vals in answers_dict.items():
            q = request.env['appointment.question'].sudo().browse(q_id)
            if q.exists():
                answer_vals_list.append((0, 0, {
                    'question_id': q.id,
                    'value_text': ', '.join(vals)
                }))
            
        booking_vals = {
            'appointment_type_id': appointment_type.id,
            'start_datetime': start_dt_utc,
            'end_datetime': end_dt_utc,
            'duration': appointment_type.appointment_duration,
            'state': 'confirmed',
            'partner_id': partner.id,
            'party_size': int(party_size),
            'answer_ids': answer_vals_list,
            'name': f"{appointment_type.name} - {start_dt.strftime('%b %d, %Y %H:%M')}"
        }
        
        if appointment_type.booking_target == 'resources' and appointment_type.resource_ids:
            requested_target_id = kwargs.get('staff_user_id')
            if requested_target_id:
                try:
                    requested_target_id = int(requested_target_id)
                except ValueError:
                    requested_target_id = False
                    
            assigned_resources = request.env['appointment.resource'].sudo()
            needed_capacity = int(party_size)
            
            resources_to_check = appointment_type.resource_ids
            if requested_target_id:
                requested_resource = resources_to_check.filtered(lambda r: r.id == requested_target_id)
                if requested_resource:
                    resources_to_check = requested_resource
                    
            # BATCH QUERY BOOKINGS
            time_limit = (datetime.utcnow() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            all_r_ids = resources_to_check.ids
            linked_ids = [r.linked_resource_id.id for r in resources_to_check if getattr(r, 'linked_resource_id', False)]
            all_r_ids.extend(linked_ids)
            
            all_bookings = request.env['appointment.booking'].sudo().search([
                ('resource_ids', 'in', all_r_ids),
                ('start_datetime', '<', end_dt_utc),
                ('end_datetime', '>', start_dt_utc),
                '|',
                    ('state', 'in', ['confirmed', 'checked_in']),
                    '&', ('state', '=', 'pending_payment'), ('create_date', '>=', time_limit)
            ])
            
            bookings_by_resource = {}
            for b in all_bookings:
                for r_id in b.resource_ids.ids:
                    bookings_by_resource.setdefault(r_id, request.env['appointment.booking'].sudo())
                    bookings_by_resource[r_id] |= b
                    
            for resource in resources_to_check:
                resource_bookings = bookings_by_resource.get(resource.id, request.env['appointment.booking'].sudo())
                r_avail = True
                overlapping_party_size = sum(b.party_size for b in resource_bookings)
                
                avail_cap = 0
                if overlapping_party_size > 0 and not (getattr(resource, 'shareable', False) or appointment_type.group_booking):
                    r_avail = False
                else:
                    avail_cap = resource.capacity - overlapping_party_size
                    
                linked_r = getattr(resource, 'linked_resource_id', False)
                if r_avail and linked_r:
                    linked_bookings = bookings_by_resource.get(linked_r.id, request.env['appointment.booking'].sudo())
                    linked_overlap = sum(b.party_size for b in linked_bookings)
                    if linked_overlap > 0 and not (getattr(linked_r, 'shareable', False) or appointment_type.group_booking):
                        r_avail = False
                    else:
                        avail_cap += linked_r.capacity - linked_overlap
                        
                if r_avail and int(party_size) > avail_cap:
                    r_avail = False
                
                if r_avail:
                    assigned_resources |= resource
                    if linked_r:
                        assigned_resources |= linked_r
                    break
            if assigned_resources:
                booking_vals['resource_ids'] = [(6, 0, assigned_resources.ids)]
            else:
                return request.redirect(f'/appointment/{appointment_type.id}?error=no_resource_available')
        elif appointment_type.booking_target == 'users' and appointment_type.sudo().user_ids:
            requested_staff_id = kwargs.get('staff_user_id')
            if requested_staff_id:
                try:
                    requested_staff_id = int(requested_staff_id)
                except ValueError:
                    requested_staff_id = False
                    
            time_limit = (datetime.utcnow() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            existing_user_bookings = request.env['appointment.booking'].sudo().search([
                ('appointment_type_id.booking_target', '=', 'users'),
                ('start_datetime', '<', end_dt_utc),
                ('end_datetime', '>', start_dt_utc),
                '|',
                    ('state', 'in', ['confirmed', 'checked_in']),
                    '&', ('state', '=', 'pending_payment'), ('create_date', '>=', time_limit)
            ])
            
            from datetime import time as dt_time
            if appointment_type.employee_schedule:
                local_start_float = start_dt.hour + start_dt.minute / 60.0
                local_end_float = local_start_float + appointment_type.appointment_duration
            
            # BATCH QUERY EMPLOYEES AND LEAVES
            users_to_check = appointment_type.sudo().user_ids
            employees = request.env['hr.employee'].sudo().search([('user_id', 'in', users_to_check.ids)])
            emp_by_user = {e.user_id.id: e for e in employees}
            
            all_cal_ids = employees.mapped('resource_calendar_id').ids
            all_resource_ids = employees.mapped('resource_id').ids
            
            all_leaves = request.env['resource.calendar.leaves'].sudo().search([
                ('resource_id', 'in', all_resource_ids + [False]),
                ('calendar_id', 'in', all_cal_ids),
                ('date_from', '<', end_dt_utc),
                ('date_to', '>', start_dt_utc)
            ])
            
            available_users = []
            for u in users_to_check:
                u_avail = True
                if appointment_type.employee_schedule:
                    emp = emp_by_user.get(u.id)
                    if not emp or not emp.resource_calendar_id:
                        u_avail = False
                    else:
                        cal = emp.resource_calendar_id
                        atts = cal.attendance_ids.filtered(lambda a: str(a.dayofweek) == str(start_dt.weekday()))
                        working = False
                        for att in atts:
                            if att.hour_from <= local_start_float + 0.001 and att.hour_to >= local_end_float - 0.001:
                                working = True
                                break
                        if not working:
                            u_avail = False
                        else:
                            leaves = all_leaves.filtered(lambda l: l.calendar_id.id == cal.id and (not l.resource_id or l.resource_id.id == emp.resource_id.id))
                            if leaves:
                                u_avail = False
                                
                if u_avail:
                    user_bookings = existing_user_bookings.filtered(lambda b: b.staff_user_id.id == u.id)
                    overlapping_party_size = sum(b.party_size for b in user_bookings)
                    
                    user_cap = u.capacity if hasattr(u, 'capacity') else appointment_type.capacity
                    if overlapping_party_size + int(party_size) > user_cap:
                        if not appointment_type.group_booking:
                            u_avail = False
                        elif overlapping_party_size + int(party_size) > user_cap:
                            u_avail = False
                            
                    if u_avail and hasattr(u, 'capacity') and int(party_size) > u.capacity:
                        u_avail = False
                        
                if u_avail:
                    available_users.append(u.id)
                    
            if not available_users:
                return request.redirect(f'/appointment/{appointment_type.id}?error=no_user_available')
                
            if requested_staff_id and appointment_type.assign_method == 'customer':
                if requested_staff_id in available_users:
                    booking_vals['staff_user_id'] = requested_staff_id
                else:
                    return request.redirect(f'/appointment/{appointment_type.id}?error=user_unavailable')
            else:
                import random
                booking_vals['staff_user_id'] = random.choice(available_users)
                
        if appointment_type.has_payment_step and appointment_type.product_id:
            booking_vals['state'] = 'pending_payment'
            
        booking = request.env['appointment.booking'].sudo().create(booking_vals)
        
        # Create Sales Order for Upfront Payment
        if appointment_type.has_payment_step and appointment_type.product_id:
            SaleOrder = request.env['sale.order'].sudo()
            so = SaleOrder.create({
                'partner_id': partner.id,
                'state': 'draft',
                'order_line': [(0, 0, {
                    'product_id': appointment_type.product_id.id,
                    'name': f"Booking Fees: {appointment_type.name} - {booking.start_datetime.strftime('%b %d, %Y %H:%M')}",
                    'product_uom_qty': 1,
                    'price_unit': appointment_type.product_id.lst_price,
                })]
            })
            booking.sale_order_id = so.id
            
            # Redirect to the custom Appointment Payment page (which embeds payment.form)
            return request.redirect(f'/appointment/{booking.id}/payment?token={booking.access_token}')
        
        # Create Opportunity if configured
        if appointment_type.create_opportunity:
            try:
                request.env['crm.lead'].sudo().create({
                    'name': f"{appointment_type.name} - {partner.name}",
                    'partner_id': partner.id,
                    'email_from': partner.email,
                    'phone': partner.phone,
                    'type': 'opportunity',
                    'description': f"Created from Appointment Booking: {appointment_type.name}\nStart Date: {booking.start_datetime}",
                    'user_id': booking.staff_user_id.id if booking.staff_user_id else False,
                })
            except Exception:
                pass
        
        invite_token = kwargs.get('invite_token')
        if invite_token:
            invite = request.env['appointment.invite'].sudo().search([('access_token', '=', invite_token)], limit=1)
            if invite:
                invite.appointment_count += 1
                
        # Trigger confirmation email only if not pending payment
        if booking.state != 'pending_payment':
            template = request.env.ref('appointment.email_template_booking_confirmation', raise_if_not_found=False)
            if template:
                template.sudo().send_mail(booking.id, force_send=False)
        
        values = {
            'appointment_type': appointment_type,
            'booking': booking,
            'start_dt': start_dt,
            'user': request.env.user if request.env.user.id != request.env.ref('base.public_user').id else None,
            'partner_name': partner.name,
            'partner_email': partner.email,
            'partner_phone': partner.phone,
            'party_size': booking.party_size,
            'guest_details': booking.calendar_contact_details
        }
        
        return request.render('appointment.appointment_confirmation', values)

    @http.route(['/appointment/<model("appointment.booking"):booking>/payment'], type='http', auth='public', website=True)
    def appointment_payment(self, booking, **kwargs):
        token = kwargs.get('token')
        if not token or booking.access_token != token:
            return request.redirect('/?error=invalid_token')
            
        if booking.state != 'pending_payment' or not booking.sale_order_id:
            return request.redirect(f'/appointment/manage/{booking.id}?token={booking.access_token}')
            
        so = request.env['sale.order'].sudo().browse(booking.sale_order_id.id)
        
        # Build payment context for payment.form
        amount = so.amount_total
        currency = so.currency_id
        partner_sudo = so.partner_id
        company_id = so.company_id.id
        
        availability_report = {}
        providers_sudo = request.env['payment.provider'].sudo()._find_available_providers(
            company_id,
            partner_sudo.id,
            amount,
            currency_id=currency.id,
            report=availability_report,
            sale_order_id=so.id
        )
        payment_methods_sudo = providers_sudo._find_available_payment_methods(
            partner_sudo.id,
            currency_id=currency.id,
            report=availability_report,
        )._deduplicate_by_code(report=availability_report)
        tokens_sudo = providers_sudo._find_available_tokens(partner_sudo.id)
        
        # Build show_tokenize_input_mapping for payment.form
        show_tokenize_input_mapping = {
            p.id: p.allow_tokenization and not p._is_tokenization_required(sale_order_id=so.id)
            for p in providers_sudo
        }
        
        # Get checkout configuration
        # pyrefly: ignore [missing-import]
        from odoo.addons.payment.controllers.portal import PaymentPortal
        payment_portal = PaymentPortal()
        
        # Build kwargs expected by payment.form
        payment_context = {
            'booking': booking,
            'amount': amount,
            'currency': currency,
            'partner_id': partner_sudo.id,
            'providers_sudo': providers_sudo,
            'payment_methods_sudo': payment_methods_sudo,
            'tokens_sudo': tokens_sudo,
            'transaction_route': so.get_portal_url(suffix='/transaction'),
            'landing_route': f'/appointment/manage/{booking.id}?token={booking.access_token}',
            'reference_prefix': so.name,
            'access_token': so._portal_ensure_token(),
            
            # Additional required kwargs
            'mode': 'payment',
            'allow_token_selection': True,
            'allow_token_deletion': False,
            'default_token_id': None,
            'show_tokenize_input_mapping': show_tokenize_input_mapping,
            'display_submit_button': True,
            'submit_button_label': 'Pay',
            'assign_token_route': '/payment/assign_token',
        }
        
        return request.render('appointment.appointment_payment', payment_context)

    @http.route(['/appointment/manage/<model("appointment.booking"):booking>'], type='http', auth='public', website=True)
    def appointment_manage(self, booking, **kwargs):
        token = kwargs.get('token')
        if not token or booking.access_token != token:
            return request.redirect('/?error=invalid_token')
            
        import pytz
        tz = pytz.timezone(booking.appointment_type_id.appointment_tz or 'UTC')
        start_dt = booking.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).replace(tzinfo=None)
        
        values = {
            'appointment_type': booking.appointment_type_id,
            'booking': booking,
            'start_dt': start_dt,
            'user': request.env.user if request.env.user.id != request.env.ref('base.public_user').id else None,
            'partner_name': booking.partner_id.name if booking.partner_id else booking.guest_details,
            'partner_email': booking.partner_id.email if booking.partner_id else '',
            'partner_phone': booking.partner_id.phone if booking.partner_id else '',
        }
        return request.render('appointment.appointment_confirmation', values)

    @http.route(['/appointment/cancel/<model("appointment.booking"):booking>'], type='http', auth='public', website=True)
    def appointment_cancel(self, booking, **kwargs):
        token = kwargs.get('token')
        if not token or booking.access_token != token:
            return request.redirect('/?error=invalid_token')
            
        from datetime import datetime, timedelta
        import pytz
        
        tz = pytz.timezone(booking.appointment_type_id.appointment_tz or 'UTC')
        now_utc = datetime.now()
        
        # Check cancellation policy
        min_hours = booking.appointment_type_id.min_cancellation_hours or 0.0
        deadline_utc = booking.start_datetime - timedelta(hours=min_hours)
        
        if now_utc > deadline_utc:
            # Too late to cancel
            return request.redirect(f'/appointment/{booking.appointment_type_id.id}?error=cancel_too_late')
            
        booking.sudo().write({'state': 'cancelled'})
        
        # Send cancellation email if configured
        if booking.appointment_type_id.cancel_template_id:
            booking.appointment_type_id.cancel_template_id.sudo().send_mail(booking.id, force_send=True)
        
        # Render a simple cancellation success page (or redirect to type with success message)
        return request.redirect(f'/appointment/{booking.appointment_type_id.id}?state=cancel-success')
