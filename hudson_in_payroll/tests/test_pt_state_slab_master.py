# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from .test_pt_state_slab import TestPtStateSlab


class TestPTStateSlabMaster(TestPtStateSlab):
    """
    Test suite matching Phase 9 deliverable name test_pt_state_slab_master.py.
    Verifies state slab master records, XML seed data, and constraint validations.
    """

    def test_08_xml_seed_data_integrity(self):
        """Verify XML seed data loaded successfully for all 9 confirmed states."""
        states = ['MH', 'KA', 'WB', 'AP', 'TS', 'TN', 'GJ', 'MP', 'KL']
        for code in states:
            state = self.env.ref(f'base.state_in_{code.lower()}')
            slabs = self.env['pt.state.slab'].search([('state_id', '=', state.id)])
            self.assertTrue(len(slabs) > 0, f"No PT seed slabs found for state code {code}")

        # Total confirmed records across 9 states is 40
        total_seed_slabs = self.env['pt.state.slab'].search_count([])
        self.assertGreaterEqual(total_seed_slabs, 40)
