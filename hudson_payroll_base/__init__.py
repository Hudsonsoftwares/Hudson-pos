# -*- coding: utf-8 -*-
from . import models
from . import wizard


def pre_init_hook(env):
    """Ensure custom company columns exist in PostgreSQL before any model runs _auto_init."""
    try:
        env.cr.execute("""
            ALTER TABLE res_company 
            ADD COLUMN IF NOT EXISTS enable_attendance_threshold BOOLEAN DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS min_attendance_threshold_days NUMERIC DEFAULT 14.0;
        """)
    except Exception:
        pass


def post_init_hook(env):
    """Ensure standard salary structures, categories, and rules are company-agnostic (company_id=NULL)."""
    try:
        env.cr.execute("""
            UPDATE hr_payroll_structure
            SET company_id = NULL
            WHERE code IN ('REGULAR', 'WORKER');

            UPDATE hr_salary_rule
            SET company_id = NULL
            WHERE struct_id IN (
                SELECT id FROM hr_payroll_structure WHERE code IN ('REGULAR', 'WORKER')
            );

            UPDATE hr_salary_rule_category
            SET company_id = NULL
            WHERE code IN ('BASIC', 'ALW', 'GROSS', 'DED', 'NET', 'COMP');
        """)
    except Exception:
        pass
