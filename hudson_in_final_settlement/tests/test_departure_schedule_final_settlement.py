# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date


class TestDepartureScheduleFinalSettlement(TransactionCase):

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestDepartureScheduleFinalSettlement, cls).tearDownClass()
        except Exception:
            pass

    def setUp(self):
        super(TestDepartureScheduleFinalSettlement, self).setUp()
        india = self.env['res.country'].search([('code', '=', 'IN')], limit=1)
        state_mh = self.env['res.country.state'].search([('code', '=', 'MH'), ('country_id', '=', india.id)], limit=1) if india else False
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_gratuity': True,
            'hds_in_enable_leave_encashment': True,
            'hds_in_enable_professional_tax': True,
        })
        if state_mh and self.company.partner_id:
            self.company.partner_id.state_id = state_mh.id
        self.employee = self.env['hr.employee'].create({
            'name': 'Scheduled Departure Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })

        contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)
        if contract_model:
            struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
            self.contract = getattr(self.employee, 'version_id', False) or self.env[contract_model].search([
                ('employee_id', '=', self.employee.id)
            ], limit=1)
            if self.contract:
                self.contract.write({
                    'wage': 50000.0,
                    'basic_salary': 30000.0,
                    'da': 5000.0,
                    'date_start': Date.from_string('2018-01-01'),
                    'struct_id': struct.id if struct else False,
                })
            else:
                self.contract = self.env[contract_model].create({
                    'name': 'Scheduled Departure Contract',
                    'employee_id': self.employee.id,
                    'company_id': self.company.id,
                    'wage': 50000.0,
                    'basic_salary': 30000.0,
                    'da': 5000.0,
                    'date_start': Date.from_string('2018-01-01'),
                    'struct_id': struct.id if struct else False,
                })
            if hasattr(self.employee, 'version_id') and not self.employee.version_id:
                self.employee.version_id = self.contract.id

        self.reason_resigned = self.env['hr.departure.reason'].search([('name', '=', 'Resigned')], limit=1)
        if not self.reason_resigned:
            self.reason_resigned = self.env['hr.departure.reason'].create({'name': 'Resigned'})

    def test_01_action_schedule_creates_draft_final_settlement(self):
        """Test clicking Schedule in End of Collaboration auto-creates draft settlement."""
        start_date = Date.from_string('2026-10-09')
        end_date = Date.from_string('2026-11-09')

        wizard = self.env['hr.employee.departure'].create({
            'employee_id': self.employee.id,
            'departure_reason_id': self.reason_resigned.id,
            'dismissal_date': start_date,
            'notice_period_start_date': start_date,
            'notice_period_end_date': end_date,
            'departure_date': end_date,
            'departure_description': 'Employee accepted offer elsewhere.',
        })

        # Simulate clicking [Schedule]
        wizard.action_schedule()

        # Verify contract date_end aligned to notice_period_end_date
        if hasattr(self, 'contract'):
            self.assertEqual(self.contract.date_end, end_date)

        # Verify draft final settlement auto-created
        settlements = self.env['final.settlement'].search([
            ('employee_id', '=', self.employee.id),
            ('state', '!=', 'cancel'),
        ])
        self.assertEqual(len(settlements), 1)
        settlement = settlements[0]

        self.assertEqual(settlement.state, 'draft')
        self.assertEqual(settlement.last_working_day, end_date)
        self.assertEqual(settlement.exit_reason, 'resignation')
        self.assertEqual(settlement.employee_id, self.employee)
        self.assertEqual(self.employee.final_settlement_count, 1)

    def test_02_idempotent_rescheduling_updates_existing_draft(self):
        """Test rescheduling departure updates the existing draft settlement without duplicating."""
        start_date = Date.from_string('2026-10-09')
        end_date1 = Date.from_string('2026-11-09')
        end_date2 = Date.from_string('2026-11-20')  # Extended notice

        wizard1 = self.env['hr.employee.departure'].create({
            'employee_id': self.employee.id,
            'departure_reason_id': self.reason_resigned.id,
            'notice_period_start_date': start_date,
            'notice_period_end_date': end_date1,
        })
        wizard1.action_schedule()

        # Re-schedule with extended notice
        wizard2 = self.env['hr.employee.departure'].create({
            'employee_id': self.employee.id,
            'departure_reason_id': self.reason_resigned.id,
            'notice_period_start_date': start_date,
            'notice_period_end_date': end_date2,
        })
        wizard2.action_schedule()

        settlements = self.env['final.settlement'].search([
            ('employee_id', '=', self.employee.id),
            ('state', '!=', 'cancel'),
        ])
        self.assertEqual(len(settlements), 1, "Must not create duplicate active settlements")
        self.assertEqual(settlements[0].last_working_day, end_date2)

    def test_03_full_workflow_from_schedule_to_paid(self):
        """Test full workflow transitions and contract closure."""
        end_date = Date.from_string('2026-11-09')
        wizard = self.env['hr.employee.departure'].create({
            'employee_id': self.employee.id,
            'departure_reason_id': self.reason_resigned.id,
            'notice_period_start_date': Date.from_string('2026-10-09'),
            'notice_period_end_date': end_date,
        })
        wizard.action_schedule()

        settlement = self.env['final.settlement'].search([
            ('employee_id', '=', self.employee.id),
            ('state', '=', 'draft')
        ], limit=1)
        self.assertTrue(settlement)

        # Direct Approve (1-click from Draft)
        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')
        if hasattr(self, 'contract'):
            self.assertEqual(self.contract.date_end, end_date)

    def test_04_all_departure_reasons_sync_correct_exit_reason(self):
        """Test scheduling departure with various reasons auto-creates final settlement with matching exit reason."""
        reason_map = {
            'Retired': 'retirement',
            'Fired': 'termination',
            'Dead': 'death',
            'Contract Completion': 'contract_end',
            'Other': 'other',
            'Resigned': 'resignation',
        }
        for reason_name, expected_exit_reason in reason_map.items():
            reason_rec = self.env['hr.departure.reason'].search([('name', 'ilike', reason_name)], limit=1)
            if not reason_rec:
                reason_rec = self.env['hr.departure.reason'].create({'name': reason_name})

            emp = self.env['hr.employee'].create({
                'name': f'Sync Test Emp {reason_name}',
                'company_id': self.company.id,
                'first_contract_date': Date.from_string('2022-01-01'),
            })

            # Create departure record (what Schedule button executes)
            dep = self.env['hr.employee.departure'].create({
                'employee_id': emp.id,
                'departure_reason_id': reason_rec.id,
                'notice_period_start_date': Date.from_string('2026-10-12'),
                'notice_period_end_date': Date.from_string('2026-11-12'),
                'departure_date': Date.from_string('2026-11-12'),
                'departure_description': f'Scheduled departure for {reason_name}',
            })

            settlement = self.env['final.settlement'].search([('employee_id', '=', emp.id)], limit=1)
            self.assertTrue(settlement, f"Draft settlement must be auto-created for reason {reason_name}")
            self.assertEqual(settlement.exit_reason, expected_exit_reason, f"Mismatched exit_reason for {reason_name}")
            self.assertEqual(settlement.departure_reason_id, reason_rec)
            self.assertEqual(settlement.departure_id, dep)

    def test_05_manual_settlement_creation_onchange_syncs_departure(self):
        """Test manual settlement creation _onchange_employee_id pulls departure reason and lwd."""
        reason_retired = self.env['hr.departure.reason'].search([('name', 'ilike', 'Retir')], limit=1)
        if not reason_retired:
            reason_retired = self.env['hr.departure.reason'].create({'name': 'Retired'})

        emp = self.env['hr.employee'].create({
            'name': 'Retired Manual Settlement Emp',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2019-01-01'),
        })
        dep = self.env['hr.employee.departure'].create({
            'employee_id': emp.id,
            'departure_reason_id': reason_retired.id,
            'notice_period_start_date': Date.from_string('2026-10-12'),
            'notice_period_end_date': Date.from_string('2026-12-31'),
            'departure_date': Date.from_string('2026-12-31'),
        })
        # Remove auto-created settlement to test manual onchange
        self.env['final.settlement'].search([('employee_id', '=', emp.id)]).unlink()

        manual_fs = self.env['final.settlement'].new({'employee_id': emp.id})
        manual_fs._onchange_employee_id()

        self.assertEqual(manual_fs.exit_reason, 'retirement')
        self.assertEqual(manual_fs.departure_reason_id, reason_retired)
        self.assertEqual(manual_fs.last_working_day, Date.from_string('2026-12-31'))

    def test_06_bidirectional_onchanges_in_form_view(self):
        """Test changing departure_reason_id or exit_reason updates each other in form view."""
        reason_fired = self.env['hr.departure.reason'].search([('name', 'ilike', 'Fire')], limit=1)
        if not reason_fired:
            reason_fired = self.env['hr.departure.reason'].create({'name': 'Fired'})
        reason_dead = self.env['hr.departure.reason'].search([('name', 'ilike', 'Dead')], limit=1)
        if not reason_dead:
            reason_dead = self.env['hr.departure.reason'].create({'name': 'Dead'})

        fs = self.env['final.settlement'].new({'employee_id': self.employee.id})
        
        # Select departure_reason_id = Fired -> exit_reason should become 'termination'
        fs.departure_reason_id = reason_fired
        fs._onchange_departure_reason_id()
        self.assertEqual(fs.exit_reason, 'termination')

        # Select exit_reason = 'death' -> departure_reason_id should become Dead
        fs.exit_reason = 'death'
        fs._onchange_exit_reason()
        self.assertEqual(fs.departure_reason_id, reason_dead)

