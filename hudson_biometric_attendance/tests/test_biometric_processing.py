# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from odoo.tests.common import TransactionCase

class TestBiometricProcessing(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a test company
        cls.company = cls.env['res.company'].create({'name': 'Hudson Test Company'})
        
        # Create test employees
        cls.employee_1 = cls.env['hr.employee'].create({
            'name': 'John Doe',
            'biometric_code': 'BIO001',
            'company_id': cls.company.id,
        })
        cls.employee_2 = cls.env['hr.employee'].create({
            'name': 'Jane Smith',
            'barcode': 'BAR002',  # standard Odoo barcode/badge ID fallback
            'company_id': cls.company.id,
        })

        # Create a dummy device
        cls.device = cls.env['hudson.attendance.device'].create({
            'name': 'Office Gate Device',
            'connection_type': 'zk_direct',
            'address': '192.168.1.150',
            'company_id': cls.company.id,
        })

    def test_employee_resolution(self):
        """Test that punches map correctly to employee via biometric_code or barcode."""
        # 1. Match via biometric_code
        punch_1 = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 8, 0, 0),
            'punch_type': 'in',
        })
        punch_1._process_punch()
        self.assertEqual(punch_1.state, 'processed', punch_1.error_message)
        self.assertTrue(punch_1.hr_attendance_id)
        self.assertEqual(punch_1.hr_attendance_id.employee_id, self.employee_1)

        # 2. Match via barcode fallback
        punch_2 = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'BAR002',
            'punch_time': datetime(2026, 7, 18, 8, 5, 0),
            'punch_type': 'in',
        })
        punch_2._process_punch()
        self.assertEqual(punch_2.state, 'processed', punch_2.error_message)
        self.assertTrue(punch_2.hr_attendance_id)
        self.assertEqual(punch_2.hr_attendance_id.employee_id, self.employee_2)

        # 3. Unmapped case
        punch_3 = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'UNKNOWN',
            'punch_time': datetime(2026, 7, 18, 8, 10, 0),
            'punch_type': 'in',
        })
        punch_3._process_punch()
        self.assertEqual(punch_3.state, 'unmapped')
        self.assertFalse(punch_3.hr_attendance_id)
        self.assertIn("No employee found", punch_3.error_message)

    def test_duplicate_handling(self):
        """Test duplicate check on external_uid and temporal proximity."""
        # Process a valid punch first
        punch_orig = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 8, 0, 0),
            'punch_type': 'in',
            'external_uid': 'TX10001',
        })
        punch_orig._process_punch()
        self.assertEqual(punch_orig.state, 'processed', punch_orig.error_message)

        # 1. Duplicate external ID
        punch_dup_uid = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 8, 10, 0),
            'punch_type': 'in',
            'external_uid': 'TX10001',  # Same UID
        })
        punch_dup_uid._process_punch()
        self.assertEqual(punch_dup_uid.state, 'duplicate')
        self.assertIn("External Unique ID TX10001 already processed", punch_dup_uid.error_message)

        # 2. Temporal duplicate (same employee, same type, within 5s margin)
        # Punch at 8:00:03 is within 5 seconds of 8:00:00
        punch_dup_time = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 8, 0, 3),
            'punch_type': 'in',
        })
        punch_dup_time._process_punch()
        self.assertEqual(punch_dup_time.state, 'duplicate')
        self.assertIn("Similar punch already processed", punch_dup_time.error_message)

    def test_attendance_flow(self):
        """Test full sequence of check-in, check-out, and constraint failures."""
        # 1. First check-in
        p_in_1 = self.env['hudson.attendance.raw.punch'].create({
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 9, 0, 0),
            'punch_type': 'in',
        })
        p_in_1._process_punch()
        self.assertEqual(p_in_1.state, 'processed', p_in_1.error_message)
        attendance = p_in_1.hr_attendance_id
        self.assertTrue(attendance)
        self.assertEqual(attendance.check_in, datetime(2026, 7, 18, 9, 0, 0))
        self.assertFalse(attendance.check_out)

        # 2. Double check-in (should fail)
        p_in_2 = self.env['hudson.attendance.raw.punch'].create({
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 10, 0, 0),
            'punch_type': 'in',
        })
        p_in_2._process_punch()
        self.assertEqual(p_in_2.state, 'failed')
        self.assertIn("already checked in", p_in_2.error_message)

        # 3. Check-out before check-in (should fail)
        p_out_early = self.env['hudson.attendance.raw.punch'].create({
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 8, 30, 0),  # before 9:00:00
            'punch_type': 'out',
        })
        p_out_early._process_punch()
        self.assertEqual(p_out_early.state, 'failed')
        self.assertIn("is before the active check-in time", p_out_early.error_message)

        # 4. Valid check-out
        p_out = self.env['hudson.attendance.raw.punch'].create({
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 17, 0, 0),
            'punch_type': 'out',
        })
        p_out._process_punch()
        self.assertEqual(p_out.state, 'processed', p_out.error_message)
        self.assertEqual(attendance.check_out, datetime(2026, 7, 18, 17, 0, 0))

        # 5. Check-out when not checked in (should fail)
        p_out_orphan = self.env['hudson.attendance.raw.punch'].create({
            'employee_code': 'BIO001',
            'punch_time': datetime(2026, 7, 18, 18, 0, 0),
            'punch_type': 'out',
        })
        p_out_orphan._process_punch()
        self.assertEqual(p_out_orphan.state, 'failed')
        self.assertIn("No active check-in found", p_out_orphan.error_message)

    def test_employee_mapping_resolution(self):
        """Test employee mapping resolution using hudson.attendance.employee.mapping."""
        # Create an employee mapping
        self.env['hudson.attendance.employee.mapping'].create({
            'device_id': self.device.id,
            'external_employee_code': 'EXT_EMP_999',
            'employee_id': self.employee_1.id,
        })

        # Create punch with external code
        punch = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'EXT_EMP_999',
            'punch_time': datetime(2026, 7, 18, 9, 0, 0),
            'punch_type': 'in',
        })
        punch._process_punch()
        self.assertEqual(punch.state, 'processed')
        self.assertEqual(punch.hr_attendance_id.employee_id, self.employee_1)

    def test_unmapped_reprocess_wizard(self):
        """Test unmapped raw punches wizard mapping and reprocessing."""
        # Create unmapped punch
        punch = self.env['hudson.attendance.raw.punch'].create({
            'device_id': self.device.id,
            'employee_code': 'UNMAPPED_CODE_100',
            'punch_time': datetime(2026, 7, 18, 9, 0, 0),
            'punch_type': 'in',
        })
        punch._process_punch()
        self.assertEqual(punch.state, 'unmapped')

        # Run wizard
        wizard = self.env['hudson.attendance.map.reprocess.wizard'].with_context(
            active_ids=[punch.id]
        ).create({
            'employee_id': self.employee_1.id,
        })
        wizard.action_map_and_reprocess()

        # Check that mapping was created
        mapping = self.env['hudson.attendance.employee.mapping'].search([
            ('device_id', '=', self.device.id),
            ('external_employee_code', '=', 'UNMAPPED_CODE_100')
        ])
        self.assertTrue(mapping)
        self.assertEqual(mapping.employee_id, self.employee_1)

        # Check punch was reprocessed
        self.assertEqual(punch.state, 'processed')
        self.assertTrue(punch.hr_attendance_id)

    def test_field_and_value_mapping_rest_poll(self):
        """Test field mapping dot-notation and value mapping translation."""
        from unittest.mock import patch

        # 1. Create Field Mappings
        self.env['hudson.attendance.field.mapping'].create({
            'device_id': self.device.id,
            'src_path': 'data.punch_uid',
            'target_field': 'external_uid',
        })
        self.env['hudson.attendance.field.mapping'].create({
            'device_id': self.device.id,
            'src_path': 'data.badge_id',
            'target_field': 'employee_code',
        })
        self.env['hudson.attendance.field.mapping'].create({
            'device_id': self.device.id,
            'src_path': 'data.time_str',
            'target_field': 'punch_time',
        })
        punch_type_mapping = self.env['hudson.attendance.field.mapping'].create({
            'device_id': self.device.id,
            'src_path': 'data.status_code',
            'target_field': 'punch_type',
        })

        # 2. Create Value Mappings
        self.env['hudson.attendance.value.mapping'].create({
            'field_mapping_id': punch_type_mapping.id,
            'src_value': 'IN_VAL_1',
            'target_value': 'in',
        })

        # Configure REST Device
        self.device.write({
            'connection_type': 'rest_api',
            'address': 'http://dummy-rest-endpoint.local/punches',
        })

        # Mock requests.get response
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "data": {
                    "punch_uid": "REST_UID_8877",
                    "badge_id": "BIO001",
                    "time_str": "2026-07-18 09:00:00",
                    "status_code": "IN_VAL_1",
                }
            }

            self.device.sync_punches()

        # Check raw punch created and processed
        punch = self.env['hudson.attendance.raw.punch'].search([
            ('external_uid', '=', 'REST_UID_8877')
        ])
        self.assertTrue(punch)
        self.assertEqual(punch.employee_code, 'BIO001')
        self.assertEqual(punch.punch_type, 'in')
        self.assertEqual(punch.state, 'processed')

    def test_anomalies_and_regularization_workflow(self):
        """Test anomaly generation and regularization request approval/applying."""
        # Create an attendance exceeding 12 hours to trigger Unusual Hours anomaly
        att = self.env['hr.attendance'].with_context(biometric_punch_processing=True).create({
            'employee_id': self.employee_1.id,
            'check_in': datetime(2026, 7, 18, 8, 0, 0),
            'check_out': datetime(2026, 7, 18, 22, 0, 0),  # 14 hours
        })

        anomaly = self.env['hudson.attendance.anomaly'].search([
            ('attendance_id', '=', att.id),
            ('anomaly_type', '=', 'unusual_hours')
        ])
        self.assertTrue(anomaly)

        # Create Regularization request
        reg = self.env['hudson.attendance.regularization'].create({
            'employee_id': self.employee_1.id,
            'anomaly_id': anomaly.id,
            'attendance_id': att.id,
            'corrected_check_in': datetime(2026, 7, 18, 8, 0, 0),
            'corrected_check_out': datetime(2026, 7, 18, 17, 0, 0),  # Corrected to 9 hours
            'reason': 'Forgot to check out on time, left at 5 PM.',
        })

        self.assertEqual(reg.state, 'draft')
        reg.action_submit()
        self.assertEqual(reg.state, 'submitted')
        reg.action_approve()
        self.assertEqual(reg.state, 'approved')
        reg.action_apply()
        self.assertEqual(reg.state, 'applied')

        # Check attendance was updated
        self.assertEqual(att.check_out, datetime(2026, 7, 18, 17, 0, 0))
