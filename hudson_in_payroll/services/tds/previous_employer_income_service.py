# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class PreviousEmployerIncomeResult:
    """
    Data Transfer Object (DTO) holding aggregated Previous Employer income and tax details.
    """
    def __init__(self, taxable_salary=0.0, tds_deducted=0.0, pt_deducted=0.0, pf_contributed=0.0, has_declaration=False):
        self.taxable_salary = taxable_salary
        self.tds_deducted = tds_deducted
        self.pt_deducted = pt_deducted
        self.pf_contributed = pf_contributed
        self.has_declaration = has_declaration


class PreviousEmployerIncomeService(BaseStatutoryService):
    """
    Phase 4 Service: Previous Employer Income Aggregation Service.
    Aggregates taxable salary, TDS deducted, Professional Tax, and EPF from previous employers
    declared via Form 12B / Income Declaration for mid-year joiners.

    Source Priority:
      1. tds.employee.income.declaration (stored Form 12B — most authoritative)
      2. tds.employee.income.declaration found via tds.employee.declaration link
      3. tds.employee.declaration (main declaration — reads its linked inc_decl directly,
         bypassing the store=False computed field to avoid stale cache)
      4. hr.employee direct fields (hds_in_prev_taxable_gross / hds_in_prev_tds_deducted)
    """

    def aggregate_previous_employer_income(self, employee, financial_year):
        """
        Aggregates previous employer income for the employee in the specified Financial Year.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :return: PreviousEmployerIncomeResult
        """
        if not employee or not financial_year:
            return PreviousEmployerIncomeResult(has_declaration=False)

        taxable_salary = 0.0
        tds_deducted = 0.0
        pt_deducted = 0.0
        pf_contributed = 0.0
        has_declaration = False

        _logger.warning(
            "[PREV_EMP_INCOME_SVC] START | employee_id=%s | fy_id=%s | fy_name=%s",
            employee.id, financial_year.id,
            getattr(financial_year, 'name', 'N/A')
        )

        # ── Source 1: tds.employee.income.declaration (stored, authoritative) ──────────
        inc_decl = self.env['tds.employee.income.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id),
        ], limit=1)
        if not inc_decl:
            inc_decl = self.env['tds.employee.income.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
            ], order='id desc', limit=1)

        _logger.warning(
            "[PREV_EMP_INCOME_SVC] Source-1 search | inc_decl_id=%s | "
            "prev_gross=%s | prev_tds=%s",
            inc_decl.id if inc_decl else 'NOT FOUND',
            float(inc_decl.prev_employer_taxable_gross or 0.0) if inc_decl else 'N/A',
            float(inc_decl.prev_employer_tds or 0.0) if inc_decl else 'N/A',
        )

        if inc_decl:
            s1_gross = float(inc_decl.prev_employer_taxable_gross or 0.0)
            s1_tds = float(inc_decl.prev_employer_tds or 0.0)
            s1_pt = float(inc_decl.prev_employer_pt or 0.0)
            s1_pf = float(inc_decl.prev_employer_pf or 0.0)
            if s1_gross > 0.0:
                taxable_salary = max(taxable_salary, s1_gross)
                has_declaration = True
            if s1_tds > 0.0:
                tds_deducted = max(tds_deducted, s1_tds)
                has_declaration = True
            pt_deducted = max(pt_deducted, s1_pt)
            pf_contributed = max(pf_contributed, s1_pf)

        # ── Source 2: tds.employee.declaration (main declaration) ─────────────────────
        if taxable_salary == 0.0 or tds_deducted == 0.0:
            main_decl = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
            ], order='id desc', limit=1)
            if not main_decl:
                main_decl = self.env['tds.employee.declaration'].sudo().search([
                    ('employee_id', '=', employee.id),
                ], order='id desc', limit=1)

            _logger.warning(
                "[PREV_EMP_INCOME_SVC] Source-2 search | main_decl_id=%s",
                main_decl.id if main_decl else 'NOT FOUND',
            )

            if main_decl:
                linked_inc_decl = self.env['tds.employee.income.declaration'].sudo().search([
                    ('employee_id', '=', main_decl.employee_id.id),
                ], order='id desc', limit=1)

                if linked_inc_decl:
                    s2_gross = float(linked_inc_decl.prev_employer_taxable_gross or 0.0)
                    s2_tds = float(linked_inc_decl.prev_employer_tds or 0.0)
                    if s2_gross > 0.0:
                        taxable_salary = max(taxable_salary, s2_gross)
                        has_declaration = True
                    if s2_tds > 0.0:
                        tds_deducted = max(tds_deducted, s2_tds)
                        has_declaration = True
                    pt_deducted = max(pt_deducted, float(linked_inc_decl.prev_employer_pt or 0.0))
                    pf_contributed = max(pf_contributed, float(linked_inc_decl.prev_employer_pf or 0.0))

                try:
                    main_decl.invalidate_recordset(['prev_employer_taxable_gross', 'prev_employer_tds',
                                                    'prev_employer_pt', 'prev_employer_pf'])
                except Exception:
                    pass
                raw_gross = float(main_decl.prev_employer_taxable_gross or 0.0)
                raw_tds = float(main_decl.prev_employer_tds or 0.0)
                if raw_gross > 0.0:
                    taxable_salary = max(taxable_salary, raw_gross)
                    has_declaration = True
                if raw_tds > 0.0:
                    tds_deducted = max(tds_deducted, raw_tds)
                    has_declaration = True

        # ── Source 3: hr.employee direct fields ───────────────────────────────────────
        if taxable_salary == 0.0 or tds_deducted == 0.0:
            emp_gross = float(getattr(employee, 'hds_in_prev_taxable_gross', 0.0) or 0.0)
            emp_tds = float(getattr(employee, 'hds_in_prev_tds_deducted', 0.0) or 0.0)

            _logger.warning(
                "[PREV_EMP_INCOME_SVC] Source-3 hr.employee fields | "
                "hds_in_prev_taxable_gross=%s | hds_in_prev_tds_deducted=%s",
                emp_gross, emp_tds
            )

            if emp_gross > 0.0:
                taxable_salary = max(taxable_salary, emp_gross)
                has_declaration = True
            if emp_tds > 0.0:
                tds_deducted = max(tds_deducted, emp_tds)
                has_declaration = True
            pt_deducted = max(pt_deducted, float(getattr(employee, 'hds_in_prev_pt_deducted', 0.0) or 0.0))
            pf_contributed = max(pf_contributed, float(getattr(employee, 'hds_in_prev_employer_pf', 0.0) or 0.0))

        _logger.warning(
            "[PREV_EMP_INCOME_SVC] RESULT | has_declaration=%s | "
            "taxable_salary=%s | tds_deducted=%s | pt=%s | pf=%s",
            has_declaration, taxable_salary, tds_deducted, pt_deducted, pf_contributed
        )

        return PreviousEmployerIncomeResult(
            taxable_salary=taxable_salary,
            tds_deducted=tds_deducted,
            pt_deducted=pt_deducted,
            pf_contributed=pf_contributed,
            has_declaration=has_declaration
        )
