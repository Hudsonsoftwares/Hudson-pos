# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration script for Hudson Indian Payroll v19.0.1.0.6.

    Problem: The `hds_in_payment_mode` field on `hr_payslip` and `hr_employee`
    was previously a VARCHAR Selection field storing string keys like 'bank_transfer'.
    It has been changed to a Many2one (INTEGER FK to hds_payment_mode).

    Odoo's upgrade path fails with:
        psycopg2.errors.InvalidTextRepresentation:
        invalid input syntax for type integer: "bank_transfer"

    Fix: Drop the old varchar columns BEFORE Odoo tries to ALTER them.
    Odoo will then recreate them as clean INTEGER columns.
    The data loss is intentional here — employees/payslips will get their
    payment mode re-assigned via the post_init or manually by the admin.
    """
    _logger.info(
        "HDS Pre-Migration 19.0.1.0.6: Dropping old VARCHAR hds_in_payment_mode "
        "columns to allow conversion to Many2one (INTEGER FK)."
    )

    # Drop from hr_payslip if it exists as a non-integer column
    cr.execute("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'hr_payslip'
          AND column_name = 'hds_in_payment_mode';
    """)
    row = cr.fetchone()
    if row and row[0] in ('character varying', 'varchar', 'text'):
        _logger.info(
            "HDS Pre-Migration: hr_payslip.hds_in_payment_mode is VARCHAR ('%s') — dropping column.", row[0]
        )
        cr.execute("ALTER TABLE hr_payslip DROP COLUMN IF EXISTS hds_in_payment_mode;")
        _logger.info("HDS Pre-Migration: Dropped hr_payslip.hds_in_payment_mode (VARCHAR).")
    elif row:
        _logger.info(
            "HDS Pre-Migration: hr_payslip.hds_in_payment_mode already type '%s' — no action needed.", row[0]
        )
    else:
        _logger.info(
            "HDS Pre-Migration: hr_payslip.hds_in_payment_mode column not found — will be created fresh."
        )

    # Drop from hr_employee if it exists as a non-integer column
    cr.execute("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
          AND column_name = 'hds_in_payment_mode';
    """)
    row = cr.fetchone()
    if row and row[0] in ('character varying', 'varchar', 'text'):
        _logger.info(
            "HDS Pre-Migration: hr_employee.hds_in_payment_mode is VARCHAR ('%s') — dropping column.", row[0]
        )
        cr.execute("ALTER TABLE hr_employee DROP COLUMN IF EXISTS hds_in_payment_mode;")
        _logger.info("HDS Pre-Migration: Dropped hr_employee.hds_in_payment_mode (VARCHAR).")
    elif row:
        _logger.info(
            "HDS Pre-Migration: hr_employee.hds_in_payment_mode already type '%s' — no action needed.", row[0]
        )
    else:
        _logger.info(
            "HDS Pre-Migration: hr_employee.hds_in_payment_mode column not found — will be created fresh."
        )

    _logger.info(
        "HDS Pre-Migration 19.0.1.0.6: Column cleanup complete. "
        "Odoo will now create fresh INTEGER FK columns for hds_in_payment_mode."
    )
