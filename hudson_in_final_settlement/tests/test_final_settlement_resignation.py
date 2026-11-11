# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date
from odoo.exceptions import UserError, ValidationError  # pyrefly: ignore [missing-import]


class TestFinalSettlementResignation(TransactionCase):

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestFinalSettlementResignation, cls).tearDownClass()
        except Exception:
            pass

    def setUp(self):
        super(TestFinalSettlementResignation, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Resignation Settlement Test Company'
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Resigning Exiting Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-06-01'),
        })
        self.resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'resignation_type': 'resigned',
            'joined_date': Date.from_string('2018-06-01'),
            'expected_revealing_date': Date.from_string('2026-04-30'),
            'reason': 'Moving to higher study',
        })

    def test_01_create_settlement_from_approved_resignation(self):
        """Test settlement creation from approved resignation with auto sync."""
        self.resignation.write({
            'state': 'approved',
            'approved_revealing_date': Date.from_string('2026-04-30')
        })

        action = self.resignation.action_create_final_settlement()
        self.assertEqual(action['res_model'], 'final.settlement')

        settlement = self.env['final.settlement'].browse(action['res_id'])
        self.assertEqual(settlement.employee_id, self.employee)
        self.assertEqual(settlement.company_id, self.company)
        self.assertEqual(settlement.resignation_id, self.resignation)
        self.assertEqual(settlement.last_working_day, Date.from_string('2026-04-30'))
        self.assertEqual(settlement.exit_reason, 'resignation')
        self.assertEqual(settlement.state, 'draft')

    def test_02_prevent_duplicate_active_settlements(self):
        """Test active settlement uniqueness constraint per resignation."""
        self.resignation.write({'state': 'approved'})

        # First settlement creation
        action = self.resignation.action_create_final_settlement()
        settlement1 = self.env['final.settlement'].browse(action['res_id'])

        # Calling action_create_final_settlement again should return existing settlement
        action2 = self.resignation.action_create_final_settlement()
        self.assertEqual(action2['res_id'], settlement1.id)

        # Attempting direct ORM creation of duplicate active settlement should raise ValidationError
        with self.assertRaises(ValidationError):
            self.env['final.settlement'].create({
                'employee_id': self.employee.id,
                'resignation_id': self.resignation.id,
                'last_working_day': Date.from_string('2026-04-30'),
            })

    def test_03_unapproved_resignation_prevention(self):
        """Test error raised when trying to create settlement for unapproved resignation."""
        self.resignation.write({'state': 'draft'})
        with self.assertRaises(UserError):
            self.resignation.action_create_final_settlement()

    def test_04_multi_company_isolation(self):
        """Test multi-company values synchronization."""
        company2 = self.env['res.company'].create({'name': 'Secondary Exit Company'})
        employee2 = self.env['hr.employee'].create({
            'name': 'Company 2 Employee',
            'company_id': company2.id
        })
        resignation2 = self.env['hr.resignation'].create({
            'employee_id': employee2.id,
            'state': 'approved',
            'expected_revealing_date': Date.from_string('2026-05-15'),
            'reason': 'Relocation',
        })

        action = resignation2.action_create_final_settlement()
        settlement2 = self.env['final.settlement'].browse(action['res_id'])
        self.assertEqual(settlement2.company_id, company2)
