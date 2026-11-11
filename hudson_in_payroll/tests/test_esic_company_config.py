# -*- coding: utf-8 -*-
import datetime
from odoo.tests import common, tagged
from odoo.exceptions import ValidationError
from ..services.esic.contribution_period_service import ESICContributionPeriodService


@tagged('post_install', '-at_install')
class TestEsicCompanyConfig(common.TransactionCase):

    def setUp(self):
        super(TestEsicCompanyConfig, self).setUp()
        self.company = self.env.company

    def test_01_res_company_esic_fields(self):
        """Test default values and update on res.company ESIC configuration fields."""
        self.assertTrue(self.company.hds_in_esic_applicable)

        self.company.write({
            'hds_in_esic_applicable': True,
            'hds_in_esic_employer_code': '31000123450000101',
            'hds_in_esic_registration_no': 'ESIC/MH/3100012',
            'hds_in_esic_branch_office': 'Sub-Regional Office Thane',
        })

        self.assertEqual(self.company.hds_in_esic_employer_code, '31000123450000101')
        self.assertEqual(self.company.hds_in_esic_registration_no, 'ESIC/MH/3100012')
        self.assertEqual(self.company.hds_in_esic_branch_office, 'Sub-Regional Office Thane')

    def test_02_res_config_settings_esic_related_fields(self):
        """Test reading and writing ESIC fields via res.config.settings transient model."""
        config = self.env['res.config.settings'].create({
            'hds_in_esic_applicable': True,
            'hds_in_esic_employer_code': '31999999990000101',
            'hds_in_esic_registration_no': 'ESIC/KA/9999999',
            'hds_in_esic_branch_office': 'SRO Peenya',
        })
        config.execute()

        self.assertEqual(self.company.hds_in_esic_employer_code, '31999999990000101')
        self.assertEqual(self.company.hds_in_esic_registration_no, 'ESIC/KA/9999999')
        self.assertEqual(self.company.hds_in_esic_branch_office, 'SRO Peenya')

    def test_03_esic_contribution_period_model_crud(self):
        """Test creating, reading, and computing fields on esic.contribution.period model with directly configurable months."""
        PeriodModel = self.env['esic.contribution.period']

        # 1. Create standard April-September & October-March
        period_std = PeriodModel.create({
            'period1_start_month': '4',
            'period1_end_month': '9',
            'period2_start_month': '10',
            'period2_end_month': '3',
            'company_id': self.company.id,
            'active': True,
        })
        self.assertIn("April–September & October–March", period_std.name)
        self.assertIn("April to September", period_std.summary)

        # 2. Create custom months (e.g. July-December & January-June)
        period_custom = PeriodModel.create({
            'period1_start_month': '7',
            'period1_end_month': '12',
            'period2_start_month': '1',
            'period2_end_month': '6',
            'company_id': self.company.id,
            'active': False,
        })
        self.assertIn("July–December & January–June", period_custom.name)
        self.assertIn("July to December", period_custom.summary)

        # 3. Validation error on invalid dates
        with self.assertRaises(ValidationError):
            PeriodModel.create({
                'period1_start_month': '4',
                'period1_end_month': '9',
                'period2_start_month': '10',
                'period2_end_month': '3',
                'date_from': datetime.date(2026, 12, 31),
                'date_to': datetime.date(2026, 1, 1),
            })

    def test_04_esic_contribution_period_service_calculation(self):
        """Test ESICContributionPeriodService respects configurable period months."""
        service = ESICContributionPeriodService(self.env)
        PeriodModel = self.env['esic.contribution.period']

        # Clear existing active periods for company test isolation
        existing = PeriodModel.search([('company_id', '=', self.company.id)])
        existing.write({'active': False})

        # 1. Standard April-September & October-March
        period_rec = PeriodModel.create({
            'period1_start_month': '4',
            'period1_end_month': '9',
            'period2_start_month': '10',
            'period2_end_month': '3',
            'company_id': self.company.id,
            'active': True,
        })
        start, end = service.get_contribution_period_bounds(datetime.date(2026, 5, 10), company=self.company)
        self.assertEqual(start, datetime.date(2026, 4, 1))
        self.assertEqual(end, datetime.date(2026, 9, 30))

        start, end = service.get_contribution_period_bounds(datetime.date(2027, 2, 10), company=self.company)
        self.assertEqual(start, datetime.date(2026, 10, 1))
        self.assertEqual(end, datetime.date(2027, 3, 31))

        # 2. Configured to July-December & January-June
        period_rec.write({
            'period1_start_month': '7',
            'period1_end_month': '12',
            'period2_start_month': '1',
            'period2_end_month': '6',
        })
        start, end = service.get_contribution_period_bounds(datetime.date(2026, 8, 15), company=self.company)
        self.assertEqual(start, datetime.date(2026, 7, 1))
        self.assertEqual(end, datetime.date(2026, 12, 31))

        start, end = service.get_contribution_period_bounds(datetime.date(2026, 3, 10), company=self.company)
        self.assertEqual(start, datetime.date(2026, 1, 1))
        self.assertEqual(end, datetime.date(2026, 6, 30))

        # 3. Configured to May-October & November-April
        period_rec.write({
            'period1_start_month': '5',
            'period1_end_month': '10',
            'period2_start_month': '11',
            'period2_end_month': '4',
        })
        start, end = service.get_contribution_period_bounds(datetime.date(2026, 6, 1), company=self.company)
        self.assertEqual(start, datetime.date(2026, 5, 1))
        self.assertEqual(end, datetime.date(2026, 10, 31))

        start, end = service.get_contribution_period_bounds(datetime.date(2027, 1, 15), company=self.company)
        self.assertEqual(start, datetime.date(2026, 11, 1))
        self.assertEqual(end, datetime.date(2027, 4, 30))
