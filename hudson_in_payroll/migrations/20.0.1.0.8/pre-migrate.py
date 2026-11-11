# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Payment modes moved from hudson_in_payroll to hudson_payroll_base (shared by every localization).
# The external ids keep their names; only their module changes, so the upgrade sees the records as
# moved (nothing is deleted). NEFT / RTGS and UPI stay in the Indian module. The same script runs in
# hudson_payroll_base, so the move happens whichever module is upgraded first.
MOVED_NAMES = (
    'model_hds_payment_mode',
    'field_hr_employee__hds_in_payment_mode',
    'field_hr_payslip__hds_in_payment_mode',
    'hds_payment_mode_view_list',
    'hds_payment_mode_view_form',
    'hds_payment_mode_view_search',
    'action_hds_payment_mode',
    'menu_hds_payment_mode',
    'access_hds_payment_mode_user',
    'access_hds_payment_mode_manager',
    'hds_payment_mode_comp_rule',
    'payment_mode_bank_transfer',
    'payment_mode_cheque',
    'payment_mode_cash',
)


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data
           SET module = 'hudson_payroll_base'
         WHERE module = 'hudson_in_payroll'
           AND (name IN %s OR name LIKE 'field\_hds\_payment\_mode\_\_%%')
           AND NOT EXISTS (SELECT 1 FROM ir_model_data other
                            WHERE other.module = 'hudson_payroll_base' AND other.name = ir_model_data.name)
    """, [MOVED_NAMES])
    _logger.info("Payment modes: %s external ids moved to hudson_payroll_base", cr.rowcount)
