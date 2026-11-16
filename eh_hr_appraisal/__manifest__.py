{
    'name': 'Appraisals',
    'version': '20.0.1.1.0',
    'category': 'Human Resources/Appraisals',
    'summary': 'Employee appraisals, 360 feedback, goals and skills evolution',
    'description': """
Appraisals
==========
Same workflow as the Odoo Appraisals app:

* Appraisals plans and automation (first appraisal, second one, then periodic).
* To Confirm > Confirmed > Done workflow; Mark as Done locks, Reopen unlocks.
* Employee's and Manager's Feedback from templates, each Private until shared
  (Shared to Appraisers / Shared to Employee), private note for the appraisers.
* Skills tab with Target Job, final rating from the Evaluation Scale.
* 360 Feedback surveys (Ask Feedback), meetings, goals library and tags.
* Reporting: Appraisal Analysis and Skills Evolution.
* Access levels: No / Officer: Access all appraisals / Administrator.
    """,
    'author': 'Antigravity',
    'depends': ['hr', 'mail', 'survey', 'hr_skills', 'eh_hr_compat', 'calendar'],
    'data': [
        'security/hr_appraisal_security.xml',
        'security/ir.access.csv',
        'security/hr_appraisal_company_rules.xml',
        'data/ir_sequence_data.xml',
        'data/hr_appraisal_data.xml',
        'data/mail_template_data.xml',
        'data/hr_appraisal_cron.xml',
        'wizard/appraisal_launch_wizard_views.xml',
        'wizard/hr_appraisal_ask_feedback_views.xml',
        'views/hr_appraisal_goal_template_views.xml',
        'views/hr_appraisal_goal_views.xml',
        'views/hr_appraisal_template_views.xml',
        'views/survey_views.xml',
        'views/hr_appraisal_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_appraisal_scale_views.xml',
        'views/hr_appraisal_goal_tag_views.xml',
        'views/mail_activity_views.xml',
        'views/hr_appraisal_report_views.xml',
        'views/calendar_event_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'eh_hr_appraisal/static/src/scss/hr_appraisal.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
