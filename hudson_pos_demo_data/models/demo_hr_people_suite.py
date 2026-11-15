# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - HR people demo data (Employees, Contracts, Skills, Time Off, Attendances).

Idempotent: every record created here is bound to an xmlid ``hudson_pos_demo_data.rc_hrp_*``.
Reuses the employees of ``demo_hr_suite`` by name (Suresh Kumar, Rahul Nair, Ananya Sharma ...).

  * Employees  - 12 more staff (outlet manager, accountant, sous chef, cooks, barista, servers, cashier,
                 riders, kitchen helper) with departments, jobs, managers/coaches, work locations, birthdays
  * Contracts  - hr.version per employee: monthly INR wage (hourly for part-time), India payroll structure
                 type, employee type (regular / probation / part-time / seasonal), start/end/trial dates
  * Skills     - Kitchen Skills, Languages (adds Malayalam/Tamil), Certifications (FSSAI, First Aid, Fire Safety)
  * Time Off   - Kerala leave types, 2026 allocations, ~20 requests in every state, Kerala public holidays
  * Attendance - last 14 working days for every employee (late arrivals, overtime, one auto check-out)
"""
import logging
import random
from datetime import date, datetime, time, timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
IST_OFFSET = timedelta(hours=5, minutes=30)
YEAR = 2026
CTX = {'tracking_disable': True, 'mail_notrack': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_activity_automation_skip': True, 'no_mail_to_attendees': True, 'mail_auto_subscribe_no_notify': True}


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    if not _ref(env, xid):
        env['ir.model.data'].sudo().create({
            'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True})
    return record


def _get_or_create(env, xid, model, vals, search_domain=None):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    if search_domain:
        found = env[model].sudo().with_context(active_test=False).search(search_domain, limit=1)
        if found:
            return _bind(env, xid, found)
    return _bind(env, xid, env[model].sudo().create(vals))


def _utc(day, hour_float):
    """IST wall-clock (date + float hours) -> naive UTC datetime."""
    h = int(hour_float)
    m = int(round((hour_float - h) * 60))
    return datetime.combine(day, time(0, 0)) + timedelta(hours=h, minutes=m) - IST_OFFSET


def _emp(env, name):
    return env['hr.employee'].sudo().with_context(active_test=False).search([('name', '=', name)], limit=1)


# --------------------------------------------------------------------------- master data
DEPARTMENTS = [  # xid, name (reuses demo_hr_suite names), manager name
    ('rc_hrp_dept_kitchen', 'Kitchen & Culinary', 'Rahul Nair'),
    ('rc_hrp_dept_service', 'Service & Hospitality', 'Thomas Mathew'),
    ('rc_hrp_dept_bar', 'Bar & Cafe', 'Priya Menon'),
    ('rc_hrp_dept_delivery', 'Logistics & Delivery', 'Arun Varma'),
    ('rc_hrp_dept_management', 'Administration & Management', 'Suresh Kumar'),
    ('rc_hrp_dept_accounts', 'Accounts', 'Lakshmi Iyer'),
]

# shift calendars (IST): name, [(hour_from, hour_to)], Mon-Sat
CALENDARS = {
    'morning': ('rc_hrp_cal_morning', 'Restaurant Morning Shift (Mon-Sat 07:00-15:00)', [(7.0, 11.0), (11.5, 15.0)]),
    'evening': ('rc_hrp_cal_evening', 'Restaurant Evening Shift (Mon-Sat 15:00-23:00)', [(15.0, 19.0), (19.5, 23.0)]),
    'office': ('rc_hrp_cal_office', 'Office Hours (Mon-Sat 09:30-18:00)', [(9.5, 13.0), (14.0, 18.0)]),
    'parttime': ('rc_hrp_cal_parttime', 'Part-time Evenings (Mon-Sat 18:00-22:00)', [(18.0, 22.0)]),
}

# new employees: xid, name, job, dept xid, manager, coach, location, gender, birthday, mobile
NEW_EMPLOYEES = [
    ('rc_hrp_emp_thomas', 'Thomas Mathew', 'Outlet Manager', 'rc_hrp_dept_service', 'Suresh Kumar', None, 'outlet', 'male', '1986-03-12', '+91 98470 11201'),
    ('rc_hrp_emp_lakshmi', 'Lakshmi Iyer', 'Accountant', 'rc_hrp_dept_accounts', 'Suresh Kumar', None, 'outlet', 'female', '1990-07-22', '+91 98470 11202'),
    ('rc_hrp_emp_deepa', 'Deepa Krishnan', 'Sous Chef - Central Kitchen', 'rc_hrp_dept_kitchen', 'Rahul Nair', 'Rahul Nair', 'kitchen', 'female', '1991-11-30', '+91 98470 11203'),
    ('rc_hrp_emp_manoj', 'Manoj Pillai', 'Tandoor Cook', 'rc_hrp_dept_kitchen', 'Rahul Nair', 'Ananya Sharma', 'outlet', 'male', '1993-01-18', '+91 98470 11204'),
    ('rc_hrp_emp_fathima', 'Fathima Rasheed', 'Pastry Cook', 'rc_hrp_dept_kitchen', 'Deepa Krishnan', 'Deepa Krishnan', 'kitchen', 'female', '1997-05-09', '+91 98470 11205'),
    ('rc_hrp_emp_ajay', 'Ajay Menon', 'South Indian Cook', 'rc_hrp_dept_kitchen', 'Rahul Nair', 'Vishnu Kumar', 'outlet', 'male', '1995-08-27', '+91 98470 11206'),
    ('rc_hrp_emp_sabu', 'Sabu Thomas', 'Kitchen Helper', 'rc_hrp_dept_kitchen', 'Deepa Krishnan', None, 'kitchen', 'male', '1988-12-02', '+91 98470 11207'),
    ('rc_hrp_emp_anjali', 'Anjali Das', 'Barista (Part-time)', 'rc_hrp_dept_bar', 'Priya Menon', 'Priya Menon', 'outlet', 'female', '2001-02-14', '+91 98470 11208'),
    ('rc_hrp_emp_nikhil', 'Nikhil Raj', 'Server', 'rc_hrp_dept_service', 'Mohammed Bilal', 'Mohammed Bilal', 'outlet', 'male', '1999-06-03', '+91 98470 11209'),
    ('rc_hrp_emp_reshma', 'Reshma Babu', 'Server', 'rc_hrp_dept_service', 'Mohammed Bilal', 'Mohammed Bilal', 'outlet', 'female', '2000-09-19', '+91 98470 11210'),
    ('rc_hrp_emp_gokul', 'Gokul Krishna', 'Cashier (Seasonal)', 'rc_hrp_dept_service', 'Thomas Mathew', 'Sneha Pillai', 'outlet', 'male', '2002-04-25', '+91 98470 11211'),
    ('rc_hrp_emp_faisal', 'Faisal Ahmed', 'Delivery Rider', 'rc_hrp_dept_delivery', 'Arun Varma', 'Arun Varma', 'outlet', 'male', '1998-10-11', '+91 98470 11212'),
]

# contract per employee: name -> (employee type key, structure key, monthly wage, hourly, start, end, trial_end_offset_days, shift)
EXISTING_JOBS = {'Suresh Kumar': 'Restaurant General Manager'}
CONTRACTS = {
    'Suresh Kumar': ('regular', 'employee', 85000, 0, '2019-06-01', None, None, 'office'),
    'Thomas Mathew': ('regular', 'employee', 55000, 0, '2021-02-01', None, None, 'office'),
    'Lakshmi Iyer': ('regular', 'employee', 42000, 0, '2022-04-01', None, None, 'office'),
    'Rahul Nair': ('regular', 'employee', 75000, 0, '2018-09-01', None, None, 'morning'),
    'Ananya Sharma': ('regular', 'worker', 48000, 0, '2020-01-15', None, None, 'evening'),
    'Deepa Krishnan': ('regular', 'worker', 45000, 0, '2022-08-01', None, None, 'morning'),
    'Vishnu Kumar': ('regular', 'worker', 26000, 0, '2021-11-01', None, None, 'morning'),
    'Manoj Pillai': ('regular', 'worker', 28000, 0, '2023-03-01', None, None, 'evening'),
    'Fathima Rasheed': ('regular', 'worker', 27000, 0, '2024-06-10', None, None, 'morning'),
    'Ajay Menon': ('regular', 'worker', 26000, 0, '2023-09-01', None, None, 'morning'),
    'Sabu Thomas': ('regular', 'worker', 16000, 0, '2020-07-01', None, None, 'evening'),
    'Priya Menon': ('regular', 'worker', 32000, 0, '2021-05-01', None, None, 'morning'),
    'Anjali Das': ('parttime', 'worker', 16640, 160, '2025-12-01', None, None, 'parttime'),
    'Mohammed Bilal': ('regular', 'worker', 30000, 0, '2020-03-01', None, None, 'evening'),
    'Sneha Pillai': ('regular', 'worker', 22000, 0, '2022-01-10', None, None, 'morning'),
    'Nikhil Raj': ('regular', 'worker', 19000, 0, '2024-02-01', None, None, 'evening'),
    'Reshma Babu': ('probation', 'worker', 18000, 0, None, None, 10, 'morning'),       # joined ~3 months ago, probation ends in 10 days
    'Gokul Krishna': ('seasonal', 'worker', 17000, 0, '2026-10-01', '2027-01-15', None, 'morning'),
    'Arun Varma': ('regular', 'worker', 21000, 0, '2021-08-01', None, None, 'evening'),
    'Kevin Joseph': ('regular', 'worker', 23000, 0, '2022-10-01', None, None, 'morning'),
    'Faisal Ahmed': ('probation', 'worker', 18500, 0, None, None, 40, 'evening'),       # joined ~7 weeks ago
}

SKILL_TYPES = {
    'kitchen': ('rc_hrp_sktype_kitchen', 'Kitchen Skills', False,
                [('Trainee', 25), ('Competent', 50), ('Skilled', 75), ('Master', 100)],
                ['Tandoor', 'Grill & Barbecue', 'Pastry & Baking', 'South Indian / Kerala Cuisine', 'Indo-Chinese', 'Barista & Latte Art']),
    'cert': ('rc_hrp_sktype_cert', 'Certifications', True,
             [('Certified', 100)],
             ['FSSAI Food Safety Supervisor (FoSTaC)', 'First Aid', 'Fire Safety Warden']),
}
EXTRA_LANGUAGES = ['Malayalam', 'Tamil']  # added to the existing "Languages" skill type (English & Hindi exist)

# employee -> [(type key, skill, level)]  type key: kitchen | cert | lang
SKILLS = {
    'Rahul Nair': [('kitchen', 'South Indian / Kerala Cuisine', 'Master'), ('kitchen', 'Grill & Barbecue', 'Skilled'), ('cert', 'FSSAI Food Safety Supervisor (FoSTaC)', 'Certified'), ('lang', 'Malayalam', 'C2'), ('lang', 'English', 'C1')],
    'Ananya Sharma': [('kitchen', 'Indo-Chinese', 'Skilled'), ('kitchen', 'Pastry & Baking', 'Competent'), ('cert', 'FSSAI Food Safety Supervisor (FoSTaC)', 'Certified'), ('lang', 'Hindi', 'C2'), ('lang', 'English', 'C1')],
    'Deepa Krishnan': [('kitchen', 'Pastry & Baking', 'Master'), ('kitchen', 'South Indian / Kerala Cuisine', 'Skilled'), ('cert', 'FSSAI Food Safety Supervisor (FoSTaC)', 'Certified'), ('lang', 'Malayalam', 'C2'), ('lang', 'Tamil', 'B2')],
    'Vishnu Kumar': [('kitchen', 'South Indian / Kerala Cuisine', 'Skilled'), ('kitchen', 'Grill & Barbecue', 'Competent'), ('lang', 'Malayalam', 'C2')],
    'Manoj Pillai': [('kitchen', 'Tandoor', 'Master'), ('kitchen', 'Grill & Barbecue', 'Skilled'), ('lang', 'Malayalam', 'C2'), ('lang', 'Hindi', 'B1')],
    'Fathima Rasheed': [('kitchen', 'Pastry & Baking', 'Skilled'), ('cert', 'First Aid', 'Certified'), ('lang', 'Malayalam', 'C2'), ('lang', 'English', 'B2')],
    'Ajay Menon': [('kitchen', 'South Indian / Kerala Cuisine', 'Skilled'), ('kitchen', 'Tandoor', 'Trainee'), ('lang', 'Malayalam', 'C2'), ('lang', 'Tamil', 'B1')],
    'Sabu Thomas': [('kitchen', 'South Indian / Kerala Cuisine', 'Trainee'), ('cert', 'FSSAI Food Safety Supervisor (FoSTaC)', 'Certified'), ('lang', 'Malayalam', 'C2')],
    'Priya Menon': [('kitchen', 'Barista & Latte Art', 'Master'), ('cert', 'First Aid', 'Certified'), ('lang', 'English', 'C1'), ('lang', 'Malayalam', 'C2')],
    'Anjali Das': [('kitchen', 'Barista & Latte Art', 'Competent'), ('lang', 'English', 'B2'), ('lang', 'Malayalam', 'C2')],
    'Mohammed Bilal': [('cert', 'Fire Safety Warden', 'Certified'), ('lang', 'English', 'C1'), ('lang', 'Hindi', 'B2'), ('lang', 'Malayalam', 'C2')],
    'Nikhil Raj': [('lang', 'English', 'B2'), ('lang', 'Malayalam', 'C2'), ('lang', 'Tamil', 'A2')],
    'Reshma Babu': [('lang', 'English', 'B1'), ('lang', 'Malayalam', 'C2')],
    'Sneha Pillai': [('cert', 'First Aid', 'Certified'), ('lang', 'English', 'C1'), ('lang', 'Malayalam', 'C2')],
    'Gokul Krishna': [('lang', 'English', 'B1'), ('lang', 'Malayalam', 'C2')],
    'Thomas Mathew': [('cert', 'Fire Safety Warden', 'Certified'), ('cert', 'First Aid', 'Certified'), ('lang', 'English', 'C2'), ('lang', 'Hindi', 'B2')],
    'Arun Varma': [('cert', 'First Aid', 'Certified'), ('lang', 'Malayalam', 'C2'), ('lang', 'Hindi', 'A2')],
    'Faisal Ahmed': [('lang', 'Malayalam', 'C2'), ('lang', 'Hindi', 'B1')],
    'Lakshmi Iyer': [('lang', 'English', 'C2'), ('lang', 'Tamil', 'C2'), ('lang', 'Malayalam', 'B2')],
    'Suresh Kumar': [('cert', 'FSSAI Food Safety Supervisor (FoSTaC)', 'Certified'), ('lang', 'English', 'C2'), ('lang', 'Malayalam', 'C2'), ('lang', 'Hindi', 'B2')],
    'Kevin Joseph': [('cert', 'First Aid', 'Certified'), ('lang', 'Malayalam', 'C2'), ('lang', 'English', 'B1')],
}
# certifications with validity: (employee, skill) -> (valid_from offset days, valid_to offset days)
CERT_VALIDITY = {
    ('Rahul Nair', 'FSSAI Food Safety Supervisor (FoSTaC)'): (-600, 130),
    ('Ananya Sharma', 'FSSAI Food Safety Supervisor (FoSTaC)'): (-700, 25),   # expires soon
    ('Sabu Thomas', 'FSSAI Food Safety Supervisor (FoSTaC)'): (-760, -30),    # expired -> renewal needed
    ('Deepa Krishnan', 'FSSAI Food Safety Supervisor (FoSTaC)'): (-200, 530),
}

# leave types: xid, name, code, requires allocation, validation, unit, unpaid, allocation days, color, support document
LEAVE_TYPES = [
    ('rc_hrp_lt_casual', 'Casual Leave', 'RC_CL', True, 'manager', 'half_day', False, 12, 2, False),
    ('rc_hrp_lt_sick', 'Sick Leave', 'RC_SL', True, 'hr', 'half_day', False, 12, 1, True),
    ('rc_hrp_lt_earned', 'Earned Leave', 'RC_EL', True, 'both', 'day', False, 15, 4, False),
    ('rc_hrp_lt_festival', 'Festival Leave (Onam / Christmas)', 'RC_FL', True, 'manager', 'day', False, 3, 9, False),
    ('rc_hrp_lt_unpaid', 'Unpaid Leave', 'RC_UL', False, 'both', 'day', True, 0, 7, False),
    ('rc_hrp_lt_compoff', 'Compensatory Off', 'RC_CO', True, 'manager', 'day', False, 0, 10, False),
]
COMPOFF = {'Anjali Das': 1, 'Mohammed Bilal': 2, 'Manoj Pillai': 1, 'Kevin Joseph': 1}

KERALA_HOLIDAYS = [
    ('rc_hrp_ph_republic_2026', 'Republic Day', '2026-01-26'),
    ('rc_hrp_ph_vishu_2026', 'Vishu', '2026-04-15'),
    ('rc_hrp_ph_independence_2026', 'Independence Day', '2026-08-15'),
    ('rc_hrp_ph_uthradom_2026', 'First Onam (Uthradom)', '2026-08-25'),
    ('rc_hrp_ph_thiruvonam_2026', 'Thiruvonam', '2026-08-26'),
    ('rc_hrp_ph_gandhi_2026', 'Gandhi Jayanti', '2026-10-02'),
    ('rc_hrp_ph_keralapiravi_2026', 'Kerala Piravi', '2026-11-01'),
    ('rc_hrp_ph_christmas_2026', 'Christmas', '2026-12-25'),
    ('rc_hrp_ph_republic_2027', 'Republic Day', '2027-01-26'),
]


# --------------------------------------------------------------------------- steps
def _calendars(env):
    cals = {}
    for key, (xid, name, slots) in CALENDARS.items():
        if _ref(env, xid):
            cals[key] = _ref(env, xid)
            continue
        lines = []
        for day in range(6):  # Mon-Sat
            for h_from, h_to in slots:
                lines.append(Command.create({'dayofweek': str(day), 'hour_from': h_from, 'hour_to': h_to}))
        cals[key] = _get_or_create(env, xid, 'resource.calendar', {
            'name': name, 'tz': 'Asia/Kolkata', 'company_id': env.company.id, 'attendance_ids': [Command.clear()] + lines,
        })
    return cals


def _master(env):
    res = {}
    Loc = env['hr.work.location'].sudo()
    company_partner = env.company.partner_id
    res['outlet'] = _get_or_create(env, 'rc_hrp_loc_outlet', 'hr.work.location', {
        'name': 'Marine Drive Outlet', 'location_type': 'office', 'address_id': company_partner.id, 'company_id': env.company.id},
        [('name', '=', 'Marine Drive Outlet')])
    kitchen_addr = _get_or_create(env, 'rc_hrp_addr_central_kitchen', 'res.partner', {
        'name': 'Resto Cafe Central Kitchen', 'parent_id': company_partner.id, 'type': 'other',
        'street': 'Infopark Road, Kakkanad', 'city': 'Kochi', 'zip': '682042',
        'state_id': env.company.state_id.id, 'country_id': env.company.country_id.id})
    res['kitchen'] = _get_or_create(env, 'rc_hrp_loc_kitchen', 'hr.work.location', {
        'name': 'Central Kitchen - Kakkanad', 'location_type': 'office', 'address_id': kitchen_addr.id, 'company_id': env.company.id},
        [('name', '=', 'Central Kitchen - Kakkanad')])
    EType = env['hr.employee.type'].sudo()
    res['etype'] = {
        'regular': EType.search([('name', '=', 'Regular Employee')], limit=1) or EType.search([('name', '=', 'Employee')], limit=1),
        'probation': EType.search([('name', '=', 'Probationary')], limit=1),
        'seasonal': EType.search([('name', '=', 'Occasional / Seasonal')], limit=1),
        'parttime': _get_or_create(env, 'rc_hrp_etype_parttime', 'hr.employee.type', {'name': 'Part-time'}, [('name', '=', 'Part-time')]),
    }
    SType = env['hr.payroll.structure.type'].sudo() if 'hr.payroll.structure.type' in env else None
    res['stype'] = {}
    res['struct'] = {}
    if SType is not None:
        for key, name in (('employee', 'India: Employee Pay'), ('worker', 'India: Worker Pay')):
            st = SType.search([('name', '=', name)], limit=1)
            res['stype'][key] = st
            if st and 'hr.payroll.structure' in env:
                Struct = env['hr.payroll.structure'].sudo()
                type_field = 'type_id' if 'type_id' in Struct._fields else None
                res['struct'][key] = Struct.search([(type_field, '=', st.id)], limit=1) if type_field else Struct.browse()
    return res


def _departments(env):
    depts = {}
    for xid, name, _manager in DEPARTMENTS:
        depts[xid] = _get_or_create(env, xid, 'hr.department', {'name': name, 'company_id': env.company.id},
                                    [('name', '=', name)])
    return depts


def _job(env, title, dept):
    Job = env['hr.job'].sudo()
    job = Job.search([('name', '=', title), ('department_id', '=', dept.id)], limit=1) or Job.search([('name', '=', title)], limit=1)
    if not job:
        job = Job.create({'name': title, 'department_id': dept.id, 'company_id': env.company.id})
    return job


def _employees(env, master, depts, cals):
    Emp = env['hr.employee'].sudo().with_context(**CTX)
    for xid, name, job_title, dept_xid, _mgr, _coach, loc, gender, bday, mobile in NEW_EMPLOYEES:
        if _ref(env, xid):
            continue
        existing = _emp(env, name)
        if existing:
            _bind(env, xid, existing)
            continue
        dept = depts[dept_xid]
        login = name.lower().replace(' ', '.')
        vals = {
            'name': name, 'job_title': job_title, 'job_id': _job(env, job_title, dept).id, 'department_id': dept.id,
            'work_email': f'{login}@restocafe.example.com', 'mobile_phone': mobile, 'work_phone': '+91 484 400 1234',
            'birthday': bday, 'company_id': env.company.id,
        }
        if 'sex' in Emp._fields:
            vals['sex'] = gender
        elif 'gender' in Emp._fields:
            vals['gender'] = gender
        _bind(env, xid, Emp.create(vals))
    # department managers, then hierarchy (department manager writes can reset parent_id)
    for xid, _name, manager in DEPARTMENTS:
        m = _emp(env, manager)
        if m and depts[xid].manager_id != m:
            depts[xid].manager_id = m
    for _xid, name, _job_t, _dept, mgr, coach, loc, *_ in NEW_EMPLOYEES:
        e = _emp(env, name)
        vals = {}
        if mgr and _emp(env, mgr):
            vals['parent_id'] = _emp(env, mgr).id
        if coach and _emp(env, coach):
            vals['coach_id'] = _emp(env, coach).id
        e.write(vals)
    # reporting lines for the demo_hr_suite staff
    for name, mgr in (('Ananya Sharma', 'Rahul Nair'), ('Vishnu Kumar', 'Rahul Nair'), ('Priya Menon', 'Thomas Mathew'),
                      ('Mohammed Bilal', 'Thomas Mathew'), ('Sneha Pillai', 'Thomas Mathew'), ('Arun Varma', 'Thomas Mathew'),
                      ('Kevin Joseph', 'Arun Varma'), ('Rahul Nair', 'Suresh Kumar')):
        e, m = _emp(env, name), _emp(env, mgr)
        if e and m and e.parent_id != m:
            e.parent_id = m


def _contracts(env, master, cals):
    today = fields.Date.context_today(env['hr.employee'])
    for name, (etype, skey, wage, hourly, start, end, trial_days, shift) in CONTRACTS.items():
        e = _emp(env, name)
        if not e:
            continue
        xid = f'rc_hrp_contract_{name.lower().replace(" ", "_")}'
        version = e.version_id
        if not version:
            continue
        if _ref(env, xid):
            continue
        if trial_days is not None:  # probationers: joined recently, probation of 3 months
            start_d = today + timedelta(days=trial_days) - timedelta(days=90)
            trial_end = today + timedelta(days=trial_days)
        else:
            start_d = fields.Date.to_date(start)
            trial_end = start_d + timedelta(days=90)
        cal = cals[shift]
        loc_key = next((n[6] for n in NEW_EMPLOYEES if n[1] == name), 'kitchen' if name in ('Deepa Krishnan',) else 'outlet')
        vals = {
            'wage': wage, 'contract_date_start': start_d, 'trial_date_end': trial_end,
            'resource_calendar_id': cal.id, 'date_version': min(start_d, today),
        }
        if end:
            vals['contract_date_end'] = fields.Date.to_date(end)
        if master['etype'].get(etype):
            vals['employee_type_id'] = master['etype'][etype].id
        V = env['hr.version']
        if 'structure_type_id' in V._fields and master['stype'].get(skey):
            vals['structure_type_id'] = master['stype'][skey].id
        if 'struct_id' in V._fields and master['struct'].get(skey):
            vals['struct_id'] = master['struct'][skey].id
        if 'schedule_pay' in V._fields:
            vals['schedule_pay'] = 'monthly'
        if hourly and 'hourly_rate' in V._fields:
            vals['hourly_rate'] = hourly
            if 'pay_by_attendance' in V._fields:
                vals['pay_by_attendance'] = True
        if 'work_location_id' in V._fields:
            vals['work_location_id'] = master[loc_key].id
        version.sudo().with_context(**CTX).write(vals)
        e.sudo().write({'tz': 'Asia/Kolkata'} if 'tz' in e._fields else {})
        _bind(env, xid, version)


def _skills(env):
    SType, Skill, Level, ESkill = (env[m].sudo() for m in ('hr.skill.type', 'hr.skill', 'hr.skill.level', 'hr.employee.skill'))
    types, skills, levels = {}, {}, {}
    for key, (xid, name, is_cert, lvls, names) in SKILL_TYPES.items():
        st = _ref(env, xid)
        if not st:
            vals = {'name': name, 'skill_level_ids': [Command.create({'name': n, 'level_progress': p, 'default_level': i == 0})
                                                      for i, (n, p) in enumerate(lvls)],
                    'skill_ids': [Command.create({'name': n}) for n in names]}
            if 'is_certification' in SType._fields:
                vals['is_certification'] = is_cert
            st = _get_or_create(env, xid, 'hr.skill.type', vals, [('name', '=', name)])
        types[key] = st
    lang = SType.search([('name', '=', 'Languages')], limit=1)
    if lang:
        for n in EXTRA_LANGUAGES:
            if not lang.skill_ids.filtered(lambda s: s.name == n):
                _bind(env, f'rc_hrp_skill_lang_{n.lower()}', Skill.create({'name': n, 'skill_type_id': lang.id}))
        types['lang'] = lang
    today = fields.Date.context_today(env['hr.employee'])
    for emp_name, rows in SKILLS.items():
        e = _emp(env, emp_name)
        if not e:
            continue
        for tkey, skill_name, level_name in rows:
            st = types.get(tkey)
            if not st:
                continue
            skill = st.skill_ids.filtered(lambda s: s.name == skill_name)[:1]
            level = st.skill_level_ids.filtered(lambda l: l.name == level_name)[:1] or st.skill_level_ids[:1]
            if not skill or not level:
                continue
            xid = f'rc_hrp_eskill_{e.id}_{skill.id}'
            if _ref(env, xid) or ESkill.search_count([('employee_id', '=', e.id), ('skill_id', '=', skill.id)]):
                continue
            vals = {'employee_id': e.id, 'skill_id': skill.id, 'skill_level_id': level.id, 'skill_type_id': st.id}
            validity = CERT_VALIDITY.get((emp_name, skill_name))
            if tkey == 'cert':
                vf, vt = validity or (-365, 730)
                if 'valid_from' in ESkill._fields:
                    vals['valid_from'] = today + timedelta(days=vf)
                if 'valid_to' in ESkill._fields:
                    vals['valid_to'] = today + timedelta(days=vt)
            _bind(env, xid, ESkill.create(vals))


def _leave_types(env):
    WET = env['hr.work.entry.type'].sudo()
    india = env.ref('base.in')
    res = {}
    for xid, name, code, req_alloc, validation, unit, unpaid, _days, color, doc in LEAVE_TYPES:
        vals = {
            'name': name, 'code': code, 'country_id': india.id, 'count_as': 'absence', 'requires_allocation': req_alloc,
            'leave_validation_type': validation, 'request_unit': unit, 'unit_of_measure': 'day', 'color': color,
            'employee_requests': code == 'RC_CO', 'allocation_validation_type': 'hr' if code == 'RC_CO' else 'no_validation',
        }
        optional = {'unpaid': unpaid, 'support_document': doc, 'time_off_selectable': True, 'amount_rate': 0.0 if unpaid else 1.0,
                    'include_in_leave_encashment': code == 'RC_EL', 'l10n_in_is_sandwich_leave': code == 'RC_EL'}
        vals.update({k: v for k, v in optional.items() if k in WET._fields})
        res[xid] = _get_or_create(env, xid, 'hr.work.entry.type', vals, [('code', '=', code), ('country_id', '=', india.id)])
    return res


def _public_holidays(env):
    for xid, name, day in KERALA_HOLIDAYS:
        if _ref(env, xid):
            continue
        d = fields.Date.to_date(day)
        _get_or_create(env, xid, 'resource.calendar.leaves', {
            'name': name, 'company_id': env.company.id, 'calendar_id': False, 'resource_id': False,
            'date_from': _utc(d, 0.0), 'date_to': _utc(d, 23.0 + 59 / 60),
        })


def _allocations(env, ltypes):
    Alloc = env['hr.leave.allocation'].sudo().with_context(**CTX)
    employees = env['hr.employee'].sudo().search([('company_id', '=', env.company.id)])
    exec_type = env.ref('hr.contract_type_company_executive', raise_if_not_found=False)
    for e in employees:
        if exec_type and e.employee_type_id == exec_type:
            continue
        plan = [(xid, days) for xid, _n, _c, req, _v, _u, _up, days, _col, _d in LEAVE_TYPES if req and days]
        if e.name in COMPOFF:
            plan.append(('rc_hrp_lt_compoff', COMPOFF[e.name]))
        for lt_xid, days in plan:
            xid = f'rc_hrp_alloc_{lt_xid[10:]}_{e.id}'
            if _ref(env, xid):
                continue
            lt = ltypes[lt_xid]
            alloc = Alloc.create({
                'name': f'{lt.name} {YEAR}' if lt_xid != 'rc_hrp_lt_compoff' else 'Comp-off for extra Onam / event shifts',
                'employee_id': e.id, 'work_entry_type_id': lt.id, 'number_of_days': days,
                'date_from': date(YEAR, 1, 1), 'date_to': date(YEAR, 12, 31),
            })
            if alloc.state != 'validate':
                alloc.write({'state': 'validate'})
            _bind(env, xid, alloc)


def _working_day(d, back=True):
    while d.weekday() == 6:  # Sunday off
        d = d - timedelta(days=1) if back else d + timedelta(days=1)
    return d


def _leave_plan(today):
    nxt_mon = today + timedelta(days=(7 - today.weekday()) or 7)
    fri = nxt_mon + timedelta(days=4)
    d = lambda s: fields.Date.to_date(s)
    past = lambda n: _working_day(today - timedelta(days=n))
    # key, employee, type xid, from, to, period(None|'am'|'pm'), outcome, description
    return [
        ('onam_rahul', 'Rahul Nair', 'rc_hrp_lt_festival', d('2026-08-24'), d('2026-08-24'), None, 'approve', 'Onam eve with family in Thrissur'),
        ('onam_priya', 'Priya Menon', 'rc_hrp_lt_festival', d('2026-08-27'), d('2026-08-28'), None, 'approve', 'Third Onam - family visit to Palakkad'),
        ('onam_ajay', 'Ajay Menon', 'rc_hrp_lt_festival', d('2026-08-24'), d('2026-08-24'), None, 'refuse', 'Onam Sadya catering week - all cooks needed'),
        ('sick_vishnu', 'Vishnu Kumar', 'rc_hrp_lt_sick', past(20), past(19), None, 'approve', 'Viral fever - medical certificate attached'),
        ('casual_bilal', 'Mohammed Bilal', 'rc_hrp_lt_casual', past(9), past(9), None, 'approve', 'Sister\'s engagement ceremony'),
        ('earned_sneha', 'Sneha Pillai', 'rc_hrp_lt_earned', d('2026-10-12'), d('2026-10-14'), None, 'approve', 'Trip to Munnar'),
        ('half_thomas', 'Thomas Mathew', 'rc_hrp_lt_casual', past(5), past(5), 'pm', 'approve', 'Bank and RTO work (afternoon)'),
        ('unpaid_manoj', 'Manoj Pillai', 'rc_hrp_lt_unpaid', d('2026-09-14'), d('2026-09-15'), None, 'approve', 'House shifting - casual leave exhausted'),
        ('compoff_anjali', 'Anjali Das', 'rc_hrp_lt_compoff', past(3), past(3), None, 'approve', 'Comp-off for the Diwali catering shift'),
        ('sick_fathima', 'Fathima Rasheed', 'rc_hrp_lt_sick', past(2), past(2), None, 'approve', 'Migraine'),
        ('xmas_ananya', 'Ananya Sharma', 'rc_hrp_lt_earned', d('2026-12-21'), d('2026-12-24'), None, 'confirm', 'Christmas with family in Delhi'),
        ('casual_bilal2', 'Mohammed Bilal', 'rc_hrp_lt_casual', fri, fri, None, 'confirm', 'Friday prayers and family function'),
        ('casual_nikhil', 'Nikhil Raj', 'rc_hrp_lt_casual', nxt_mon + timedelta(days=1), nxt_mon + timedelta(days=2), None, 'confirm', 'College convocation'),
        ('earned_faisal', 'Faisal Ahmed', 'rc_hrp_lt_casual', nxt_mon + timedelta(days=9), nxt_mon + timedelta(days=9), None, 'confirm', 'Two-wheeler licence renewal'),
        ('earned_deepa', 'Deepa Krishnan', 'rc_hrp_lt_earned', d('2026-12-07'), d('2026-12-09'), None, 'first', 'Sabarimala pilgrimage'),
        ('casual_lakshmi', 'Lakshmi Iyer', 'rc_hrp_lt_casual', nxt_mon + timedelta(days=14), nxt_mon + timedelta(days=14), None, 'confirm', 'GST audit follow-up at home office - personal day'),
        ('xmas_gokul', 'Gokul Krishna', 'rc_hrp_lt_festival', d('2026-12-24'), d('2026-12-24'), None, 'confirm', 'Christmas eve at Fort Kochi'),
        ('xmas_ajay', 'Ajay Menon', 'rc_hrp_lt_earned', d('2026-12-23'), d('2026-12-26'), None, 'refuse', 'Peak Christmas catering week - request after 2 Jan'),
        ('nye_reshma', 'Reshma Babu', 'rc_hrp_lt_casual', d('2026-12-31'), d('2026-12-31'), None, 'refuse', 'New Year\'s Eve - full house booked'),
        ('cancel_arun', 'Arun Varma', 'rc_hrp_lt_casual', d('2026-09-21'), d('2026-09-21'), None, 'cancel', 'Plan changed - cancelled by employee'),
        ('cancel_kevin', 'Kevin Joseph', 'rc_hrp_lt_earned', nxt_mon + timedelta(days=3), nxt_mon + timedelta(days=4), None, 'cancel', 'Trip postponed'),
    ]


def _leaves(env, ltypes):
    # leave_fast_create: no auto-approval for the (super)user creating the requests; approvals are done explicitly
    Leave = env['hr.leave'].sudo().with_context(leave_fast_create=True, **CTX)
    today = fields.Date.context_today(env['hr.employee'])
    for key, emp_name, lt_xid, d_from, d_to, period, outcome, desc in _leave_plan(today):
        xid = f'rc_hrp_leave_{key}'
        if _ref(env, xid):
            continue
        e = _emp(env, emp_name)
        if not e:
            continue
        try:
            with env.cr.savepoint():
                vals = {'employee_id': e.id, 'work_entry_type_id': ltypes[lt_xid].id, 'private_name': desc,
                        'request_date_from': d_from, 'request_date_to': d_to}
                if period:
                    vals.update({'request_duration': period, 'request_date_from_period': period, 'request_date_to_period': period})
                leave = Leave.create(vals).with_context(leave_fast_create=False)
                if not leave.exists():
                    _logger.warning("Hudson POS: demo leave %s dropped by Odoo (no allocation / outside schedule)", key)
                    continue
                if outcome in ('approve', 'first', 'refuse', 'cancel') and leave.state == 'confirm':
                    if outcome == 'refuse':
                        leave.action_refuse()
                    elif outcome == 'first':
                        if leave.validation_type == 'both':
                            leave.write({'state': 'validate1'})
                    else:
                        leave.action_approve(check_state=False)
                        if leave.state == 'validate1':
                            leave._action_validate(check_state=False)
                        if outcome == 'cancel':
                            leave._force_cancel(desc, 'mail.mt_note', notify_responsibles=False)
                if outcome == 'refuse' and leave.state != 'refuse':
                    leave.write({'state': 'refuse'})
                leave.message_post(body=desc, message_type='comment', subtype_xmlid='mail.mt_note')
                _bind(env, xid, leave)
        except Exception as e:
            _logger.exception("Hudson POS: demo leave %s failed: %s", key, e)


def _attendances(env):
    Att = env['hr.attendance'].sudo().with_context(**CTX)
    today = fields.Date.context_today(env['hr.employee'])
    days, d = [], today - timedelta(days=1)
    while len(days) < 14:
        if d.weekday() != 6:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    holidays = {fields.Date.to_date(day) for _x, _n, day in KERALA_HOLIDAYS}
    exec_type = env.ref('hr.contract_type_company_executive', raise_if_not_found=False)
    auto_checkout_done = False
    for name, contract in CONTRACTS.items():
        e = _emp(env, name)
        if not e or (exec_type and e.employee_type_id == exec_type):
            continue
        cal_key = contract[7]
        slots = CALENDARS[cal_key][2]
        start_h, end_h = slots[0][0], slots[-1][1]
        leaves = env['hr.leave'].sudo().search([('employee_id', '=', e.id), ('state', 'in', ('validate', 'validate1', 'confirm'))])
        leave_days = set()
        for lv in leaves:
            cur = lv.request_date_from
            while cur and cur <= lv.request_date_to:
                leave_days.add(cur)
                cur += timedelta(days=1)
        start_contract = e.version_id.contract_date_start
        for day in days:
            xid = f'rc_hrp_att_{e.id}_{day.isoformat().replace("-", "")}'
            if _ref(env, xid) or day in holidays or day in leave_days or (start_contract and day < start_contract):
                continue
            rnd = random.Random(f'{name}-{day.isoformat()}')
            roll = rnd.random()
            check_in_h = start_h + rnd.uniform(-0.15, 0.08)          # a few minutes early / on time
            if roll < 0.08:
                check_in_h = start_h + rnd.uniform(0.25, 0.6)          # late arrival 15-35 min
            check_out_h = end_h + rnd.uniform(-0.05, 0.2)
            if 0.08 <= roll < 0.18:
                check_out_h = end_h + rnd.uniform(1.0, 2.5)            # overtime
            check_in, check_out = _utc(day, check_in_h), _utc(day, min(check_out_h, 23.9))
            if Att.search_count([('employee_id', '=', e.id), ('check_in', '<', check_out),
                                 '|', ('check_out', '=', False), ('check_out', '>', check_in)]):
                continue
            vals = {'employee_id': e.id, 'check_in': check_in, 'check_out': check_out, 'in_mode': 'kiosk', 'out_mode': 'kiosk'}
            if not auto_checkout_done and name == 'Nikhil Raj' and day == days[-3]:
                # forgot to check out: closed by Odoo's automatic check-out at shift end + tolerance
                vals.update({'check_out': _utc(day, end_h + 2.0), 'out_mode': 'auto_check_out'})
                auto_checkout_done = True
            _bind(env, xid, Att.create(vals))


# --------------------------------------------------------------------------- entry point
def load_hr_people_suite_demo_data(env):
    if 'hr.employee' not in env:
        return
    env = env(context=dict(env.context, **CTX))
    state = {}
    steps = [
        ('calendars', lambda: state.update(cals=_calendars(env))),
        ('master data', lambda: state.update(master=_master(env), depts=_departments(env))),
        ('employees', lambda: _employees(env, state['master'], state['depts'], state['cals'])),
        ('contracts', lambda: _contracts(env, state['master'], state['cals'])),
    ]
    if 'hr.skill' in env:
        steps.append(('skills', lambda: _skills(env)))
    if 'hr.leave' in env:
        steps += [
            ('leave types', lambda: state.update(ltypes=_leave_types(env))),
            ('public holidays', lambda: _public_holidays(env)),
            ('allocations', lambda: _allocations(env, state['ltypes'])),
            ('time off', lambda: _leaves(env, state['ltypes'])),
        ]
    if 'hr.attendance' in env:
        steps.append(('attendances', lambda: _attendances(env)))
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
                env.flush_all()
        except Exception as e:
            _logger.exception("Hudson POS: HR people demo step '%s' failed: %s", name, e)
            if name in ('calendars', 'master data', 'employees'):
                return
    _logger.info("Hudson POS: Resto Cafe HR people demo data loaded.")
