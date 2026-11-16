from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged, TransactionCase
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('post_install', '-at_install', 'eh_hr_appraisal')
class TestAppraisalWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nolog=True))
        company = cls.env.company
        company.write({'appraisal_plan': True, 'appraisal_360_feedback': True})

        def user(login, groups='base.group_user'):
            return mail_new_test_user(cls.env, login=login, groups=groups, email=f'{login}@example.com', company_id=company.id)

        cls.user_employee = user('appr_employee')
        cls.user_manager = user('appr_manager')
        cls.user_colleague = user('appr_colleague')
        cls.user_officer = user('appr_officer', 'base.group_user,eh_hr_appraisal.group_hr_appraisal_user')
        cls.user_admin = user('appr_admin', 'base.group_user,eh_hr_appraisal.group_hr_appraisal_manager')

        Employee = cls.env['hr.employee']
        cls.manager = Employee.create({'name': 'Manager', 'user_id': cls.user_manager.id, 'company_id': company.id})
        cls.employee = Employee.create({
            'name': 'Employee', 'user_id': cls.user_employee.id, 'parent_id': cls.manager.id, 'company_id': company.id,
        })
        cls.colleague = Employee.create({'name': 'Colleague', 'user_id': cls.user_colleague.id, 'company_id': company.id})
        cls.officer = Employee.create({'name': 'Officer', 'user_id': cls.user_officer.id, 'company_id': company.id})

        cls.skill_type = cls.env['hr.skill.type'].create({
            'name': 'Languages',
            'skill_ids': [(0, 0, {'name': 'French'}), (0, 0, {'name': 'Dutch'})],
            'skill_level_ids': [
                (0, 0, {'name': 'Beginner', 'level_progress': 25, 'default_level': True}),
                (0, 0, {'name': 'Intermediate', 'level_progress': 50}),
                (0, 0, {'name': 'Expert', 'level_progress': 100}),
            ],
        })
        cls.french, cls.dutch = cls.skill_type.skill_ids
        cls.beginner, cls.intermediate, cls.expert = cls.skill_type.skill_level_ids.sorted('level_progress')
        cls.employee.write({'employee_skill_ids': [(0, 0, {
            'skill_type_id': cls.skill_type.id, 'skill_id': cls.french.id, 'skill_level_id': cls.beginner.id,
        })]})

    def _new_appraisal(self):
        return self.env['hr.appraisal'].with_user(self.user_manager).create({'employee_id': self.employee.id})

    # ------------------------------------------------------------------

    def test_access_levels(self):
        officer = self.env.ref('eh_hr_appraisal.group_hr_appraisal_user')
        admin = self.env.ref('eh_hr_appraisal.group_hr_appraisal_manager')
        self.assertEqual(officer.name, 'Officer: Access all appraisals')
        self.assertEqual(admin.name, 'Administrator')
        self.assertEqual(officer.privilege_id, admin.privilege_id)
        self.assertIn(officer, admin.implied_ids)
        self.assertFalse(self.env.ref('eh_hr_appraisal.group_hr_appraisal_admin', raise_if_not_found=False))

    def test_new_appraisal_defaults(self):
        appraisal = self._new_appraisal()
        self.assertEqual(appraisal.state, 'draft')
        self.assertEqual(appraisal.appraiser_ids, self.manager)
        self.assertEqual(appraisal.date_appraisal, fields.Date.today() + relativedelta(months=1))
        self.assertEqual(appraisal.template_id, self.env.ref('eh_hr_appraisal.hr_appraisal_template_default'))
        self.assertIn('My work', appraisal.sudo().employee_feedback)
        self.assertIn('Improvements', appraisal.sudo().manager_feedback)
        self.assertFalse(appraisal.appraisal_skill_ids, "Skills are only loaded on confirmation")

        form = Form(self.env['hr.appraisal'].with_user(self.user_manager))
        form.employee_id = self.employee
        self.assertEqual(form.appraiser_ids[:], self.manager)

    def test_feedback_only_once_confirmed(self):
        appraisal = self._new_appraisal()
        with self.assertRaises(UserError):
            appraisal.with_user(self.user_employee).employee_feedback = '<p>Too early</p>'
        with self.assertRaises(UserError):
            appraisal.with_user(self.user_manager).manager_feedback = '<p>Too early</p>'
        with self.assertRaises(UserError):
            appraisal.with_user(self.user_employee).action_confirm()

    def test_full_workflow(self):
        appraisal = self._new_appraisal()
        appraisal.with_user(self.user_manager).action_confirm()
        self.assertEqual(appraisal.state, 'ongoing')
        # Employee and appraisers are notified
        confirm = appraisal.message_ids.filtered(lambda m: 'is confirmed' in (m.body or ''))
        self.assertTrue(confirm)
        self.assertIn(self.user_employee.partner_id, confirm.partner_ids)
        self.assertIn(self.user_manager.partner_id, confirm.partner_ids)
        self.assertTrue(appraisal.activity_ids.filtered(lambda a: a.user_id == self.user_employee))
        # Skills loaded from the employee
        self.assertEqual(appraisal.appraisal_skill_ids.skill_id, self.french)

        as_employee = appraisal.with_user(self.user_employee)
        as_manager = appraisal.with_user(self.user_manager)

        # Employee self-assessment stays private until shared
        as_employee.employee_feedback = '<p>My self assessment</p>'
        self.assertFalse(as_manager.read(['employee_feedback'])[0]['employee_feedback'])
        self.assertFalse(as_manager.employee_feedback_visible)
        as_employee.action_publish_employee_feedback()
        self.assertIn('My self assessment', as_manager.read(['employee_feedback'])[0]['employee_feedback'])

        # Manager feedback stays private until shared to the employee
        as_manager.manager_feedback = '<p>Great job</p>'
        self.assertFalse(as_employee.read(['manager_feedback'])[0]['manager_feedback'])
        as_manager.action_publish_manager_feedback()
        self.assertIn('Great job', as_employee.read(['manager_feedback'])[0]['manager_feedback'])

        # Private note: never for the employee
        as_manager.private_note = '<p>Promotion candidate</p>'
        self.assertFalse(as_employee.read(['private_note'])[0]['private_note'])
        self.assertIn('Promotion', as_manager.read(['private_note'])[0]['private_note'])

        # The employee cannot rate nor close their own appraisal
        rating = self.env.ref('eh_hr_appraisal.hr_appraisal_scale_exceeds_expectations')
        with self.assertRaises(UserError):
            as_employee.rating_id = rating
        with self.assertRaises(UserError):
            as_employee.action_done()
        with self.assertRaises(UserError):
            as_manager.employee_feedback = '<p>Rewritten by manager</p>'

        # Skills: the employee improved
        as_employee.appraisal_skill_ids.write({'skill_level_id': self.intermediate.id, 'justification': 'Course'})
        as_manager.appraisal_skill_ids = [(0, 0, {
            'skill_type_id': self.skill_type.id, 'skill_id': self.dutch.id, 'skill_level_id': self.beginner.id,
        })]

        as_manager.rating_id = rating
        as_manager.action_done()
        self.assertEqual(appraisal.state, 'done')
        self.assertEqual(appraisal.date_done, fields.Date.today())
        # First appraisal done: second one after appraisal_plan_next_month
        expected = fields.Date.today() + relativedelta(months=self.env.company.appraisal_plan_next_month)
        self.assertEqual(appraisal.date_next, expected)
        self.assertEqual(self.employee.next_appraisal_date, expected)
        # Skills written back to the employee
        levels = {s.skill_id: s.skill_level_id for s in self.employee.current_employee_skill_ids}
        self.assertEqual(levels[self.french], self.intermediate)
        self.assertEqual(levels[self.dutch], self.beginner)
        # Skills evolution report
        report = self.env['hr.appraisal.skill.report'].search([('appraisal_id', '=', appraisal.id)])
        self.assertEqual(report.skill_id, self.french | self.dutch)
        self.assertEqual(report.filtered(lambda r: r.skill_id == self.french).evolution, 'improvement')

        # Done locks the appraisal until reopened
        with self.assertRaises(UserError):
            as_manager.manager_feedback = '<p>Changed</p>'
        as_manager.action_reopen()
        self.assertEqual(appraisal.state, 'ongoing')
        as_manager.manager_feedback = '<p>Changed</p>'

    def test_record_access(self):
        appraisal = self._new_appraisal()
        # Officer: all appraisals
        self.assertEqual(appraisal.with_user(self.user_officer).employee_id, self.employee)
        self.assertTrue(appraisal.with_user(self.user_officer).is_appraisal_manager)
        # Officer without HR rights reads employees through their public profile
        with Form(appraisal.with_user(self.user_officer)) as form:
            self.assertEqual(form.employee_id, self.employee)
        self.env['hr.employee'].with_user(self.user_officer).browse(self.officer.id).read(['name', 'parent_id'])
        # Unrelated employee: nothing
        with self.assertRaises(AccessError):
            appraisal.with_user(self.user_colleague).read(['employee_id'])
        self.assertFalse(self.env['hr.appraisal'].with_user(self.user_colleague).search([('id', '=', appraisal.id)]))
        # Employees cannot schedule their own appraisal
        with self.assertRaises(AccessError):
            self.env['hr.appraisal'].with_user(self.user_employee).create({'employee_id': self.employee.id})
        # Nobody appraises themselves, officers included
        own = self.env['hr.appraisal'].with_user(self.user_admin).create({'employee_id': self.officer.id})
        self.assertFalse(own.with_user(self.user_officer).is_appraisal_manager)
        with self.assertRaises(UserError):
            own.with_user(self.user_officer).action_confirm()

    def test_ask_feedback(self):
        appraisal = self._new_appraisal()
        appraisal.with_user(self.user_manager).action_confirm()
        wizard = self.env['hr.appraisal.ask.feedback'].with_user(self.user_manager).create({
            'appraisal_id': appraisal.id,
            'employee_ids': [(6, 0, self.colleague.ids)],
        })
        self.assertEqual(wizard.deadline, appraisal.date_appraisal)
        self.assertEqual(wizard.subject, 'Take part in Employee appraisal')
        self.assertEqual(wizard.survey_template_id, self.env.ref('eh_hr_appraisal.survey_360_feedback'))
        wizard.action_send()
        answer = self.env['survey.user_input'].search([('appraisal_id', '=', appraisal.id)])
        self.assertEqual(answer.partner_id, self.user_colleague.partner_id)
        self.assertEqual(answer.appraisal_employee_id, self.colleague)
        self.assertEqual(appraisal.survey_answer_count, 1)
        # The manager sees the request, the appraised employee does not
        self.assertTrue(self.env['survey.user_input'].with_user(self.user_manager).search([('appraisal_id', '=', appraisal.id)]))
        self.assertFalse(self.env['survey.user_input'].with_user(self.user_employee).search([('appraisal_id', '=', appraisal.id)]))
        # Resend reuses the pending request
        wizard.action_send()
        self.assertEqual(appraisal.survey_answer_count, 1)

    def test_goals_library(self):
        template = self.env['hr.appraisal.goal.template'].create({'name': 'Learn Dutch', 'timing': 3})
        action = template.action_select_employees()
        wizard = self.env['hr.appraisal.goal.assign'].with_user(self.user_manager).with_context(action['context']).create({
            'employee_ids': [(6, 0, self.employee.ids)],
        })
        wizard.action_add_goals()
        goal = self.env['hr.appraisal.goal'].search([('employee_id', '=', self.employee.id), ('template_id', '=', template.id)])
        self.assertEqual(goal.deadline, fields.Date.today() + relativedelta(months=3))
        self.assertEqual(goal.manager_id, self.manager)
        self.assertEqual(goal.state, 'draft')
        goal.with_user(self.user_employee).progress = '50'
        self.assertEqual(goal.state, 'in_progress')
        goal.with_user(self.user_manager).action_mark_as_done()
        self.assertEqual((goal.progress, goal.state), ('100', 'done'))
        with self.assertRaises(AccessError):
            goal.with_user(self.user_colleague).read(['name'])

    def test_plan_and_automation(self):
        company = self.env.company
        new = self.env['hr.employee'].create({'name': 'Newcomer', 'company_id': company.id, 'parent_id': self.manager.id})
        self.assertTrue(new.next_appraisal_date)
        # Changing the plan updates the employees without next appraisal date
        new.next_appraisal_date = False
        company.appraisal_plan_first_month = 3
        start = new.first_contract_date or new.create_date.date()
        self.assertEqual(new.next_appraisal_date, start + relativedelta(months=3))

        new.next_appraisal_date = fields.Date.today() + relativedelta(days=10)
        company.appraisal_automation = True
        self.env['hr.appraisal']._cron_appraisal_automation()
        appraisal = self.env['hr.appraisal'].search([('employee_id', '=', new.id)])
        self.assertEqual(appraisal.state, 'ongoing')
        self.assertEqual(appraisal.date_appraisal, new.next_appraisal_date)
        # No duplicate while one is in progress
        self.env['hr.appraisal']._cron_appraisal_automation()
        self.assertEqual(self.env['hr.appraisal'].search_count([('employee_id', '=', new.id)]), 1)

    def test_views_load_for_every_role(self):
        actions = {
            'eh_hr_appraisal.action_hr_appraisal': (self.user_employee, self.user_manager, self.user_officer, self.user_admin),
            'eh_hr_appraisal.action_hr_appraisal_goal': (self.user_employee, self.user_manager, self.user_officer, self.user_admin),
            'eh_hr_appraisal.action_hr_appraisal_goal_library': (self.user_manager, self.user_admin),
            'eh_hr_appraisal.action_hr_appraisal_feedback_inputs': (self.user_manager, self.user_officer),
            'eh_hr_appraisal.action_hr_appraisal_analysis_report': (self.user_officer, self.user_admin),
            'eh_hr_appraisal.action_hr_appraisal_skills_evolution': (self.user_officer, self.user_admin),
            'eh_hr_appraisal.action_hr_appraisal_template': (self.user_admin,),
            'eh_hr_appraisal.action_hr_appraisal_goal_template': (self.user_admin,),
            'eh_hr_appraisal.action_hr_appraisal_360_feedback': (self.user_admin,),
            'eh_hr_appraisal.action_hr_appraisal_scale': (self.user_admin,),
        }
        for xmlid, users in actions.items():
            action = self.env.ref(xmlid)
            views = [[False, mode] for mode in action.view_mode.split(',')]
            for user in users:
                with self.subTest(action=xmlid, user=user.login):
                    Model = self.env[action.res_model].with_user(user)
                    Model.get_views(views + [[False, 'search']])
                    Model.web_search_read([], {'display_name': {}}, limit=5)

    def test_forms_as_employee_and_manager(self):
        appraisal = self._new_appraisal()
        appraisal.with_user(self.user_manager).action_confirm()
        with Form(appraisal.with_user(self.user_employee)) as form:
            form.employee_feedback = '<p>Written in the form</p>'
            self.assertTrue(form.can_edit_employee_feedback)
            self.assertFalse(form.can_edit_manager_feedback)
        with Form(appraisal.with_user(self.user_manager)) as form:
            form.manager_feedback = '<p>Manager in the form</p>'
            form.rating_id = self.env.ref('eh_hr_appraisal.hr_appraisal_scale_meets_expectations')
            with form.appraisal_skill_ids.edit(0) as line:
                line.skill_level_id = self.expert
        self.assertEqual(appraisal.appraisal_skill_ids.skill_level_id, self.expert)
        self.assertIn('Written in the form', appraisal.sudo().employee_feedback)
        # Employee form (HR officers): Appraisals smart button and Next Appraisal Date
        hr_officer = mail_new_test_user(
            self.env, login='appr_hr_officer', email='appr_hr_officer@example.com',
            groups='base.group_user,hr.group_hr_user,eh_hr_appraisal.group_hr_appraisal_user')
        arch = self.env['hr.employee'].with_user(hr_officer).get_views([[False, 'form']])['views']['form']['arch']
        self.assertIn('action_open_appraisals', arch)
        self.assertIn('next_appraisal_date', arch)

    def test_department_template(self):
        department = self.env['hr.department'].create({'name': 'Field'})
        template = self.env['hr.appraisal.template'].create({
            'name': 'Technicians', 'department_ids': [(6, 0, department.ids)],
            'employee_feedback_template': '<p>Field questions</p>',
        })
        self.employee.department_id = department
        appraisal = self._new_appraisal()
        self.assertEqual(appraisal.template_id, template)
        self.assertEqual(appraisal.department_id, department)
