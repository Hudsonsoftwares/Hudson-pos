# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Employee Referral demo data (eh_hr_referral).

The staff referral programme of the Kochi restaurants, cafes and central kitchen. Created
idempotently (xmlids prefixed ``rc_ref_``), only for the current (main Resto Cafe) company:

  * recruitment stage points (New 5, Qualification 10, First / Second Interview 15 / 20,
    Contract Proposal 25, Contract Signed 50) - only written on stages still at 0 points
  * referral target + recruiter on the open job positions (only where still empty)
  * light (less-billable) users for 6 referring employees who had none (Priya Menon, Rahul Nair,
    Thomas Mathew, Mohammed Bilal, Sneha Pillai, Ananya Sharma) - created without invitation e-mail
  * 12 existing applicants tagged as referrals (``ref_user_id``) and 6 new referred applicants,
    across every stage incl. 3 hired and 1 refused referral
  * referral points for every stage each referred applicant has passed (same values the module awards
    on a stage change), plus the 100 point "choose an avatar" bonus for hired referrals
    (with a referral friend avatar set, as the dashboard does)
  * 6 Kerala / restaurant themed rewards and 4 redeemed rewards (never more than the points earned)
  * 4 referral alerts (Christmas & New Year rush, Fort Kochi head barista, cooks, past Onam drive)

Onboarding slides, referral levels and friends need images (binary fields) and are left to the
module's own data. No e-mail is sent: tracking/mail is disabled and any mail.mail queued while
loading is purged.
"""
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_auto_subscribe_no_notify': True, 'mail_notify_noemail': True, 'no_reset_password': True,
       'mail_notrack': True}

STAGE_POINTS = {'New': 5, 'Qualification': 10, 'First Interview': 15, 'Second Interview': 20,
                'Contract Proposal': 25, 'Contract Signed': 50}
AVATAR_BONUS = 100  # same bonus as the dashboard's "choose an avatar" for a hired referral

JOB_TARGETS = {  # job name -> referral target
    'Senior Service Captain & Waiter': 4, 'Senior Delivery Rider': 4, 'Line Cook & Prep Specialist': 3,
    'Server': 3, 'Delivery Rider': 3, 'Head Barista & Cafe Specialist': 2, 'Barista (Part-time)': 2,
    'South Indian Cook': 2, 'Kitchen Helper': 2, 'Tandoor Cook': 1, 'Sous Chef': 1, 'Fleet Logistics Driver': 1,
    'POS Cashier & Receptionist': 1, 'Restaurant General Manager': 1,
}

# employees that get a light user so they can refer friends and use the dashboard
REFERRER_USERS = [
    ('rc_ref_user_priya', 'Priya Menon'), ('rc_ref_user_rahul', 'Rahul Nair'),
    ('rc_ref_user_thomas', 'Thomas Mathew'), ('rc_ref_user_bilal', 'Mohammed Bilal'),
    ('rc_ref_user_sneha', 'Sneha Pillai'), ('rc_ref_user_ananya', 'Ananya Sharma'),
]

# existing applicants (looked up by name) -> referring employee, avatar friend for hired ones
EXISTING_REFERRALS = [
    # key, applicant name, referrer employee, friend xmlid (hired only), note
    ('fathima', 'Fathima Rasheed', 'Priya Menon', 'eh_hr_referral.referral_friend_1',
     'Former colleague of Priya at a Fort Kochi cafe - excellent latte art.'),
    ('anjana', 'Anjana Menon', 'Priya Menon', False, 'Priya\'s neighbour, 2 years at a specialty coffee bar in Kakkanad.'),
    ('sajan', 'Sajan Varghese', 'Rahul Nair', 'eh_hr_referral.referral_friend_2',
     'Rahul worked with Sajan at a Thrissur sadya caterer - appam & stew specialist.'),
    ('lakshmi', 'Lakshmi Priya', 'Rahul Nair', False, 'Recommended by Rahul for the breakfast tiffin counter.'),
    ('vipin', 'Vipin Das', 'Thomas Mathew', False, 'Heavy-vehicle licence, knows every catering venue in Ernakulam.'),
    ('hiba', 'Hiba Fathima', 'Mohammed Bilal', False, 'Banquet experience at a Marine Drive hotel.'),
    ('shahana', 'Shahana Basheer', 'Mohammed Bilal', False, 'Bilal\'s cousin - fluent in Malayalam, Hindi and Arabic.'),
    ('abhijith', 'Abhijith K', 'Mohammed Bilal', False, 'Referred for weekend banquets; not selected.'),
    ('reshma', 'Reshma Nair', 'Sneha Pillai', False, 'Sneha\'s classmate from her hotel-management course.'),
    ('gokul', 'Gokul Suresh', 'Ananya Sharma', False, 'Worked under Ananya at a Lulu Mall food court kitchen.'),
    ('nikhil', 'Nikhil Mohan', 'Administrator', False, 'Owner referral - ran a 120-cover restaurant in Kozhikode.'),
    ('arya', 'Arya Sasidharan', 'Administrator', 'eh_hr_referral.referral_friend_3',
     'Owner referral for the central kitchen.'),
]

NEW_REFERRALS = [
    # key, name, email, phone, job, stage, referrer, days ago, note
    ('rinu', 'Rinu Mathew', 'rinu.mathew@example.com', '+91 94461 22870', 'Barista (Part-time)', 'Qualification',
     'Priya Menon', 6, 'College student, weekend availability - makes a great filter coffee.'),
    ('shibu', 'Shibu Antony', 'shibu.antony@example.com', '+91 98471 30562', 'Tandoor Cook', 'Contract Proposal',
     'Rahul Nair', 15, 'Tandoor & grill cook from a Mattancherry restaurant, referred by Rahul.'),
    ('aiswarya', 'Aiswarya Gopal', 'aiswarya.gopal@example.com', '+91 90612 44718', 'Server', 'First Interview',
     'Thomas Mathew', 9, 'Hospitality diploma, worked the Biennale cafe last season.'),
    ('jasna', 'Jasna Shereef', 'jasna.shereef@example.com', '+91 81370 55209', 'Delivery Rider', 'Qualification',
     'Sneha Pillai', 5, 'Own two-wheeler and licence; knows Edappally - Kaloor routes.'),
    ('sandeep', 'Sandeep Nair', 'sandeep.nair@example.com', '+91 97785 61034', 'Barista (Part-time)', 'New',
     'Anil Raj', 2, 'Anil\'s cousin, trained at a Kochi coffee academy.'),
    ('ajith', 'Ajith Kumar', 'ajith.kumar@example.com', '+91 96051 72431', 'Kitchen Helper', 'New',
     'Deepak Menon', 1, 'Referred by Deepak for the central kitchen dish & prep station.'),
]

REWARDS = [  # xid, name, cost, description
    ('rc_ref_reward_movie', 'Movie Tickets for Two (PVR Lulu Mall)', 100,
     '<p>Two recliner tickets + popcorn combo at PVR Lulu Mall, Edappally.</p>'),
    ('rc_ref_reward_coffee', 'Malabar Coffee Hamper', 150,
     '<p>1 kg single-estate Wayanad Arabica, a brass filter-coffee set and banana chips from our bakery.</p>'),
    ('rc_ref_reward_amazon', 'Amazon Gift Voucher - INR 1,000', 200,
     '<p>Digital Amazon.in gift card worth &#8377;1,000, sent to your work e-mail.</p>'),
    ('rc_ref_reward_dinner', 'Family Dinner Voucher (4 guests)', 250,
     '<p>Dinner for four at our MG Road restaurant - Kerala seafood platter, appam & dessert included.</p>'),
    ('rc_ref_reward_dayoff', 'Extra Paid Day Off', 300,
     '<p>One additional paid leave day, to be planned with your outlet manager.</p>'),
    ('rc_ref_reward_houseboat', 'Alleppey Houseboat Day Cruise for Two', 600,
     '<p>Day cruise on the Alappuzha backwaters with traditional Kerala lunch on board.</p>'),
]

REDEMPTIONS = [  # xid, employee, reward xid
    ('rc_ref_log_priya_coffee', 'Priya Menon', 'rc_ref_reward_coffee'),
    ('rc_ref_log_rahul_dinner', 'Rahul Nair', 'rc_ref_reward_dinner'),
    ('rc_ref_log_thomas_movie', 'Thomas Mathew', 'rc_ref_reward_movie'),
    ('rc_ref_log_admin_movie', 'Administrator', 'rc_ref_reward_movie'),
]


def _ref(env, xid):
    return env.ref(xid if '.' in xid else f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals, search=None):
    rec = _ref(env, xid)
    if rec:
        return rec
    if search:
        rec = env[model].sudo().with_context(active_test=False).search(search, limit=1)
        if rec:
            return _bind(env, xid, rec)
    return _bind(env, xid, env[model].sudo().with_context(**CTX).create(vals))


def _slug(name):
    return ''.join(c if c.isalnum() else '_' for c in (name or '').lower()).strip('_')


def load_referral_suite_demo_data(env):
    if 'eh.hr.referral.alert' not in env or 'hr.applicant' not in env:
        _logger.info("Employee Referral (eh_hr_referral) not installed - skipping referral demo data")
        return
    company = env.company
    co_domain = [('company_id', 'in', (company.id, False))]
    Employee = env['hr.employee'].sudo()
    Applicant = env['hr.applicant'].sudo().with_context(active_test=False, **CTX)
    Points = env['eh.hr.referral.points'].sudo().with_context(**CTX)
    last_mail = env['mail.mail'].sudo().search([], order='id desc', limit=1).id or 0
    points_before = Points.search_count([('company_id', '=', company.id)])
    today = fields.Date.context_today(env['res.users'].sudo().browse(env.uid))
    admin = env.ref('base.user_admin', raise_if_not_found=False) or env.user
    stats = dict.fromkeys(('stages', 'jobs', 'users', 'applicants', 'new_applicants', 'points', 'rewards',
                           'logs', 'alerts'), 0)

    def emp(name):
        return Employee.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)

    def job(name):
        return env['hr.job'].sudo().search([('name', '=', name)] + co_domain, limit=1)

    # 1. stage points (do not override a configuration made by the user)
    stages = env['hr.recruitment.stage'].sudo().search(co_domain, order='sequence, id')
    for stage in stages:
        if not stage.points and STAGE_POINTS.get(stage.name):
            try:
                with env.cr.savepoint():
                    stage.with_context(**CTX).write({'points': STAGE_POINTS[stage.name]})
                    stats['stages'] += 1
            except Exception as e:
                _logger.warning("Referral demo: could not set points on stage %s: %s", stage.name, e)

    # 2. referral targets / recruiter on the job positions
    for name, target in JOB_TARGETS.items():
        j = job(name)
        if not j:
            continue
        vals = {}
        if not j.referral_target:
            vals['referral_target'] = target
        if not j.referral_recruiter_id:
            vals['referral_recruiter_id'] = admin.id
        if vals:
            try:
                with env.cr.savepoint():
                    j.with_context(**CTX).write(vals)
                    stats['jobs'] += 1
            except Exception as e:
                _logger.warning("Referral demo: could not update job %s: %s", name, e)

    # 3. light users for the referring employees (no invitation e-mail)
    for xid, name in REFERRER_USERS:
        employee = emp(name)
        user = _ref(env, xid)
        if user and user.exists():
            if employee and not employee.user_id:
                employee.with_context(bin_size=True, **CTX).write({'user_id': user.id})
            continue
        if not employee:
            continue
        try:
            with env.cr.savepoint():
                if employee.user_id:
                    _bind(env, xid, employee.user_id)
                    continue
                user = employee.with_context(**CTX)._get_or_create_light_user()
                if not user.share:
                    # bin_size: the employee already has an avatar, so no picture is copied from the user
                    employee.with_context(bin_size=True, **CTX).write({'user_id': user.id})
                    _bind(env, xid, user)
                    stats['users'] += 1
        except Exception as e:
            _logger.warning("Referral demo: could not create a user for %s: %s", name, e)

    def referrer_user(name):
        employee = emp(name)
        if employee and employee.user_id and not employee.user_id.share:
            return employee.user_id
        for xid, rname in REFERRER_USERS:
            if rname == name:
                u = _ref(env, xid)
                if u and u.exists() and not u.share:
                    if employee and not employee.user_id:
                        employee.with_context(bin_size=True, **CTX).write({'user_id': u.id})
                    return u
        return False

    source = env['utm.source'].sudo().search([('name', '=', 'Employee Referral')], limit=1)

    def award(key, applicant):
        """Points for every stage the applicant has passed, as the module awards them on stage change."""
        current = applicant.stage_id
        if not applicant.ref_user_id or not current:
            return
        job_stages = stages.filtered(lambda s: not s.job_ids or applicant.job_id in s.job_ids)
        for stage in job_stages.filtered(lambda s: (s.sequence, s.id) < (current.sequence, current.id)):
            if stage.points <= 0:
                continue
            xid = f'rc_ref_pts_{key}_{_slug(stage.name)}'
            if _ref(env, xid):
                continue
            existing = Points.search([('applicant_id', '=', applicant.id), ('stage_id', '=', stage.id)], limit=1)
            if not existing:
                existing = Points.create({
                    'user_id': applicant.ref_user_id.id, 'points': stage.points, 'company_id': company.id,
                    'applicant_id': applicant.id, 'stage_id': stage.id,
                })
            _bind(env, xid, existing)
        # current stage: the module's own method (it skips stages already awarded)
        xid = f'rc_ref_pts_{key}_{_slug(current.name)}'
        if not _ref(env, xid):
            applicant._award_referral_points()
            row = Points.search([('applicant_id', '=', applicant.id), ('stage_id', '=', current.id)], limit=1)
            if row:
                _bind(env, xid, row)

    def avatar_bonus(key, applicant, friend_xid):
        if not friend_xid or not applicant.stage_id.hired_stage:
            return
        friend = env.ref(friend_xid, raise_if_not_found=False)
        if friend and not applicant.friend_id:
            applicant.write({'friend_id': friend.id})
        xid = f'rc_ref_pts_{key}_avatar'
        if not _ref(env, xid):
            row = Points.search([('applicant_id', '=', applicant.id), ('stage_id', '=', False)], limit=1)
            if not row:
                row = Points.create({'user_id': applicant.ref_user_id.id, 'points': AVATAR_BONUS,
                                     'company_id': company.id, 'applicant_id': applicant.id})
            _bind(env, xid, row)

    # 4. existing applicants marked as referrals
    for key, app_name, referrer, friend_xid, note in EXISTING_REFERRALS:
        try:
            with env.cr.savepoint():
                xid = f'rc_ref_app_{key}'
                applicant = _ref(env, xid)
                if not applicant:
                    applicant = Applicant.search([('partner_name', '=', app_name), ('company_id', '=', company.id)],
                                                 limit=1)
                    if not applicant:
                        continue
                    _bind(env, xid, applicant)
                if not applicant.ref_user_id:
                    user = referrer_user(referrer)
                    if not user:
                        _logger.warning("Referral demo: no user for referrer %s", referrer)
                        continue
                    vals = {'ref_user_id': user.id}
                    if source:
                        vals['source_id'] = source.id
                    if note and 'applicant_notes' in applicant._fields:
                        vals['applicant_notes'] = (applicant.applicant_notes or '') + f'<p>Referral: {note}</p>'
                    applicant.write(vals)
                    stats['applicants'] += 1
                award(key, applicant)
                avatar_bonus(key, applicant, friend_xid)
        except Exception as e:
            _logger.warning("Referral demo: could not tag applicant %s: %s", app_name, e)

    # 5. new referred applicants (the module awards the current stage on create)
    stage_by_name = {s.name: s for s in stages}
    now = fields.Datetime.now()
    for key, name, email, phone, job_name, stage_name, referrer, days, note in NEW_REFERRALS:
        xid = f'rc_ref_app_{key}'
        if _ref(env, xid):
            continue
        j, stage, user = job(job_name), stage_by_name.get(stage_name), referrer_user(referrer)
        if not j or not stage or not user:
            _logger.warning("Referral demo: missing job/stage/referrer for %s", name)
            continue
        try:
            with env.cr.savepoint():
                vals = {
                    'partner_name': name, 'email_from': email, 'partner_phone': phone, 'job_id': j.id,
                    'department_id': j.department_id.id, 'stage_id': stage.id, 'company_id': company.id,
                    'ref_user_id': user.id, 'source_id': source.id if source else False,
                    'applicant_notes': f'<p>Referred by {referrer}: {note}</p>',
                }
                applicant = _bind(env, xid, Applicant.create(vals))
                open_date = now - timedelta(days=days)
                applicant.write({'date_open': open_date, 'date_last_stage_update': open_date + timedelta(days=min(days, 3))})
                env.cr.execute("UPDATE hr_applicant SET create_date = %s WHERE id = %s", (open_date, applicant.id))
                stats['new_applicants'] += 1
                award(key, applicant)
        except Exception as e:
            _logger.warning("Referral demo: could not create applicant %s: %s", name, e)

    # 6. rewards
    for xid, name, cost, description in REWARDS:
        try:
            with env.cr.savepoint():
                if not _ref(env, xid):
                    _get_or_create(env, xid, 'eh.hr.referral.reward', {
                        'name': name, 'cost': cost, 'description': description, 'company_id': company.id,
                        'gift_responsible_id': admin.id,
                    }, search=[('name', '=', name)] + co_domain)
                    stats['rewards'] += 1
        except Exception as e:
            _logger.warning("Referral demo: could not create reward %s: %s", name, e)

    # 7. redeemed rewards - only when the employee has earned enough points (as action_buy_reward checks)
    Log = env['eh.hr.referral.reward.log'].sudo()
    for xid, emp_name, reward_xid in REDEMPTIONS:
        if _ref(env, xid):
            continue
        employee, reward = emp(emp_name), _ref(env, reward_xid)
        if not employee or not employee.user_id or not reward:
            continue
        earned = sum(Points.search([('user_id', '=', employee.user_id.id)]).mapped('points'))
        spent = sum(Log.search([('employee_id', '=', employee.id)]).mapped('points'))
        if earned - spent < reward.cost:
            _logger.warning("Referral demo: %s has not enough points for %s", emp_name, reward.name)
            continue
        try:
            with env.cr.savepoint():
                _bind(env, xid, Log.with_context(**CTX).create({'employee_id': employee.id, 'reward_id': reward.id}))
                stats['logs'] += 1
        except Exception as e:
            _logger.warning("Referral demo: could not log reward %s: %s", xid, e)

    # 8. alerts on the referral dashboard
    barista = job('Head Barista & Cafe Specialist')
    alerts = [
        ('rc_ref_alert_xmas', 'Christmas & New Year catering rush: we urgently need line cooks, servers and '
                              'delivery riders - refer a friend today!', today - timedelta(days=2),
         today + timedelta(days=45), 'all_jobs', False),
        ('rc_ref_alert_barista', 'Opening soon in Fort Kochi: refer a passionate Head Barista for our new '
                                 'specialty coffee cafe', today - timedelta(days=1), today + timedelta(days=30),
         'url' if barista else 'all_jobs', f'/jobs/detail/{barista.id}' if barista else False),
        ('rc_ref_alert_cooks', 'Know a great tandoor or South Indian cook? Every hired referral = 125 points '
                               '+ 100 avatar bonus', False, False, 'not_clickable', False),
        ('rc_ref_alert_onam', 'Onam sadya season: urgent hiring of 25 temporary catering staff (closed)',
         today - timedelta(days=110), today - timedelta(days=70), 'all_jobs', False),
    ]
    for xid, name, dfrom, dto, on_click, url in alerts:
        try:
            with env.cr.savepoint():
                if not _ref(env, xid):
                    _get_or_create(env, xid, 'eh.hr.referral.alert', {
                        'name': name, 'date_from': dfrom, 'date_to': dto, 'on_click': on_click, 'url': url,
                        'company_id': company.id,
                    })
                    stats['alerts'] += 1
        except Exception as e:
            _logger.warning("Referral demo: could not create alert %s: %s", xid, e)

    # never send anything queued while loading (stage templates, invitations...)
    queued = env['mail.mail'].sudo().search([('id', '>', last_mail)])
    if queued:
        queued.unlink()
    stats['points'] = Points.search_count([('company_id', '=', company.id)]) - points_before
    _logger.info("Referral demo: %s (%s queued mails purged)", stats, len(queued))
    return stats
