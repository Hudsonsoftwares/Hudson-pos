# -*- coding: utf-8 -*-
"""Phase 0: the fixed-window rate limiter that throttles public endpoints."""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'eh_hr', 'eh_hr_security')
class TestRateLimit(TransactionCase):

    def test_hit_enforces_limit_within_window(self):
        rl = self.env['eh.hr.rate.limit']
        # A wide window keeps all calls in one bucket for the test.
        for n in range(3):
            self.assertTrue(rl.hit('test.scope', 'caller-1', 3, 3600),
                            'Call %s should be within the budget of 3.' % (n + 1))
        # The 4th call exceeds the budget.
        self.assertFalse(rl.hit('test.scope', 'caller-1', 3, 3600),
                         'The 4th call must exceed a budget of 3.')

    def test_keys_are_independent(self):
        rl = self.env['eh.hr.rate.limit']
        self.assertTrue(rl.hit('test.scope', 'caller-A', 1, 3600))
        self.assertFalse(rl.hit('test.scope', 'caller-A', 1, 3600))
        # A different caller has its own bucket and is unaffected.
        self.assertTrue(rl.hit('test.scope', 'caller-B', 1, 3600))

    def test_non_positive_limit_disables_throttle(self):
        rl = self.env['eh.hr.rate.limit']
        for _ in range(50):
            self.assertTrue(rl.hit('test.scope', 'caller-X', 0, 3600))
