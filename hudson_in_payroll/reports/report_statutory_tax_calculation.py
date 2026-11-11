# -*- coding: utf-8 -*-
import logging
import re
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ReportStatutoryTaxCalculation(models.AbstractModel):
    """
    QWeb Report Data Provider — Hudson Payroll Statutory Tax Declaration Report.
    Pure data-mapping layer. All values consumed from existing TDS services.
    No statutory calculations are performed here.
    """
    _name = 'report.hudson_in_payroll.report_statutory_tax_calculation'
    _description = 'Statutory Tax Calculation Audit Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        model_name = self.env.context.get('active_model')
        if not model_name and data:
            model_name = data.get('model_name')

        records = False
        if docids and model_name:
            recs = self.env[model_name].browse(docids).filtered(lambda r: r.exists())
            if recs:
                records = recs

        if not records and docids:
            payslips = self.env['hr.payslip'].browse(docids).filtered(lambda r: r.exists())
            if payslips:
                model_name = 'hr.payslip'
                records = payslips
            else:
                decls = self.env['tds.employee.declaration'].browse(docids).filtered(lambda r: r.exists())
                if decls:
                    model_name = 'tds.employee.declaration'
                    records = decls

        if not records:
            model_name = model_name or 'tds.employee.declaration'
            if model_name == 'tds.employee.declaration':
                emp = self.env.user.employee_id
                if emp:
                    today = fields.Date.today()
                    fy = self.env['tds.financial.year'].search([
                        ('start_date', '<=', today),
                        ('end_date', '>=', today)
                    ], limit=1)
                    domain = [('employee_id', '=', emp.id)]
                    if fy:
                        domain.append(('financial_year_id', '=', fy.id))
                    records = self.env['tds.employee.declaration'].search(domain, limit=1)
            if not records and docids:
                records = self.env[model_name].browse(docids).filtered(lambda r: r.exists())

        decl_records = self.env['tds.employee.declaration']
        report_data_list = []

        for rec in records:
            if not rec.exists():
                continue

            company = rec.company_id if hasattr(rec, 'company_id') and rec.company_id else self.env.company
            if not getattr(company, 'hds_in_tds_applicable', True):
                # pyrefly: ignore [missing-import]
                from odoo.exceptions import UserError
                raise UserError(_("Tax Calculation Report cannot be generated because TDS is disabled in Company Settings for %s.") % company.name)

            # ── Capture payslip-level date context ──────────────────────────
            payslip_rec = False
            payslip_name = 'N/A'
            payslip_date_from_str = 'N/A'
            payslip_date_to_str = 'N/A'
            payroll_month_str = 'N/A'

            if model_name == 'hr.payslip':
                payslip_rec = rec
                employee = rec.employee_id
                # Payroll month MUST come from the actual payslip record, NOT today's date
                eval_date = rec.date_to or fields.Date.today()
                payslip_name = rec.name or f'Payslip #{rec.id}'
                if rec.date_from:
                    payslip_date_from_str = rec.date_from.strftime('%d-%b-%Y')
                if rec.date_to:
                    payslip_date_to_str = rec.date_to.strftime('%d-%b-%Y')
                    payroll_month_str = rec.date_to.strftime('%B %Y')
                financial_year = self.env['tds.financial.year'].search([
                    ('start_date', '<=', eval_date),
                    ('end_date', '>=', eval_date)
                ], limit=1)
                domain = [('employee_id', '=', employee.id), ('state', '!=', 'rejected')]
                if financial_year:
                    domain.append(('financial_year_id', '=', financial_year.id))
                decl = self.env['tds.employee.declaration'].search(
                    domain, order='submission_date desc, create_date desc, id desc', limit=1
                )
                if not decl:
                    decl = self.env['tds.employee.declaration'].search(
                        [('employee_id', '=', employee.id)], order='id desc', limit=1
                    )
                    if decl and not financial_year:
                        financial_year = decl.financial_year_id
            else:
                decl = rec
                employee = decl.employee_id
                financial_year = decl.financial_year_id
                # eval_date MUST stay as today for declaration-based reports.
                # The TDS engine uses eval_date.month to decide normal vs recalculation phase.
                # Overwriting it with the last payslip's date_to would incorrectly place
                # an April report into March's recalculation window.
                eval_date = fields.Date.today()

            if employee and not getattr(employee, 'hds_in_tds_applicable', True):
                from odoo.exceptions import UserError
                raise UserError(_("Tax Calculation Report cannot be generated because TDS is disabled for employee %s.") % employee.name)

                # ── Payslip display-only lookup (for payroll month panel) ─────
                # Rule: find the payslip for TODAY's calendar month first.
                # If none, find the most recent payslip on or before today.
                # NEVER use a payslip dated after today — that would corrupt eval_date.
                import calendar as _calendar
                today = eval_date
                month_start = today.replace(day=1)
                month_end = today.replace(
                    day=_calendar.monthrange(today.year, today.month)[1]
                )

                linked_payslip = False
                if financial_year:
                    # First: payslip whose period overlaps current calendar month
                    linked_payslip = self.env['hr.payslip'].search([
                        ('employee_id', '=', employee.id),
                        ('date_from', '>=', financial_year.start_date),
                        ('date_from', '<=', month_end),
                        ('date_to', '>=', month_start),
                        ('state', 'in', ('done', 'paid', 'verify', 'draft'))
                    ], limit=1)

                    if not linked_payslip:
                        # Fallback: most recent payslip in this FY that is on or before today
                        linked_payslip = self.env['hr.payslip'].search([
                            ('employee_id', '=', employee.id),
                            ('date_from', '>=', financial_year.start_date),
                            ('date_to', '<=', today),          # cap at today — never pull future payslips
                            ('state', 'in', ('done', 'paid', 'verify', 'draft'))
                        ], order='date_to desc', limit=1)

                if linked_payslip:
                    # Use payslip dates for DISPLAY ONLY.
                    # eval_date is intentionally NOT updated here.
                    payslip_name = linked_payslip.name or f'Payslip #{linked_payslip.id}'
                    if linked_payslip.date_from:
                        payslip_date_from_str = linked_payslip.date_from.strftime('%d-%b-%Y')
                    if linked_payslip.date_to:
                        payslip_date_to_str = linked_payslip.date_to.strftime('%d-%b-%Y')
                        payroll_month_str = linked_payslip.date_to.strftime('%B %Y')
                else:
                    # No payslip found — derive display strings from today
                    payslip_name = 'No Payslip Found (Declaration View)'
                    payslip_date_from_str = month_start.strftime('%d-%b-%Y')
                    payslip_date_to_str = month_end.strftime('%d-%b-%Y')
                    payroll_month_str = today.strftime('%B %Y')

            if decl:
                decl_records |= decl

            # ── Run TDS engine ──────────────────────────────────────────────
            from ..services.tds.tds_orchestration_engine import TdsOrchestrationEngine
            tds_engine = TdsOrchestrationEngine(self.env)
            tds_res = tds_engine.hds_in_compute_tds(employee, eval_date=eval_date, payslip=payslip_rec)

            regime_code = (tds_res.regime_code or 'old').lower()
            regime_code_upper = regime_code.upper()

            # ── Sub-result objects ───────────────────────────────────────────
            proj = tds_res.annual_income_projection         # AnnualIncomeProjectionResult
            deduct = tds_res.deduction_calculation          # DeductionSummary
            tax_inc = tds_res.taxable_income                # TaxableIncomeResult
            slab = tds_res.income_tax_slab                  # SlabCalculationResult
            rebate = tds_res.rebate_engine                  # RebateResult
            surcharge = tds_res.surcharge_engine            # SurchargeResult
            cess = tds_res.health_education_cess            # CessResult
            monthly = tds_res.monthly_tds_distribution     # MonthlyTDSResult

            sal_proj = getattr(proj, 'salary_projection', None)
            prev_emp = getattr(proj, 'previous_employer_income', None)
            other_inc = getattr(proj, 'other_income_aggregation', None)
            c6a = getattr(deduct, 'chapter_6a_deductions', None)

            # ── Income values ────────────────────────────────────────────────
            gross_current_salary = float(getattr(sal_proj, 'total_projected_current_salary', 0.0) or 0.0)
            prev_emp_income = float(getattr(prev_emp, 'taxable_salary', 0.0) or 0.0)
            other_income = float(getattr(other_inc, 'total_other_income', 0.0) or 0.0)
            sec_17_2_vii_perquisite = float(getattr(proj, 'sec_17_2_vii_perquisite', 0.0) or 0.0)
            total_annual_employer_epf = float(getattr(proj, 'total_annual_employer_epf', 0.0) or 0.0)
            actual_employer_nps = float(getattr(proj, 'actual_employer_nps', 0.0) or 0.0)
            combined_employer_contribution = float(getattr(proj, 'combined_employer_contribution', 0.0) or (total_annual_employer_epf + actual_employer_nps))
            combined_ceiling = float(getattr(proj, 'combined_ceiling', 0.0) or 0.0)
            gross_total_income = float(getattr(proj, 'gross_total_income', 0.0) or 0.0)

            # Safety fallback: if sec_17_2_vii_perquisite == 0 but GTI exceeds the components sum
            unaccounted_diff = round(gross_total_income - (gross_current_salary + prev_emp_income + other_income + sec_17_2_vii_perquisite), 2)
            if unaccounted_diff > 0.01:
                sec_17_2_vii_perquisite += unaccounted_diff

            standard_deduction = float(getattr(deduct, 'standard_deduction', 0.0) or 0.0)
            professional_tax_16iii = float(getattr(deduct, 'professional_tax_16iii', 0.0) or 0.0)
            hra_exemption = float(getattr(deduct, 'hra_exemption', 0.0) or 0.0)
            home_loan_24b = float(getattr(deduct, 'home_loan_interest_24b', 0.0) or 0.0)
            sec_80eea = float(getattr(deduct, 'section_80eea_deduction', 0.0) or 0.0)
            employer_nps_80ccd2 = float(getattr(deduct, 'employer_nps_80ccd2', 0.0) or 0.0)
            family_pension_57iia = float(getattr(deduct, 'family_pension_57iia', 0.0) or 0.0)
            total_chapter6a = float(deduct.total_chapter_6a if hasattr(deduct, 'total_chapter_6a') else 0.0)
            total_allowable = float(getattr(deduct, 'total_allowable_deductions', 0.0) or 0.0)
            net_taxable_income = float(getattr(tax_inc, 'net_taxable_income', 0.0) or 0.0)
            net_taxable_before_rounding = float(getattr(tax_inc, 'net_taxable_income_before_rounding', net_taxable_income) or net_taxable_income)
            rounding_factor = float(getattr(tax_inc, 'rounding_factor', 0.0) or 0.0)

            # ── Tax values ───────────────────────────────────────────────────
            base_tax = float(getattr(slab, 'base_tax_liability', 0.0) or 0.0)
            rebate_applied = float(getattr(rebate, 'rebate_applied', 0.0) or 0.0)
            rebate_limit = float(getattr(rebate, 'rebate_limit', 0.0) or 0.0)
            rebate_applicable = bool(getattr(rebate, 'is_applicable', rebate_applied > 0))
            tax_after_rebate = float(getattr(rebate, 'tax_after_rebate', 0.0) or 0.0)
            surcharge_amount = float(getattr(surcharge, 'surcharge_amount', 0.0) or 0.0)
            surcharge_before_relief = float(getattr(surcharge, 'surcharge_before_relief', surcharge_amount) or 0.0)
            marginal_relief = float(getattr(surcharge, 'marginal_relief', 0.0) or 0.0)
            surcharge_rate = float(getattr(surcharge, 'surcharge_rate', 0.0) or 0.0)
            tax_plus_surcharge = float(getattr(surcharge, 'tax_plus_surcharge', 0.0) or 0.0)
            cess_amount = float(getattr(cess, 'cess_amount', 0.0) or 0.0)
            cess_rate = float(getattr(cess, 'cess_rate', 0.0) or 0.0)
            total_annual_tax = float(getattr(cess, 'total_annual_tax_liability', 0.0) or 0.0)
            prev_employer_tds = float(getattr(monthly, 'prev_employer_tds', 0.0) or 0.0)
            ytd_tds = float(getattr(monthly, 'ytd_tds_deducted', 0.0) or 0.0)
            remaining_liability = float(getattr(monthly, 'remaining_annual_tax_liability', 0.0) or 0.0)
            # Remaining Months = Months AFTER current payroll month according to financial year
            rem_raw = getattr(monthly, 'remaining_payroll_periods', None)
            if rem_raw is not None and int(rem_raw) > 0:
                remaining_periods_incl_current = int(rem_raw)
            else:
                from ..services.tds.payroll_period_service import PayrollPeriodService
                period_svc = PayrollPeriodService(self.env)
                remaining_periods_incl_current = max(0, int(period_svc.calculate_remaining_periods(employee, financial_year, eval_date=eval_date) or 0))
            remaining_periods = max(0, remaining_periods_incl_current - 1)
            # current_month_tds comes directly from the TDS engine result — DO NOT recompute
            current_month_tds = float(getattr(monthly, 'current_month_tds', 0.0) or 0.0)
            tds_already_deducted = prev_employer_tds + ytd_tds

            # Use authoritative current month TDS from TDS Orchestration Engine result
            projected_monthly_tds = current_month_tds

            # ── Determine TDS mode and recalculation details ─────────────────
            # Read from persisted tds.recalculation.schedule (source of truth for Feb/Mar)
            eval_month_num = eval_date.month if hasattr(eval_date, 'month') else None
            recalc_from_m_str = getattr(financial_year, 'tds_recalculation_from_month', '1') or '1'
            dist_m_cfg = int(getattr(financial_year, 'tds_recalculation_distribution_months', 3) or 3)
            try:
                recalc_from_m_num = int(recalc_from_m_str)
            except (ValueError, TypeError):
                recalc_from_m_num = 1

            month_names_report = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May',
                                  6: 'June', 7: 'July', 8: 'August', 9: 'September',
                                  10: 'October', 11: 'November', 12: 'December'}
            recalc_from_month_label = month_names_report.get(recalc_from_m_num, str(recalc_from_m_num))

            # Lookup persisted recalculation schedule for this employee+FY
            sched_rec = self.env['tds.recalculation.schedule'].search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
                ('status', '=', 'distribution_active')
            ], limit=1) if financial_year else self.env['tds.recalculation.schedule']

            if not sched_rec and eval_month_num in (1, 2, 3):
                # Also try without status filter
                sched_rec = self.env['tds.recalculation.schedule'].search([
                    ('employee_id', '=', employee.id),
                    ('financial_year_id', '=', financial_year.id),
                ], limit=1) if financial_year else self.env['tds.recalculation.schedule']

            # Determine TDS mode label
            recalc_fy_idx = recalc_from_m_num - 3 if recalc_from_m_num >= 4 else recalc_from_m_num + 9
            eval_fy_idx = (eval_month_num - 3 if eval_month_num >= 4 else eval_month_num + 9) if eval_month_num else 0
            is_in_recalc_window = eval_fy_idx >= recalc_fy_idx and dist_m_cfg > 0

            if not is_in_recalc_window:
                tds_mode = 'NORMAL PROJECTED'
                recalc_executed = 'NO'
                allocation_source = 'NORMAL PROJECTION'
                sched_annual_tax = total_annual_tax
                sched_ytd_tds = ytd_tds + prev_employer_tds
                sched_remaining = remaining_liability
                sched_jan = 0.0
                sched_feb = 0.0
                sched_mar = 0.0
            elif eval_month_num == recalc_from_m_num:
                tds_mode = 'JANUARY RECALCULATION'
                recalc_executed = 'YES'
                allocation_source = 'JANUARY RECALCULATION'
                sched_annual_tax = float(sched_rec.recalculated_annual_tax) if sched_rec else total_annual_tax
                sched_ytd_tds = float(sched_rec.ytd_tds_at_recalculation) if sched_rec else (ytd_tds + prev_employer_tds)
                sched_remaining = float(sched_rec.remaining_tax_liability) if sched_rec else remaining_liability
                sched_jan = float(sched_rec.january_tds) if sched_rec else current_month_tds
                sched_feb = float(sched_rec.february_tds) if sched_rec else 0.0
                sched_mar = float(sched_rec.march_tds) if sched_rec else 0.0
            else:
                tds_mode = 'RECALCULATED DISTRIBUTION'
                recalc_executed = 'NO'
                allocation_source = 'STORED JANUARY RECALCULATION'
                sched_annual_tax = float(sched_rec.recalculated_annual_tax) if sched_rec else total_annual_tax
                sched_ytd_tds = float(sched_rec.ytd_tds_at_recalculation) if sched_rec else (ytd_tds + prev_employer_tds)
                sched_remaining = float(sched_rec.remaining_tax_liability) if sched_rec else remaining_liability
                sched_jan = float(sched_rec.january_tds) if sched_rec else 0.0
                sched_feb = float(sched_rec.february_tds) if sched_rec else current_month_tds
                sched_mar = float(sched_rec.march_tds) if sched_rec else current_month_tds

            # ── Chapter VI-A individual section values ───────────────────────
            sec_80c_approved = float(getattr(c6a, 'section_80c', 0.0) or 0.0) if c6a else 0.0
            sec_80ccd1b_approved = float(getattr(c6a, 'section_80ccd1b', 0.0) or 0.0) if c6a else 0.0
            sec_80d_approved = float(getattr(c6a, 'section_80d', 0.0) or 0.0) if c6a else 0.0
            sec_80e_approved = float(getattr(c6a, 'section_80e', 0.0) or 0.0) if c6a else 0.0
            sec_80g_approved = float(getattr(c6a, 'section_80g', 0.0) or 0.0) if c6a else 0.0
            sec_80dd_approved = float(getattr(c6a, 'section_80dd', 0.0) or 0.0) if c6a else 0.0
            sec_80u_approved = float(getattr(c6a, 'section_80u', 0.0) or 0.0) if c6a else 0.0
            sec_80cch_approved = float(getattr(c6a, 'section_80cch', 0.0) or 0.0) if c6a else 0.0
            if sec_80cch_approved == 0.0:
                from ..services.tds.section_80cch_deduction_service import Section80CCHDeductionService
                cch_svc_tmp = Section80CCHDeductionService(self.env)
                cch_res_tmp = cch_svc_tmp.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
                sec_80cch_approved = float(getattr(cch_res_tmp, 'usable_amount', 0.0) or getattr(cch_res_tmp, 'allowed_deduction', 0.0) or getattr(cch_res_tmp, 'eligible_amount', 0.0) or 0.0)
            sec_80tta_approved = float(getattr(c6a, 'section_80tta', 0.0) or 0.0) if c6a else 0.0

            # ── Section traces (detailed per-section cards) ──────────────────
            section_traces = self._build_section_traces(decl, employee, financial_year, eval_date, tds_res)
            if regime_code == 'new':
                # New Tax Regime (Income-tax Act, 2025 — Section 202(1)): drop the "Old Regime Only" sections
                # (HRA, 24(b), 80C, 80D, 80CCD(1B), 80E, 80G, 80DD, 80U, ...). The Section 9 totals follow.
                section_traces = [t for t in section_traces
                                  if not str(t.get('regime_applicability') or '').startswith('Old Regime')]

            # ── Chapter VI-A summary rows ────────────────────────────────────
            chapter6a_rows = [
                ('Section 80C — Specified Investments', sec_80c_approved),
                ('Section 80CCD(1B) — Employee Voluntary NPS', sec_80ccd1b_approved),
                ('Section 80D — Medical Insurance Premiums', sec_80d_approved),
                ('Section 80E — Higher Education Loan Interest', sec_80e_approved),
                ('Section 80G — Charitable Donations', sec_80g_approved),
                ('Section 80DD — Dependent Disability Care', sec_80dd_approved),
                ('Section 80U — Self Disability Deduction', sec_80u_approved),
                ('Section 80CCH — Agniveer Corpus Fund', sec_80cch_approved),
                ('Section 80TTA — Savings Bank Interest', sec_80tta_approved),
            ]
            chapter6a_rows_nonzero = [(k, v) for k, v in chapter6a_rows if v > 0]
            if regime_code == 'new':
                # New regime allows only Employer NPS [Section 124 / 80CCD(2)] and the Agniveer Corpus [80CCH]
                chapter6a_display_rows = [(k, v) for k, v in (
                    ('Employer NPS Contribution — Section 124 [80CCD(2)]', employer_nps_80ccd2),
                    ('Section 80CCH — Agniveer Corpus Fund', sec_80cch_approved),
                ) if v > 0] or [('No Chapter VI-A deductions claimed (New Tax Regime)', 0.0)]
                chapter6a_display_total = sum(v for _label, v in chapter6a_display_rows)
            else:
                chapter6a_display_rows = chapter6a_rows_nonzero or chapter6a_rows[:1]  # always show at least one line
                chapter6a_display_total = total_chapter6a

            # ── Deduction breakdown rows (using approved/eligible/capped amounts) ─────
            deduction_breakdown = []
            if standard_deduction > 0:
                deduction_breakdown.append(('Standard Deduction [u/s 16(ia)]', standard_deduction))
            if professional_tax_16iii > 0:
                deduction_breakdown.append(('Professional Tax [u/s 16(iii)]', professional_tax_16iii))
            if hra_exemption > 0:
                deduction_breakdown.append(('HRA Exemption [Sec 10(13A)]', hra_exemption))
            if home_loan_24b > 0:
                deduction_breakdown.append(('Home Loan Interest [Sec 24(b)]', home_loan_24b))
            if sec_80eea > 0:
                deduction_breakdown.append(('First-Time Home Buyer Interest [Sec 80EEA]', sec_80eea))

            # Include individual approved Chapter VI-A sections (e.g. 80CCH, 80C, 80D) using approved amounts
            for c6a_label, c6a_approved in chapter6a_rows_nonzero:
                if c6a_approved > 0:
                    deduction_breakdown.append((c6a_label, c6a_approved))

            if employer_nps_80ccd2 > 0:
                deduction_breakdown.append(('Employer NPS Contribution [Section 124]', employer_nps_80ccd2))
            # Note: Family Pension Deduction [Sec 57(iia)] is NOT a Chapter VI-A deduction.
            # It is an intra-head deduction under Income from Other Sources that is already netted
            # in Section 2 to arrive at Gross Total Income. Do not include it in Section 3 deduction_breakdown.

            # ── Other Income breakdown for Section 2 ─────────────────────────
            savings_bank_interest = float(getattr(other_inc, 'savings_interest', 0.0) or 0.0)
            fd_interest = float(getattr(other_inc, 'fd_interest', 0.0) or 0.0)
            dividend_income = float(getattr(other_inc, 'dividend_income', 0.0) or 0.0)
            other_sources_misc = float(getattr(other_inc, 'other_sources_misc', 0.0) or 0.0)
            net_house_property = float(getattr(other_inc, 'net_house_property_income_loss', 0.0) or 0.0)

            fp_net = float(getattr(other_inc, 'family_pension_net', 0.0) or 0.0)
            fp_ded = float(getattr(other_inc, 'family_pension_deduction', 0.0) or 0.0)
            fp_gross = float(getattr(other_inc, 'family_pension_gross', 0.0) or 0.0)
            family_pension_declared_income = fp_gross
            if not fp_gross and decl:
                decl_fp = float(getattr(decl, 'decl_57iia_family_pension', 0.0) or 0.0)
                if not decl_fp:
                    line_57 = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '57iia' and getattr(l, 'active', True)), None)
                    if line_57:
                        decl_fp = float(line_57.declared_amount or 0.0)
                if decl_fp > 0:
                    fp_gross = decl_fp
                    fp_ded = family_pension_57iia
                    fp_net = max(0.0, fp_gross - fp_ded)
                    family_pension_declared_income = fp_gross

            other_income_breakdown = []
            if savings_bank_interest > 0:
                other_income_breakdown.append(('Savings Bank Account Interest', savings_bank_interest))
            if fd_interest > 0:
                other_income_breakdown.append(('Fixed Deposit / Term Deposit Interest', fd_interest))
            if dividend_income > 0:
                other_income_breakdown.append(('Dividend Income', dividend_income))
            if other_sources_misc > 0:
                other_income_breakdown.append(('Other Miscellaneous Income', other_sources_misc))
            if fp_gross > 0:
                fp_label = f"Family Pension Income [Net u/s 93(1)(d)]"
                if fp_ded > 0:
                    fp_label += f" (Gross: INR {fp_gross:,.2f} - Ded: INR {fp_ded:,.2f})"
                other_income_breakdown.append((fp_label, fp_net))
            if net_house_property != 0:
                other_income_breakdown.append(('Net Income / (Loss) from Let-Out Property', net_house_property))

            # ── Statutory Deduction Reconciliation (Excludes Income Items) ───
            # Family pension (income) and the Section 17(2)(vii) perquisite check (employer contributions)
            # are not deductions claimed by the employee, so they stay out of the deduction totals
            deduction_traces = [t for t in section_traces
                                if not t.get('is_family_pension') and t.get('code') != '17(2)(vii)']
            total_declared_deductions = sum(t['declared'] for t in deduction_traces)
            total_eligible_deductions = sum(t['approved'] for t in deduction_traces)
            total_excess_deductions = max(0.0, total_declared_deductions - total_eligible_deductions)
            # Detail cards worth printing: sections actually declared or allowed (no "NOT DECLARED" cards);
            # the 17(2)(vii) perquisite check only when a taxable perquisite arises
            relevant_traces = [
                t for t in section_traces
                if (t.get('approved') or 0.0) > 0
                or ((t.get('declared') or 0.0) > 0 and t.get('code') != '17(2)(vii)')
            ]

            # ── Declaration state label ──────────────────────────────────────
            state_labels = {
                'draft': 'Draft', 'declared': 'Declared', 'submitted': 'Submitted',
                'proof_submitted': 'Proof Submitted', 'proof_under_review': 'Proof Under Review',
                'proof_verified': 'Proof Verified', 'approved': 'Approved', 'rejected': 'Rejected',
            }
            if decl and decl.state:
                decl_state_label = state_labels.get(decl.state, decl.state.replace('_', ' ').title())
            else:
                decl_state_label = 'NO DECLARATION'

            statutory_trace = f"""[TDS_DEBUG_TRACE]
Employee: {employee.name if employee else 'N/A'}
Payslip ID: {payslip_rec.id if payslip_rec else 'N/A'}
Payroll Month: {payroll_month_str}
Financial Year: {financial_year.name if financial_year else 'N/A'}
Declaration ID: {decl.id if decl else 'N/A'}

================================================================================
STATUTORY REPORT TDS TRACE
================================================================================
Employee                 : {employee.name if employee else 'N/A'} (ID: {employee.id if employee else 'N/A'})
Payslip                  : {payslip_name}
Payroll Month            : {payroll_month_str}
Date From                : {payslip_date_from_str}
Date To                  : {payslip_date_to_str}
Financial Year           : {financial_year.name if financial_year else 'N/A'}
TDS Mode                 : {tds_mode}
Recalculation From Month : {recalc_from_month_label}
Distribution Months      : {dist_m_cfg}
Recalculation Executed   : {recalc_executed}
Distribution Source      : {allocation_source}
Annual Tax Liability     : INR {sched_annual_tax:,.2f}
YTD TDS                  : INR {sched_ytd_tds:,.2f}
Remaining Liability      : INR {sched_remaining:,.2f}
Projected Monthly TDS    : INR {projected_monthly_tds:,.2f}
Actual Current Month TDS : INR {current_month_tds:,.2f}
================================================================================
"""
            _logger.warning(statutory_trace)

            # ── Declared tax sections (only sections actually declared with declared amount > 0) ──
            declared_sections = []
            if decl:
                sec_dict = {}
                cat_label_map = {
                    '80c': 'Section 80C — Specified Investments',
                    '80ccd1b': 'Section 80CCD(1B) — Employee Voluntary NPS',
                    '80d_self': 'Section 80D — Medical Insurance (Self/Family)',
                    '80d_parents': 'Section 80D — Medical Insurance (Parents)',
                    '80d_preventive': 'Section 80D — Preventive Health Checkup',
                    '80tta': 'Section 80TTA — Savings Interest',
                    '80ttb': 'Section 80TTB — Senior Citizen Interest',
                    '80dd': 'Section 80DD — Dependent Disability',
                    '24b': 'Section 24(b) — Home Loan Interest (Self-Occupied)',
                    '80eea': 'Section 80EEA — First-time Home Buyer Interest',
                    '80e': 'Section 80E — Education Loan Interest',
                    '80g': 'Section 80G — Charitable Donations',
                    '80gg': 'Section 80GG — Rent Paid (No HRA)',
                    'hra': 'Section 10(13A) — House Rent Exemption',
                    '80ccd2': 'Employer NPS Contribution — Section 124',
                    '57iia': 'Family Pension — Section 93(1)(d)',
                    '80cch': 'Section 80CCH — Agniveer Corpus Fund',
                }
                for line in getattr(decl, 'line_ids', getattr(decl, 'declaration_line_ids', [])):
                    d_amt = float(getattr(line, 'declared_amount', 0.0) or 0.0)
                    if d_amt > 0:
                        lbl = cat_label_map.get(line.category, line.category.upper() if line.category else 'Other Claim')
                        sec_dict[lbl] = sec_dict.get(lbl, 0.0) + d_amt

                header_map = [
                    ('Section 80C — Specified Investments', float(getattr(decl, 'decl_80c_total_declared', 0.0) or 0.0)),
                    ('Section 80CCD(1B) — Employee Voluntary NPS', float(getattr(decl, 'decl_80ccd1b_nps', 0.0) or 0.0)),
                    ('Section 80D — Medical Insurance', float(getattr(decl, 'decl_80d_total_declared', 0.0) or (getattr(decl, 'decl_80d_self', 0.0) + getattr(decl, 'decl_80d_parents', 0.0) + getattr(decl, 'decl_80d_preventive', 0.0)) or 0.0)),
                    ('Section 80E — Education Loan Interest', float(getattr(decl, 'decl_80e_education_loan', 0.0) or 0.0)),
                    ('Section 80G — Charitable Donations', float(getattr(decl, 'decl_80g_donation', 0.0) or 0.0)),
                    ('Section 80DD — Dependent Disability', float(getattr(decl, 'decl_80dd_disability', 0.0) or 0.0)),
                    ('Section 80U — Self Disability', float(getattr(decl, 'decl_80u_self_disability', 0.0) or 0.0)),
                    ('Section 80CCH — Agniveer Corpus Fund', float(getattr(decl, 'decl_80cch_agniveer', 0.0) or 0.0)),
                    ('Employer NPS Contribution — Section 124', float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or 0.0)),
                    ('Section 24(b) — Home Loan Interest (Self-Occupied)', float(getattr(decl, 'decl_24b_self_interest', 0.0) or 0.0)),
                    ('Section 10(13A) — House Rent Exemption', float(getattr(decl, 'decl_hra_annual_rent', 0.0) or 0.0)),
                ]
                for lbl, d_amt in header_map:
                    if d_amt > 0:
                        sec_key_prefix = lbl.split('—')[0].strip()
                        already_present = any(sec_key_prefix in k for k in sec_dict.keys())
                        if not already_present:
                            sec_dict[lbl] = d_amt

                for lbl, d_amt in sec_dict.items():
                    declared_sections.append({'section': lbl, 'declared_amount': d_amt})

            report_data_list.append({
                'declared_sections': declared_sections,
                # ── Identity ──────────────────────────────────────────────────
                'declaration': decl,
                'employee': employee,
                'financial_year': financial_year,
                'assessment_year': self._get_assessment_year(financial_year),
                'regime_code': regime_code_upper,
                # Label of the employee's tax regime selection (no hardcoded text)
                'regime_label': dict(employee._fields['hds_in_tax_regime']._description_selection(self.env)).get(regime_code, regime_code_upper)
                if employee and 'hds_in_tax_regime' in employee._fields else regime_code_upper,
                'eval_date': eval_date.strftime('%d-%b-%Y') if eval_date else 'N/A',
                'declaration_id': decl.id if decl else 'N/A',
                'declaration_name': (decl.name or f'DECL-{decl.id}') if decl else 'No Declaration Record',
                'declaration_state': decl_state_label if decl else 'NO DECLARATION',
                'submission_date': decl.submission_date.strftime('%d-%b-%Y') if (decl and decl.submission_date) else 'Not Submitted',
                'employer_category': str(getattr(employee, 'hds_in_employer_category',
                                                 getattr(employee, 'employer_type', 'private')) or 'private').upper(),
                # ── Payroll Period Context ─────────────────────────────────────
                'payroll_month': payroll_month_str,
                'payslip_date_from': payslip_date_from_str,
                'payslip_date_to': payslip_date_to_str,
                'payslip_name': payslip_name,
                # ── Income ────────────────────────────────────────────────────
                'gross_current_salary': gross_current_salary,
                'prev_emp_income': prev_emp_income,
                'sec_17_2_vii_perquisite': sec_17_2_vii_perquisite,
                'total_annual_employer_epf': total_annual_employer_epf,
                'actual_employer_nps': actual_employer_nps,
                'combined_employer_contribution': combined_employer_contribution,
                'combined_ceiling': combined_ceiling,
                'other_income': other_income,
                'other_income_breakdown': other_income_breakdown,
                'family_pension_declared_income': family_pension_declared_income,
                'gross_total_income': gross_total_income,
                # ── Deductions ────────────────────────────────────────────────
                'standard_deduction': standard_deduction,
                'professional_tax_16iii': professional_tax_16iii,
                'hra_exemption': hra_exemption,
                'home_loan_24b': home_loan_24b,
                'sec_80eea': sec_80eea,
                'total_chapter6a': total_chapter6a,
                'employer_nps_80ccd2': employer_nps_80ccd2,
                'family_pension_57iia': family_pension_57iia,
                'total_allowable_deductions': total_allowable,
                'deduction_breakdown': deduction_breakdown,
                # ── Taxable Income ────────────────────────────────────────────
                'net_taxable_income': net_taxable_income,
                'net_taxable_before_rounding': net_taxable_before_rounding,
                'rounding_factor': rounding_factor,
                # ── Tax Computation ───────────────────────────────────────────
                'base_tax': base_tax,
                'rebate_applied': rebate_applied,
                'rebate_limit': rebate_limit,
                'rebate_applicable': rebate_applicable,
                'tax_after_rebate': tax_after_rebate,
                'surcharge_amount': surcharge_amount,
                'surcharge_before_relief': surcharge_before_relief,
                'marginal_relief': marginal_relief,
                'surcharge_rate': surcharge_rate,
                'tax_plus_surcharge': tax_plus_surcharge,
                'cess_amount': cess_amount,
                'cess_rate': cess_rate,
                'total_annual_tax': total_annual_tax,
                # ── TDS Distribution ──────────────────────────────────────────
                'prev_employer_tds': prev_employer_tds,
                'ytd_tds': ytd_tds,
                'tds_already_deducted': tds_already_deducted,
                'remaining_liability': remaining_liability,
                'remaining_periods': remaining_periods,
                'remaining_periods_incl_current': remaining_periods_incl_current,
                'projected_monthly_tds': projected_monthly_tds,
                'current_month_tds': current_month_tds,
                # ── TDS Recalculation Mode & Schedule ──────────────────────────
                'tds_mode': tds_mode,
                'tds_recalc_from_month': recalc_from_month_label,
                'tds_distribution_months': dist_m_cfg,
                'tds_recalc_executed': recalc_executed,
                'tds_allocation_source': allocation_source,
                'tds_recalc_annual_tax': sched_annual_tax,
                'tds_recalc_ytd_tds': sched_ytd_tds,
                'tds_recalc_remaining': sched_remaining,
                'tds_jan_allocation': sched_jan,
                'tds_feb_allocation': sched_feb,
                'tds_mar_allocation': sched_mar,
                # ── Chapter VI-A Summary ──────────────────────────────────────
                'chapter6a_rows': chapter6a_display_rows,
                'relevant_traces': relevant_traces,
                'chapter6a_total_display': chapter6a_display_total,
                # ── Section Traces ────────────────────────────────────────────
                'section_traces': section_traces,
                # ── Reconciliation ────────────────────────────────────────────
                'total_declared': total_declared_deductions,
                'total_eligible': total_eligible_deductions,
                'total_excess': total_excess_deductions,
                # ── Meta ──────────────────────────────────────────────────────
                'generated_on': fields.Date.today().strftime('%d-%b-%Y'),
                'generated_by': self.env.user.name,
            })

        return {
            'doc_ids': records.ids if records else (decl_records.ids if decl_records else (docids or [])),
            'doc_model': model_name or 'tds.employee.declaration',
            'docs': records if records else decl_records,
            'reports': report_data_list,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_assessment_year(self, financial_year):
        if not financial_year or not financial_year.start_date:
            return 'AY 2026-27'
        s_year = financial_year.start_date.year + 1
        e_year = financial_year.end_date.year + 1
        return f'AY {s_year}-{str(e_year)[-2:]}'

    def _fmt(self, value):
        """Format float as INR string."""
        try:
            return f'INR {float(value or 0.0):,.2f}'
        except Exception:
            return 'INR 0.00'

    def _eligibility_badge(self, trace):
        """Return a human-readable eligibility conclusion."""
        declared = trace.get('declared', 0.0)
        approved = trace.get('approved', 0.0)
        is_eligible = trace.get('is_eligible', False)
        if not is_eligible and declared == 0.0:
            return 'NOT DECLARED'
        if not is_eligible:
            return 'NOT ELIGIBLE'
        if declared > 0 and approved < declared:
            return 'PARTIALLY ELIGIBLE — Statutory Cap Applied'
        if declared > 0 and approved >= declared:
            return 'ELIGIBLE'
        return 'NOT APPLICABLE'

    def _build_section_traces(self, decl, employee, financial_year, eval_date, tds_res):
        traces = []
        if not decl:
            return traces

        regime_code = (tds_res.regime_code or 'old').lower()
        fmt = self._fmt

        # ── Salary projection (used across multiple sections) ─────────────────
        from ..services.tds.salary_projection_service import SalaryProjectionService
        sal_proj_svc = SalaryProjectionService(self.env)
        sal_res = sal_proj_svc.project_salary(employee, financial_year, eval_date=eval_date)
        annual_basic = (sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)
        actual_hra = sal_res.total_hra or 0.0

        # ── Parameter service ─────────────────────────────────────────────────
        from ..services.tds.tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)

        # ─────────────────────────────────────────────────────────────────────
        # 1. Section 10(13A) — HRA Exemption
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section10_hra_exemption_service import Section10HraExemptionService
        hra_line = decl.declaration_line_ids.filtered(lambda l: l.category == 'hra') if decl else False
        annual_rent = float(
            hra_line[0].usable_amount if (hra_line and hra_line[0].usable_amount > 0.0)
            else ((decl.decl_hra_annual_rent if decl else 0.0) or 0.0)
        )
        is_metro = bool(decl.decl_hra_is_metro) if decl else False
        hra_svc = Section10HraExemptionService(self.env)
        hra_res = hra_svc.calculate_exemption(
            annual_rent_paid=annual_rent, actual_hra_received=actual_hra,
            annual_basic_salary=annual_basic, is_metro=is_metro,
            eval_date=eval_date, employee=employee,
            financial_year=financial_year, declaration=decl
        )
        hra_approved = hra_res.exempt_amount if regime_code == 'old' else 0.0
        hra_excess = max(0.0, annual_rent - hra_approved)
        traces.append({
            'code': '10(13A)',
            'name': 'Section 10(13A) — House Rent Allowance (HRA) Exemption',
            'statutory_ref': 'Section 10(13A) r/w Rule 2A',
            'source_type': 'Salary Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': annual_rent,
            'approved': hra_approved,
            'excess': hra_excess,
            'cap_applied': hra_excess > 0,
            'is_eligible': hra_approved > 0,
            'eligibility_status': self._eligibility_badge({'declared': annual_rent, 'approved': hra_approved, 'is_eligible': hra_approved > 0}),
            'reason': hra_res.remarks if regime_code == 'old' else 'HRA Exemption not permitted under New Tax Regime Income-tax Act, 2025 — Section 202(1).',
            'inputs': [
                ('Annual Rent Paid', fmt(annual_rent)),
                ('Actual HRA Received', fmt(actual_hra)),
                ('Annual Basic Salary + DA', fmt(annual_basic)),
                ('Metro City Accommodation', 'YES (50% of Basic+DA)' if is_metro else 'NO (40% of Basic+DA)'),
                ('Landlord Name', decl.decl_hra_landlord_name or 'N/A'),
                ('Landlord PAN', decl.decl_hra_landlord_pan or 'N/A'),
            ],
            'formulas': [
                ('Formula 1 — Actual HRA Received', fmt(getattr(hra_res, 'actual_hra_received', actual_hra))),
                ('Formula 2 — Rent Paid minus 10% of Basic+DA', fmt(getattr(hra_res, 'rent_excess_basic', 0.0))),
                ('Formula 3 — 50%/40% of Basic+DA', fmt(getattr(hra_res, 'basic_pct_limit', 0.0))),
                ('Eligible — Least of Three Formulas', fmt(hra_res.exempt_amount)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 2. Section 24(b) — Home Loan Interest (Self-Occupied)
        # ─────────────────────────────────────────────────────────────────────
        sec_24b_amt = float(decl.decl_24b_self_interest or 0.0)
        max_24b_limit = float(tds_param_svc.get_home_loan_interest_limit(eval_date=eval_date) or 0.0)
        approved_24b = min(sec_24b_amt, max_24b_limit) if regime_code == 'old' else 0.0
        excess_24b = max(0.0, sec_24b_amt - approved_24b)
        traces.append({
            'code': '24(b)',
            'name': 'Section 24(b) — Self-Occupied Home Loan Interest',
            'statutory_ref': 'Section 24(b) of Income Tax Act',
            'source_type': 'Loan Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': sec_24b_amt,
            'approved': approved_24b,
            'excess': excess_24b,
            'cap_applied': excess_24b > 0,
            'is_eligible': approved_24b > 0,
            'eligibility_status': self._eligibility_badge({'declared': sec_24b_amt, 'approved': approved_24b, 'is_eligible': approved_24b > 0}),
            'reason': (f'Declared INR {sec_24b_amt:,.2f} capped at statutory ceiling INR {max_24b_limit:,.0f}.' if regime_code == 'old'
                       else 'Section 24(b) Home Loan Interest not permitted under New Tax Regime.'),
            'inputs': [
                ('Declared Home Loan Interest', fmt(sec_24b_amt)),
                ('Statutory Ceiling', fmt(max_24b_limit)),
                ('Approved Deduction', fmt(approved_24b)),
                ('Excess / Disallowed Amount', fmt(excess_24b)),
            ],
            'formulas': [
                (f'min(Declared, INR {max_24b_limit:,.0f})', fmt(approved_24b)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 3. Section 80EEA — First-Time Home Buyer Interest
        # ─────────────────────────────────────────────────────────────────────
        remaining_interest = max(sec_24b_amt - approved_24b, 0.0)
        from ..services.tds.section_80eea_eligibility_service import Section80EEAEligibilityService
        eea_svc = Section80EEAEligibilityService(self.env)
        eea_res = eea_svc.validate_eligibility(
            decl, eval_date=eval_date, regime_code=regime_code,
            employee=employee, financial_year=financial_year,
            claimed_interest_amount=remaining_interest
        )
        eea_excess = max(0.0, remaining_interest - eea_res.allowed_deduction)
        traces.append({
            'code': '80EEA',
            'name': 'Section 80EEA — First-Time Home Buyer Additional Interest',
            'statutory_ref': 'Section 80EEA of Income Tax Act',
            'source_type': 'Loan Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': remaining_interest,
            'approved': eea_res.allowed_deduction,
            'excess': eea_excess,
            'cap_applied': eea_excess > 0,
            'is_eligible': eea_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': remaining_interest, 'approved': eea_res.allowed_deduction, 'is_eligible': eea_res.is_eligible}),
            'reason': eea_res.remarks,
            'inputs': [
                ('Residual Interest (after 24b cap)', fmt(remaining_interest)),
                ('Loan Sanction Date', decl.decl_80eea_loan_sanction_date.strftime('%d-%b-%Y') if decl.decl_80eea_loan_sanction_date else 'N/A'),
                ('Property Stamp Duty Value', fmt(decl.decl_80eea_property_stamp_value or 0.0)),
                ('First-Time Home Buyer', 'YES' if decl.decl_80eea_first_time_home_buyer else 'NO'),
                ('Claimed under Sec 80EE', 'YES' if decl.decl_80eea_claimed_under_80ee else 'NO'),
                ('Lending Institution', decl.decl_80eea_lending_institution or 'N/A'),
                ('Loan Account No.', decl.decl_80eea_loan_account_number or 'N/A'),
            ],
            'formulas': [],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 4. Section 80C — Composite Specified Investments (Unified Trace)
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.tds_declaration_lifecycle_logger import TdsDeclarationLifecycleLogger
        cap_80c = float(tds_param_svc.get_80c_limit(eval_date=eval_date) or 0.0)
        c80_payload = TdsDeclarationLifecycleLogger.build_section_80c_composite_trace_payload(
            declaration=decl, regime_code=regime_code, eval_date=eval_date, statutory_cap=cap_80c, env=self.env
        )

        c80_inputs = []
        for comp in c80_payload['components']:
            c80_inputs.append((
                f"{comp['name']} [{comp['statutory_ref']}]",
                f"Declared: {fmt(comp['declared_amount'])} | Eligible: {fmt(comp['eligible_amount'])} | Considered: {fmt(comp['amount_considered'])}"
            ))
        c80_inputs.append(('Total 80C Components Aggregate', fmt(c80_payload['total_eligible_before_cap'])))
        c80_inputs.append(('Section 80C Statutory Limit', fmt(c80_payload['statutory_limit'])))
        c80_inputs.append(('Final Allowable 80C Deduction', fmt(c80_payload['final_eligible_deduction'])))
        c80_inputs.append(('Excess / Disallowed Amount', fmt(c80_payload['excess_disallowed'])))

        traces.append({
            'code': '80C',
            'name': 'Section 80C — Composite Specified Savings & Investments',
            'statutory_ref': 'Section 80C of Income Tax Act, 1961',
            'source_type': 'Investment Declaration',
            'regime_applicability': f'Old Regime Only (Capped at INR {cap_80c:,.0f})',
            'declared': c80_payload['total_declared'],
            'approved': c80_payload['final_eligible_deduction'],
            'excess': c80_payload['excess_disallowed'],
            'cap_applied': c80_payload['cap_applied'],
            'is_eligible': c80_payload['is_eligible'],
            'eligibility_status': self._eligibility_badge({'declared': c80_payload['total_declared'], 'approved': c80_payload['final_eligible_deduction'], 'is_eligible': c80_payload['is_eligible']}),
            'reason': c80_payload['reason'],
            'is_composite_80c': True,
            'components_data': c80_payload['components'],
            'composite_payload': c80_payload,
            'inputs': c80_inputs,
            'formulas': [
                (f'min(Total Eligible Components, INR {cap_80c:,.0f})', fmt(c80_payload['final_eligible_deduction'])),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 5. Section 80D — Medical Insurance Premiums
        # ─────────────────────────────────────────────────────────────────────
        d_self = float(decl.decl_80d_self or 0.0)
        d_parents = float(decl.decl_80d_parents or 0.0)
        d_prev = float(decl.decl_80d_preventive or 0.0)
        self_is_senior = bool(getattr(decl, 'decl_80d_self_is_senior', False))
        parents_is_senior = bool(getattr(decl, 'decl_80d_parents_is_senior', False))

        cap_self = float(tds_param_svc.get_80d_limit(is_senior=self_is_senior, is_parents=False, eval_date=eval_date) or 0.0)
        cap_parents = float(tds_param_svc.get_80d_limit(is_senior=parents_is_senior, is_parents=True, eval_date=eval_date) or 0.0)
        cap_preventive = float(tds_param_svc.get_parameter('80D_PREVENTIVE_CHECKUP_LIMIT', eval_date=eval_date) or 0.0)
        cap_combined = cap_self + cap_parents

        total_80d_raw = d_self + d_parents + d_prev
        approved_80d_self = min(d_self + min(d_prev, cap_preventive), cap_self)
        approved_80d_parents = min(d_parents, cap_parents)
        approved_80d = (approved_80d_self + approved_80d_parents) if regime_code == 'old' else 0.0
        excess_80d = max(0.0, total_80d_raw - approved_80d)

        traces.append({
            'code': '80D',
            'name': 'Section 80D — Medical Insurance Premiums & Preventive Checkup',
            'statutory_ref': 'Section 80D of Income Tax Act',
            'source_type': 'Insurance Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': total_80d_raw,
            'approved': approved_80d,
            'excess': excess_80d,
            'cap_applied': excess_80d > 0,
            'is_eligible': total_80d_raw > 0 and regime_code == 'old',
            'eligibility_status': self._eligibility_badge({'declared': total_80d_raw, 'approved': approved_80d, 'is_eligible': total_80d_raw > 0 and regime_code == 'old'}),
            'reason': (f'Section 80D allowable deduction INR {approved_80d:,.2f} (Self Cap: INR {cap_self:,.0f}, Parents Cap: INR {cap_parents:,.0f}).' if regime_code == 'old'
                       else 'Section 80D Medical Insurance deduction not permitted under New Tax Regime.'),
            'inputs': [
                ('Self & Family Insurance Claim', fmt(d_self)),
                ('Self Section Statutory Limit', f'INR {cap_self:,.2f} ({ "Senior Citizen 60+" if self_is_senior else "Non-Senior" })'),
                ('Parents Insurance Claim', fmt(d_parents)),
                ('Parents Section Statutory Limit', f'INR {cap_parents:,.2f} ({ "Senior Citizen 60+" if parents_is_senior else "Non-Senior" })'),
                ('Preventive Annual Health Checkup', fmt(d_prev)),
                ('Preventive Checkup Sublimit', f'{fmt(cap_preventive)} (included in Self cap)'),
                ('Total Declared Medical 80D', fmt(total_80d_raw)),
                ('Combined Profile Statutory Cap', f'INR {cap_combined:,.2f} (Self INR {cap_self:,.0f} + Parents INR {cap_parents:,.0f})'),
                ('Approved 80D Deduction', fmt(approved_80d)),
            ],
            'formulas': [
                ('Self Allowable', f'min(Self + min(Preventive, INR {cap_preventive:,.0f}), INR {cap_self:,.0f}) = INR {approved_80d_self:,.2f}'),
                ('Parents Allowable', f'min(Parents, INR {cap_parents:,.0f}) = INR {approved_80d_parents:,.2f}'),
                ('Total Allowable 80D', f'INR {approved_80d_self:,.2f} + INR {approved_80d_parents:,.2f} = INR {approved_80d:,.2f}'),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 6. Section 80CCD(1B) — Voluntary NPS
        # ─────────────────────────────────────────────────────────────────────
        nps_1b = float(decl.decl_80ccd1b_nps or 0.0)
        cap_nps_1b = float(tds_param_svc.get_80ccd1b_limit(eval_date=eval_date) or 0.0)
        approved_nps_1b = min(nps_1b, cap_nps_1b) if regime_code == 'old' else 0.0
        excess_nps1b = max(0.0, nps_1b - approved_nps_1b)
        traces.append({
            'code': '80CCD(1B)',
            'name': 'Section 80CCD(1B) — Additional Voluntary NPS Contribution',
            'statutory_ref': 'Section 80CCD(1B) of Income Tax Act',
            'source_type': 'NPS Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': nps_1b,
            'approved': approved_nps_1b,
            'excess': excess_nps1b,
            'cap_applied': excess_nps1b > 0,
            'is_eligible': nps_1b > 0 and regime_code == 'old',
            'eligibility_status': self._eligibility_badge({'declared': nps_1b, 'approved': approved_nps_1b, 'is_eligible': nps_1b > 0 and regime_code == 'old'}),
            'reason': (f'Additional NPS contribution INR {nps_1b:,.2f} capped at INR {cap_nps_1b:,.0f}.' if regime_code == 'old'
                       else 'Section 80CCD(1B) deduction not permitted under New Tax Regime.'),
            'inputs': [
                ('Voluntary NPS Contribution', fmt(nps_1b)),
                ('Statutory Ceiling', fmt(cap_nps_1b)),
                ('Approved Deduction', fmt(approved_nps_1b)),
                ('Excess / Disallowed', fmt(excess_nps1b)),
            ],
            'formulas': [
                (f'min(Declared, INR {cap_nps_1b:,.0f})', fmt(approved_nps_1b)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 7. Section 80G — Charitable Donations
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_80g_deduction_service import Section80GDeductionService
        g_svc = Section80GDeductionService(self.env)
        g_res = g_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        g_amt = float(decl.decl_80g_donation or 0.0)
        g_excess = max(0.0, g_amt - g_res.allowed_deduction)
        g_category_map = {
            '100_no_limit': '100% — No Qualifying Limit',
            '50_no_limit': '50% — No Qualifying Limit',
            '100_with_limit': '100% — Subject to Qualifying Limit',
            '50_with_limit': '50% — Subject to Qualifying Limit',
        }
        g_mode_map = {
            'cash': 'Cash', 'cheque': 'Cheque', 'dd': 'Demand Draft',
            'neft_rtgs': 'NEFT / RTGS', 'upi': 'UPI / BHIM', 'other_digital': 'Other Digital Payment',
        }
        traces.append({
            'code': '80G',
            'name': 'Section 80G — Charitable Donations to Approved Institutions',
            'statutory_ref': 'Section 80G of Income Tax Act',
            'source_type': 'Donation Declaration',
            'regime_applicability': 'Old Regime Only',
            'declared': g_amt,
            'approved': g_res.allowed_deduction,
            'excess': g_excess,
            'cap_applied': g_excess > 0,
            'is_eligible': g_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': g_amt, 'approved': g_res.allowed_deduction, 'is_eligible': g_res.is_eligible}),
            'reason': g_res.remarks,
            'inputs': [
                ('Donation Amount', fmt(g_amt)),
                ('Donee Institution Name', decl.decl_80g_institution_name or 'N/A'),
                ('Deduction Category', g_category_map.get(decl.decl_80g_category, '50% — Subject to Limit')),
                ('Approved under Sec 80G', 'YES' if decl.decl_80g_is_approved else 'NO'),
                ('Payment Mode', g_mode_map.get(decl.decl_80g_mode, 'NEFT / RTGS')),
                ('Donation Date', decl.decl_80g_donation_date.strftime('%d-%b-%Y') if decl.decl_80g_donation_date else 'N/A'),
                ('Receipt Number', decl.decl_80g_receipt_number or 'N/A'),
                ('Donee PAN', decl.decl_80g_donee_pan or 'N/A'),
                ('Registration / Approval No.', decl.decl_80g_approval_number or 'N/A'),
                ('Eligible Deduction', fmt(g_res.allowed_deduction)),
            ],
            'formulas': [],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 8. Section 80E — Higher Education Loan Interest
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_80e_deduction_service import Section80EDeductionService
        e_svc = Section80EDeductionService(self.env)
        e_res = e_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        e_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80e') if decl else []
        e_amt = float(getattr(decl, 'decl_80e_amount', 0.0) or (sum(l.declared_amount for l in e_line) if e_line else 0.0))
        e_excess = max(0.0, e_amt - e_res.allowed_deduction)
        traces.append({
            'code': '80E',
            'name': 'Section 80E — Higher Education Loan Interest',
            'statutory_ref': 'Section 80E of Income Tax Act',
            'source_type': 'Loan Declaration',
            'regime_applicability': 'Old Regime Only (No Upper Limit)',
            'declared': e_amt,
            'approved': e_res.allowed_deduction,
            'excess': e_excess,
            'cap_applied': False,
            'is_eligible': e_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': e_amt, 'approved': e_res.allowed_deduction, 'is_eligible': e_res.is_eligible}),
            'reason': e_res.remarks,
            'inputs': [
                ('Interest Amount Paid', fmt(e_amt)),
                ('Statutory Cap', 'None — 100% of actual interest eligible'),
                ('Eligible Deduction', fmt(e_res.allowed_deduction)),
                ('Excess / Disallowed', fmt(e_excess)),
            ],
            'formulas': [
                ('Eligible = 100% of Declared Interest', fmt(e_res.allowed_deduction)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 9. Section 80DD — Dependent Disability Care
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_80dd_deduction_service import Section80DDDeductionService
        dd_svc = Section80DDDeductionService(self.env)
        dd_res = dd_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        dd_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80dd') if decl else []
        dd_amt = float(getattr(decl, 'decl_80dd_amount', 0.0) or (sum(l.declared_amount for l in dd_line) if dd_line else 0.0))
        is_severe_dd = bool(getattr(decl, 'decl_80dd_is_severe', False) or (any(getattr(l, 'is_severe_disability', False) for l in dd_line) if dd_line else False))
        dd_excess = max(0.0, dd_amt - dd_res.allowed_deduction)
        traces.append({
            'code': '80DD',
            'name': 'Section 80DD — Maintenance & Treatment of Dependent with Disability',
            'statutory_ref': 'Section 80DD of Income Tax Act',
            'source_type': 'Disability Certificate Declaration',
            'regime_applicability': 'Old Regime Only (Flat Deduction)',
            'declared': dd_amt,
            'approved': dd_res.allowed_deduction,
            'excess': dd_excess,
            'cap_applied': dd_excess > 0,
            'is_eligible': dd_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': dd_amt, 'approved': dd_res.allowed_deduction, 'is_eligible': dd_res.is_eligible}),
            'reason': dd_res.remarks,
            'inputs': [
                ('Declared Medical Expenditure', fmt(dd_amt)),
                ('Severe Disability (>= 80%)', 'YES' if is_severe_dd else 'NO'),
                ('Eligible Amount (Statutory Flat)', fmt(dd_res.allowed_deduction)),
                ('Excess / Disallowed Amount', fmt(dd_excess)),
            ],
            'formulas': [
                ('Flat statutory deduction (' + ('severe' if is_severe_dd else 'normal') + ' disability)', fmt(dd_res.allowed_deduction)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 10. Section 80U — Self Disability Deduction
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_80u_deduction_service import Section80UDeductionService
        u_svc = Section80UDeductionService(self.env)
        u_res = u_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        u_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80u') if decl else []
        u_amt = float(getattr(decl, 'decl_80u_amount', 0.0) or (sum(l.declared_amount for l in u_line) if u_line else 0.0))
        is_severe_u = bool(getattr(decl, 'decl_80u_is_severe', False) or (any(getattr(l, 'is_severe_disability', False) for l in u_line) if u_line else False))
        u_excess = max(0.0, u_amt - u_res.allowed_deduction)
        traces.append({
            'code': '80U',
            'name': 'Section 80U — Person with Disability (Self)',
            'statutory_ref': 'Section 80U of Income Tax Act',
            'source_type': 'Disability Certificate Declaration',
            'regime_applicability': 'Old Regime Only (Flat Deduction)',
            'declared': u_amt,
            'approved': u_res.allowed_deduction,
            'excess': u_excess,
            'cap_applied': u_excess > 0,
            'is_eligible': u_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': u_amt, 'approved': u_res.allowed_deduction, 'is_eligible': u_res.is_eligible}),
            'reason': u_res.remarks,
            'inputs': [
                ('Declared Disability Amount', fmt(u_amt)),
                ('Severe Disability (>= 80%)', 'YES' if is_severe_u else 'NO'),
                ('Eligible Amount (Statutory Flat)', fmt(u_res.allowed_deduction)),
                ('Excess / Disallowed Amount', fmt(u_excess)),
            ],
            'formulas': [
                ('Flat statutory deduction (' + ('severe' if is_severe_u else 'normal') + ' disability)', fmt(u_res.allowed_deduction)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 11. Section 80CCH — Agniveer Corpus Fund
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_80cch_deduction_service import Section80CCHDeductionService
        cch_svc = Section80CCHDeductionService(self.env)
        cch_res = cch_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        cch_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80cch') if decl else []
        cch_amt = float(getattr(decl, 'decl_80cch_agniveer', 0.0) or (sum(l.declared_amount for l in cch_line) if cch_line else 0.0))
        cch_allowed = getattr(cch_res, 'usable_amount', getattr(cch_res, 'allowed_deduction', getattr(cch_res, 'eligible_amount', 0.0)))
        cch_excess = max(0.0, cch_amt - cch_allowed)
        traces.append({
            'code': '80CCH',
            'name': 'Section 80CCH — Agniveer Corpus Fund Contribution',
            'statutory_ref': 'Section 80CCH of Income Tax Act',
            'source_type': 'Agniveer Scheme Declaration',
            'regime_applicability': 'Both Old & New Regime — 100% Eligible',
            'declared': cch_amt,
            'approved': cch_allowed,
            'excess': cch_excess,
            'cap_applied': cch_excess > 0,
            'is_eligible': cch_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': cch_amt, 'approved': cch_allowed, 'is_eligible': cch_res.is_eligible}),
            'reason': cch_res.remarks,
            'inputs': [
                ('Employee Agniveer Contribution', fmt(cch_amt)),
                ('Eligibility Percentage', '100.00%'),
                ('Eligible Amount', fmt(cch_allowed)),
                ('Excess / Disallowed Amount', fmt(cch_excess)),
            ],
            'formulas': [
                ('Eligible = 100% of Declared Amount', fmt(cch_allowed)),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 12. Section 93(1)(d) — Family Pension Deduction & Tax Impact
        # ─────────────────────────────────────────────────────────────────────
        from ..services.tds.section_57iia_deduction_service import Section57IIADeductionService
        p_svc = Section57IIADeductionService(self.env)
        p_res = p_svc.validate_and_trace(decl, eval_date=eval_date, regime_code=regime_code, employee=employee, financial_year=financial_year)
        p_line = decl.declaration_line_ids.filtered(lambda l: l.category == '57iia') if decl else []
        p_amt = float(getattr(decl, 'decl_57iia_family_pension', 0.0) or (sum(l.declared_amount for l in p_line) if p_line else 0.0))
        one_third_p = round(p_amt / 3.0, 2)
        p_max = float(tds_param_svc.get_family_pension_limit(regime=regime_code, eval_date=eval_date) or 0.0)
        p_eligible = float(p_res.allowed_deduction or 0.0)
        p_excess = max(0.0, p_amt - p_eligible)
        net_taxable_family_pension = max(0.0, p_amt - p_eligible)

        fp_stat_label = Section57IIADeductionService.get_legal_reference_label(financial_year, eval_date=eval_date)
        fp_sec_code = Section57IIADeductionService.get_statutory_section_code(financial_year, eval_date=eval_date)

        traces.append({
            'code': fp_sec_code,
            'name': 'Family Pension',
            'statutory_ref': fp_stat_label,
            'source_type': 'Family Pension Declaration',
            'regime_applicability': 'Both Old & New Regime',
            'declared': p_amt,
            'approved': p_eligible,
            'excess': p_excess,
            'cap_applied': (one_third_p > p_max),
            'is_eligible': p_res.is_eligible,
            'eligibility_status': self._eligibility_badge({'declared': p_amt, 'approved': p_eligible, 'is_eligible': p_res.is_eligible}),
            'reason': (f'Deduction INR {p_eligible:,.2f} = lower of 1/3rd of the pension (INR {one_third_p:,.2f}) and the '
                       f'statutory ceiling (INR {p_max:,.2f}); taxable family pension INR {net_taxable_family_pension:,.2f}.'
                       if p_amt else p_res.remarks),
            'is_family_pension': True,
            'tax_impact': {
                'family_pension_declared': p_amt,
                'added_to_other_income': p_amt,
                'eligible_deduction': p_eligible,
                'net_taxable_family_pension': net_taxable_family_pension,
            },
            'inputs': [
                ('Gross Family Pension Declared', fmt(p_amt)),
                ('1/3rd of Family Pension', fmt(one_third_p)),
                ('Statutory Ceiling', fmt(p_max)),
                ('Eligible Deduction', fmt(p_eligible)),
            ],
            'formulas': [
                ('Step 1 — Gross Family Pension Added to Other Income', fmt(p_amt)),
                ('Step 2 — Calculate 1/3rd of Family Pension', fmt(one_third_p)),
                (f'Step 3 — Statutory Limit ({regime_code.capitalize()} Regime: INR {p_max:,.0f})', fmt(p_max)),
                ('Step 4 — Eligible Deduction = min(1/3rd, Statutory Limit)', fmt(p_eligible)),
                ('Step 5 — Net Taxable Family Pension in Other Sources = Gross minus Eligible Deduction', fmt(net_taxable_family_pension)),
            ],
        })


        # ─────────────────────────────────────────────────────────────────────
        # 13. Section 80CCD(2) — Employer NPS Contribution
        # ─────────────────────────────────────────────────────────────────────
        nps2_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80ccd2') if decl else []
        nps2_amt = float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or (sum(l.declared_amount for l in nps2_line) if nps2_line else 0.0))
        emp_type = getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) or 'private'
        nps_pct = float(tds_param_svc.get_employer_nps_limit(regime=regime_code, employer_type=emp_type, eval_date=eval_date) or 0.0)
        sal_b = annual_basic
        calc_ceiling = sal_b * (nps_pct / 100.0)
        from ..services.tds.eligibility_rule_engine_service import EligibilityRuleEngineService
        elig_svc = EligibilityRuleEngineService(self.env)
        elig_res = elig_svc.evaluate_eligibility(
            '80ccd2', declared_amount=nps2_amt, regime_code=regime_code,
            employer_type=emp_type, salary_base=sal_b,
            employee=employee, financial_year=financial_year,
            declaration_state=decl.state
        )
        approved_80ccd2 = elig_res.eligible_deduction
        excess_80ccd2 = float(getattr(elig_res, 'excess_amount', 0.0) or 0.0)
        traces.append({
            'code': '124',
            'name': 'Employer NPS Contribution — Section 124',
            'statutory_ref': 'Section 124 (formerly Section 80CCD(2)) of Income Tax Act',
            'source_type': 'Employer Payroll Data',
            'regime_applicability': 'Both Old & New Regime',
            'declared': nps2_amt,
            'approved': approved_80ccd2,
            'excess': excess_80ccd2,
            'cap_applied': excess_80ccd2 > 0,
            'is_eligible': approved_80ccd2 > 0,
            'eligibility_status': self._eligibility_badge({'declared': nps2_amt, 'approved': approved_80ccd2, 'is_eligible': approved_80ccd2 > 0}),
            'reason': elig_res.rule_applied,
            'inputs': [
                ('Employer NPS Contribution (Declared)', fmt(nps2_amt)),
                ('Eligibility %', f'{nps_pct:.2f}%'),
                ('Salary Base (Basic + DA)', fmt(sal_b)),
                ('Statutory Ceiling  =  Salary Base × Eligibility %', fmt(calc_ceiling)),
                ('Eligible Amount', fmt(approved_80ccd2)),
                ('Excess Amount', fmt(excess_80ccd2)),
            ],
            'formulas': [
                ('Statutory Ceiling  =  Salary Base × Eligibility %',
                 f'{fmt(sal_b)} × {nps_pct:.2f}% = {fmt(calc_ceiling)}'),
                ('Eligible  =  min(Declared, Ceiling)',
                 f'min({fmt(nps2_amt)}, {fmt(calc_ceiling)}) = {fmt(approved_80ccd2)}'),
            ],
        })

        # ─────────────────────────────────────────────────────────────────────
        # 14. Section 17(2)(vii) — Employer Contribution Perquisite Audit Trace
        # ─────────────────────────────────────────────────────────────────────
        proj = getattr(tds_res, 'annual_income_projection', None)
        sec_17_val = float(getattr(proj, 'sec_17_2_vii_perquisite', 0.0) or 0.0) if proj else 0.0
        ann_epf = float(getattr(proj, 'total_annual_employer_epf', 0.0) or 0.0) if proj else 0.0
        ann_nps = float(getattr(proj, 'actual_employer_nps', 0.0) or 0.0) if proj else 0.0
        tot_contrib = float(getattr(proj, 'combined_employer_contribution', 0.0) or (ann_epf + ann_nps)) if proj else (ann_epf + ann_nps)
        ceiling_17 = float((getattr(proj, 'combined_ceiling', 0.0) if proj else 0.0)
                           or tds_param_svc.get_combined_employer_contribution_limit(eval_date=eval_date) or 0.0)

        if tot_contrib > 0 or sec_17_val > 0:
            traces.append({
                'code': '17(2)(vii)',
                'name': 'Section 17(2)(vii) — Employer Contributions Perquisite Audit (EPF, NPS, Superannuation)',
                'statutory_ref': 'Section 17(2)(vii) of Income-tax Act, 1961',
                'source_type': 'Employer Statutory Contributions',
                'regime_applicability': 'Both Old & New Regime (Taxable Perquisite Added to GTI)',
                'declared': tot_contrib,
                'approved': sec_17_val,
                'excess': sec_17_val,
                'cap_applied': sec_17_val > 0,
                'is_eligible': True,
                'eligibility_status': 'TAXABLE PERQUISITE APPLIED' if sec_17_val > 0 else 'WITHIN STATUTORY CEILING (NOT TAXABLE)',
                'reason': (
                    f"Combined employer contributions (INR {tot_contrib:,.2f}) exceed aggregate statutory ceiling of INR {ceiling_17:,.2f}. "
                    f"Excess of INR {sec_17_val:,.2f} is treated as a taxable perquisite and added to Gross Total Income (GTI)."
                    if sec_17_val > 0 else
                    f"Combined employer contributions (INR {tot_contrib:,.2f}) are within the aggregate statutory ceiling of INR {ceiling_17:,.2f}. No taxable perquisite arises."
                ),
                'inputs': [
                    ('Projected Annual Employer EPF Contribution', fmt(ann_epf)),
                    ('Declared Employer NPS Contribution', fmt(ann_nps)),
                    ('Total Combined Employer Contribution', fmt(tot_contrib)),
                    ('Statutory Aggregate Ceiling', fmt(ceiling_17)),
                    ('Taxable Perquisite Added to Gross Total Income', fmt(sec_17_val)),
                ],
                'formulas': [
                    ('Formula — Combined Contribution', f'{fmt(ann_epf)} + {fmt(ann_nps)} = {fmt(tot_contrib)}'),
                    ('Formula — Taxable Perquisite', f'max(0.0, {fmt(tot_contrib)} − {fmt(ceiling_17)}) = {fmt(sec_17_val)}'),
                ],
            })

        # Internal parameter codes (HDS_IN_...) are not meant for the printed report
        for trace in traces:
            if isinstance(trace.get('reason'), str):
                trace['reason'] = re.sub(r'\s*\(?\bHDS_IN_[A-Z0-9_]+\)?', '', trace['reason']).strip()
        return traces


class ReportStatutoryTaxPayslip(models.AbstractModel):
    """
    QWeb Report Data Provider — Hudson Payroll Statutory Tax Payslip Report.
    Binds uniquely to hr.payslip model to prevent model mismatch during PDF rendering.
    """
    _name = 'report.hudson_in_payroll.report_statutory_tax_payslip'
    _description = 'Statutory Tax Payslip Calculation Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        data['model_name'] = 'hr.payslip'
        return self.env['report.hudson_in_payroll.report_statutory_tax_calculation'].with_context(
            active_model='hr.payslip'
        )._get_report_values(docids, data=data)
