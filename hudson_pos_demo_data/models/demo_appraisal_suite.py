# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Appraisals demo data (eh_hr_appraisal).

Performance reviews of the kitchen, bar, service, delivery and accounts teams of the Kochi restaurant
and Central Kitchen. Created idempotently (xmlids prefixed ``rc_apr_``), only for the current company:

  * 8 goal tags (Food Quality, Hygiene & FSSAI, Guest Experience, Speed of Service, Upselling,
    Cost Control, Leadership, Training)
  * 11 goal templates in the Goals Library (KDS ticket time, FSSAI audit with 2 sub-goals, latte art
    certification, dessert upselling, food-waste reduction, mentoring, ratings, delivery, month-end close)
  * 2 restaurant appraisal templates with tailored employee / manager questions
    (Kitchen & Culinary Review, Front of House Review); other departments keep the module's Default
  * 15 appraisals in every state, with dates relative to today:
      - 7 Done (last annual cycle ~6 months ago, plus a 6-month probation review last month) with
        filled and shared feedback, a private note and a final rating from the Evaluation Scale
      - 5 Confirmed (current cycle; one overdue) with self-assessments in progress
      - 2 To Confirm (next cycle, template questions only)
      - 1 Cancelled (seasonal cashier whose contract ended)
  * ~35 goals linked to their appraisals with progress 0-100 %, deadlines and tags (some late)
  * skills evaluated in Done / Confirmed appraisals (loaded from the employee's skills, with
    previous levels, proposed levels and justifications, plus soft skills)
  * 360 feedback answers (survey.user_input on the module's "Employee Opinion Form"), done and pending
  * appraisal meetings (calendar.event linked to the appraisal) for confirmed reviews

States are written directly instead of action_confirm / action_done: confirmation posts a notification
to the employees, and Mark as Done would write the appraised skill levels back onto the employees.
Any mail.mail queued while loading is purged. Images are not touched.
"""
import logging
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
TZ = pytz.timezone('Asia/Kolkata')
CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_auto_subscribe_no_notify': True, 'mail_notify_noemail': True, 'no_mail_to_attendees': True,
       'mail_notrack': True}

# ---------------------------------------------------------------------------------------------------
# Goal tags & goals library
# ---------------------------------------------------------------------------------------------------
TAGS = [  # xid, name, color
    ('rc_apr_tag_food_quality', 'Food Quality', 2),
    ('rc_apr_tag_hygiene', 'Hygiene & FSSAI', 10),
    ('rc_apr_tag_guest', 'Guest Experience', 4),
    ('rc_apr_tag_speed', 'Speed of Service', 3),
    ('rc_apr_tag_upsell', 'Upselling', 5),
    ('rc_apr_tag_cost', 'Cost Control', 1),
    ('rc_apr_tag_leadership', 'Leadership', 9),
    ('rc_apr_tag_training', 'Training', 7),
]

GOAL_TEMPLATES = [  # xid, name, timing (months), tags, skills, description, parent
    ('rc_apr_gt_kds', 'Reduce ticket time to under 12 min on KDS', 3, ['speed', 'food_quality'], [],
     '<p>Average bump time per ticket on the Kitchen Display below <strong>12 minutes</strong> during lunch '
     'and dinner service, measured from the weekly KDS report. Mise en place complete before 11:30 and 18:30.</p>', None),
    ('rc_apr_gt_fssai', 'Pass FSSAI audit with zero major findings', 6, ['hygiene'], ['FSSAI Food Safety Supervisor (FoSTaC)'],
     '<p>Licence renewal inspection by the Commissionerate of Food Safety with <strong>no major non-conformity</strong>: '
     'temperature logs, pest control, labelling (FIFO / use-by), personal hygiene and water test reports.</p>', None),
    ('rc_apr_gt_fssai_logs', 'Daily temperature & cleaning logs 100% complete', 1, ['hygiene'], [],
     '<p>Cold room, chillers and hot-holding logs filled twice per shift, signed by the shift lead.</p>', 'rc_apr_gt_fssai'),
    ('rc_apr_gt_fssai_deep', 'Monthly deep-clean & pest-control checklist signed off', 1, ['hygiene'], [],
     '<p>Hood filters, drains and dry store deep-cleaned; pest-control vendor report filed every month.</p>', 'rc_apr_gt_fssai'),
    ('rc_apr_gt_latte', 'Latte art certification (Barista Skills Intermediate)', 4, ['training', 'food_quality'],
     ['Barista & Latte Art'],
     '<p>Pass the intermediate barista course: consistent microfoam, rosetta and tulip on 8 oz cups, '
     'espresso dialled-in every morning (18 g in / 36 g out, 27-30 s).</p>', None),
    ('rc_apr_gt_dessert', 'Upsell desserts to 25% of tables', 3, ['upsell', 'guest'], ['Persuasion'],
     '<p>Suggest the dessert of the day (elaneer payasam, tender coconut pudding, brownie sizzler) to every table. '
     'Target: dessert ordered on <strong>25%</strong> of dine-in bills, tracked from POS reports.</p>', None),
    ('rc_apr_gt_waste', 'Cut food waste by 10%', 6, ['cost', 'food_quality'], [],
     '<p>Weigh and log pre- and post-consumer waste daily. Reduce the monthly waste value by <strong>10%</strong> '
     'versus the last quarter through batch cooking, FIFO and reuse of trimmings in staff meals.</p>', None),
    ('rc_apr_gt_mentor', 'Mentor a new team member through onboarding', 3, ['leadership', 'training'], ['Leadership'],
     '<p>Buddy a new joiner for the first 30 days: station walk-through, recipe cards, hygiene SOPs and a '
     'sign-off checklist reviewed with the manager.</p>', None),
    ('rc_apr_gt_rating', 'Keep a 4.5+ guest rating for your section', 6, ['guest'], [],
     '<p>Average Google / Zomato rating of 4.5 or more on reviews mentioning your section; '
     'every complaint closed the same day with the outlet manager.</p>', None),
    ('rc_apr_gt_delivery', 'On-time delivery rate above 95%', 3, ['speed', 'guest'], [],
     '<p>Orders delivered within the promised slot on <strong>95%</strong> of trips; insulated bags and seals checked '
     'before every dispatch.</p>', None),
    ('rc_apr_gt_close', 'Close month-end books by the 5th working day', 3, ['cost'], [],
     '<p>POS sessions reconciled daily, vendor bills and GST input matched, P&amp;L per outlet shared with '
     'the General Manager by the 5th working day.</p>', None),
]


def _qa_template(questions):
    """Template body: headings with an empty paragraph to answer."""
    html = '<div>'
    for title, hint in questions:
        html += f'<h3>{title}</h3><p><em>{hint}</em></p><p><br></p>'
    return html + '</div>'


def _qa(pairs):
    """Filled feedback: question headings with the answers."""
    html = '<div>'
    for title, answer in pairs:
        html += f'<h3>{title}</h3><p>{answer}</p>'
    return html + '</div>'


KITCHEN_EMP_Q = [
    ('What am I most proud of in the kitchen since my last review?', 'A dish, a service or an improvement you made.'),
    ('How have I kept my station hygienic and FSSAI-ready?', 'Temperature logs, labelling, personal hygiene, cleaning.'),
    ('Which dishes or techniques do I want to master next?', 'Cuisine, station or equipment you would like to learn.'),
    ('What would help me work better?', 'Equipment, prep lists, rota, training, support from the team.'),
]
KITCHEN_MGR_Q = [
    ('Food quality & consistency', 'Taste, portioning and plating against the recipe cards.'),
    ('Hygiene, FSSAI & HACCP discipline', 'Logs, storage, cross-contamination, grooming.'),
    ('Speed on the pass / KDS ticket times', 'Behaviour during lunch and dinner rush.'),
    ('Teamwork & attitude', 'Support to colleagues, communication with service, punctuality.'),
    ('Development plan for the next 6 months', 'Training, station rotation, responsibilities.'),
]
FOH_EMP_Q = [
    ('Which guest moments am I proud of?', 'A compliment, a recovered complaint, a special occasion you handled.'),
    ('How do I use menu knowledge to recommend and upsell?', 'Desserts, beverages, combos, specials of the day.'),
    ('What is hardest for me during peak hours?', 'Table turns, order taking, coordination with the kitchen or bar.'),
    ('What training or support do I need?', 'Coffee, wine, POS, languages, grooming, leadership.'),
]
FOH_MGR_Q = [
    ('Guest experience & reviews', 'Warmth, attentiveness, handling of complaints, online reviews.'),
    ('Speed of service & table turns', 'Order-to-table time, coordination with KDS and bar.'),
    ('Upselling & average bill', 'Dessert / beverage attach rate from POS reports.'),
    ('POS accuracy, cash handling & grooming', 'Voids, cash differences, uniform and punctuality.'),
    ('Next steps', 'Objectives and support for the coming cycle.'),
]
DEFAULT_EMP_Q = [  # short form of the module's Default template, used for filled answers
    ('What are my most important achievements since my last appraisal?', ''),
    ('What has been the most challenging aspect of my work, and why?', ''),
    ('What do I need to improve my work?', ''),
    ('What are my short- and long-term goals?', ''),
]
DEFAULT_MGR_Q = [
    ('Give one positive achievement that convinced you of the employee\'s value.', ''),
    ('Evaluation (stress resistance, time management, teamwork, autonomy, proactivity)', ''),
    ('How could the employee improve?', ''),
    ('Long term career discussion', ''),
]

APPRAISAL_TEMPLATES = [  # xid, name, departments, employee questions, manager questions
    ('rc_apr_tpl_kitchen', 'Kitchen & Culinary Review', ['Kitchen & Culinary'], KITCHEN_EMP_Q, KITCHEN_MGR_Q),
    ('rc_apr_tpl_foh', 'Front of House Review', ['Service & Hospitality', 'Bar & Cafe'], FOH_EMP_Q, FOH_MGR_Q),
]
QUESTIONS = {
    'kitchen': (KITCHEN_EMP_Q, KITCHEN_MGR_Q),
    'foh': (FOH_EMP_Q, FOH_MGR_Q),
    'default': (DEFAULT_EMP_Q, DEFAULT_MGR_Q),
}

SCALE = {
    'ni': 'eh_hr_appraisal.hr_appraisal_scale_needs_improvement',
    'me': 'eh_hr_appraisal.hr_appraisal_scale_meets_expectations',
    'ee': 'eh_hr_appraisal.hr_appraisal_scale_exceeds_expectations',
    'se': 'eh_hr_appraisal.hr_appraisal_scale_strongly_exceeds_expectations',
}
SCALE_NAMES = {'ni': 'Needs improvement', 'me': 'Meets expectations', 'ee': 'Exceeds expectations',
               'se': 'Strongly Exceeds Expectations'}

# ---------------------------------------------------------------------------------------------------
# Appraisals. emp = (name, job) - two employees are called Fathima Rasheed.
# date = months offset from today (+ days), done = days after date_appraisal the review was closed.
# skills: {skill: (current level, previous level or None, justification)} on the loaded skill lines
# extra_skills: [(skill type, skill, level, justification)] added on top (soft skills)
# goals: (xid, name, tags, progress, deadline in months from today, description, goal template xid)
# fb360: (xid, colleague, done?, strengths, improvements, collaboration 1-4, comments)
# ---------------------------------------------------------------------------------------------------
APPRAISALS = [
    # ---------------- Done - last annual cycle
    dict(xid='rc_apr_a01', emp=('Vishnu Kumar', 'Line Cook & Prep Specialist'), state='done', months=-6, days=-10, done=4,
         tpl='kitchen', rating='ee',
         ef=['Ran the grill station alone for the whole Onam week (1,100 covers a day) without a single return from the pass.',
             'Temperature logs filled every shift, all marinated meats labelled with prep and use-by dates; cleaned the '
             'grill hood filters every Sunday.',
             'Tandoor with Manoj chetan and the new Indo-Chinese wok station.',
             'A second blast chiller would save a lot of time during evening prep.'],
         mf=['Consistent, tasty and well portioned: food-cost variance on his station is the lowest in the kitchen.',
             'Very disciplined - FIFO and labelling are a model for the new joiners.',
             'Ticket times on the grill average 11 minutes, under the 12-minute target.',
             'Always first to help the pastry corner when it is short-staffed. Punctual.',
             'Cross-train on Tandoor (target Skilled), then cover the Sous Chef on weekends.'],
         private='<p>Recommended for a 10% increment and the weekend shift-lead allowance.</p>',
         skills={'Grill & Barbecue': ('Competent', 'Trainee', 'Handled the Onam rush alone on the grill.')},
         extra_skills=[('Soft Skills', 'Teamwork', 'Advanced', 'Covers other stations without being asked.')],
         goals=[('rc_apr_g01', 'Reduce ticket time to under 12 min on KDS', ['speed', 'food_quality'], '100', -7,
                 None, 'rc_apr_gt_kds'),
                ('rc_apr_g02', 'Cut food waste by 10%', ['cost'], '100', -6, None, 'rc_apr_gt_waste')]),
    dict(xid='rc_apr_a02', emp=('Manoj Pillai', 'Tandoor Cook'), state='done', months=-6, days=-8, done=3,
         tpl='kitchen', rating='se',
         ef=['Launched the new tandoori platter and the Malabar-style kebab range - now 18% of dinner sales.',
             'Tandoor area cleaned and ash removed after every service, raw and cooked marinades in separate colour-coded tubs.',
             'Would like to learn charcoal grilling for the planned rooftop barbecue nights.',
             'A dedicated helper for the tandoor between 19:00 and 22:00.'],
         mf=['Outstanding - the platter has 4.7 stars on Zomato and guests ask for "Manoj\'s kebabs".',
             'Zero findings on his station during the FSSAI inspection.',
             'Breads leave the tandoor within 6 minutes even on Saturday nights.',
             'Patiently trained Ajay on the tandoor; calm under pressure.',
             'Lead the rooftop barbecue nights; mentor Ajay to Competent on Tandoor.'],
         private='<p>Top performer of the cycle. Propose promotion to Chef de Partie - Tandoor & Grill.</p>',
         skills={'Tandoor': ('Master', 'Skilled', 'Created and standardised the tandoori platter.')},
         extra_skills=[('Soft Skills', 'Leadership', 'Intermediate', 'Trains Ajay on the tandoor.')],
         goals=[('rc_apr_g03', 'Launch a tandoori platter on the dinner menu', ['food_quality', 'upsell'], '100', -7,
                 '<p>Recipe cards, plating photo and costing approved by the Head Chef.</p>', None),
                ('rc_apr_g04', 'Pass FSSAI audit with zero major findings', ['hygiene'], '100', -6, None, 'rc_apr_gt_fssai')]),
    dict(xid='rc_apr_a03', emp=('Anjali Das', 'Barista (Part-time)'), state='done', months=-5, days=-20, done=5,
         tpl='foh', rating='me',
         ef=['A regular guest posted my rosetta on Instagram and tagged the cafe - 2,000 likes!',
             'I always suggest a cookie or brownie with the coffee, mostly in the evenings.',
             'Saturday mornings when the dine-in and the Swiggy orders come together.',
             'Latte art course and help with milk steaming for oat milk.'],
         mf=['Friendly and well liked by the regulars; remembers names and usual orders.',
             'Drinks sometimes wait on the bar during rush - needs to sequence the orders on the KDS.',
             'Food attach rate on coffee orders 14%, team average 18%.',
             'POS voids within limits; grooming always correct.',
             'Enrol in the latte art certification and practise espresso calibration with Priya every morning.'],
         private='<p>Keep on part-time contract; review full-time conversion after the certification.</p>',
         skills={'Barista & Latte Art': ('Competent', 'Trainee', 'Can now pour a consistent heart and rosetta.')},
         extra_skills=[('Soft Skills', 'Communication', 'Advanced', 'Very good rapport with regular guests.')],
         goals=[('rc_apr_g05', 'Pour a consistent rosetta on every latte', ['food_quality', 'training'], '100', -6, None, None),
                ('rc_apr_g06', 'Sell a bakery item with 20% of coffee orders', ['upsell'], '75', -5,
                 '<p>Reached 17% - carried over to the next cycle.</p>', None)]),
    dict(xid='rc_apr_a04', emp=('Mohammed Bilal', 'Senior Service Captain & Waiter'), state='done', months=-6, days=-5, done=2,
         tpl='foh', rating='ee',
         ef=['Handled the 350-guest Varghese wedding reception service - not one table waited more than 10 minutes for the sadya.',
             'I brief the servers on the specials and the dessert of the day at every pre-shift meeting.',
             'Coordinating the kitchen pass and the floor when we are two servers short.',
             'A wine & spirits service course before the bar licence comes in.'],
         mf=['Guests and corporate clients ask for him by name; 23 five-star reviews mention "Bilal".',
             'Table turn on his section is 52 min at lunch versus 60 min for the floor.',
             'His section has the best dessert attach rate (22%).',
             'Zero cash differences in 12 months; always immaculate.',
             'Train two servers in upselling; prepare for the Floor Manager role.'],
         private='<p>Succession candidate for Outlet Manager. Increment 12%.</p>',
         skills={},
         extra_skills=[('Soft Skills', 'Leadership', 'Advanced', 'Runs pre-shift briefings and the floor at events.'),
                       ('Soft Skills', 'Conflict Management', 'Advanced', 'Recovers unhappy guests with tact.')],
         goals=[('rc_apr_g07', 'Keep a 4.5+ guest rating for your section', ['guest'], '100', -6, None, 'rc_apr_gt_rating'),
                ('rc_apr_g08', 'Mentor a new team member through onboarding', ['leadership', 'training'], '100', -7,
                 '<p>Nikhil Raj onboarded and signed off.</p>', 'rc_apr_gt_mentor')],
         fb360=[('rc_apr_fb01', ('Nikhil Raj', 'Server'), True, 'Calm during the rush and always explains why, not just what.',
                 'Could delegate more instead of running every big table himself.', 4,
                 'Best captain I have worked with.'),
                ('rc_apr_fb02', ('Sneha Pillai', 'POS Cashier & Receptionist'), True,
                 'Bills are always correct, KOTs are clear and he closes tables quickly.',
                 'Sometimes forgets to update reservations in the system.', 3, '')]),
    dict(xid='rc_apr_a05', emp=('Arun Varma', 'Senior Delivery Rider'), state='done', months=-6, days=-3, done=6,
         tpl='default', rating='me',
         ef=['Planned the Kakkanad-Edappally routes for the corporate lunch boxes - 220 meals delivered before 12:45 daily.',
             'Monsoon flooding in Kaloor made deliveries very difficult in June and July.',
             'Rain gear for the team and a second insulated bag per bike.',
             'Become fleet supervisor and handle the catering van logistics.'],
         mf=['Reliable and knows every lane of Kochi; the corporate client renewed the contract.',
             'Stress resistance good, time management good, teamwork good, autonomy very good, proactivity average.',
             'Needs to report bike maintenance issues before they cause delays.',
             'Fleet supervisor path within a year if the delivery KPIs hold.'],
         private='<p>Increment 8%.</p>',
         skills={},
         extra_skills=[('Soft Skills', 'Time Management', 'Advanced', 'Corporate lunch boxes always before 12:45.')],
         goals=[('rc_apr_g09', 'On-time delivery rate above 95%', ['speed', 'guest'], '100', -6, None, 'rc_apr_gt_delivery'),
                ('rc_apr_g10', 'Weekly bike maintenance checklist for the fleet', ['cost'], '50', -5, None, None)]),
    dict(xid='rc_apr_a06', emp=('Lakshmi Iyer', 'Accountant'), state='done', months=-6, days=-1, done=5,
         tpl='default', rating='ee',
         ef=['Migrated the POS session reconciliation to daily and cut cash differences by 70%.',
             'GST annual return with the new e-invoicing rules for catering invoices.',
             'An Odoo accounting refresher and a shared folder for vendor bills.',
             'Take over payroll next year and qualify as CMA.'],
         mf=['The month-end close moved from the 12th to the 6th working day.',
             'Excellent time management and autonomy; very good teamwork with the outlet managers.',
             'Present the P&L in simpler terms to the kitchen team.',
             'Supports her CMA studies; payroll handover planned.'],
         private='<p>Increment 10% + exam leave for the CMA intermediate.</p>',
         skills={},
         extra_skills=[('Soft Skills', 'Organizational', 'Expert', 'Daily POS reconciliation process set up.')],
         goals=[('rc_apr_g11', 'Close month-end books by the 5th working day', ['cost'], '75', -6,
                 '<p>Down to the 6th working day - one more day to gain.</p>', 'rc_apr_gt_close'),
                ('rc_apr_g12', 'Daily POS cash reconciliation for all outlets', ['cost'], '100', -8, None, None)]),
    # ---------------- Done - 6-month review last month
    dict(xid='rc_apr_a07', emp=('Reshma Babu', 'Server'), state='done', months=-1, days=-5, done=3,
         tpl='foh', rating='ni', next_months=3,  # improvement plan: re-evaluated in 3 months
         ef=['A family thanked me for organising a surprise birthday cake for their grandmother.',
             'I am still learning the menu, especially the seafood specials.',
             'Remembering modifiers and entering them correctly on the POS.',
             'Menu training and English speaking practice.'],
         mf=['Warm with guests, but two complaints for wrong orders this quarter.',
             'Order-to-table time is above the floor average; orders are entered late on the POS.',
             'Dessert attach rate 6% - needs to suggest desserts proactively.',
             'Four voids in September due to wrong modifiers.',
             'Menu test with Bilal every Monday, POS refresher with Sneha, review again in 3 months.'],
         private='<p>Improvement plan agreed - re-evaluate in 3 months before confirming the role.</p>',
         skills={'English': ('B1', None, 'Improving with daily guest interaction.')},
         extra_skills=[],
         goals=[('rc_apr_g13', 'Pass the menu knowledge test (90%)', ['training', 'guest'], '50', 1,
                 '<p>Written and oral test on allergens, spice levels and the seafood specials.</p>', None),
                ('rc_apr_g14', 'Upsell desserts to 25% of tables', ['upsell'], '25', 2, None, 'rc_apr_gt_dessert')]),
    # ---------------- Confirmed - current cycle
    dict(xid='rc_apr_a08', emp=('Ananya Sharma', 'Sous Chef'), state='ongoing', months=0, days=14, tpl='kitchen',
         ef=['Ran the kitchen for 10 days while Chef Rahul was at the Kerala food festival, including two corporate events.',
             'Introduced colour-coded boards and a digital temperature probe log for the whole kitchen.',
             'Modern Kerala plating and fermentation for the new tasting menu.',
             'A proper training budget for the commis and a fixed day off.'],
         ef_pub=True,
         mf=['Very consistent; the Indo-Chinese section has the fewest returns.', '', '', '', ''],
         target='Head Chef',
         skills={'Pastry & Baking': ('Skilled', None, 'Took over the dessert menu during Deepa\'s leave.'),
                 'Indo-Chinese': ('Master', None, 'Created the new Indo-Chinese lunch combos.')},
         extra_skills=[('Soft Skills', 'Leadership', 'Advanced', 'Led the kitchen for 10 days alone.')],
         goals=[('rc_apr_g15', 'Pass FSSAI audit with zero major findings', ['hygiene'], '75', 2, None, 'rc_apr_gt_fssai'),
                ('rc_apr_g16', 'Cut food waste by 10%', ['cost', 'food_quality'], '50', 3, None, 'rc_apr_gt_waste'),
                ('rc_apr_g17', 'Mentor a new team member through onboarding', ['leadership', 'training'], '25', 1,
                 '<p>Buddy for Sajan Varghese (South Indian Cook).</p>', 'rc_apr_gt_mentor')],
         fb360=[('rc_apr_fb03', ('Deepa Krishnan', 'Sous Chef - Central Kitchen'), True,
                 'Organised, calm, and shares her prep lists with the Central Kitchen every evening.',
                 'Could be firmer with late deliveries from vendors.', 4, 'Ready for more responsibility.'),
                ('rc_apr_fb04', ('Vishnu Kumar', 'Line Cook & Prep Specialist'), False, None, None, None, None)],
         meeting=(12, 15)),
    dict(xid='rc_apr_a09', emp=('Fathima Rasheed', 'Pastry Cook'), state='ongoing', months=0, days=24, tpl='kitchen',
         ef=['', '', '', ''], target='Sous Chef - Central Kitchen',
         skills={'Pastry & Baking': ('Master', None, 'Laminated doughs and entremets now consistent.')},
         extra_skills=[],
         goals=[('rc_apr_g18', 'Launch 3 Kerala-fusion desserts for the Christmas menu', ['food_quality', 'upsell'], '50', 1,
                 '<p>Plum-cake tiramisu, elaneer panna cotta, jaggery-banana tart.</p>', None),
                ('rc_apr_g19', 'Daily temperature & cleaning logs 100% complete', ['hygiene'], '100', -1, None,
                 'rc_apr_gt_fssai_logs')],
         meeting=(20, 11)),
    dict(xid='rc_apr_a10', emp=('Nikhil Raj', 'Server'), state='ongoing', months=0, days=-6, tpl='foh',  # overdue
         ef=['Guests at table 12 left a 5-star review naming me after I handled a nut allergy carefully with the kitchen.',
             'I recommend the fresh lime soda and the payasam - my dessert attach rate is 19%.',
             'Large groups without a reservation at lunch time.',
             'Wine service training and leading the floor on Tuesdays.'],
         ef_pub=True,
         goals=[('rc_apr_g20', 'Upsell desserts to 25% of tables', ['upsell', 'guest'], '75', -1, None, 'rc_apr_gt_dessert'),
                ('rc_apr_g21', 'Keep a 4.5+ guest rating for your section', ['guest'], '50', 3, None, 'rc_apr_gt_rating')],
         extra_skills=[('Soft Skills', 'Persuasion', 'Intermediate', 'Dessert attach rate up from 11% to 19%.')]),
    dict(xid='rc_apr_a11', emp=('Faisal Ahmed', 'Delivery Rider'), state='ongoing', months=0, days=19, tpl='default',
         ef=['', '', '', ''],
         goals=[('rc_apr_g22', 'On-time delivery rate above 95%', ['speed'], '50', 1,
                 '<p>October: 91% on time (rain days excluded: 94%).</p>', 'rc_apr_gt_delivery'),
                ('rc_apr_g23', 'Zero spilled orders - seal and bag check on every dispatch', ['guest', 'food_quality'],
                 '75', 2, None, None)],
         skills={'Hindi': ('B2', None, 'Handles the north-Indian corporate clients on calls.')},
         meeting=(18, 16)),
    dict(xid='rc_apr_a12', emp=('Priya Menon', 'Head Barista & Cafe Specialist'), state='ongoing', months=1, days=-1,
         tpl='foh', appraisers=['Thomas Mathew', 'Suresh Kumar'],
         ef=['Launched the single-estate filter coffee menu with Malabar Coffee Estates; cafe sales up 15%.',
             'Coffee pairing card with desserts - 21% of coffee orders now include a dessert.',
             'Training part-timers while running the bar during the evening rush.',
             'A second grinder and an SCA trainer certification.'],
         ef_pub=True,
         mf=['Signature coffees are a real draw - the cafe NPS went from 48 to 61.', '', '', '', ''],
         extra_skills=[('Soft Skills', 'Leadership', 'Advanced', 'Trains Anjali and the weekend part-timers.'),
                       ('Soft Skills', 'Creativity', 'Expert', 'Designed the seasonal coffee menu.')],
         goals=[('rc_apr_g24', 'Latte art certification (Barista Skills Intermediate)', ['training', 'food_quality'], '75', 1,
                 '<p>Coach Anjali Das to pass the certification.</p>', 'rc_apr_gt_latte'),
                ('rc_apr_g25', 'Cut milk and coffee wastage by 10%', ['cost'], '50', 2, None, 'rc_apr_gt_waste'),
                ('rc_apr_g26', 'Launch a winter coffee & dessert pairing menu', ['upsell', 'guest'], '0', 2, None, None)],
         fb360=[('rc_apr_fb05', ('Anjali Das', 'Barista (Part-time)'), True,
                 'Great teacher, very patient, the coffee quality is always perfect.',
                 'The bar schedule is shared quite late in the week.', 4, ''),
                ('rc_apr_fb06', ('Mohammed Bilal', 'Senior Service Captain & Waiter'), True,
                 'Coffee and desserts come out together, guests love the pairing card.',
                 'Bar tickets pile up when she is training someone during the rush.', 3, '')],
         meeting=(25, 10)),
    # ---------------- To Confirm - next cycle
    dict(xid='rc_apr_a13', emp=('Vishnu Kumar', 'Line Cook & Prep Specialist'), state='draft', months=5, days=0,
         tpl='kitchen',
         goals=[('rc_apr_g27', 'Reach Skilled level on Tandoor', ['training'], '25', 4,
                 '<p>Two tandoor shifts per week with Manoj.</p>', None),
                ('rc_apr_g28', 'Reduce ticket time to under 12 min on KDS', ['speed'], '0', 3,
                 '<p>Now on the Indo-Chinese wok station.</p>', 'rc_apr_gt_kds')]),
    dict(xid='rc_apr_a14', emp=('Sneha Pillai', 'POS Cashier & Receptionist'), state='draft', months=2, days=0, tpl='foh',
         goals=[('rc_apr_g29', 'Keep cash differences at zero for every POS session', ['cost'], '75', 2, None, None),
                ('rc_apr_g30', 'Upsell the loyalty card to 30 guests a week', ['upsell', 'guest'], '25', 2, None, None)]),
    # ---------------- Cancelled
    dict(xid='rc_apr_a15', emp=('Gokul Krishna', 'Cashier (Seasonal)'), state='cancel', months=0, days=-20, tpl='foh',
         private='<p>Cancelled - seasonal contract for the Onam season ended before the review date.</p>',
         goals=[('rc_apr_g31', 'Learn split bills and refunds on the POS', ['training'], '50', -1, None, None)]),
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


def _local_dt(day, hour):
    local = TZ.localize(datetime.combine(day, time(hour, 0)))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


def load_appraisal_suite_demo_data(env):
    if 'hr.appraisal' not in env:
        _logger.info("Appraisals (eh_hr_appraisal) not installed - skipping appraisal demo data")
        return
    company = env.company
    co_domain = [('company_id', 'in', (company.id, False))]
    Employee = env['hr.employee'].sudo()
    last_mail = env['mail.mail'].sudo().search([], order='id desc', limit=1).id or 0
    today = fields.Date.context_today(env['res.users'].sudo().browse(env.uid))

    def emp(name, job=None):
        domain = [('name', '=', name), ('company_id', '=', company.id)]
        if job:
            domain.append(('job_id.name', '=', job))
        return Employee.search(domain, order='id', limit=1)

    # ---- tags
    tags = {}
    for xid, name, color in TAGS:
        try:
            with env.cr.savepoint():
                tags[xid.replace('rc_apr_tag_', '')] = _get_or_create(
                    env, xid, 'hr.appraisal.goal.tag', {'name': name, 'color': color}, search=[('name', '=', name)])
        except Exception as e:
            _logger.warning("Appraisal demo: could not create tag %s: %s", xid, e)

    def tag_ids(keys):
        return [tags[k].id for k in keys if k in tags]

    # ---- goals library
    Skill = env['hr.skill'].sudo()
    goal_templates = {}
    for xid, name, timing, tkeys, skills, desc, parent in GOAL_TEMPLATES:
        try:
            with env.cr.savepoint():
                goal_templates[xid] = _get_or_create(env, xid, 'hr.appraisal.goal.template', {
                    'name': name, 'timing': timing, 'description': desc,
                    'tag_ids': [Command.set(tag_ids(tkeys))],
                    'skill_ids': [Command.set(Skill.search([('name', 'in', skills)]).ids)],
                    'parent_id': goal_templates[parent].id if parent and parent in goal_templates else False,
                }, search=[('name', '=', name)])
        except Exception as e:
            _logger.warning("Appraisal demo: could not create goal template %s: %s", xid, e)

    # ---- appraisal templates
    Department = env['hr.department'].sudo()
    templates = {}
    for xid, name, depts, emp_q, mgr_q in APPRAISAL_TEMPLATES:
        try:
            with env.cr.savepoint():
                templates[xid.replace('rc_apr_tpl_', '')] = _get_or_create(env, xid, 'hr.appraisal.template', {
                    'name': name, 'company_id': company.id,
                    'department_ids': [Command.set(Department.search(
                        [('name', 'in', depts), ('company_id', 'in', (company.id, False))]).ids)],
                    'employee_feedback_template': _qa_template(emp_q),
                    'manager_feedback_template': _qa_template(mgr_q),
                }, search=[('name', '=', name)] + co_domain)
        except Exception as e:
            _logger.warning("Appraisal demo: could not create appraisal template %s: %s", xid, e)
    default_tpl = _ref(env, 'eh_hr_appraisal.hr_appraisal_template_default') or env['hr.appraisal.template'].sudo().search(
        co_domain + [('department_ids', '=', False)], limit=1)
    if default_tpl:
        templates['default'] = default_tpl

    # ---- evaluation scale
    Scale = env['hr.appraisal.scale'].sudo()
    scales = {}
    for key, xid in SCALE.items():
        scales[key] = _ref(env, xid) or Scale.search([('name', '=ilike', SCALE_NAMES[key])] + co_domain, limit=1)

    # ---- helpers for skills / surveys
    SkillType = env['hr.skill.type'].sudo()

    def level_of(skill_type, name):
        return skill_type.skill_level_ids.filtered(lambda lv: lv.name == name)[:1]

    def previous_level(skill_type, level):
        levels = skill_type.skill_level_ids.sorted('level_progress')
        lower = levels.filtered(lambda lv: lv.level_progress < level.level_progress)
        return lower[-1:] if lower else level

    survey = _ref(env, 'eh_hr_appraisal.survey_360_feedback') or company.sudo().appraisal_survey_template_id
    q = {k: _ref(env, f'eh_hr_appraisal.survey_360_feedback_q_{k}')
         for k in ('strengths', 'improvements', 'collaboration', 'comments')}
    q_answers = {i: _ref(env, f'eh_hr_appraisal.survey_360_feedback_q_collaboration_a{i}') for i in range(1, 5)}

    Appraisal = env['hr.appraisal'].sudo().with_context(**CTX)
    Goal = env['hr.appraisal.goal'].sudo().with_context(**CTX)
    counts = dict(appraisals=0, goals=0, skills=0, feedback=0, meetings=0)
    for spec in APPRAISALS:
        employee = emp(*spec['emp'])
        if not employee:
            _logger.warning("Appraisal demo: employee %s not found for %s", spec['emp'], spec['xid'])
            continue
        appraisal = _ref(env, spec['xid'])
        if not appraisal:
            try:
                with env.cr.savepoint():
                    appraisal = _create_appraisal(env, spec, employee, emp, templates, scales, today, Appraisal,
                                                  SkillType, level_of, previous_level, counts)
                    counts['appraisals'] += 1
            except Exception as e:
                appraisal = False
                _logger.warning("Appraisal demo: could not create %s: %s", spec['xid'], e)
        # ---- goals (bound individually)
        for gxid, gname, gtags, progress, gmonths, gdesc, gtpl in spec.get('goals', []):
            if _ref(env, gxid):
                continue
            try:
                with env.cr.savepoint():
                    tpl = goal_templates.get(gtpl) if gtpl else False
                    deadline = today + relativedelta(months=gmonths)
                    _bind(env, gxid, Goal.create({
                        'name': gname,
                        'employee_id': employee.id,
                        'manager_id': employee.parent_id.id or False,
                        'appraisal_id': appraisal.id if appraisal else False,
                        'template_id': tpl.id if tpl else False,
                        'description': gdesc or (tpl.description if tpl else False),
                        'deadline': deadline,
                        'progress': progress,
                        'tag_ids': [Command.set(tag_ids(gtags))],
                    }))
                    counts['goals'] += 1
            except Exception as e:
                _logger.warning("Appraisal demo: could not create goal %s: %s", gxid, e)
        # ---- 360 feedback
        if appraisal and survey:
            for fxid, colleague, done, strengths, improvements, collab, comments in spec.get('fb360', []):
                if _ref(env, fxid):
                    continue
                try:
                    with env.cr.savepoint():
                        colleague_emp = emp(*colleague)
                        partner = colleague_emp.work_contact_id or colleague_emp.user_id.partner_id
                        answer = survey.sudo().with_context(**CTX)._create_answer(
                            partner=partner, check_attempts=False,
                            deadline=_local_dt(appraisal.date_appraisal, 23),
                            appraisal_id=appraisal.id, appraisal_employee_id=colleague_emp.id)
                        if done:
                            lines = []
                            for key, text in (('strengths', strengths), ('improvements', improvements),
                                              ('comments', comments)):
                                if text and q[key]:
                                    lines.append({'user_input_id': answer.id, 'question_id': q[key].id,
                                                  'answer_type': 'text_box', 'value_text_box': text})
                            if collab and q['collaboration'] and q_answers.get(collab):
                                lines.append({'user_input_id': answer.id, 'question_id': q['collaboration'].id,
                                              'answer_type': 'suggestion', 'suggested_answer_id': q_answers[collab].id})
                            env['survey.user_input.line'].sudo().create(lines)
                            answer.write({'state': 'done', 'end_datetime': _local_dt(
                                appraisal.date_appraisal - timedelta(days=7), 17)})
                        _bind(env, fxid, answer)
                        counts['feedback'] += 1
                except Exception as e:
                    _logger.warning("Appraisal demo: could not create 360 feedback %s: %s", fxid, e)

    # ---- next appraisal date of the reviewed employees: earliest open appraisal, else next after the last done
    try:
        with env.cr.savepoint():
            for spec in APPRAISALS:
                appraisal = _ref(env, spec['xid'])
                if not appraisal:
                    continue
                employee = appraisal.employee_id.sudo()
                open_ones = env['hr.appraisal'].sudo().search(
                    [('employee_id', '=', employee.id), ('state', 'in', ('draft', 'ongoing'))], order='date_appraisal')
                done = env['hr.appraisal'].sudo().search(
                    [('employee_id', '=', employee.id), ('state', '=', 'done')], order='date_done desc', limit=1)
                target = open_ones[:1].date_appraisal or done.date_next
                if target and employee.next_appraisal_date != target:
                    employee.with_context(**CTX).write({'next_appraisal_date': target})
    except Exception as e:
        _logger.warning("Appraisal demo: could not set next appraisal dates: %s", e)

    # ---- never send anything: purge mails queued while loading
    mails = env['mail.mail'].sudo().search([('id', '>', last_mail), ('state', 'in', ('outgoing', 'exception'))])
    if mails:
        mails.unlink()
    _logger.info("Appraisal demo: %s", counts)
    return counts


def _create_appraisal(env, spec, employee, emp, templates, scales, today, Appraisal, SkillType, level_of,
                      previous_level, counts):
    state = spec['state']
    tpl_key = spec.get('tpl', 'default')
    template = templates.get(tpl_key)
    emp_q, mgr_q = QUESTIONS[tpl_key]
    date_appraisal = today + relativedelta(months=spec.get('months', 0), days=spec.get('days', 0))
    appraisers = employee.parent_id
    if spec.get('appraisers'):
        appraisers = env['hr.employee'].sudo()
        for name in spec['appraisers']:
            appraisers |= emp(name)
    vals = {
        'employee_id': employee.id,
        'date_appraisal': date_appraisal,
        'template_id': template.id if template else False,
        'appraiser_ids': [Command.set(appraisers.ids)],
        'state': state,
    }
    if spec.get('target'):
        job = env['hr.job'].sudo().search([('name', '=', spec['target']),
                                           ('company_id', 'in', (employee.company_id.id, False))], limit=1)
        vals['target_job_id'] = job.id or False
    # filled feedback (empty answers keep the question with a blank paragraph)
    if spec.get('ef') and any(spec['ef']):
        vals['employee_feedback'] = _qa([(qt, a or '<br>') for (qt, _h), a in zip(emp_q, spec['ef'])])
    if spec.get('mf') and any(spec['mf']):
        vals['manager_feedback'] = _qa([(qt, a or '<br>') for (qt, _h), a in zip(mgr_q, spec['mf'])])
    if spec.get('private'):
        vals['private_note'] = spec['private']
    if state == 'done':
        date_done = min(date_appraisal + timedelta(days=spec.get('done', 0)), today)
        months = spec.get('next_months') or (employee.company_id.appraisal_plan_recurring_month or 12)
        vals.update({
            'employee_feedback_published': True,
            'manager_feedback_published': True,
            'rating_id': scales[spec['rating']].id if scales.get(spec.get('rating')) else False,
            'date_done': date_done,
            'date_next': date_done + relativedelta(months=months),
        })
    elif state == 'ongoing':
        vals['employee_feedback_published'] = bool(spec.get('ef_pub'))
    appraisal = Appraisal.create(vals)
    _bind(env, spec['xid'], appraisal)

    # ---- skills (Confirmed / Done)
    if state in ('ongoing', 'done'):
        appraisal._populate_skills()
        for line in appraisal.appraisal_skill_ids:
            change = (spec.get('skills') or {}).get(line.skill_id.name)
            if not change:
                continue
            current, previous, justification = change
            level = level_of(line.skill_type_id, current)
            if not level:
                continue
            upd = {'skill_level_id': level.id, 'justification': justification}
            if state == 'done':
                # the validated level is the employee's level today: show the level they came from
                prev = level_of(line.skill_type_id, previous) if previous else previous_level(line.skill_type_id, level)
                upd.update({'previous_skill_level_id': prev.id, 'previous_level_progress': prev.level_progress})
            line.write(upd)
        for type_name, skill_name, level_name, justification in spec.get('extra_skills', []):
            skill_type = SkillType.search([('name', '=', type_name)], limit=1)
            skill = skill_type.skill_ids.filtered(lambda s: s.name == skill_name)[:1]
            level = level_of(skill_type, level_name)
            if not (skill and level) or skill in appraisal.appraisal_skill_ids.skill_id:
                continue
            prev = previous_level(skill_type, level)
            env['hr.appraisal.skill'].sudo().create({
                'appraisal_id': appraisal.id, 'skill_type_id': skill_type.id, 'skill_id': skill.id,
                'skill_level_id': level.id, 'justification': justification,
                'previous_skill_level_id': prev.id if prev != level else False,
                'previous_level_progress': prev.level_progress if prev != level else 0,
            })
        counts['skills'] += len(appraisal.appraisal_skill_ids)

    # ---- appraisal meeting (calendar), no invitations
    if spec.get('meeting') and 'calendar.event' in env:
        day_offset, hour = spec['meeting']
        start = _local_dt(today + timedelta(days=day_offset), hour)
        partners = (appraisal.employee_id | appraisal.appraiser_ids).sudo().mapped(
            lambda e: e.user_id.partner_id or e.work_contact_id)
        env['calendar.event'].sudo().with_context(**CTX).create({
            'name': f"Appraisal of {employee.name}",
            'start': start, 'stop': start + timedelta(minutes=45),
            'partner_ids': [Command.set(partners.ids)],
            'res_model_id': env['ir.model']._get_id('hr.appraisal'),
            'res_id': appraisal.id,
            'location': "Manager's Office (1st floor)",
            'description': '<p>Review of the self-assessment, goals and skills.</p>',
        })
        counts['meetings'] += 1
    return appraisal
