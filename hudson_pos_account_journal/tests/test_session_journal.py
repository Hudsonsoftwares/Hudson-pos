# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged('post_install', '-at_install')
class TestSessionClosingJournal(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product = self.create_product('Connector Product', self.categ_basic, 10.0)

    def test_closing_entry_in_pos_journal(self):
        self.open_new_session()
        self.env['pos.order'].sync_from_ui([self.create_ui_order_data([(self.product, 1)])])
        self.pos_session.close_session_from_ui()

        moves = self.pos_session.sale_move_ids
        self.assertTrue(moves, "Closing the session should create a journal entry")
        self.assertEqual(moves.journal_id, self.config.journal_id)
        self.assertEqual(moves.state, 'posted')
