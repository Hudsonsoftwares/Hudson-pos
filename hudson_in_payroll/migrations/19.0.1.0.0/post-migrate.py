# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migration script for Hudson Indian Payroll v19.0.1.0.0.
    Ensures that any legacy Kerala Monthly Professional Tax records in the database
    are updated to Half-Yearly and synchronized with the latest statutory seed data.
    """
    _logger.info("Hudson Indian Payroll Migration: Synchronizing Kerala PT Slabs...")

    # 1. Force noupdate=False for pt.state.slab records in ir_model_data
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = false
        WHERE module = 'hudson_in_payroll' AND model = 'pt.state.slab';
    """)

    # 2. Update legacy DB records linked to XML IDs pt_slab_kl_01, pt_slab_kl_02, pt_slab_kl_03
    cr.execute("""
        UPDATE pt_state_slab
        SET periodicity = 'half_yearly',
            salary_from = 0.0,
            salary_to = 11999.0,
            pt_amount = 0.0
        WHERE id IN (
            SELECT res_id FROM ir_model_data WHERE module = 'hudson_in_payroll' AND name = 'pt_slab_kl_01'
        );
    """)

    cr.execute("""
        UPDATE pt_state_slab
        SET periodicity = 'half_yearly',
            salary_from = 12000.0,
            salary_to = 17999.0,
            pt_amount = 120.0
        WHERE id IN (
            SELECT res_id FROM ir_model_data WHERE module = 'hudson_in_payroll' AND name = 'pt_slab_kl_02'
        );
    """)

    cr.execute("""
        UPDATE pt_state_slab
        SET periodicity = 'half_yearly',
            salary_from = 18000.0,
            salary_to = 29999.0,
            pt_amount = 180.0
        WHERE id IN (
            SELECT res_id FROM ir_model_data WHERE module = 'hudson_in_payroll' AND name = 'pt_slab_kl_03'
        );
    """)

    # 3. Clean up any remaining obsolete monthly records for Kerala
    cr.execute("""
        UPDATE pt_state_slab
        SET periodicity = 'half_yearly'
        WHERE state_id = (SELECT id FROM res_country_state WHERE code = 'KL')
          AND periodicity = 'monthly';
    """)

    _logger.info("Hudson Indian Payroll Migration: Kerala PT Slabs successfully synchronized to Half-Yearly.")
