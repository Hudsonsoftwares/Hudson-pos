# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migration script for Hudson Indian Payroll v19.0.1.0.3.
    Reassigns the ir.model.data 'module' column from 'hudson_in_payroll'
    to 'hudson_payroll_core' for hr.rule.parameter and hr.rule.parameter.value
    metadata, security ACLs, views, actions, and menu items.
    """
    _logger.info("Hudson Indian Payroll Migration: Transferring hr.rule.parameter XML IDs to hudson_payroll_core...")

    # 1. Transfer ir.model and ir.model.fields metadata records
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND (
              (model = 'ir.model' AND res_id IN (
                  SELECT id FROM ir_model WHERE model IN ('hr.rule.parameter', 'hr.rule.parameter.value')
              ))
              OR
              (model = 'ir.model.fields' AND res_id IN (
                  SELECT id FROM ir_model_fields WHERE model IN ('hr.rule.parameter', 'hr.rule.parameter.value')
              ))
          );
    """)
    _logger.info("Migrated %s model/field metadata records to hudson_payroll_core.", cr.rowcount)

    # 2. Transfer ir.model.access security ACL records
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND model = 'ir.model.access'
          AND (
              name IN ('access_hr_rule_parameter_manager', 'access_hr_rule_parameter_value_manager')
              OR res_id IN (
                  SELECT id FROM ir_model_access
                  WHERE model_id IN (
                      SELECT id FROM ir_model WHERE model IN ('hr.rule.parameter', 'hr.rule.parameter.value')
                  )
              )
          );
    """)
    _logger.info("Migrated %s security access records to hudson_payroll_core.", cr.rowcount)

    # 3. Transfer ir.ui.view records
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND model = 'ir.ui.view'
          AND name IN (
              'hds_in_hr_rule_parameter_value_view_tree',
              'hds_in_hr_rule_parameter_view_form',
              'hds_in_hr_rule_parameter_view_search',
              'hds_in_hr_rule_parameter_view_tree'
          );
    """)
    _logger.info("Migrated %s view records to hudson_payroll_core.", cr.rowcount)

    # 4. Transfer ir.actions.act_window records
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND model = 'ir.actions.act_window'
          AND name = 'hds_in_action_hr_rule_parameter';
    """)
    _logger.info("Migrated %s action records to hudson_payroll_core.", cr.rowcount)

    # 5. Transfer ir.ui.menu records
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND model = 'ir.ui.menu'
          AND name = 'hds_in_menu_hr_rule_parameter';
    """)
    _logger.info("Migrated %s menu records to hudson_payroll_core.", cr.rowcount)

    # 6. Transfer ir.model.constraint records if any
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'hudson_payroll_core'
        WHERE module = 'hudson_in_payroll'
          AND model = 'ir.model.constraint'
          AND res_id IN (
              SELECT id FROM ir_model_constraint
              WHERE model IN (
                  SELECT id FROM ir_model WHERE model IN ('hr.rule.parameter', 'hr.rule.parameter.value')
              )
          );
    """)
    _logger.info("Migrated %s constraint records to hudson_payroll_core.", cr.rowcount)

    _logger.info("Hudson Indian Payroll Migration: hr.rule.parameter XML ID transfer to hudson_payroll_core completed successfully.")
