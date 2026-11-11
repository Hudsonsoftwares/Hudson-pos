# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsAuditLogging(TransactionCase):

    def setUp(self):
        super(TestTdsAuditLogging, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'is_active': True,
            })

        self.employee = self.env['hr.employee'].create({
            'name': 'Audit Logging Test Employee',
            'birthday': '1995-01-01',
        })

    def test_01_structured_audit_summary_logging(self):
        """Test that TdsOrchestrationEngine executes cleanly and logs the structured audit summary."""
        from hudson_in_payroll.services.tds.tds_orchestration_engine import TdsOrchestrationEngine

        engine = TdsOrchestrationEngine(self.env)
        eval_date = fields.Date.from_string('2025-04-15')

        # Execute TDS calculation
        res = engine.hds_in_compute_tds(self.employee, eval_date=eval_date)

        # Assert calculation completeness and non-null result
        self.assertIsNotNone(res)
        self.assertIsNotNone(res.current_month_tds)
        self.assertEqual(res.employee_id, self.employee.id)
