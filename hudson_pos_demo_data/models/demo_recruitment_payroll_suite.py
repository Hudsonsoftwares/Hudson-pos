# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Recruitment, Online Jobs and Payroll demo data.

Recruitment / Online Jobs (hr_recruitment + website_hr_recruitment):
  * the 9 existing Resto Cafe jobs get descriptions, requirements, salary range and are published,
    plus 2 new openings (South Indian Cook, Kitchen Helper)
  * ~26 applicants in every stage (new, qualification, interviews, contract proposal, hired, refused)
    with sources (Website, Naukri, Indeed, Walk-in, Employee Referral), tags, priority, salaries in INR,
    interview meetings, and one hired applicant converted into an employee
Payroll (custom Hudson Indian Payroll - hudson_payroll_base / hudson_in_payroll):
  * monthly wages with Basic / HRA / Fixed breakdown, PAN, UAN, ESIC numbers, bank accounts
  * last month's pay run validated, current month's pay run computed (draft), with EPF / ESIC lines,
    a reimbursement input and a salary-advance deduction
"""
import logging
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_notrack': True, 'mail_auto_subscribe_no_notify': True, 'test_mode': True}


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    if not _ref(env, xid):
        env['ir.model.data'].sudo().create({
            'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
        })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().with_context(**CTX).create(vals))


def _user(env, key):
    return (_ref(env, 'rc_user_arjun') if key == 'arjun' else None) or env.ref('base.user_admin')


# --------------------------------------------------------------------------- recruitment
JOBS = {
    # existing job name: (xid, expected new hires, salary min, max, description, requirements)
    'Head Chef': ('rc_rec_job_head_chef', 1, 55000, 75000,
                  'Lead our Kerala and continental kitchen: menu planning, food cost, hygiene and a team of 12 cooks.',
                  '8+ years in a busy restaurant kitchen, 3 as Head or Executive Chef. FSSAI food safety training. Malayalam and English.'),
    'Sous Chef': ('rc_rec_job_sous_chef', 1, 38000, 48000,
                  'Run the hot line during service, train commis cooks and keep the cold room and prep lists in order.',
                  '5+ years of hot-kitchen experience, strong in Kerala seafood and tandoor.'),
    'Line Cook & Prep Specialist': ('rc_rec_job_line_cook', 3, 16000, 22000,
                                    'Prepare mise en place and cook à la minute on the grill, tawa and fry stations.',
                                    '1-3 years in a restaurant kitchen. Freshers with a catering diploma are welcome.'),
    'Head Barista & Cafe Specialist': ('rc_rec_job_barista', 2, 20000, 30000,
                                       'Dial in espresso, pour latte art and serve our filter coffee and cold brew menu.',
                                       '1+ year as a barista. Latte art and customer-facing English.'),
    'Senior Service Captain & Waiter': ('rc_rec_job_server', 4, 15000, 22000,
                                        'Welcome guests, take orders on the POS tablet, upsell and keep tables turning.',
                                        'Hotel management or 1+ year in fine-dine service. Weekend availability.'),
    'POS Cashier & Receptionist': ('rc_rec_job_cashier', 1, 15000, 19000,
                                   'Handle billing, UPI and card payments, table bookings and phone orders.',
                                   'Comfortable with POS systems and cash handling. Malayalam, English, Hindi.'),
    'Senior Delivery Rider': ('rc_rec_job_rider', 4, 14000, 20000,
                              'Deliver orders across Kochi on our EV scooters with insulated boxes.',
                              'Two-wheeler licence, smartphone, knowledge of Kochi city routes.'),
    'Fleet Logistics Driver': ('rc_rec_job_driver', 1, 18000, 24000,
                               'Drive the catering van for events and the morning market run.',
                               'LMV licence with 3+ years experience. Event-day night shifts.'),
    'Restaurant General Manager': ('rc_rec_job_manager', 1, 70000, 95000,
                                   'Own the P&L of the Marine Drive outlet: people, guests, hygiene and growth.',
                                   '10+ years in restaurant operations, 3 as outlet or general manager.'),
}
NEW_JOBS = [  # xid, name, department name, hires, min, max, description, requirements
    ('rc_rec_job_south_indian_cook', 'South Indian Cook', 'Kitchen & Culinary', 2, 18000, 26000,
     'Cook appam, dosa, puttu, Sadya curries and Malabar biryani for dine-in and catering.',
     '3+ years in a Kerala kitchen. Sadya experience for 300+ guests is a plus.'),
    ('rc_rec_job_kitchen_helper', 'Kitchen Helper', 'Kitchen & Culinary', 4, 12000, 15000,
     'Wash, peel and cut, keep the dish area and stores clean, help the line during rush hours.',
     'No experience needed. Food and accommodation provided.'),
]
SOURCES = ['Website', 'Naukri', 'Indeed', 'Walk-in', 'Employee Referral']
TAGS = [('rc_rec_tag_exp', 'Experienced', 10), ('rc_rec_tag_fresher', 'Fresher', 4), ('rc_rec_tag_malayalam', 'Malayalam', 2),
        ('rc_rec_tag_english', 'Fluent English', 3), ('rc_rec_tag_night', 'Night Shift OK', 5), ('rc_rec_tag_licence', 'Two-wheeler Licence', 6)]

# xid, name, email, phone, job xid, stage name|'refused', source, tags, priority, expected, proposed, days ago, refuse reason, interviewer
APPLICANTS = [
    ('rc_rec_app_01', 'Akhil Raj', 'akhil.raj@example.com', '+91 98950 11201', 'rc_rec_job_line_cook', 'New', 'Naukri', ['rc_rec_tag_exp'], '1', 20000, 0, 1, None, 'admin'),
    ('rc_rec_app_02', 'Divya Krishnan', 'divya.k@example.com', '+91 94470 22302', 'rc_rec_job_barista', 'New', 'Website', ['rc_rec_tag_english'], '2', 24000, 0, 2, None, 'arjun'),
    ('rc_rec_app_03', 'Faisal Ahammed', 'faisal.a@example.com', '+91 97450 33403', 'rc_rec_job_rider', 'New', 'Walk-in', ['rc_rec_tag_licence', 'rc_rec_tag_night'], '0', 16000, 0, 1, None, 'arjun'),
    ('rc_rec_app_04', 'Nimisha Joseph', 'nimisha.j@example.com', '+91 81290 44504', 'rc_rec_job_server', 'New', 'Indeed', ['rc_rec_tag_fresher'], '1', 15000, 0, 3, None, 'admin'),
    ('rc_rec_app_05', 'Sajan Varghese', 'sajan.v@example.com', '+91 90370 55605', 'rc_rec_job_south_indian_cook', 'New', 'Employee Referral', ['rc_rec_tag_exp', 'rc_rec_tag_malayalam'], '2', 24000, 0, 2, None, 'admin'),
    ('rc_rec_app_06', 'Amal Dev', 'amal.dev@example.com', '+91 85470 66706', 'rc_rec_job_kitchen_helper', 'Qualification', 'Walk-in', ['rc_rec_tag_fresher'], '0', 13000, 0, 5, None, 'admin'),
    ('rc_rec_app_07', 'Reshma Nair', 'reshma.n@example.com', '+91 95620 77807', 'rc_rec_job_cashier', 'Qualification', 'Naukri', ['rc_rec_tag_english', 'rc_rec_tag_malayalam'], '1', 17000, 0, 6, None, 'arjun'),
    ('rc_rec_app_08', 'Joel Thomas', 'joel.t@example.com', '+91 70120 88908', 'rc_rec_job_line_cook', 'Qualification', 'Website', ['rc_rec_tag_fresher'], '1', 16000, 0, 7, None, 'admin'),
    ('rc_rec_app_09', 'Shahana Basheer', 'shahana.b@example.com', '+91 96330 99009', 'rc_rec_job_server', 'Qualification', 'Indeed', ['rc_rec_tag_night'], '2', 18000, 0, 4, None, 'arjun'),
    ('rc_rec_app_10', 'Gokul Suresh', 'gokul.s@example.com', '+91 94960 10110', 'rc_rec_job_sous_chef', 'First Interview', 'Naukri', ['rc_rec_tag_exp'], '2', 45000, 0, 9, None, 'admin'),
    ('rc_rec_app_11', 'Anjana Menon', 'anjana.m@example.com', '+91 98460 21211', 'rc_rec_job_barista', 'First Interview', 'Employee Referral', ['rc_rec_tag_exp', 'rc_rec_tag_english'], '3', 27000, 0, 8, None, 'arjun'),
    ('rc_rec_app_12', 'Rijo Paul', 'rijo.p@example.com', '+91 77360 32312', 'rc_rec_job_rider', 'First Interview', 'Walk-in', ['rc_rec_tag_licence'], '1', 17000, 0, 6, None, 'arjun'),
    ('rc_rec_app_13', 'Lakshmi Priya', 'lakshmi.p@example.com', '+91 81130 43413', 'rc_rec_job_south_indian_cook', 'Second Interview', 'Website', ['rc_rec_tag_exp', 'rc_rec_tag_malayalam'], '2', 25000, 0, 12, None, 'admin'),
    ('rc_rec_app_14', 'Nikhil Mohan', 'nikhil.m@example.com', '+91 99610 54514', 'rc_rec_job_manager', 'Second Interview', 'Naukri', ['rc_rec_tag_exp', 'rc_rec_tag_english'], '3', 90000, 0, 14, None, 'admin'),
    ('rc_rec_app_15', 'Hiba Fathima', 'hiba.f@example.com', '+91 86060 65615', 'rc_rec_job_server', 'Second Interview', 'Indeed', ['rc_rec_tag_english'], '1', 19000, 0, 10, None, 'arjun'),
    ('rc_rec_app_16', 'Vipin Das', 'vipin.d@example.com', '+91 97440 76716', 'rc_rec_job_driver', 'Contract Proposal', 'Employee Referral', ['rc_rec_tag_exp', 'rc_rec_tag_night'], '2', 22000, 21000, 16, None, 'arjun'),
    ('rc_rec_app_17', 'Sruthi Ramesh', 'sruthi.r@example.com', '+91 94000 87817', 'rc_rec_job_line_cook', 'Contract Proposal', 'Website', ['rc_rec_tag_exp'], '2', 20000, 19500, 15, None, 'admin'),
    ('rc_rec_app_18', 'Fathima Rasheed', 'fathima.r@example.com', '+91 95390 98918', 'rc_rec_job_barista', 'Contract Signed', 'Employee Referral', ['rc_rec_tag_exp', 'rc_rec_tag_english'], '3', 26000, 25000, 24, None, 'arjun'),
    ('rc_rec_app_19', 'Midhun Babu', 'midhun.b@example.com', '+91 80860 09019', 'rc_rec_job_rider', 'Contract Signed', 'Walk-in', ['rc_rec_tag_licence', 'rc_rec_tag_night'], '1', 17000, 17500, 28, None, 'arjun'),
    ('rc_rec_app_20', 'Arya Sasidharan', 'arya.s@example.com', '+91 73560 10120', 'rc_rec_job_kitchen_helper', 'Contract Signed', 'Walk-in', ['rc_rec_tag_fresher'], '0', 13000, 13000, 21, None, 'admin'),
    ('rc_rec_app_21', 'Rohit Sharma', 'rohit.sharma@example.com', '+91 98110 21221', 'rc_rec_job_head_chef', 'refused', 'Naukri', ['rc_rec_tag_exp'], '1', 120000, 0, 30, 'Refused by applicant: salary', 'admin'),
    ('rc_rec_app_22', 'Neethu George', 'neethu.g@example.com', '+91 94950 32322', 'rc_rec_job_cashier', 'refused', 'Indeed', [], '0', 18000, 0, 26, 'Does not fit the job requirements', 'arjun'),
    ('rc_rec_app_23', 'Abhijith K', 'abhijith.k@example.com', '+91 90610 43423', 'rc_rec_job_server', 'refused', 'Website', ['rc_rec_tag_fresher'], '0', 15000, 0, 19, 'Job already fulfilled', 'arjun'),
    ('rc_rec_app_24', 'Sreejith Unni', 'sreejith.u@example.com', '+91 85900 54524', 'rc_rec_job_rider', 'refused', 'Walk-in', ['rc_rec_tag_licence'], '0', 16000, 0, 22, 'Refused by applicant: job fit', 'arjun'),
    ('rc_rec_app_25', 'Meera Venugopal', 'meera.v@example.com', '+91 96050 65625', 'rc_rec_job_sous_chef', 'Qualification', 'Website', ['rc_rec_tag_exp', 'rc_rec_tag_malayalam'], '2', 42000, 0, 3, None, 'admin'),
    ('rc_rec_app_26', 'Tom Kurian', 'tom.k@example.com', '+91 81380 76726', 'rc_rec_job_south_indian_cook', 'First Interview', 'Walk-in', ['rc_rec_tag_malayalam'], '1', 22000, 0, 5, None, 'admin'),
]
HIRE_AS_EMPLOYEE = 'rc_rec_app_18'  # Fathima Rasheed -> Barista, joins on the 1st of this month


def _load_recruitment(env):
    if 'hr.applicant' not in env:
        return
    Job = env['hr.job'].sudo().with_context(**CTX)
    company = env.company
    address = company.partner_id
    # 1. existing jobs: bind, describe, publish
    jobs = {}
    for name, (xid, hires, smin, smax, desc, req) in JOBS.items():
        job = _ref(env, xid) or Job.search([('name', '=', name)], limit=1)
        if not job:
            continue
        _bind(env, xid, job)
        jobs[xid] = job
        if not job.description:
            vals = {'description': f'<p>{desc}</p>', 'requirements': req, 'no_of_recruitment': hires, 'address_id': address.id}
            if 'salary_min' in job._fields:
                vals.update({'salary_min': smin, 'salary_max': smax, 'payment_interval': 'monthly'})
            job.write(vals)
    for xid, name, dept, hires, smin, smax, desc, req in NEW_JOBS:
        department = env['hr.department'].search([('name', '=', dept)], limit=1)
        vals = {'name': name, 'department_id': department.id, 'no_of_recruitment': hires, 'description': f'<p>{desc}</p>',
                'requirements': req, 'address_id': address.id}
        if 'salary_min' in Job._fields:
            vals.update({'salary_min': smin, 'salary_max': smax, 'payment_interval': 'monthly'})
        # the HR people suite may already have created this job title: reuse it (job names are unique per company)
        existing = _ref(env, xid) or Job.with_context(active_test=False).search(
            [('name', '=', name), ('company_id', 'in', [company.id, False])], limit=1)
        if existing:
            if not _ref(env, xid):
                _bind(env, xid, existing)
            if not existing.description:
                existing.write({k: v for k, v in vals.items() if k != 'name'})
            if 'active' in existing._fields and not existing.active:
                existing.active = True
            jobs[xid] = existing
            continue
        jobs[xid] = _get_or_create(env, xid, 'hr.job', vals)
    for job in jobs.values():
        if 'is_published' in job._fields and not job.is_published:
            job.is_published = True
    # 2. sources and tags
    sources = {}
    for name in SOURCES:
        sources[name] = env['utm.source'].search([('name', '=', name)], limit=1) or _get_or_create(
            env, 'rc_rec_src_' + name.lower().replace(' ', '_').replace('-', '_'), 'utm.source', {'name': name})
    tags = {xid: env['hr.applicant.category'].search([('name', '=', name)], limit=1) or _get_or_create(
        env, xid, 'hr.applicant.category', {'name': name, 'color': color}) for xid, name, color in TAGS}
    stages = {s.name: s for s in env['hr.recruitment.stage'].search([])}
    reasons = {r.name: r for r in env['hr.applicant.refuse.reason'].search([])}
    App = env['hr.applicant'].sudo().with_context(**CTX)
    now = fields.Datetime.now()
    created = env['hr.applicant']
    for (xid, name, email, phone, job_xid, stage_name, source, tag_xids, prio, expected, proposed, days,
         reason, interviewer) in APPLICANTS:
        if _ref(env, xid) or job_xid not in jobs:
            continue
        job = jobs[job_xid]
        stage = stages.get('New') if stage_name == 'refused' else stages.get(stage_name)
        if stage_name == 'refused':
            stage = stages.get('Qualification') or stage
        user = _user(env, interviewer)
        vals = {
            'partner_name': name, 'email_from': email, 'partner_phone': phone, 'job_id': job.id,
            'department_id': job.department_id.id, 'stage_id': stage.id if stage else False,
            'source_id': sources[source].id, 'categ_ids': [Command.set([tags[t].id for t in tag_xids])],
            'priority': prio, 'salary_expected': expected, 'user_id': user.id,
            'interviewer_ids': [Command.set(user.ids)],
            'applicant_notes': f'<p>Applied via {source}. Expected salary ₹{expected:,}/month.</p>',
        }
        if 'user_id' not in App._fields:
            vals.pop('user_id')
            vals['recruiter_id'] = user.id
        if proposed:
            vals['salary_proposed'] = proposed
        app = App.create(vals)
        _bind(env, xid, app)
        created |= app
        open_date = now - timedelta(days=days)
        write = {'date_open': open_date, 'date_last_stage_update': open_date + timedelta(days=min(days, 2))}
        app.write(write)
        env.cr.execute("UPDATE hr_applicant SET create_date = %s WHERE id = %s", (open_date, app.id))
        if stage_name == 'refused':
            app.write({'refuse_reason_id': reasons.get(reason, env['hr.applicant.refuse.reason']).id,
                       'active': False, 'refuse_date': open_date + timedelta(days=4)})
        app.message_post(body=f'Applicant screened by {user.name}: {", ".join(tags[t].name for t in tag_xids) or "no tags"}.',
                         message_type='comment', subtype_xmlid='mail.mt_note')
        # interview meetings for interview stages
        if stage_name in ('First Interview', 'Second Interview') and 'calendar.event' in env:
            start = datetime.combine(fields.Date.today() + timedelta(days=(2 if stage_name == 'First Interview' else 4)), time(5, 30))
            ev_vals = {'name': f'Interview: {name} – {job.name}', 'start': start, 'stop': start + timedelta(minutes=45),
                       'user_id': user.id, 'partner_ids': [Command.set(user.partner_id.ids)],
                       'location': 'Resto Cafe, Marine Drive – Manager cabin',
                       'res_model_id': env['ir.model']._get_id('hr.applicant'), 'res_id': app.id}
            if 'applicant_id' in env['calendar.event']._fields:
                ev_vals['applicant_id'] = app.id
            env['calendar.event'].sudo().with_context(**CTX, no_mail_to_attendees=True).create(ev_vals)
    # 3. one hired applicant becomes an employee (joins on the 1st of the current month)
    hired = _ref(env, HIRE_AS_EMPLOYEE)
    if hired and not hired.employee_id and not _ref(env, 'rc_rec_emp_fathima'):
        emp = _get_or_create(env, 'rc_rec_emp_fathima', 'hr.employee', {
            'name': hired.partner_name, 'job_id': hired.job_id.id, 'job_title': hired.job_id.name,
            'department_id': hired.department_id.id, 'work_email': 'fathima.rasheed@restocafe.example.com',
            'mobile_phone': hired.partner_phone,
        })
        hired.employee_id = emp
    _logger.info("Hudson POS: recruitment demo - %s applicants created", len(created))


# --------------------------------------------------------------------------- payroll
WAGES = {  # employee name -> monthly CTC wage (INR)
    'Suresh Kumar': 85000, 'Rahul Nair': 65000, 'Ananya Sharma': 42000, 'Priya Menon': 28000,
    'Mohammed Bilal': 21000, 'Kevin Joseph': 20000, 'Vishnu Kumar': 19500, 'Sneha Pillai': 18000,
    'Arun Varma': 17500, 'Fathima Rasheed': 25000,
}
DEFAULT_WAGE = 18000
BANKS = ['Federal Bank', 'South Indian Bank', 'State Bank of India', 'HDFC Bank']


def _payroll_employees(env):
    """Employees that should be on payroll: the Resto Cafe staff (not Administrator)."""
    emps = env['hr.employee'].search([('name', 'in', list(WAGES))])
    hrp = env['ir.model.data'].search([('module', '=', MODULE), ('model', '=', 'hr.employee'), ('name', '=like', 'rc_hrp_%')])
    emps |= env['hr.employee'].browse(hrp.mapped('res_id')).exists()
    return emps.filtered(lambda e: e.active)


def _prepare_employee(env, emp, struct, idx):
    version = emp.version_id if 'version_id' in emp._fields and emp.version_id else \
        env['hr.version'].search([('employee_id', '=', emp.id)], limit=1, order='id desc')
    if not version:
        return
    wage = WAGES.get(emp.name) or version.wage or DEFAULT_WAGE
    joined = date(2026, fields.Date.today().month, 1) if emp == _ref(env, 'rc_rec_emp_fathima') else date(2025, 4, 1)
    vals = {}
    if not version.wage:
        basic, hra = round(wage * 0.5), round(wage * 0.2)
        vals.update({'wage': wage, 'basic_salary': basic, 'hra': hra, 'fixed_allowance': wage - basic - hra})
    if not version.contract_date_start:
        vals['contract_date_start'] = joined
    if not version.struct_id:
        vals['struct_id'] = struct.id
    # demo: full monthly salary, not pro-rated by biometric attendance
    if 'pay_by_attendance' in version._fields and version.pay_by_attendance:
        vals['pay_by_attendance'] = False
    if 'enable_attendance_threshold' in version._fields and version.enable_attendance_threshold:
        vals['enable_attendance_threshold'] = False
    if vals:
        version.sudo().with_context(**CTX).write(vals)
    wage = version.wage
    evals = {}
    for field, value in (('hds_in_epf_applicable', True), ('hds_in_esic_applicable', wage <= 21000),
                         ('hds_in_pt_applicable', True)):
        if field in emp._fields and emp[field] != value:
            evals[field] = value
    if 'hds_in_pan' in emp._fields and not emp.hds_in_pan:
        # valid PAN format: 5 letters, 4 digits, 1 letter (personal PAN has P as 4th letter)
        evals['hds_in_pan'] = 'A%sCP%s%04d%s' % ('BCDEFGHJKL'[idx % 10], 'KLMNRSTVWX'[emp.id % 10],
                                                 (1000 + emp.id * 37) % 10000, 'ABCDEFGHJK'[(idx + emp.id) % 10])
    if 'hds_in_uan' in emp._fields and not emp.hds_in_uan:
        evals['hds_in_uan'] = '1012%08d' % (emp.id * 7654321 % 10 ** 8)
    if 'hds_in_esic_ip_number' in emp._fields and wage <= 21000 and not emp.hds_in_esic_ip_number:
        evals['hds_in_esic_ip_number'] = '31%08d' % (emp.id * 1357913 % 10 ** 8)
    if evals:
        emp.sudo().with_context(**CTX).write(evals)
    # salary bank account
    if 'bank_account_id' in emp._fields and not emp.bank_account_id and emp.work_contact_id:
        bank_name = BANKS[idx % len(BANKS)]
        PB = env['res.partner.bank'].sudo()
        acc = PB.search([('partner_id', '=', emp.work_contact_id.id)], limit=1)
        if not acc:
            bvals = {'acc_number': '1450%010d' % (emp.id * 97531), 'partner_id': emp.work_contact_id.id}
            if 'bank_name' in PB._fields:
                bvals['bank_name'] = bank_name
            elif 'res.bank' in env and 'bank_id' in PB._fields:
                bank = env['res.bank'].search([('name', '=', bank_name)], limit=1) or env['res.bank'].sudo().create({'name': bank_name})
                bvals['bank_id'] = bank.id
            acc = PB.create(bvals)
        emp.sudo().with_context(**CTX).write({'bank_account_id': acc.id})


def _pay_run(env, xid, name, month_start, validate):
    run = _ref(env, xid)
    if run:
        return run
    Run = env['hr.payslip.run'].sudo().with_context(**CTX)
    month_end = month_start + relativedelta(months=1, days=-1)
    run = _bind(env, xid, Run.create({'name': name, 'date_start': month_start, 'date_end': month_end}))
    run.with_context(**CTX).action_generate_payslips()
    payroll_emps = _payroll_employees(env)
    # the module's generator falls back to the current contract even if it starts after the period
    run.slip_ids.filtered(lambda s: s.employee_id not in payroll_emps or (
        s.contract_id and s.contract_id.contract_date_start and s.contract_id.contract_date_start > month_end)).unlink()
    # inputs: fuel reimbursement for the delivery rider, salary advance recovery for the line cook
    InputType = env['hr.payslip.input.type']
    for emp_name, code, amount, label in (('Arun Varma', 'REIMBURSEMENT', 1250.0, 'Fuel reimbursement – delivery runs'),
                                          ('Vishnu Kumar', 'DEDUCTION', 2000.0, 'Salary advance recovery (1 of 3)')):
        slip = run.slip_ids.filtered(lambda s: s.employee_id.name == emp_name)[:1]
        itype = InputType.search([('code', '=', code)], limit=1)
        if slip and itype and not slip.input_line_ids.filtered(lambda i: i.input_type_id == itype):
            ivals = {'payslip_id': slip.id, 'input_type_id': itype.id, 'amount': amount}
            if 'name' in env['hr.payslip.input']._fields:
                ivals['name'] = label
            env['hr.payslip.input'].sudo().create(ivals)
    run.with_context(**CTX).action_compute_all()
    if validate:
        run.with_context(**CTX, skip_duplicate_check=True).action_batch_validate()
    return run


def _load_payroll(env):
    if 'hr.payslip.run' not in env or 'hr.payroll.structure' not in env:
        return
    struct = env['hr.payroll.structure'].search([('code', '=', 'REGULAR')], limit=1) or \
        env['hr.payroll.structure'].search([], limit=1)
    if not struct:
        return
    company = env.company.sudo()
    cvals = {k: True for k in ('hds_in_epf_applicable', 'hds_in_esic_applicable', 'hds_in_enable_professional_tax')
             if k in company._fields and not company[k]}
    if cvals:
        company.write(cvals)
    for idx, emp in enumerate(_payroll_employees(env)):
        _prepare_employee(env, emp, struct, idx)
    this_month = fields.Date.today().replace(day=1)
    last_month = this_month - relativedelta(months=1)
    _pay_run(env, 'rc_pay_run_last_month', f'{last_month:%B %Y} Payroll – Resto Cafe', last_month, validate=True)
    _pay_run(env, 'rc_pay_run_this_month', f'{this_month:%B %Y} Payroll – Resto Cafe', this_month, validate=False)


# --------------------------------------------------------------------------- entry point
def _purge_demo_mails(env, last_mail_id):
    """Applicant acknowledgements / interview invitations must never reach the demo e-mail addresses."""
    mails = env['mail.mail'].sudo().search([('id', '>', last_mail_id), ('state', 'in', ('outgoing', 'exception')),
                                            ('model', 'in', ('hr.applicant', 'calendar.event', 'hr.payslip', 'hr.payslip.run'))])
    mails.unlink()


def load_recruitment_payroll_suite_demo_data(env):
    env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM mail_mail")
    last_mail_id = env.cr.fetchone()[0]
    for name, step in (('recruitment', _load_recruitment), ('payroll', _load_payroll),
                       ('mail cleanup', lambda e: _purge_demo_mails(e, last_mail_id))):
        try:
            with env.cr.savepoint():
                step(env)
        except Exception as e:
            _logger.exception("Hudson POS: %s demo data failed: %s", name, e)
    _logger.info("Hudson POS: Resto Cafe Recruitment & Payroll demo data loaded.")
