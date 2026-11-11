import logging
from datetime import datetime, time, date
import pytz
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
from ..services.epf.epf_service import EPFService
from ..services.esic.esic_service import ESICService
from ..services.lwf.lwf_service import LWFService
from ..services.gratuity.gratuity_service import GratuityService
from ..services.professional_tax.professional_tax_service import ProfessionalTaxService
from ..services.tds.tds_orchestration_engine import TdsOrchestrationEngine
from ..services.bonus.bonus_service import BonusService

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    _hds_in_last_computed_decl_write_date = fields.Datetime(
        string="Last Computed Declaration Timestamp", copy=False
    )
    hds_in_tds_applicable = fields.Boolean(
        string="TDS Applicable",
        compute='_compute_hds_in_tds_applicable',
        store=False,
    )

    @api.depends('company_id.hds_in_tds_applicable', 'employee_id.hds_in_tds_applicable')
    def _compute_hds_in_tds_applicable(self):
        for rec in self:
            comp_tds = bool(rec.company_id and rec.company_id.hds_in_tds_applicable)
            emp_tds = bool(rec.employee_id and rec.employee_id.hds_in_tds_applicable)
            rec.hds_in_tds_applicable = comp_tds and emp_tds
    hds_in_esic_daily_wage_exempt = fields.Boolean(
        string="ESIC Daily Wage Exempt (Rule 51-B)",
        copy=False,
        readonly=True,
        help="Statutory exemption under ESI Rule 51-B when average daily wage is <= ₹176/day."
    )
    hds_in_esic_average_daily_wage = fields.Monetary(
        string="ESIC Average Daily Wage",
        currency_field='currency_id',
        copy=False,
        readonly=True,
        help="Average daily wage during the wage period (ESI Wage / Paid Days)."
    )
    hds_in_esic_paid_days = fields.Float(
        string="ESIC Paid Days in Period",
        copy=False,
        readonly=True,
        help="Number of payable/worked days in the wage period (after deducting LOP/unpaid leave)."
    )
    hds_in_employer_epf = fields.Monetary(
        string="Employer EPF (12%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="12% EPF/EPS Employer Contribution (3.67% EPF + 8.33% EPS)"
    )
    hds_in_employer_epf_share = fields.Monetary(
        string="Employer EPF (3.67%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="Employer EPF 3.67% Contribution (Net EPF)"
    )
    hds_in_employer_eps = fields.Monetary(
        string="Employer EPS (8.33%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="Employer Pension Scheme 8.33% Contribution"
    )
    hds_in_employer_edli = fields.Monetary(
        string="EDLI (0.5%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="Employees Deposit Linked Insurance 0.5% Contribution"
    )
    hds_in_employer_epf_admin = fields.Monetary(
        string="EPF Admin (0.5%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="EPF Administration Charges 0.5%"
    )
    hds_in_employer_esic = fields.Monetary(
        string="Employer ESIC (3.25%)",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="3.25% ESIC Employer Contribution"
    )
    hds_in_employer_lwf = fields.Monetary(
        string="Employer LWF Share",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="Employer Labour Welfare Fund Contribution"
    )
    hds_in_total_employer_statutory = fields.Monetary(
        string="Total Employer Statutory",
        compute="_compute_hds_in_employer_statutory",
        store=True,
        currency_field="currency_id",
        help="Total Employer Statutory Cost (EPF 12% + EDLI + Admin + ESIC + LWF)"
    )

    # Government deposit of the payslip (Payroll dashboard "Govt Deposit"): employee and employer
    # statutory shares and TDS, by the same line codes as the dashboard total
    hds_in_govt_ee_epf = fields.Monetary(string="Employee EPF", compute="_compute_hds_in_govt_deposit",
                                         store=True, currency_field="currency_id")
    hds_in_govt_er_epf = fields.Monetary(string="Employer EPF (12%)", compute="_compute_hds_in_govt_deposit",
                                         store=True, currency_field="currency_id")
    hds_in_govt_edli_admin = fields.Monetary(string="EDLI & EPF Admin", compute="_compute_hds_in_govt_deposit",
                                             store=True, currency_field="currency_id")
    hds_in_govt_ee_esic = fields.Monetary(string="Employee ESIC", compute="_compute_hds_in_govt_deposit",
                                          store=True, currency_field="currency_id")
    hds_in_govt_er_esic = fields.Monetary(string="Employer ESIC", compute="_compute_hds_in_govt_deposit",
                                          store=True, currency_field="currency_id")
    hds_in_govt_pt = fields.Monetary(string="Professional Tax", compute="_compute_hds_in_govt_deposit",
                                     store=True, currency_field="currency_id")
    hds_in_govt_ee_lwf = fields.Monetary(string="Employee LWF", compute="_compute_hds_in_govt_deposit",
                                         store=True, currency_field="currency_id")
    hds_in_govt_er_lwf = fields.Monetary(string="Employer LWF", compute="_compute_hds_in_govt_deposit",
                                         store=True, currency_field="currency_id")
    hds_in_govt_tds = fields.Monetary(string="TDS", compute="_compute_hds_in_govt_deposit",
                                      store=True, currency_field="currency_id")
    hds_in_govt_deposit_total = fields.Monetary(string="Total Govt Deposit", compute="_compute_hds_in_govt_deposit",
                                                store=True, currency_field="currency_id",
                                                help="TDS + PT + EPF (employee, employer, EDLI, admin) + ESIC + LWF")

    hds_in_employee_pan = fields.Char(related='employee_id.hds_in_pan', string="PAN")

    # Net salary of the payslip (Payroll dashboard "Net Salary"): gross less the employee deductions
    hds_in_net_salary = fields.Monetary(string="Net Salary", compute="_compute_hds_in_net_breakdown", store=True,
                                        currency_field="currency_id")
    hds_in_net_other_deductions = fields.Monetary(
        string="Other Deductions", compute="_compute_hds_in_net_breakdown", store=True, currency_field="currency_id",
        help="Gross salary less net salary, other than employee EPF, ESIC, LWF, professional tax and TDS "
             "(e.g. loans, advances, salary deductions)")

    @api.depends('gross_wage', 'net_wage', 'contract_id.wage', 'line_ids.total', 'line_ids.code',
                 'hds_in_govt_ee_epf', 'hds_in_govt_ee_esic', 'hds_in_govt_pt', 'hds_in_govt_ee_lwf', 'hds_in_govt_tds')
    def _compute_hds_in_net_breakdown(self):
        for slip in self:
            def line_total(code):
                line = slip.line_ids.filtered(lambda l: (l.code or '').upper() == code)[:1]
                return abs(float(line.total or 0.0))
            # Net as the dashboard counts it
            net = float(slip.net_wage or 0.0) or line_total('NET')
            contract_wage = float(slip.contract_id.wage or 0.0)
            if net <= 0.0 and contract_wage > 0.0 and not slip.line_ids:
                net = contract_wage
            # Deductions from the payslip's own gross (a payslip without earnings has none)
            gross = float(slip.gross_wage or 0.0) or line_total('GROSS')
            employee_deductions = (slip.hds_in_govt_ee_epf + slip.hds_in_govt_ee_esic + slip.hds_in_govt_pt
                                   + slip.hds_in_govt_ee_lwf + slip.hds_in_govt_tds)
            slip.hds_in_net_salary = net
            slip.hds_in_net_other_deductions = (gross - net - employee_deductions) if gross else 0.0

    # Cost to company of the payslip (Payroll dashboard "Total Payroll Cost (CTC)"): gross pay plus the
    # employer cost lines, by the same rules as the dashboard total
    hds_in_ctc_gross = fields.Monetary(string="Gross Salary", compute="_compute_hds_in_ctc", store=True,
                                       currency_field="currency_id")
    hds_in_ctc_er_epf = fields.Monetary(string="Employer EPF (12%)", compute="_compute_hds_in_ctc", store=True,
                                        currency_field="currency_id")
    hds_in_ctc_er_edli = fields.Monetary(string="EDLI", compute="_compute_hds_in_ctc", store=True,
                                         currency_field="currency_id")
    hds_in_ctc_er_admin = fields.Monetary(string="EPF Admin", compute="_compute_hds_in_ctc", store=True,
                                          currency_field="currency_id")
    hds_in_ctc_er_esic = fields.Monetary(string="Employer ESIC", compute="_compute_hds_in_ctc", store=True,
                                         currency_field="currency_id")
    hds_in_ctc_er_lwf = fields.Monetary(string="Employer LWF", compute="_compute_hds_in_ctc", store=True,
                                        currency_field="currency_id")
    hds_in_ctc_er_other = fields.Monetary(string="Other Employer Cost", compute="_compute_hds_in_ctc", store=True,
                                          currency_field="currency_id",
                                          help="Other salary rules marked 'Contributes to Employer Cost'")
    hds_in_ctc_employer_cost = fields.Monetary(string="Employer Cost", compute="_compute_hds_in_ctc", store=True,
                                               currency_field="currency_id")
    hds_in_ctc_total = fields.Monetary(string="CTC", compute="_compute_hds_in_ctc", store=True,
                                       currency_field="currency_id", help="Gross salary + employer cost")

    @api.depends('gross_wage', 'contract_id.wage', 'line_ids.total', 'line_ids.code',
                 'line_ids.salary_rule_id.hds_in_contributes_to_employer_cost')
    def _compute_hds_in_ctc(self):
        employer_codes = ('EMPLOYER_EPF', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN', 'ESIC_ER', 'LWF_ER')
        buckets = {
            'er_epf': ('EMPLOYER_EPF', 'ER_PF', 'EPS', 'EPF_SHARE'), 'er_edli': ('EDLI',),
            'er_admin': ('EPF_ADMIN', 'EDLI_ADMIN'), 'er_esic': ('ESIC_ER', 'ER_ESI'), 'er_lwf': ('LWF_ER', 'ER_LWF'),
        }
        for slip in self:
            gross = float(slip.gross_wage or 0.0)
            if not gross:
                gross_line = slip.line_ids.filtered(lambda line: (line.code or '').upper() == 'GROSS')[:1]
                gross = abs(float(gross_line.total or 0.0))
            contract_wage = float(slip.contract_id.wage or 0.0)
            if gross <= 0.0 and contract_wage > 0.0:
                gross = contract_wage
            codes = {(line.code or '').upper() for line in slip.line_ids}
            has_er_epf = 'EMPLOYER_EPF' in codes or 'ER_PF' in codes
            vals = dict.fromkeys(('er_epf', 'er_edli', 'er_admin', 'er_esic', 'er_lwf', 'er_other'), 0.0)
            for line in slip.line_ids:
                code = (line.code or '').upper()
                if not (line.salary_rule_id.hds_in_contributes_to_employer_cost or code in employer_codes
                        or (not has_er_epf and code in ('EPS', 'EPF_SHARE'))):
                    continue
                bucket = next((key for key, bucket_codes in buckets.items() if code in bucket_codes), 'er_other')
                vals[bucket] += abs(float(line.total or 0.0))
            for key, value in vals.items():
                slip[f'hds_in_ctc_{key}'] = value
            employer_cost = sum(vals.values())
            slip.hds_in_ctc_gross = gross
            slip.hds_in_ctc_employer_cost = employer_cost
            slip.hds_in_ctc_total = gross + employer_cost

    @api.depends('line_ids.total', 'line_ids.code')
    def _compute_hds_in_govt_deposit(self):
        for slip in self:
            codes = {(line.code or '').upper() for line in slip.line_ids}
            has_er_epf = 'EMPLOYER_EPF' in codes or 'ER_PF' in codes
            legacy_esi = 'ESIC_EE' not in codes and 'ESIC_ER' not in codes
            vals = dict.fromkeys(('ee_epf', 'er_epf', 'edli_admin', 'ee_esic', 'er_esic', 'pt', 'ee_lwf', 'er_lwf', 'tds'), 0.0)
            for line in slip.line_ids:
                code = (line.code or '').upper()
                amt = abs(float(line.total or 0.0))
                if code in ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS'):
                    vals['tds'] += amt
                elif code in ('PT', 'PROF_TAX'):
                    vals['pt'] += amt
                if code in ('PF', 'EPF', 'EE_PF'):
                    vals['ee_epf'] += amt
                elif code in ('EMPLOYER_EPF', 'ER_PF') or (not has_er_epf and code in ('EPS', 'EPF_SHARE')):
                    vals['er_epf'] += amt
                elif code in ('EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                    vals['edli_admin'] += amt
                if code in ('ESIC_EE', 'EE_ESI'):
                    vals['ee_esic'] += amt
                elif code in ('ESIC_ER', 'ER_ESI'):
                    vals['er_esic'] += amt
                elif code == 'ESI' and legacy_esi:
                    # Single ESI line (older structures): 0.75% employee and 3.25% employer of the 4%
                    ee_part = round(amt * 0.75 / 4.0, 2)
                    vals['ee_esic'] += ee_part
                    vals['er_esic'] += amt - ee_part
                if code in ('LWF_EE', 'EE_LWF', 'LWF'):
                    vals['ee_lwf'] += amt
                elif code in ('LWF_ER', 'ER_LWF'):
                    vals['er_lwf'] += amt
            for key, value in vals.items():
                slip[f'hds_in_govt_{key}'] = value
            slip.hds_in_govt_deposit_total = sum(vals.values())

    @api.depends('line_ids.total', 'line_ids.code')
    def _compute_hds_in_employer_statutory(self):
        for slip in self:
            er_epf_share = 0.0
            er_eps = 0.0
            er_edli = 0.0
            er_admin = 0.0
            er_esic = 0.0
            er_lwf = 0.0
            codes = set((l.code or '').upper() for l in slip.line_ids)
            has_split_pf = 'EPS' in codes or 'EPF_SHARE' in codes

            for line in slip.line_ids:
                code = (line.code or '').upper()
                amt = abs(float(line.total or 0.0))

                if code == 'EPF_SHARE':
                    er_epf_share += amt
                elif code == 'EPS':
                    er_eps += amt
                elif code == 'EDLI':
                    er_edli += amt
                elif code in ('EPF_ADMIN', 'EDLI_ADMIN'):
                    er_admin += amt
                elif not has_split_pf and code in ('EMPLOYER_EPF', 'ER_PF'):
                    er_epf_share += amt

                # Employer ESIC
                if code in ('ESIC_ER', 'ER_ESI'):
                    er_esic += amt
                elif code == 'ESI' and 'ESIC_EE' not in codes and 'ESIC_ER' not in codes:
                    er_esic += amt

                # Employer LWF
                if code in ('LWF_ER', 'ER_LWF'):
                    er_lwf += amt

            # Pure 12% Employer EPF Contribution (EPF 3.67% + EPS 8.33%)
            er_epf_12 = er_epf_share + er_eps
            slip.hds_in_employer_epf_share = er_epf_share
            slip.hds_in_employer_eps = er_eps
            slip.hds_in_employer_edli = er_edli
            slip.hds_in_employer_epf_admin = er_admin
            slip.hds_in_employer_epf = er_epf_12
            slip.hds_in_employer_esic = er_esic
            slip.hds_in_employer_lwf = er_lwf
            # Total Statutory = EPF 12% + EDLI 0.5% + Admin 0.5% + ESIC 3.25% + LWF
            slip.hds_in_total_employer_statutory = er_epf_12 + er_edli + er_admin + er_esic + er_lwf

    # Transient in-memory dictionary cache for active payslip evaluation contexts
    _eval_contexts = {}

    # -------------------------------------------------------------------------
    # STATUTORY CONTEXT INJECTION HOOK
    # -------------------------------------------------------------------------
    def _get_statutory_context(self, localdict):
        """
        Extensible hook to inject domain services and actual recordsets into localdict.
        Stores localdict in HrPayslip._eval_contexts[self.id]
        so that payslip_record.hds_in_compute_*() calls require ZERO parameters in XML.
        
        Future localization modules (ESIC, PT, LWF, TDS) extend this hook via super().
        """
        self.ensure_one()
        HrPayslip._eval_contexts[self.id] = localdict
        localdict.update({
            'epf_service': EPFService(self.env, localdict=localdict),
            'esic_service': ESICService(self.env, localdict=localdict),
            'lwf_service': LWFService(self.env, localdict=localdict),
            'gratuity_service': GratuityService(self.env, localdict=localdict),
            'pt_service': ProfessionalTaxService(self.env, localdict=localdict),
            'tds_orchestration_engine': TdsOrchestrationEngine(self.env),
            'bonus_service': BonusService(self.env, localdict=localdict),
            'payslip_record': self,
        })
        return localdict

    def _get_localization_context(self, localdict):
        """Override base hook to inject India statutory services and context."""
        localdict = super()._get_localization_context(localdict)
        return self._get_statutory_context(localdict)

    def hds_in_compute_tds(self, localdict=None):
        """
        Payslip statutory method called by salary rule HDS_IN_TDS.
        Invokes TdsOrchestrationEngine master entry point and returns monthly TDS deduction.
        """
        self.ensure_one()
        company = self.company_id or self.employee_id.company_id or self.env.company
        if not getattr(company, 'hds_in_tds_applicable', False):
            _logger.info(
                "[TDS_APPLICABILITY_CHECK] TDS is disabled for company '%s' (ID: %s). Skipping TDS calculation for payslip %s.",
                getattr(company, 'name', 'N/A'),
                getattr(company, 'id', 'N/A'),
                self.name or self.id
            )
            return 0.0
        if not getattr(self.employee_id, 'hds_in_tds_applicable', False):
            _logger.info(
                "[TDS_APPLICABILITY_CHECK] TDS is disabled for employee '%s' (ID: %s). Skipping TDS calculation for payslip %s.",
                getattr(self.employee_id, 'name', 'N/A'),
                getattr(self.employee_id, 'id', 'N/A'),
                self.name or self.id
            )
            return 0.0
        if self._get_earned_wage_ratio(localdict=localdict) <= 0.0:
            _logger.info(
                "[TDS_EARNED_RATIO_GUARD] Earned wage ratio is <= 0.0. Skipping TDS calculation for payslip %s.",
                self.name or self.id
            )
            return 0.0

        eval_ctx = localdict or self._get_payroll_eval_context(raise_if_missing=False)
        if eval_ctx and 'categories' in eval_ctx:
            cats = eval_ctx['categories']
            net_before_tds = (getattr(cats, 'BASIC', 0.0) or 0.0) + (getattr(cats, 'ALW', 0.0) or 0.0) + (getattr(cats, 'DED', 0.0) or 0.0)
            if net_before_tds <= 0.0:
                _logger.info(
                    "[TDS_NET_WAGE_GUARD] Net wage before TDS is <= 0 (₹%.2f). Skipping TDS calculation for payslip %s.",
                    net_before_tds, self.name or self.id
                )
                return 0.0

        _logger.warning(
            "[TDS_ENTRY_AUDIT] hds_in_compute_tds ENTERED | payslip=%s | employee=%s",
            self.id,
            self.employee_id.id,
        )

        import inspect
        _logger.warning(
            "[TDS_ENGINE_PATH_AUDIT] TdsOrchestrationEngine loaded from: %s | class: %s",
            inspect.getfile(TdsOrchestrationEngine),
            TdsOrchestrationEngine,
        )

        icp = self.env['ir.config_parameter'].sudo()
        get_param_fn = getattr(icp, 'get_param', None) or getattr(icp, 'get_str', None)
        debug_enabled = (get_param_fn('hudson_in_payroll.tds_debug_logging', 'False') == 'True') if get_param_fn else False
        if debug_enabled:
            _logger.warning("=" * 80)
            _logger.warning("TDS ENGINE STARTED FOR PAYSLIP: %s (Employee: %s)", self.name, self.employee_id.name)
            _logger.warning("=" * 80)
        eval_date = self.date_to or fields.Date.today()
        engine = TdsOrchestrationEngine(self.env)
        res = engine.hds_in_compute_tds(self.employee_id, eval_date=eval_date, payslip=self)

        if debug_enabled:
            # ── EXTRACT VARIABLES FOR DETAILED [TDS_DEBUG_TRACE] LOGGING ──────────
            emp = self.employee_id
            contract = self.contract_id or (emp.contract_id if hasattr(emp, 'contract_id') else False)
            contract_wage = float(contract.wage or 0.0) if contract else 0.0
            contract_id = contract.id if contract else 'N/A'

            financial_year = self.env['tds.financial.year'].search([
                ('start_date', '<=', eval_date),
                ('end_date', '>=', eval_date)
            ], limit=1)
            fy_name = financial_year.name if financial_year else 'N/A'

            decl = self.env['tds.employee.declaration'].search([
                ('employee_id', '=', emp.id)
            ], order='id desc', limit=1)

            regime_code = res.regime_code if hasattr(res, 'regime_code') else 'old'

            # 1. AT METHOD ENTRY
            _logger.warning("""[TDS_DEBUG_TRACE] ENTER hds_in_compute_tds
employee_id=%s
employee_name=%s
contract_id=%s
date_from=%s
date_to=%s
tax_regime=%s
financial_year=%s
contract_wage=%s""",
                emp.id, emp.name, contract_id, self.date_from, self.date_to,
                regime_code, fy_name, contract_wage
            )

            # 2. SHOW ANNUAL INCOME INPUTS
            sal_proj = res.annual_income_projection.salary_projection
            prev_emp = res.annual_income_projection.previous_employer_income
            oth_inc = res.annual_income_projection.other_income_aggregation

            fy_emp_months = max(1, (sal_proj.months_elapsed + sal_proj.months_remaining) if sal_proj else 12)
            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=BASIC
name=Basic Salary
monthly=%s
annual=%s
included=True""", sal_proj.total_basic / float(fy_emp_months) if sal_proj.total_basic else 0.0, sal_proj.total_basic)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=HRA
name=House Rent Allowance
monthly=%s
annual=%s
included=True""", sal_proj.total_hra / float(fy_emp_months) if sal_proj.total_hra else 0.0, sal_proj.total_hra)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=DA
name=Dearness Allowance
monthly=%s
annual=%s
included=True""", sal_proj.total_da / float(fy_emp_months) if sal_proj.total_da else 0.0, sal_proj.total_da)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=ALLOWANCES
name=Other Allowances
monthly=%s
annual=%s
included=True""", sal_proj.total_allowances / float(fy_emp_months) if sal_proj.total_allowances else 0.0, sal_proj.total_allowances)

            if prev_emp.taxable_salary > 0:
                _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=PREV_EMP
name=Previous Employer Income
monthly=0.0
annual=%s
included=True""", prev_emp.taxable_salary)

            if oth_inc.total_other_income != 0:
                _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=OTHER_INC
name=Income from Other Sources
monthly=0.0
annual=%s
included=True""", oth_inc.total_other_income)

            # 3. SHOW PROJECTION
            current_inc = sal_proj.ytd_basic + sal_proj.ytd_da + sal_proj.ytd_hra + sal_proj.ytd_bonus + sal_proj.ytd_allowances
            projected_inc = sal_proj.projected_basic + sal_proj.projected_da + sal_proj.projected_hra + sal_proj.projected_bonus + sal_proj.projected_allowances
            gti = res.annual_income_projection.gross_total_income

            _logger.warning("""[TDS_DEBUG_TRACE] ANNUAL_PROJECTION
months_elapsed=%s
months_remaining=%s
previous_income=%s
current_income=%s
projected_income=%s
annual_gross_income=%s""",
                sal_proj.months_elapsed, sal_proj.months_remaining,
                prev_emp.taxable_salary, current_inc, projected_inc, gti
            )

            # 4. SHOW EXEMPTIONS
            ded_calc = res.deduction_calculation
            hra_claimed = float(decl.decl_hra_annual_rent or 0.0) if decl else 0.0
            hra_allowed = ded_calc.hra_exemption
            _logger.warning("""[TDS_DEBUG_TRACE] EXEMPTION
name=HRA
claimed=%s
eligible=%s
allowed=%s
deducted=%s""", hra_claimed, hra_allowed, hra_allowed, hra_allowed)

            home_loan_claimed = float(decl.decl_24b_self_interest or 0.0) if decl else 0.0
            home_loan_allowed = ded_calc.home_loan_interest_24b
            _logger.warning("""[TDS_DEBUG_TRACE] EXEMPTION
name=Home Loan Sec 24(b)
claimed=%s
eligible=%s
allowed=%s
deducted=%s""", home_loan_claimed, home_loan_allowed, home_loan_allowed, home_loan_allowed)

            # 5. SHOW DEDUCTIONS
            c6a = getattr(ded_calc, 'chapter_6a_deductions', None)
            sec_80c = getattr(c6a, 'section_80c', 0.0) if c6a else 0.0
            sec_80ccd1b = getattr(c6a, 'section_80ccd1b', 0.0) if c6a else 0.0
            sec_80d = getattr(c6a, 'section_80d', 0.0) if c6a else 0.0
            sec_80dd = getattr(c6a, 'section_80dd', 0.0) if c6a else 0.0
            sec_80tta = getattr(c6a, 'section_80tta_80ttb', 0.0) if c6a else 0.0
            sec_80eea = getattr(c6a, 'section_80eea_deduction', getattr(ded_calc, 'section_80eea_deduction', 0.0))
            emp_nps = getattr(ded_calc, 'employer_nps_80ccd2', 0.0)
            fam_pen = getattr(ded_calc, 'family_pension_57iia', 0.0)
            sec_80cch_val = 0.0
            cch_claimed = 0.0
            if decl:
                cch_ln = next((l for l in decl.declaration_line_ids if l.category == '80cch'), None)
                if cch_ln:
                    sec_80cch_val = cch_ln.usable_amount
                    cch_claimed = float(cch_ln.tax_firm_approved_amount or cch_ln.approved_amount or cch_ln.declared_amount or 0.0) if decl.state in ('proof_verified', 'approved') else float(cch_ln.declared_amount or 0.0)
                else:
                    sec_80cch_val = float(getattr(decl, 'decl_80cch_agniveer', 0.0) or 0.0)
                    cch_claimed = sec_80cch_val

            std_ded_limit = 75000.0 if regime_code == 'new' else 50000.0
            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=Standard Deduction
claimed=%s
eligible=%s
limit=%s
allowed=%s""", ded_calc.standard_deduction, ded_calc.standard_deduction, std_ded_limit, ded_calc.standard_deduction)

            c80_claimed = (
                float(getattr(decl, 'decl_80c_epf', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_lic', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_elss', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_tuition', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_ppf', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_ssy', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_fd', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_nsc', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_housing_principal', 0.0) or 0.0) +
                float(getattr(decl, 'decl_80c_other', 0.0) or 0.0)
            ) if decl else sec_80c
            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80C
claimed=%s
eligible=%s
limit=150000
allowed=%s""", c80_claimed, sec_80c, sec_80c)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCD(1B)
claimed=%s
eligible=%s
limit=50000
allowed=%s""", decl.decl_80ccd1b_nps if decl else sec_80ccd1b, sec_80ccd1b, sec_80ccd1b)

            nps2_claimed = float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or (next((l.declared_amount for l in decl.declaration_line_ids if l.category == '80ccd2'), 0.0) if decl else 0.0) or 0.0) if decl else emp_nps
            if nps2_claimed == 0.0:
                nps2_claimed = emp_nps
            nps2_limit = round(((sal_proj.total_basic or 0.0) + (sal_proj.total_da or 0.0)) * (0.14 if regime_code == 'new' else 0.10), 2) if sal_proj else emp_nps
            if nps2_limit == 0.0:
                nps2_limit = emp_nps

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCD(2)
claimed=%s
eligible=%s
limit=%s
allowed=%s""", nps2_claimed, emp_nps, nps2_limit, emp_nps)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80D
claimed=%s
eligible=%s
limit=100000
allowed=%s""", (decl.decl_80d_self + decl.decl_80d_parents) if decl else sec_80d, sec_80d, sec_80d)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80DD
claimed=%s
eligible=%s
limit=125000
allowed=%s""", sec_80dd, sec_80dd, sec_80dd)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80TTA/80TTB
claimed=%s
eligible=%s
limit=50000
allowed=%s""", sec_80tta, sec_80tta, sec_80tta)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80EEA
claimed=%s
eligible=%s
limit=150000
allowed=%s""", sec_80eea, sec_80eea, sec_80eea)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=57(iia)
claimed=%s
eligible=%s
limit=15000
allowed=%s""", fam_pen, fam_pen, fam_pen)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCH
claimed=%s
eligible=%s
allowed=%s""", cch_claimed, sec_80cch_val, sec_80cch_val)

            sec_80e_val = getattr(c6a, 'section_80e', 0.0) if c6a else 0.0
            e80_declared = float(getattr(decl, 'decl_80e_interest', 0.0) or 0.0) if decl else sec_80e_val
            e80_verified = 0.0
            e80_approved = 0.0
            e80_eligible = sec_80e_val
            e80_allowed = sec_80e_val
            if decl:
                e_ln = next((l for l in decl.declaration_line_ids if l.category == '80e'), None)
                if e_ln:
                    e80_declared = float(e_ln.declared_amount or 0.0) if e_ln.declared_amount is not False else e80_declared
                    e80_verified = float(getattr(e_ln, 'verified_amount', 0.0) or 0.0)
                    e80_approved = float(getattr(e_ln, 'tax_firm_approved_amount', 0.0) or getattr(e_ln, 'approved_amount', 0.0) or 0.0)
                    e80_eligible = float(getattr(e_ln, 'eligible_amount', 0.0) or 0.0) or sec_80e_val
                    e80_allowed = sec_80e_val
                else:
                    e80_approved = float(getattr(decl, 'decl_80e_approved_amount', 0.0) or 0.0)
                    e80_verified = e80_approved

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80E
claimed=%s
declared=%s
verified=%s
approved=%s
eligible=%s
allowed=%s""", e80_declared, e80_declared, e80_verified, e80_approved, e80_eligible, e80_allowed)

            sec_80g_val = getattr(c6a, 'section_80g', 0.0) if c6a else 0.0
            g80_claimed = float(getattr(decl, 'decl_80g_donation', 0.0) or 0.0) if decl else sec_80g_val
            if decl:
                g_ln = next((l for l in decl.declaration_line_ids if l.category == '80g'), None)
                if g_ln:
                    g80_claimed = float(g_ln.tax_firm_approved_amount or g_ln.approved_amount or g_ln.declared_amount or 0.0) if decl.state in ('proof_verified', 'approved') else float(g_ln.declared_amount or 0.0)
            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80G
claimed=%s
eligible=%s
allowed=%s""", g80_claimed, sec_80g_val, sec_80g_val)

            sec_80gg_val = getattr(c6a, 'section_80gg', 0.0) if c6a else 0.0
            gg80_declared = float(getattr(decl, 'decl_80gg_rent', 0.0) or 0.0) if decl else sec_80gg_val
            gg80_verified = 0.0
            gg80_approved = 0.0
            gg80_eligible = sec_80gg_val
            gg80_allowed = sec_80gg_val
            if decl:
                gg_ln = next((l for l in decl.declaration_line_ids if l.category == '80gg'), None)
                if gg_ln:
                    gg80_declared = float(gg_ln.declared_amount or 0.0) if gg_ln.declared_amount is not False else gg80_declared
                    gg80_verified = float(getattr(gg_ln, 'verified_amount', 0.0) or 0.0)
                    gg80_approved = float(getattr(gg_ln, 'tax_firm_approved_amount', 0.0) or getattr(gg_ln, 'approved_amount', 0.0) or 0.0)
                    gg80_eligible = float(getattr(gg_ln, 'eligible_amount', 0.0) or 0.0) or sec_80gg_val
                    gg80_allowed = sec_80gg_val
                else:
                    gg80_approved = gg80_declared
                    gg80_verified = gg80_declared

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80GG
claimed=%s
declared=%s
verified=%s
approved=%s
eligible=%s
allowed=%s""", gg80_declared, gg80_declared, gg80_verified, gg80_approved, gg80_eligible, gg80_allowed)

            # 6. SHOW TAXABLE INCOME CALCULATION
            tot_exemptions = ded_calc.hra_exemption + ded_calc.home_loan_interest_24b
            tot_deductions = ded_calc.total_allowable_deductions
            net_taxable_inc = res.taxable_income.net_taxable_income

            _logger.warning("""[TDS_DEBUG_TRACE] TAXABLE_INCOME_CALCULATION
annual_gross_income=%s
total_exemptions=%s
standard_deduction=%s
total_deductions=%s
taxable_income_before_rounding=%s
taxable_income_after_rounding=%s""",
                gti, tot_exemptions, ded_calc.standard_deduction, tot_deductions,
                net_taxable_inc, net_taxable_inc
            )

            # 7. SHOW TAX SLAB CALCULATION
            slab_calc = res.income_tax_slab
            for sb in (slab_calc.slab_breakdown if hasattr(slab_calc, 'slab_breakdown') and slab_calc.slab_breakdown else []):
                rate_pct = sb.get('rate', 0.0) * 100 if sb.get('rate', 0.0) <= 1 else sb.get('rate', 0.0)
                _logger.warning("""[TDS_DEBUG_TRACE] TAX_SLAB
lower=%s
upper=%s
taxable_in_slab=%s
rate=%s
tax=%s""",
                    sb.get('lower_limit', 0), sb.get('upper_limit', 0),
                    sb.get('taxable_in_slab', 0.0), rate_pct, sb.get('tax', 0.0)
                )

            # 8. SHOW TAX BEFORE REBATE
            base_tax = slab_calc.base_tax_liability
            _logger.warning("""[TDS_DEBUG_TRACE] TAX_BEFORE_REBATE
taxable_income=%s
tax_before_rebate=%s""", net_taxable_inc, base_tax)

            # 9. SHOW REBATE
            reb = res.rebate_engine
            _logger.warning("""[TDS_DEBUG_TRACE] REBATE
rebate_eligible=%s
rebate_amount=%s
tax_after_rebate=%s""",
                reb.is_applicable if hasattr(reb, 'is_applicable') else (reb.rebate_applied > 0),
                reb.rebate_applied, reb.tax_after_rebate
            )

            # 10. SHOW SURCHARGE
            sur = res.surcharge_engine
            sur_rate = getattr(sur, 'surcharge_rate_pct', getattr(sur, 'surcharge_rate', 0.0))
            _logger.warning("""[TDS_DEBUG_TRACE] SURCHARGE
tax_before_surcharge=%s
surcharge_rate=%s
surcharge_amount=%s
tax_after_surcharge=%s""",
                reb.tax_after_rebate, sur_rate, sur.surcharge_amount, sur.tax_plus_surcharge
            )

            # 11. SHOW CESS
            cess_obj = res.health_education_cess
            cess_rate_val = getattr(cess_obj, 'cess_rate_pct', getattr(cess_obj, 'cess_rate', 0.04))
            _logger.warning("""[TDS_DEBUG_TRACE] CESS
cess_base=%s
cess_rate=%s
cess_amount=%s""", sur.tax_plus_surcharge, cess_rate_val, cess_obj.cess_amount)

            # 12. SHOW FINAL ANNUAL TAX LIABILITY
            ann_tax_liab = cess_obj.total_annual_tax_liability
            _logger.warning("""[TDS_DEBUG_TRACE] FINAL_ANNUAL_TAX
tax_before_cess=%s
cess=%s
total_annual_tax_liability=%s""", sur.tax_plus_surcharge, cess_obj.cess_amount, ann_tax_liab)

            # Dedicated SECTION 80EEA CALCULATION FLOW TRACE & END-TO-END TRACE
            home_loan_declared = home_loan_claimed
            home_loan_allowed = float(getattr(ded_calc, 'home_loan_interest_24b', 0.0) or 0.0)
            residual_interest = max(home_loan_declared - home_loan_allowed, 0.0)

            eea_line = next((l for l in decl.declaration_line_ids if l.category == '80eea'), None) if decl else None
            eea_declared = float(getattr(decl, 'decl_80eea_interest_amount', 0.0) or 0.0) if decl else 0.0
            if eea_line and (eea_line.declared_amount or 0.0) > 0.0:
                eea_declared = max(eea_declared, float(eea_line.declared_amount or 0.0))

            eea_verified = float(getattr(eea_line, 'verified_amount', 0.0) or 0.0) if eea_line else 0.0
            eea_approved = float(getattr(eea_line, 'tax_firm_approved_amount', 0.0) or getattr(eea_line, 'approved_amount', 0.0) or 0.0) if eea_line else (float(getattr(decl, 'decl_80eea_approved_amount', 0.0) or 0.0) if decl else 0.0)
            if home_loan_declared > 0.0:
                eea_eligible_base = min(residual_interest, eea_declared) if eea_declared > 0.0 else residual_interest
            else:
                eea_eligible_base = eea_declared
            eea_sanction_date = getattr(decl, 'decl_80eea_loan_sanction_date', None) if decl else None
            eea_stamp_val = float(getattr(decl, 'decl_80eea_property_stamp_value', 0.0) or 0.0) if decl else 0.0
            eea_first_buyer = bool(getattr(decl, 'decl_80eea_first_time_home_buyer', False)) if decl else False
            eea_claimed_80ee = bool(getattr(decl, 'decl_80eea_claimed_under_80ee', False)) if decl else False
            eea_lender_type = getattr(decl, 'decl_80eea_lender_type', 'scheduled_bank') or 'scheduled_bank' if decl else 'scheduled_bank'
            eea_lending_inst = getattr(decl, 'decl_80eea_lending_institution', 'N/A') or 'N/A' if decl else 'N/A'
            eea_loan_acct = getattr(decl, 'decl_80eea_loan_account_number', 'N/A') or 'N/A' if decl else 'N/A'
            eea_sanction_date_str = eea_sanction_date.strftime('%Y-%m-%d') if hasattr(eea_sanction_date, 'strftime') and eea_sanction_date else (str(eea_sanction_date) if eea_sanction_date else 'N/A')

            eea_s_date_obj = fields.Date.from_string(str(eea_sanction_date)) if eea_sanction_date else None
            eea_cond_date_window = bool(eea_s_date_obj and fields.Date.from_string("2019-04-01") <= eea_s_date_obj <= fields.Date.from_string("2022-03-31"))
            eea_cond_stamp = bool(eea_stamp_val > 0.0 and eea_stamp_val <= 4500000.0)
            eea_cond_lender = bool(eea_lender_type in ('scheduled_bank', 'housing_finance_company', 'nbfc'))
            has_eea_claim = bool(eea_declared > 0.0 or eea_sanction_date)
            total_chapter_6a = c6a.total_chapter_6a if c6a else 0.0

            trace_80eea_full = f"""
=========================================================
[SECTION_80EEA_CALCULATION_FLOW_TRACE]
=========================================================
Source: hr.payslip._compute_tds_distribution()

---------------- 1. DECLARATION INPUT ----------------
employee_id                         : {self.employee_id.id}
employee_name                       : {self.employee_id.name}
declaration_id                      : {decl.id if decl else 'N/A'}
financial_year                      : {fy_name}
declaration_state                   : {decl.state if decl else 'no_declaration'}
explicit_80eea_claim                : {"YES" if has_eea_claim else "NO"}
declared_80eea_amount               : INR {eea_declared:,.2f}
loan_sanction_date                  : {eea_sanction_date_str}
property_stamp_value                : INR {eea_stamp_val:,.2f}
first_time_home_buyer               : {"YES" if eea_first_buyer else "NO"}
claimed_under_80ee                  : {"YES" if eea_claimed_80ee else "NO"}
lender_type                         : {eea_lender_type}
lending_institution                 : {eea_lending_inst}
loan_account_number                 : {eea_loan_acct}


---------------- 2. HOME LOAN / 24(b) ----------------
original_home_loan_interest_declared: INR {home_loan_declared:,.2f}
section_24b_eligible_amount         : INR {home_loan_declared:,.2f}
section_24b_allowed_amount          : INR {home_loan_allowed:,.2f}
exact_amount_deducted_under_24b     : INR {home_loan_allowed:,.2f}


---------------- 3. 80EEA RESIDUAL CALCULATION ----------------
Formula                             : residual_interest = original_home_loan_interest - allowed_24b_interest
original_interest                   : INR {home_loan_declared:,.2f}
allowed_24b                         : INR {home_loan_allowed:,.2f}
residual_interest                   : INR {residual_interest:,.2f}
declared_80eea_amount               : INR {eea_declared:,.2f}
eligible_base_used                  : INR {eea_eligible_base:,.2f} ({'Residual interest after Section 24(b)' if residual_interest > 0.0 else 'Declared 80EEA Amount'})


---------------- 4. 80EEA STATUTORY ELIGIBILITY ----------------
Tax Regime (Old Regime)             : {"PASS (OLD)" if (regime_code == 'old') else "FAIL (NEW - Not permitted under New Tax Regime Section 202(1))"}
First-Time Home Buyer Condition     : {"PASS" if eea_first_buyer else "FAIL (Assessee is not a first-time buyer)"}
Loan Sanction Date                  : {eea_sanction_date_str}
Sanction-Date Window (2019-2022)    : {"PASS (Between 01-Apr-2019 and 31-Mar-2022)" if eea_cond_date_window else "FAIL (Outside statutory window)"}
Property Stamp Duty Value (<= 45L)  : {"PASS (INR " + f"{eea_stamp_val:,.2f} <= INR 4,500,000.00)" if eea_cond_stamp else "FAIL (Exceeds INR 4,500,000.00)"}
Lender Institution Condition        : {"PASS (Approved Financial Institution/Bank)" if eea_cond_lender else "FAIL"}
Section 80EE Exclusivity            : {"PASS (No Section 80EE claimed)" if not eea_claimed_80ee else "FAIL (Already claimed u/s 80EE)"}
Final Eligibility Result            : {"PASS (ELIGIBLE)" if sec_80eea > 0 else "FAIL (INELIGIBLE)"}
Rejection Reason                    : {"None (Conditions Met)" if sec_80eea > 0 else "Section 80EEA conditions not satisfied or not claimed."}


---------------- 5. 80EEA AMOUNT LIFECYCLE ----------------
declared_amount                     : INR {eea_declared:,.2f}
projected_amount                    : INR {eea_declared:,.2f}
residual_eligible_amount            : INR {residual_interest:,.2f}
statutory_80eea_cap                 : INR 150,000.00
capped_eligible_amount              : INR {sec_80eea:,.2f}
verified_amount                     : INR {eea_verified:,.2f}
hr_approved_amount                  : INR {eea_approved:,.2f}
usable_amount                       : INR {sec_80eea:,.2f}
final_selected_amount               : INR {sec_80eea:,.2f}
final_Chapter_VIA_amount            : INR {sec_80eea:,.2f}


---------------- 6. FINAL AGGREGATION ----------------
section_24b                         : INR {home_loan_allowed:,.2f}
section_80eea                       : INR {sec_80eea:,.2f}
total_chapter_6a_deductions         : INR {total_chapter_6a:,.2f}
total_deductions                    : INR {tot_deductions:,.2f}
taxable_income                      : INR {net_taxable_inc:,.2f}
annual_tax                          : INR {ann_tax_liab:,.2f}

---------------- CALCULATION SEQUENCE ----------------
Sequence: Total Interest (INR {home_loan_declared:,.2f}) → 24(b) (INR {home_loan_allowed:,.2f}) → Residual Interest (INR {residual_interest:,.2f}) → 80EEA Cap (INR 150,000.00) → Final 80EEA (INR {sec_80eea:,.2f})

=========================================================

[80EEA_END_TO_END_TRACE]
explicit_80eea_claim = {"YES" if has_eea_claim else "NO"}
sanction_date = {eea_sanction_date_str}
first_time_buyer = {"YES" if eea_first_buyer else "NO"}
property_value = INR {eea_stamp_val:,.2f}
lender_type = {eea_lender_type}
section_24b_original_interest = INR {home_loan_declared:,.2f}
section_24b_final_amount = INR {home_loan_allowed:,.2f}
section_80eea_residual_interest = INR {residual_interest:,.2f}
section_80eea_declared_amount = INR {eea_declared:,.2f}
section_80eea_statutory_cap = INR 150,000.00
eligible_amount = INR {eea_eligible_base:,.2f}
approved_amount = INR {sec_80eea:,.2f}
final_80eea_amount = INR {sec_80eea:,.2f}
final_chapter6a_amount = INR {sec_80eea:,.2f}
calculation_sequence = Total Interest (INR {home_loan_declared:,.2f}) → 24(b) (INR {home_loan_allowed:,.2f}) → Residual Interest (INR {residual_interest:,.2f}) → 80EEA Cap (INR 150,000.00) → Final 80EEA (INR {sec_80eea:,.2f})
section24b = INR {home_loan_allowed:,.2f}
total_deductions = INR {tot_deductions:,.2f}
taxable_income = INR {net_taxable_inc:,.2f}
annual_tax = INR {ann_tax_liab:,.2f}
=========================================================
"""
            _logger.warning(trace_80eea_full)

            _logger.warning("""[TDS_DEBUG_TRACE][80EEA_CALCULATION_AUDIT]
TOTAL_INTEREST=%s
FINAL_24B_AMOUNT=%s
RESIDUAL_INTEREST_FOR_80EEA=%s
80EEA_DECLARED_AMOUNT=%s
80EEA_STATUTORY_CAP=150000.00
80EEA_ELIGIBILITY_RESULT=%s
FINAL_80EEA_AMOUNT=%s
FINAL_CHAPTER_VIA_80EEA=%s""",
                f"INR {home_loan_declared:,.2f}",
                f"INR {home_loan_allowed:,.2f}",
                f"INR {residual_interest:,.2f}",
                f"INR {eea_declared:,.2f}",
                "ELIGIBLE" if sec_80eea > 0 else ("INELIGIBLE" if not has_eea_claim else "ZERO_RESIDUAL"),
                f"INR {sec_80eea:,.2f}",
                f"INR {sec_80eea:,.2f}"
            )

            # 13. SHOW MONTHLY TDS CALCULATION
            mth = res.monthly_tds_distribution
            rem_periods = mth.remaining_payroll_periods or 1
            rem_liab = mth.remaining_annual_tax_liability
            raw_mth_tds = rem_liab / rem_periods if rem_periods else 0.0

            eval_m_n = eval_date.month if hasattr(eval_date, 'month') else 4
            eval_fy_i = eval_m_n - 3 if eval_m_n >= 4 else eval_m_n + 9
            m_names_d = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
                         7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            curr_m_name = m_names_d.get(eval_m_n, str(eval_m_n))
            c_m_cnt = max(0, eval_fy_i - 1)
            f_m_cnt = max(0, 12 - eval_fy_i)

            _logger.warning("""[TDS_DEBUG_TRACE][PAYROLL_MONTH_CONTEXT]
completed_payroll_months=%s
current_payroll_month=%s
future_payroll_months=%s
tds_distribution_months=%s""",
                c_m_cnt, curr_m_name, f_m_cnt, rem_periods
            )

            _logger.warning("""[TDS_DEBUG_TRACE] MONTHLY_TDS
annual_tax_liability=%s
months_remaining=%s
previous_tds_deducted=%s
current_month_tds_before_rounding=%s
current_month_tds=%s""",
                ann_tax_liab, rem_periods, mth.total_tds_paid_so_far,
                raw_mth_tds, mth.current_month_tds
            )

            # 14. IMPORTANT: TRACE PREVIOUS TDS
            prev_payslip_cnt = sal_proj.months_elapsed - 1 if sal_proj.months_elapsed > 0 else 0
            _logger.warning("""[TDS_DEBUG_TRACE] PREVIOUS_TDS
previous_payslip_count=%s
previous_tds=%s
annual_tax_liability=%s
balance_tax=%s
months_remaining=%s""",
                prev_payslip_cnt, mth.total_tds_paid_so_far, ann_tax_liab,
                rem_liab, rem_periods
            )

            # 15. TRACE THE EXACT RETURN
            _logger.warning("""[TDS_DEBUG_TRACE] RETURN
total_annual_tax_liability=%s
current_month_tds=%s""", ann_tax_liab, res.current_month_tds)

            _logger.warning("HDS_IN_TDS TRACE | Inside HrPayslip.hds_in_compute_tds() | total_annual_tax_liability: %s, returning res.current_month_tds: %s", getattr(getattr(res, 'health_education_cess', None), 'total_annual_tax_liability', 'N/A'), res.current_month_tds)

        financial_year = self.env['tds.financial.year'].search([
            ('start_date', '<=', eval_date),
            ('end_date', '>=', eval_date)
        ], limit=1)
        fy_name = financial_year.name if financial_year else 'N/A'
        calc_run_id = getattr(res, 'calculation_run_id', None) or self.env.context.get('tds_calc_run_id', 'N/A')

        stored_sched = self.env['tds.recalculation.schedule'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('financial_year_id', '=', financial_year.id)
        ], order='id desc', limit=1) if financial_year else False

        fresh_ann_tax = float(res.total_annual_tax_liability or 0.0)
        prev_ann_tax = float(getattr(res, 'previous_annual_tax', None) if getattr(res, 'previous_annual_tax', None) is not None else (stored_sched.recalculated_annual_tax if stored_sched else fresh_ann_tax))
        tax_diff = fresh_ann_tax - prev_ann_tax

        mth_dist = getattr(res, 'monthly_tds_distribution', None)
        ytd_tds_val = float(getattr(mth_dist, 'total_tds_paid_so_far', 0.0) or getattr(mth_dist, 'ytd_tds_deducted', 0.0) or 0.0) if mth_dist else 0.0
        rem_tax_val = float(getattr(mth_dist, 'remaining_annual_tax_liability', 0.0) or 0.0) if mth_dist else 0.0
        rem_months_val = int(getattr(mth_dist, 'remaining_payroll_periods', 0) or 0) if mth_dist else 0
        monthly_tds_val = float(res.current_month_tds or 0.0)
        hra_exemption_val = float(getattr(getattr(res, 'deduction_calculation', None), 'hra_exemption', 0.0) or 0.0)

        _logger.warning("""[TDS_ANNUAL_RECALC_AUDIT]
payslip_id=%s
calculation_run_id=%s
previous_annual_tax=%s
fresh_annual_tax=%s
tax_difference=%s
ytd_tds=%s
remaining_tax=%s
remaining_months=%s
monthly_tds=%s
hra_exemption_received_by_annual_tax=%s
final_tds=%s""",
            self.id,
            calc_run_id,
            f"INR {prev_ann_tax:,.2f}",
            f"INR {fresh_ann_tax:,.2f}",
            f"INR {tax_diff:,.2f}",
            f"INR {ytd_tds_val:,.2f}",
            f"INR {rem_tax_val:,.2f}",
            rem_months_val,
            f"INR {monthly_tds_val:,.2f}",
            f"INR {hra_exemption_val:,.2f}",
            f"INR {monthly_tds_val:,.2f}"
        )

        _logger.warning("""[FINAL_TDS_TRACE]
calculation_run_id=%s
payslip_id=%s
payslip_name=%s
evaluation_date=%s
financial_year=%s
final_HDS_IN_TDS=%s""",
            calc_run_id,
            self.id,
            self.name,
            eval_date,
            fy_name,
            f"INR {res.current_month_tds:,.2f}"
        )

        eval_ctx = localdict or self._get_payroll_eval_context(raise_if_missing=False)
        final_tds = float(res.current_month_tds or 0.0)
        if eval_ctx and 'categories' in eval_ctx:
            cats = eval_ctx['categories']
            net_before_tds = (getattr(cats, 'BASIC', 0.0) or 0.0) + (getattr(cats, 'ALW', 0.0) or 0.0) + (getattr(cats, 'DED', 0.0) or 0.0)
            if net_before_tds <= 0.0:
                final_tds = 0.0
            elif final_tds > net_before_tds:
                _logger.info(
                    "[TDS_NET_CAP] Capping monthly TDS from ₹%.2f to net payable ₹%.2f for payslip %s",
                    final_tds, net_before_tds, self.name or self.id
                )
                final_tds = max(0.0, net_before_tds)

        result = -final_tds
        _logger.warning(
            "[TDS_EXIT_AUDIT] hds_in_compute_tds EXIT | payslip=%s | final_tds=%s",
            self.id,
            result,
        )

        return result

    def action_print_statutory_report(self):
        """
        Renders Statutory Tax Calculation Report and opens the interactive online viewer modal.
        Provides direct download and print options inside the viewer modal.
        """
        self.ensure_one()
        company = self.company_id or self.employee_id.company_id or self.env.company
        if not company.hds_in_tds_applicable:
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled in Company Settings."))
        if not getattr(self.employee_id, 'hds_in_tds_applicable', False):
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled for employee '%s'.") % (self.employee_id.name or ''))

        import base64
        pdf_bytes, report_format = self.env['ir.actions.report']._render_qweb_pdf(
            'hudson_in_payroll.action_report_statutory_tax_payslip', [self.id]
        )
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        filename = f"Tax_Calculation_Report_{self.employee_id.name or 'Employee'}_{self.date_to or ''}.pdf"

        wizard = self.env['hds.tax.report.viewer.wizard'].create({
            'payslip_id': self.id,
            'employee_id': self.employee_id.id,
            'pdf_file': b64_pdf,
            'pdf_filename': filename,
        })

        return {
            'name': _("Tax Calculation Report - %s") % (self.employee_id.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'hds.tax.report.viewer.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def action_download_statutory_report(self):
        """
        Direct download action for the Statutory Tax Calculation Report PDF.
        """
        self.ensure_one()
        company = self.company_id or self.employee_id.company_id or self.env.company
        if not company.hds_in_tds_applicable:
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled in Company Settings."))
        if not getattr(self.employee_id, 'hds_in_tds_applicable', False):
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled for employee '%s'.") % (self.employee_id.name or ''))
        return self.env.ref('hudson_in_payroll.action_report_statutory_tax_payslip').report_action(self)

    def get_tds_summary(self):
        """
        Helper method for standard Payslip PDF Report to retrieve the exact
        TDS calculation summary for this payslip using its date_to evaluation date.
        Reuses the master TDS Orchestration Engine result.
        """
        self.ensure_one()
        rep_provider = self.env['report.hudson_in_payroll.report_statutory_tax_calculation']
        res_dict = rep_provider.with_context(active_model='hr.payslip')._get_report_values([self.id], data={'model_name': 'hr.payslip'})
        reports = res_dict.get('reports', [])
        if reports:
            return reports[0]
        return {}



    # -------------------------------------------------------------------------
    # OVERRIDDEN GET_PAYSLIP_LINES
    # -------------------------------------------------------------------------
    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        """
        Overridden to inject domain services and real hr.payslip record into localdict.
        """
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = (
                localdict['categories'].dict[category.code] + amount
                if category.code in localdict['categories'].dict else amount
            )
            return localdict

        class DummyInput(object):
            amount = 0.0
            number_of_days = 0.0
            number_of_hours = 0.0
            total = 0.0
            rate = 0.0
            quantity = 0.0

            def __float__(self):
                return 0.0

            def __int__(self):
                return 0

            def __bool__(self):
                return False

            def __repr__(self):
                return "0.0"

            def __str__(self):
                return "0.0"

            def __abs__(self):
                return 0.0

            def __neg__(self):
                return 0.0

            def __pos__(self):
                return 0.0

            def __add__(self, other):
                return float(other) if isinstance(other, (int, float)) else other

            def __radd__(self, other):
                return float(other) if isinstance(other, (int, float)) else other

            def __sub__(self, other):
                return -float(other) if isinstance(other, (int, float)) else 0.0

            def __rsub__(self, other):
                return float(other) if isinstance(other, (int, float)) else 0.0

            def __mul__(self, other):
                return 0.0

            def __rmul__(self, other):
                return 0.0

            def __truediv__(self, other):
                return 0.0

            def __rtruediv__(self, other):
                return 0.0

            def __eq__(self, other):
                if isinstance(other, DummyInput):
                    return True
                if isinstance(other, (int, float)):
                    return float(other) == 0.0
                return not bool(other)

            def __lt__(self, other):
                val = float(other) if isinstance(other, (int, float)) else 0.0
                return 0.0 < val

            def __le__(self, other):
                val = float(other) if isinstance(other, (int, float)) else 0.0
                return 0.0 <= val

            def __gt__(self, other):
                val = float(other) if isinstance(other, (int, float)) else 0.0
                return 0.0 > val

            def __ge__(self, other):
                val = float(other) if isinstance(other, (int, float)) else 0.0
                return 0.0 >= val

            def __getattr__(self, attr):
                return self

            def __call__(self, *args, **kwargs):
                return self

        class BrowsableObject(object):
            def __init__(self, employee_id, dict_val, env):
                self.employee_id = employee_id
                self.dict = dict_val
                self.env = env
                self.amount = 0.0

            def get(self, attr, default=None):
                if isinstance(self.dict, dict):
                    return self.dict.get(attr, default)
                return getattr(self.dict, attr, default)

            def keys(self):
                if isinstance(self.dict, dict):
                    return self.dict.keys()
                return []

            def values(self):
                if isinstance(self.dict, dict):
                    return self.dict.values()
                return []

            def items(self):
                if isinstance(self.dict, dict):
                    return self.dict.items()
                return []

            def __contains__(self, attr):
                if isinstance(self.dict, dict):
                    return attr in self.dict
                return hasattr(self.dict, attr)

            def __getitem__(self, attr):
                if isinstance(self.dict, dict):
                    return self.dict.get(attr, DummyInput())
                return getattr(self.dict, attr, DummyInput())

            def __getattr__(self, attr):
                if isinstance(self.dict, dict):
                    return self.dict.get(attr, DummyInput())
                return getattr(self.dict, attr, DummyInput())

        class InputLine(BrowsableObject):
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                    FROM hr_payslip as hp, hr_payslip_line as pl
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        payslip = self.env['hr.payslip'].browse(payslip_id)

        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict, self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        baselocaldict = {
            'categories': categories,
            'rules': rules,
            'payslip': payslips,
            'worked_days': worked_days,
            'inputs': inputs
        }

        contracts = self.env['hr.version'].browse(contract_ids)
        if payslip.struct_id:
            structure_ids = list(set(payslip.struct_id._get_parent_structure().ids))
        elif len(contracts) == 1 and contracts.struct_id:
            structure_ids = list(set(contracts.struct_id._get_parent_structure().ids))
        else:
            structure_ids = contracts.get_all_structures()

        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in sorted(rule_ids, key=lambda x: x[1])]
        sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)

        try:
            for contract in contracts:
                employee = contract.employee_id
                localdict = dict(baselocaldict, employee=employee, contract=contract)

                # INJECTION HOOK: Inject epf_service and payslip_record into localdict & store _eval_contexts
                localdict = payslip._get_statutory_context(localdict)

                for rule in sorted_rules:
                    key = rule.code + '-' + str(contract.id)
                    localdict['result'] = None
                    localdict['result_qty'] = 1.0
                    localdict['result_rate'] = 100

                    # Auto-heal legacy database TDS salary rule code if present
                    if rule.code == 'TDS' and rule.amount_python_compute and 'categories.GROSS or categories.ALW' in rule.amount_python_compute:
                        rule.sudo().write({
                            'amount_python_compute': """
bonus_line = payslip.env['hds.in.bonus.line'].search([('payslip_id', '=', payslip.id)], limit=1)
bonus_doc = bonus_line.bonus_id if bonus_line else False
gross_val = categories.GROSS if isinstance(categories.GROSS, (int, float)) else (categories.ALW if isinstance(categories.ALW, (int, float)) else 0.0)
if bonus_doc and bonus_doc.tax_treatment == 'exempt':
    result = 0.0
elif bonus_doc and bonus_doc.tax_treatment == 'partial':
    taxable_val = max(0.0, gross_val - (bonus_doc.tax_exempt_limit or 0.0))
    result = - (taxable_val * 0.10)
else:
    result = - (gross_val * 0.10)
"""
                        })

                    # Auto-heal HDS_IN_TDS salary rule in database if net_before_tds guard is missing
                    if rule.code == 'HDS_IN_TDS' and ('net_before_tds' not in (rule.amount_python_compute or '') or 'locals()' in (rule.amount_python_compute or '')):
                        rule.sudo().write({
                            'amount_python_compute': """net_before_tds = (categories.BASIC or 0.0) + (categories.ALW or 0.0) + (categories.DED or 0.0)
if net_before_tds <= 0.0:
    result = 0.0
else:
    result = payslip_record.hds_in_compute_tds()
"""
                        })

                    if rule._satisfy_condition(localdict) and rule.id not in blacklist:
                        amount, qty, rate = rule._compute_rule(localdict)

                        if rule.code in ('HDS_IN_TDS', 'TDS'):
                            _logger.warning("HDS_IN_TDS TRACE | Stage 3: Immediately after rule._compute_rule() | Rule Code: %s | amount: %s | qty: %s | rate: %s | tot_rule: %s", rule.code, amount, qty, rate, (amount * qty * rate / 100.0))

                        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                        tot_rule = (amount * qty * rate / 100.0)
                        localdict[rule.code] = tot_rule
                        rules_dict[rule.code] = rule
                        localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)

                        if rule.code in ('HDS_IN_TDS', 'TDS'):
                            _logger.warning("HDS_IN_TDS TRACE | Stage 4: Immediately before creating hr.payslip.line dict | Rule Code: %s | amount: %s | qty: %s | rate: %s", rule.code, amount, qty, rate)

                        result_dict[key] = {
                            'salary_rule_id': rule.id,
                            'contract_id': contract.id,
                            'name': rule.name,
                            'code': rule.code,
                            'category_id': rule.category_id.id,
                            'sequence': rule.sequence,
                            'appears_on_payslip': (True if rule.appears_on_payslip == 'always' else False if rule.appears_on_payslip == 'never' else bool(amount)),
                            'condition_select': rule.condition_select,
                            'condition_python': rule.condition_python,
                            'condition_range': rule.condition_range,
                            'condition_range_min': rule.condition_range_min,
                            'condition_range_max': rule.condition_range_max,
                            'amount_select': rule.amount_select,
                            'amount_fix': rule.amount_fix,
                            'amount_python_compute': rule.amount_python_compute,
                            'amount_percentage': rule.amount_percentage,
                            'amount_percentage_base': rule.amount_percentage_base,
                            'register_id': rule.register_id.id,
                            'amount': amount,
                            'employee_id': contract.employee_id.id,
                            'quantity': qty,
                            'rate': rate,
                        }

                        if rule.code in ('HDS_IN_TDS', 'TDS'):
                            _logger.warning("HDS_IN_TDS TRACE | Stage 5: Immediately after payslip line appended | Key: %s | line_dict: %s", key, result_dict[key])
                    else:
                        blacklist += [id for id, seq in rule._recursive_search_of_rules()]
        finally:
            # Clean up transient context after computation
            HrPayslip._eval_contexts.pop(payslip_id, None)

        return list(result_dict.values())

    # -------------------------------------------------------------------------
    # PRIVATE STATUTORY DELEGATION HELPERS
    # -------------------------------------------------------------------------
    def _get_payroll_eval_context(self, raise_if_missing=True):
        """
        Safely retrieves the transient evaluation context (_eval_context)
        bound during _get_payslip_lines execution.
        Raises UserError if executed outside active payslip sheet computation.
        """
        self.ensure_one()
        eval_ctx = HrPayslip._eval_contexts.get(self.id)
        if not eval_ctx and raise_if_missing:
            raise UserError(_(
                "Statutory calculation methods on 'hr.payslip' can only be executed "
                "during active payslip sheet computation."
            ))
        return eval_ctx

    def _delegate_statutory_service(self, service_class, compute_method_name, negate=False, localdict=None, **kwargs):
        """
        Generic DRY helper to instantiate statutory service facades with evaluation context
        and delegate computation cleanly without repeating validation logic.
        """
        import logging
        _logger = logging.getLogger(__name__)
        self.ensure_one()
        _logger.debug(">>> Delegating to: %s", service_class.__name__)
        eval_ctx = localdict or self._get_payroll_eval_context(raise_if_missing=(localdict is None))
        if eval_ctx:
            cats = eval_ctx.get('categories')
            gross_val = cats.GROSS if cats and hasattr(cats, 'GROSS') else None
            _logger.debug(">>> Localdict GROSS: %s", gross_val)

        service = service_class(self.env, localdict=eval_ctx)
        compute_fn = getattr(service, compute_method_name)
        result = compute_fn(self, **kwargs)
        _logger.debug(">>> PT Result Returned: %s", getattr(result, 'amount', result))
        amount = result.amount if hasattr(result, 'amount') else result
        return -amount if negate else amount

    # -------------------------------------------------------------------------
    # PUBLIC ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_is_epf_applicable(self):
        """Returns True if EPF master toggle is enabled at both Company and Employee levels."""
        emp = getattr(self, 'employee_id', False)
        if not emp or not getattr(emp, 'hds_in_epf_applicable', False):
            return False
        comp = getattr(self, 'company_id', False) or (emp and getattr(emp, 'company_id', False)) or self.env.company
        if comp and hasattr(comp, 'hds_in_epf_applicable') and not comp.hds_in_epf_applicable:
            return False
        return True

    def hds_in_compute_pf_wage(self, localdict=None):
        """Public API entrypoint for PF_WAGE Salary Rule (Zero arguments in XML, optional localdict for testing)."""
        return self._delegate_statutory_service(EPFService, 'compute_pf_wage', localdict=localdict)

    def hds_in_compute_employee_epf(self, localdict=None):
        """Public API entrypoint for Employee EPF Salary Rule (Zero arguments in XML, optional localdict for testing)."""
        return self._delegate_statutory_service(EPFService, 'compute_employee_epf', negate=True, localdict=localdict)

    def hds_in_compute_employer_epf(self, localdict=None):
        """Public API entrypoint for Employer EPF Contribution (12% of Contribution Wage). Zero arguments in XML, optional localdict for testing."""
        return self._delegate_statutory_service(EPFService, 'compute_employer_epf', localdict=localdict)

    def hds_in_compute_employer_total_pf(self, localdict=None):
        """Public API entrypoint for Total Employer PF Contribution (12% of Contribution Wage)."""
        return self._delegate_statutory_service(EPFService, 'compute_employer_total_pf', localdict=localdict)

    def hds_in_compute_employer_epf_share(self, localdict=None):
        """Public API entrypoint for Net Employer EPF Share (12% - EPS = ₹790)."""
        return self._delegate_statutory_service(EPFService, 'compute_employer_epf_share', localdict=localdict)

    def hds_in_compute_employer_eps(self):
        """Public API entrypoint for Employer Pension Scheme (EPS) Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(EPFService, 'compute_employer_eps')

    def hds_in_compute_employer_edli(self):
        """Public API entrypoint for Employer EDLI Contribution Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(EPFService, 'compute_employer_edli')

    def hds_in_compute_epf_admin(self):
        """Public API entrypoint for EPF Admin Charges Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(EPFService, 'compute_epf_admin')

    def hds_in_compute_edli_admin(self):
        """Public API entrypoint for EDLI Admin Charges Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(EPFService, 'compute_edli_admin')

    def hds_in_compute_epf_admin_charge(self):
        """Alias for hds_in_compute_epf_admin for backward compatibility."""
        return self.hds_in_compute_epf_admin()

    def hds_in_compute_edli_admin_charge(self):
        """Alias for hds_in_compute_edli_admin for backward compatibility."""
        return self.hds_in_compute_edli_admin()

    # -------------------------------------------------------------------------
    # PUBLIC ESIC ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_compute_esic_wage(self):
        """Public API entrypoint for ESIC_WAGE Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(ESICService, 'compute_esic_wage')

    def hds_in_compute_esic_employee(self):
        """Public API entrypoint for ESIC_EE Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(ESICService, 'compute_esic_employee', negate=True)

    def hds_in_compute_esic_employer(self):
        """Public API entrypoint for ESIC_ER Salary Rule (Zero arguments)."""
        return self._delegate_statutory_service(ESICService, 'compute_esic_employer')

    def _validate_company_state_statutory(self):
        """Validates that statutory work state is resolvable (via Work Address or Company Address)."""
        if self.env.context.get('install_mode') or self.env.context.get('test_enable'):
            return
        emp = self.employee_id
        if emp and emp.address_id and emp.address_id.state_id:
            return
        if emp and emp.work_location_id and emp.work_location_id.address_id and emp.work_location_id.address_id.state_id:
            return
        company = self.company_id or (emp.company_id if emp else self.env.company)
        if company and company.partner_id and company.partner_id.state_id:
            return
        # pyrefly: ignore [missing-import]
        from odoo.exceptions import ValidationError
        raise ValidationError(_(
            "Company State is not configured! Please configure the State in Company Address "
            "(Settings > Companies > Address) or Employee Work Address (Employees > Work Information) "
            "for employee '%(emp)s' to calculate statutory deductions.",
            emp=emp.name if emp else ''
        ))

    # -------------------------------------------------------------------------
    # PUBLIC LWF ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_compute_lwf_employee(self):
        """Public API entrypoint for LWF_EE Salary Rule (Zero arguments)."""
        company = self.company_id or (self.employee_id.company_id if self.employee_id else self.env.company)
        if not getattr(company, 'hds_in_enable_lwf', False):
            return 0.0
        if self.employee_id and hasattr(self.employee_id, 'hds_in_lwf_applicable') and not self.employee_id.hds_in_lwf_applicable:
            return 0.0
        emp_type_name = ''
        if self.employee_id:
            if getattr(self.employee_id, 'employee_type_id', False):
                emp_type_name = (self.employee_id.employee_type_id.name or '').lower()
            elif getattr(self.employee_id, 'employee_type', False):
                emp_type_name = str(self.employee_id.employee_type).lower()
        if any(term in emp_type_name for term in ('contract', 'freelance')):
            return 0.0
        self._validate_company_state_statutory()
        return self._delegate_statutory_service(LWFService, 'compute_lwf_employee', negate=True)

    def hds_in_compute_lwf_employer(self):
        """Public API entrypoint for LWF_ER Salary Rule (Zero arguments)."""
        company = self.company_id or (self.employee_id.company_id if self.employee_id else self.env.company)
        if not getattr(company, 'hds_in_enable_lwf', False):
            return 0.0
        if self.employee_id and hasattr(self.employee_id, 'hds_in_lwf_applicable') and not self.employee_id.hds_in_lwf_applicable:
            return 0.0
        emp_type_name = ''
        if self.employee_id:
            if getattr(self.employee_id, 'employee_type_id', False):
                emp_type_name = (self.employee_id.employee_type_id.name or '').lower()
            elif getattr(self.employee_id, 'employee_type', False):
                emp_type_name = str(self.employee_id.employee_type).lower()
        if any(term in emp_type_name for term in ('contract', 'freelance')):
            return 0.0
        self._validate_company_state_statutory()
        return self._delegate_statutory_service(LWFService, 'compute_lwf_employer')

    # -------------------------------------------------------------------------
    # PUBLIC GRATUITY ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_compute_gratuity(self):
        """
        Public API entrypoint for Gratuity Salary Rule (Zero arguments in XML).
        Computes Gross Gratuity Payable. If linked to a Final Settlement record,
        synchronizes directly from settlement.gratuity_gross_amount; otherwise
        delegates to GratuityService with return_gross=True.
        """
        company = self.company_id or (self.employee_id.company_id if self.employee_id else self.env.company)
        if not getattr(company, 'hds_in_enable_gratuity', False):
            return 0.0

        if 'final.settlement' in self.env:
            settlement = self.env['final.settlement'].search([
                ('payslip_id', '=', self.id),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if not settlement and self.employee_id:
                settlement = self.env['final.settlement'].search([
                    ('employee_id', '=', self.employee_id.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)
            if settlement and settlement.gratuity_gross_amount > 0.0:
                return float(settlement.gratuity_gross_amount)

        return self._delegate_statutory_service(GratuityService, 'compute_gratuity', return_gross=True)

    def hds_in_compute_tds_gratuity(self):
        """
        Public API entrypoint for TDS_GRATUITY Salary Rule (Zero arguments in XML).
        DEPRECATED / RETIRED: Standalone TDS on gratuity is retired under the unified
        annual tax architecture. Taxable gratuity is now consolidated into the annual
        taxable salary projection and computed via HDS_IN_TDS (Section 192).
        Returns 0.0 to prevent duplicate tax withholding.
        """
        return 0.0

    # -------------------------------------------------------------------------
    # PUBLIC PROFESSIONAL TAX ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_compute_professional_tax(self, localdict=None):
        """
        Public API entrypoint for Professional Tax (PT) Salary Rule (Zero arguments in XML).
        Delegates computation to ProfessionalTaxService via _delegate_statutory_service DRY helper.
        Thin orchestration layer containing zero business logic.
        """
        company = self.company_id or (self.employee_id.company_id if self.employee_id else self.env.company)
        if not getattr(company, 'hds_in_enable_professional_tax', False):
            return 0.0
        if self.employee_id and hasattr(self.employee_id, 'hds_in_pt_applicable') and not self.employee_id.hds_in_pt_applicable:
            return 0.0
        self._validate_company_state_statutory()
        return self._delegate_statutory_service(ProfessionalTaxService, 'compute_pt_amount', negate=True, localdict=localdict)

    def hds_in_compute_pt(self, localdict=None):
        """Alias for hds_in_compute_professional_tax for backward compatibility."""
        return self.hds_in_compute_professional_tax(localdict=localdict)

    # -------------------------------------------------------------------------
    # PUBLIC BONUS ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_compute_performance_bonus(self):
        """Public API entrypoint for PERF_BONUS Salary Rule (Zero arguments in XML)."""
        return self._delegate_statutory_service(BonusService, 'compute_performance_bonus')

    def hds_in_compute_retention_bonus(self):
        """Public API entrypoint for RETENTION_BONUS Salary Rule (Zero arguments in XML)."""
        return self._delegate_statutory_service(BonusService, 'compute_retention_bonus')

    # -------------------------------------------------------------------------
    # PUBLIC LEAVE ENCASHMENT ORCHESTRATION API FOR SALARY RULES (Zero Arguments in XML)
    # -------------------------------------------------------------------------
    def hds_in_has_approved_leave_encashment(self):
        """
        Zero-parameter XML helper to check for approved in-service encashment requests.
        Evaluated dynamically in salary rule condition.
        """
        self.ensure_one()
        if not self.employee_id or not self.company_id:
            return False
        if not getattr(self.company_id, 'hds_in_enable_leave_encashment', False):
            return False
        return bool(self.env['hds.leave.encashment.request'].search_count([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'approved'),
            ('request_date', '<=', self.date_to),
            ('payslip_id', 'in', (False, self.id)),
        ]))

    def hds_in_compute_in_service_leave_encashment(self, localdict=None):
        """
        Public API entrypoint for LEAVE_ENCASH Salary Rule.
        Delegates computation to LeaveEncashmentService.
        """
        from ..services.leave_encashment.leave_encashment_service import LeaveEncashmentService
        eval_ctx = localdict or self._get_payroll_eval_context(raise_if_missing=False) or {}
        if not eval_ctx:
            eval_ctx = {
                'payslip': self,
                'payslip_record': self,
                'employee': self.employee_id,
                'contract': self.contract_id or getattr(self.employee_id, 'version_id', False),
            }
        svc = LeaveEncashmentService(self.env, localdict=eval_ctx)
        return svc.compute_in_service_encashment(self)

    def hds_in_compute_exit_leave_encashment(self):
        """
        Public API entrypoint for Exit Leave Encashment on Final Settlement payslips.
        Delegates computation to LeaveEncashmentService.compute_leave_encashment.
        """
        self.ensure_one()
        from ..services.leave_encashment.leave_encashment_service import LeaveEncashmentService
        eval_ctx = self._get_payroll_eval_context(raise_if_missing=False) or {}
        if not eval_ctx:
            eval_ctx = {
                'payslip': self,
                'payslip_record': self,
                'employee': self.employee_id,
                'contract': self.contract_id or getattr(self.employee_id, 'version_id', False),
            }
        svc = LeaveEncashmentService(self.env, localdict=eval_ctx)
        return svc.compute_leave_encashment(
            employee=self.employee_id,
            payslip=self,
            last_working_day=self.date_to,
            contract=self.contract_id or getattr(self.employee_id, 'version_id', False)
        )


    # -------------------------------------------------------------------------
    # WAGE RESOLUTION HELPERS
    # -------------------------------------------------------------------------
    def _get_earned_wage_ratio(self, localdict=None):
        """
        Computes the ratio of earned wages to master wages (0.0 to 1.0).

        With the Earned Proration model (pay_by_attendance=True):
          BASIC / HRA / DA are already prorated by (earned_hours / scheduled_hours)
          inside the salary rules. Returning 1.0 here prevents statutory components
          (EPF, ESIC, PT) from double-prorating an already-reduced figure.

        Without pay_by_attendance (fixed-salary + unpaid-leave deduction):
          Uses legacy logic — ratio is derived from unpaid leave deductions vs total earnings.
        """
        self.ensure_one()
        ld = localdict or self._get_payroll_eval_context(raise_if_missing=False) or {}
        contract = ld.get('contract') or self.contract_id

        # ── Earned Proration / Attendance Threshold Model ───────────────────────
        # When pay_by_attendance is ON or Attendance Threshold is active, salary
        # components are already at their earned value (prorated). Statutory
        # calculations (PF/ESIC/PT) should simply multiply those earned amounts
        # × 1.0 — no further reduction needed to prevent double reduction.
        if getattr(contract, 'pay_by_attendance', False) or getattr(contract, 'enable_attendance_threshold', True):
            return 1.0

        # ── Fixed salary + LOP model ────────────────────────────────────────────
        # For contracts without pay_by_attendance, the only deductions that could
        # reduce the statutory base are formal Unpaid (LOP) leave entries.
        # We compute ratio = 1 - (unpaid_deduction / total_earnings).
        categories = ld.get('categories')
        worked_days = ld.get('worked_days')

        total_earnings = 0.0
        if categories:
            total_earnings = float(getattr(categories, 'GROSS', 0.0) or 0.0)
            if total_earnings <= 0.0:
                total_earnings = float(getattr(categories, 'BASIC', 0.0) or 0.0) + float(getattr(categories, 'ALW', 0.0) or 0.0)
        if total_earnings <= 0.0 and contract:
            total_earnings = float(getattr(contract, 'wage', 0.0) or 0.0)

        unpaid_ded = abs(float(ld.get('UNPAID') or 0.0))

        if unpaid_ded <= 0.0 and worked_days and contract and hasattr(worked_days, 'UNPAID') and worked_days.UNPAID:
            unpaid_hrs = float(getattr(worked_days.UNPAID, 'number_of_hours', 0.0) or 0.0)
            unpaid_days = float(getattr(worked_days.UNPAID, 'number_of_days', 0.0) or 0.0)
            if unpaid_hrs > 0.0 and hasattr(contract, 'get_period_shortage_rate'):
                rate = abs(contract.get_period_shortage_rate(self.date_from, self.date_to))
                unpaid_ded = min(unpaid_hrs * rate, total_earnings)
            elif unpaid_days > 0.0 and hasattr(contract, 'get_period_day_rate'):
                rate = abs(contract.get_period_day_rate(self.date_from, self.date_to))
                unpaid_ded = min(unpaid_days * rate, total_earnings)

        if unpaid_ded <= 0.0 and self.worked_days_line_ids and contract:
            u_wd = self.worked_days_line_ids.filtered(lambda w: w.code == 'UNPAID')
            if u_wd:
                unpaid_hrs = sum(u_wd.mapped('number_of_hours'))
                unpaid_days = sum(u_wd.mapped('number_of_days'))
                if unpaid_hrs > 0.0 and hasattr(contract, 'get_period_shortage_rate'):
                    rate = abs(contract.get_period_shortage_rate(self.date_from, self.date_to))
                    unpaid_ded = min(unpaid_hrs * rate, total_earnings)
                elif unpaid_days > 0.0 and hasattr(contract, 'get_period_day_rate'):
                    rate = abs(contract.get_period_day_rate(self.date_from, self.date_to))
                    unpaid_ded = min(unpaid_days * rate, total_earnings)

        if unpaid_ded <= 0.0 and self.line_ids:
            u_line = self.line_ids.filtered(lambda l: l.code == 'UNPAID')
            if u_line:
                unpaid_ded = abs(sum(u_line.mapped('total')))

        if total_earnings > 0.0 and unpaid_ded > 0.0:
            if unpaid_ded >= (total_earnings - 0.5):
                return 0.0
            return max(0.0, min(1.0, (total_earnings - unpaid_ded) / total_earnings))

        return 1.0

    def hds_in_get_actual_pf_wage(self, localdict=None):
        """
        Calculates actual PF-eligible wage by summing components with hds_in_include_in_pf_wage = True,
        scaled by the earned wage ratio (factoring in attendance shortage and unpaid leaves).
        Does NOT read localdict['PF_WAGE'] to prevent circular dependency.
        """
        import logging
        _logger = logging.getLogger(__name__)

        self.ensure_one()
        ld = localdict or self._get_payroll_eval_context(raise_if_missing=False)
        if ld and ld.get('PF_WAGE') is not None and float(ld.get('PF_WAGE', 0.0) or 0.0) > 0.0:
            return float(ld['PF_WAGE'])

        pf_wage = 0.0

        # Scope rules strictly to current salary structure when available
        struct = self.struct_id or (self.contract_id and self.contract_id.struct_id)
        if struct:
            pf_rules = struct.get_all_rules().filtered(
                lambda r: r.hds_in_include_in_pf_wage and r.active and r.code != 'PF_WAGE'
            )
        else:
            pf_rules = self.env['hr.salary.rule'].search([
                ('hds_in_include_in_pf_wage', '=', True),
                ('active', '=', True),
                ('code', '!=', 'PF_WAGE'),
            ])

        if ld:
            for rule in pf_rules:
                val = ld.get(rule.code)
                if val is None and isinstance(ld.get('rules'), dict):
                    rule_obj = ld['rules'].get(rule.code)
                    if hasattr(rule_obj, 'total'):
                        val = rule_obj.total
                    elif isinstance(rule_obj, dict):
                        val = rule_obj.get('total')
                amount = float(val or 0.0)
                _logger.info("PF Rule %s -> %s", rule.code, amount)
                pf_wage += amount
            ratio = self._get_earned_wage_ratio(localdict=ld)
            return round(pf_wage * ratio, 2)

        for line in self.line_ids:
            if line.salary_rule_id.hds_in_include_in_pf_wage and line.salary_rule_id.code != 'PF_WAGE':
                pf_wage += line.total

        ratio = self._get_earned_wage_ratio(localdict=ld)
        return round(pf_wage * ratio, 2)

    def get_pf_eligible_wage(self, localdict=None):
        """Alias for hds_in_get_actual_pf_wage for backwards compatibility."""
        return self.hds_in_get_actual_pf_wage(localdict=localdict)

    def hds_in_get_pf_contribution_wage(self, localdict=None):
        """Calculates employee's PF Contribution Wage for this payslip."""
        self.ensure_one()
        ld = localdict or self._get_payroll_eval_context(raise_if_missing=False)
        return EPFService(self.env, localdict=ld).wage_calc.get_pf_contribution_wage(self)

    def get_pf_contribution_wage(self, localdict=None):
        """Alias for hds_in_get_pf_contribution_wage for backwards compatibility."""
        return self.hds_in_get_pf_contribution_wage(localdict=localdict)

    hds_in_statutory_audit_count = fields.Integer(
        string="Audit Trail",
        compute='_compute_hds_in_statutory_audit_count'
    )

    def _compute_hds_in_statutory_audit_count(self):
        audit_data = self.env['hds.in.payroll.audit']._read_group(
            [('payslip_id', 'in', self.ids)],
            ['payslip_id'],
            ['__count']
        )
        mapped_data = {payslip.id: count for payslip, count in audit_data}
        for slip in self:
            slip.hds_in_statutory_audit_count = mapped_data.get(slip.id, 0)

    def action_view_statutory_audits(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hudson_in_payroll.hds_in_payroll_audit_action")
        action['domain'] = [('payslip_id', '=', self.id)]
        action['context'] = {'default_payslip_id': self.id, 'default_employee_id': self.employee_id.id}
        return action

    def action_compute_sheet(self):
        """Auto-sync BONUS input lines before computing salary rules."""
        for slip in self:
            if slip.state == 'draft' and slip.contract_id and slip.employee_id:
                bonus_lines = self.env['hds.in.bonus.line'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('bonus_id.payment_method', '=', 'monthly_payroll'),
                    ('bonus_id.state', 'in', ('manager_approved', 'hr_approved', 'approved', 'processed', 'paid')),
                    ('bonus_id.date_from', '<=', slip.date_to),
                    ('bonus_id.date_to', '>=', slip.date_from),
                    ('amount', '>', 0.0)
                ])
                for b_line in bonus_lines:
                    input_line = slip.input_line_ids.filtered(lambda i: i.code == 'BONUS')
                    if input_line:
                        input_line.write({'amount': b_line.amount, 'name': b_line.bonus_id.name})
                    else:
                        self.env['hr.payslip.input'].create({
                            'name': b_line.bonus_id.name,
                            'code': 'BONUS',
                            'amount': b_line.amount,
                            'payslip_id': slip.id,
                            'contract_id': slip.contract_id.id,
                            'date_from': slip.date_from,
                            'date_to': slip.date_to,
                        })
        try:
            res = super(HrPayslip, self).action_compute_sheet()
        finally:
            for slip in self:
                HrPayslip._eval_contexts.pop(slip.id, None)
        for slip in self:
            if slip.employee_id:
                decl = self.env['tds.employee.declaration'].search([
                    ('employee_id', '=', slip.employee_id.id)
                ], order='write_date desc, id desc', limit=1)
                if decl and decl.write_date:
                    slip._hds_in_last_computed_decl_write_date = decl.write_date
        return res

    def action_payslip_done(self):
        """
        Override action_payslip_done() to guard against redundant recomputation
        if payslip lines already exist and employee declaration has not changed.
        """
        for slip in self:
            if slip.has_no_running_contract:
                raise ValidationError(_("• No running contract"))
            needs_recompute = False
            if not slip.line_ids:
                needs_recompute = True
            else:
                if slip.employee_id:
                    decl = self.env['tds.employee.declaration'].search([
                        ('employee_id', '=', slip.employee_id.id)
                    ], order='write_date desc, id desc', limit=1)
                    if not decl:
                        needs_recompute = True
                    elif decl.write_date != slip._hds_in_last_computed_decl_write_date:
                        needs_recompute = True
                else:
                    needs_recompute = True

            if needs_recompute:
                slip.action_compute_sheet()

        res = super(HrPayslip, self).action_payslip_done()
        # Finalize and deduct Time Off for approved in-service leave encashment requests
        for slip in self:
            encash_requests = self.env['hds.leave.encashment.request'].search([
                ('payslip_id', '=', slip.id),
                ('state', '=', 'approved'),
            ])
            for req in encash_requests:
                req.action_finalize_payout(slip)

        return res

    def action_payslip_cancel(self):
        """Rollback in-service leave encashments when a payslip is cancelled."""
        for slip in self:
            encash_requests = self.env['hds.leave.encashment.request'].search([
                ('payslip_id', '=', slip.id),
                ('state', '=', 'paid'),
            ])
            for req in encash_requests:
                req.action_rollback_payout()
        return super(HrPayslip, self).action_payslip_cancel()

    def unlink(self):
        """Release any draft encashment requests held by deleted payslips."""
        self.env['hds.leave.encashment.request'].search([
            ('payslip_id', 'in', self.ids),
            ('state', '!=', 'paid'),
        ]).write({'payslip_id': False})
        return super(HrPayslip, self).unlink()

    def compute_sheet(self):
        """Alias for action_compute_sheet for backwards compatibility."""
        return self.action_compute_sheet()

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = super(HrPayslip, self).get_inputs(contracts, date_from, date_to)
        for contract in contracts:
            emp = contract.employee_id
            bonus_lines = self.env['hds.in.bonus.line'].search([
                ('employee_id', '=', emp.id),
                ('bonus_id.payment_method', '=', 'monthly_payroll'),
                ('bonus_id.state', 'in', ('manager_approved', 'hr_approved', 'approved', 'processed', 'paid')),
                '|',
                '&', ('bonus_id.date_from', '<=', date_to), ('bonus_id.date_to', '>=', date_from),
                '&', ('bonus_id.payment_date', '>=', date_from), ('bonus_id.payment_date', '<=', date_to),
                ('amount', '>', 0.0)
            ])
            for b_line in bonus_lines:
                existing = [i for i in res if i.get('code') == 'BONUS' and i.get('contract_id') == contract.id]
                if existing:
                    existing[0]['amount'] = b_line.amount
                    existing[0]['name'] = b_line.bonus_id.name
                else:
                    res.append({
                        'name': b_line.bonus_id.name,
                        'code': 'BONUS',
                        'amount': b_line.amount,
                        'contract_id': contract.id,
                        'date_from': date_from,
                        'date_to': date_to,
                    })
        return res

    def get_payslip_pdf_data(self):
        """
        Construct compact single-page PDF payslip data structure
        matching sample reference layout, without altering any payroll computations.
        """
        self.ensure_one()
        import calendar as _calendar
        emp = self.employee_id
        company = self.company_id

        # Month Year display
        month_str = self.date_to.strftime('%B %Y').upper() if self.date_to else ''

        # Employee Identification / Statutory Numbers
        emp_no = getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False) or f"EMP{emp.id:04d}"
        location = getattr(emp.work_location_id, 'name', False) or company.city or 'Main Office'

        # Joining Date: prefer employee's date_of_joining / date_start; fallback to contract
        joining_date = (
            getattr(emp, 'date_of_joining', False)
            or getattr(emp, 'joining_date', False)
            or getattr(emp, 'hds_in_doj', False)
            or (self.contract_id.date_start if self.contract_id else False)
        )

        # Date of Birth — uses sudo() to bypass hr.group_hr_user restriction
        dob = emp.sudo().birthday

        # Gender — In Odoo 19, gender moved from hr.employee to hr.version as field 'sex'
        # (displayed as "Gender" in UI). Use sudo() to bypass hr.group_hr_user restriction.
        _gender_map = {'male': 'Male', 'female': 'Female', 'other': 'Other'}
        gender_val = ''
        try:
            # Odoo 19: field is 'sex' on hr.version (the active contract version)
            version = getattr(emp, 'version_id', False)
            if version:
                gender_val = version.sudo().sex or ''
            # Fallback: older field 'gender' directly on hr.employee (Odoo 16/17)
            if not gender_val:
                gender_val = emp.sudo().gender or ''
        except Exception:
            gender_val = ''
        gender = _gender_map.get(gender_val, gender_val.title()) if gender_val else 'N/A'

        # Statutory Numbers — fetched from employee; fallback gracefully to '-'
        pan = getattr(emp, 'hds_in_pan', False) or getattr(emp, 'pan_no', False) or emp.identification_id or '-'
        aadhaar = getattr(emp, 'hds_in_aadhaar', False) or getattr(emp, 'aadhaar_no', False) or '-'
        epf_no = getattr(emp, 'hds_in_pf_member_id', False) or getattr(emp, 'hds_in_epf_number', False) or getattr(emp, 'pf_number', False) or '-'
        esic_no = getattr(emp, 'hds_in_esic_ip_number', False) or getattr(emp, 'hds_in_esic_number', False) or getattr(emp, 'esic_number', False) or '-'
        uan = getattr(emp, 'hds_in_uan', False) or getattr(emp, 'hds_in_epf_uan', False) or getattr(emp, 'uan', False) or '-'

        # Attendance / Worked Days - scheduled working days in the month (not calendar days 30/31)
        contract = self.contract_id or (emp.version_id if hasattr(emp, 'version_id') else False)
        std_days_val = 0.0
        if hasattr(self, '_get_attendance_vs_schedule') and contract and self.date_from and self.date_to:
            try:
                sched_data = self._get_attendance_vs_schedule(contract, self.date_from, self.date_to)
                std_days_val = sched_data.get('total_period_scheduled_days') or sched_data.get('scheduled_days', 0.0)
            except Exception:
                std_days_val = 0.0

        if not std_days_val and contract:
            std_days_val = float(getattr(contract, 'standard_working_days_per_month', 0.0) or 0.0)

        if not std_days_val and hasattr(self.env.company, 'standard_working_days_per_month'):
            std_days_val = float(getattr(self.env.company, 'standard_working_days_per_month', 0.0) or 0.0)

        if not std_days_val and self.date_from and self.date_to:
            cal = getattr(contract, 'resource_calendar_id', False) or getattr(emp, 'resource_calendar_id', False) or self.env.company.resource_calendar_id
            if cal:
                try:
                    tz_name = getattr(cal, 'tz', False) or 'UTC'
                    tz = pytz.timezone(tz_name)
                    dt_from = tz.localize(datetime.combine(self.date_from, time.min))
                    dt_to = tz.localize(datetime.combine(self.date_to, time.max))
                    hours = cal.get_work_hours_count(dt_from, dt_to, compute_leaves=False)
                    day_hours = getattr(cal, 'hours_per_day', 8.0) or 8.0
                    std_days_val = round(hours / day_hours, 1) if day_hours else 26.0
                except Exception:
                    std_days_val = 26.0
            else:
                std_days_val = 26.0
        elif not std_days_val:
            std_days_val = 26.0

        std_days = int(std_days_val) if float(std_days_val).is_integer() else round(std_days_val, 1)

        lop_days_raw = sum(
            w.number_of_days for w in self.worked_days_line_ids
            if (w.code or '').upper() in ('UNPAID', 'ABSENT', 'SHORTAGE', 'LOP', 'LEAVE_UNPAID')
        ) if self.worked_days_line_ids else 0.0
        lop_days = int(lop_days_raw) if float(lop_days_raw).is_integer() else round(lop_days_raw, 1)

        if hasattr(self, 'total_worked_days') and self.worked_days_line_ids:
            days_worked_raw = float(self.total_worked_days)
        elif self.worked_days_line_ids:
            work_days = sum(
                w.number_of_days for w in self.worked_days_line_ids
                if (w.code or '').upper() not in ('UNPAID', 'ABSENT', 'SHORTAGE', 'LOP', 'LEAVE_UNPAID')
            )
            days_worked_raw = max(0.0, work_days - lop_days_raw)
        else:
            days_worked_raw = float(std_days_val)
        days_worked = int(days_worked_raw) if float(days_worked_raw).is_integer() else round(days_worked_raw, 1)

        lop_rev_raw = sum(w.number_of_days for w in self.worked_days_line_ids if 'REV' in (w.code or '').upper()) if self.worked_days_line_ids else 0.0
        lop_rev_days = int(lop_rev_raw) if float(lop_rev_raw).is_integer() else round(lop_rev_raw, 1)

        # Payment Mode — fetched from payslip Many2one (populated from employee)
        mode_rec = self.hds_in_payment_mode or (emp.hds_in_payment_mode if emp else False)
        payment_mode = (mode_rec.name.upper() if mode_rec else 'BANK TRANSFER')
        is_cash_mode = mode_rec.is_cash if mode_rec else False

        # Bank Details — masked account number (show **** + last 4 digits only)
        if is_cash_mode:
            bank_name = 'N/A'
            acc_no = 'N/A'
        else:
            bank_acc = (
                getattr(emp, 'bank_account_id', False)
                or getattr(emp, 'primary_bank_account_id', False)
                or (emp.bank_account_ids[0] if getattr(emp, 'bank_account_ids', False) else False)
            )
            if not bank_acc:
                partner = getattr(emp, 'work_contact_id', False) or (
                    emp.user_id.partner_id if getattr(emp, 'user_id', False) else None
                )
                if partner and getattr(partner, 'bank_ids', False):
                    bank_acc = partner.bank_ids[0]

            bank_name = '-'
            if bank_acc:
                bank_name = (
                    getattr(bank_acc, 'bank_name', '')
                    or getattr(bank_acc, 'acc_holder_name', '')
                    or '-'
                )
            raw_acc = (getattr(bank_acc, 'account_number', False) or getattr(bank_acc, 'acc_number', '')) if bank_acc else ''
            # Mask: show only last 4 digits, rest replaced with asterisks
            if raw_acc and raw_acc != '-' and len(raw_acc) > 4:
                acc_no = '*' * (len(raw_acc) - 4) + raw_acc[-4:]
            elif raw_acc:
                acc_no = raw_acc
            else:
                acc_no = '-'

        # Earnings lines vs Deductions lines
        earnings_lines = []
        deductions_lines = []

        total_earnings = 0.0
        total_deductions = 0.0

        # Calculate YTD for each rule up to current date_to in current FY
        fy = self.env['tds.financial.year'].search([
            ('start_date', '<=', self.date_to or fields.Date.today()),
            ('end_date', '>=', self.date_to or fields.Date.today())
        ], limit=1)

        ytd_domain = [
            ('employee_id', '=', emp.id),
            ('state', 'in', ('done', 'paid')),
            ('date_to', '<=', self.date_to)
        ]
        if fy:
            ytd_domain.extend([('date_from', '>=', fy.start_date), ('date_to', '<=', fy.end_date)])
        past_slips = self.env['hr.payslip'].search(ytd_domain)

        ytd_map = {}
        for ps in past_slips:
            for l in ps.line_ids:
                code = (l.code or '').upper()
                ytd_map[code] = ytd_map.get(code, 0.0) + abs(float(l.total or 0.0))

        pf_wage = 0.0
        for line in self.line_ids.filtered(lambda l: l.appears_on_payslip):
            code = (line.code or '').upper()
            cat_code = (line.category_id.code or '').upper() if line.category_id else ''
            amt = float(line.total or 0.0)

            # Skip calculation base rules (PF_WAGE, PF_CALC, ESI_CALC), gross, net, comp from earnings/deductions
            if cat_code in ('GROSS', 'NET', 'COMP', 'PF_CALC', 'ESI_CALC', 'CALC') or code in ('PF_WAGE', 'PF_CALC', 'ESI_WAGE', 'GROSS', 'NET'):
                if code == 'PF_WAGE' or cat_code == 'PF_CALC':
                    pf_wage = abs(amt)
                continue

            # Suppress zero-amount lines: if amount is 0, do not show in the payslip
            if abs(round(amt, 2)) <= 0.001:
                continue

            ytd_amt = ytd_map.get(code, abs(amt))

            if cat_code in ('DED', 'TDS') or amt < 0:
                abs_amt = abs(amt)
                deductions_lines.append({
                    'name': line.name,
                    'code': code,
                    'amount': abs_amt,
                    'ytd': ytd_amt
                })
                total_deductions += abs_amt
            else:
                earnings_lines.append({
                    'name': line.name,
                    'code': code,
                    'amount': amt,
                    'ytd': ytd_amt
                })
                total_earnings += amt

        # Ensure gross and net match official gross and net salary rules
        gross_rule_line = self.line_ids.filtered(lambda l: (l.code or '').upper() == 'GROSS')
        if gross_rule_line:
            total_earnings = float(gross_rule_line[0].total or total_earnings)

        net_rule_line = self.line_ids.filtered(lambda l: (l.code or '').upper() == 'NET')
        if net_rule_line:
            net_salary = float(net_rule_line[0].total or 0.0)
        else:
            net_salary = float(self.net_amount or (total_earnings - total_deductions))

        # TDS Applicability: Reflect TDS information ONLY for employees who have the TDS checkbox enabled
        company = self.company_id or self.env.company
        show_tds_block = bool(
            getattr(company, 'hds_in_tds_applicable', False)
            and getattr(emp, 'hds_in_tds_applicable', False)
        )

        if not show_tds_block:
            tds_res = None
            tax_rows = []
            tax_comp_income = []
            tax_comp_deductions = []
            total_tax_deductions = 0.0
            gti_annual = 0.0
            gti_exempt = 0.0
            gti_taxable = 0.0
            net_taxable_income = 0.0
            base_tax = 0.0
            tax_after_rebate = 0.0
            rebate_applied = 0.0
            surcharge_rate = 0.0
            surcharge_amount = 0.0
            surcharge_before_relief = 0.0
            marginal_relief = 0.0
            is_surcharge_applicable = False
            tax_plus_surcharge = 0.0
            cess_val = 0.0
            total_annual_tax = 0.0
            current_month_tds = 0.0
            prev_employer_tds_pdf = 0.0
            tds_recovered_ytd = 0.0
            remaining_tds_liability = 0.0
            remaining_months = 0
            projected_monthly_tds = 0.0
            investments = []
            hra_declarations = []
            decl = None
            regime_code = ''
            regime_display = 'N/A'
            regime_header = ''
        else:
            # TDS Engine Data Lookup
            eval_date = self.date_to or fields.Date.today()
            tds_engine = TdsOrchestrationEngine(self.env)
            tds_res = tds_engine.hds_in_compute_tds(emp, eval_date=eval_date, payslip=self)

            # Tax calculation breakdown values
            proj = tds_res.annual_income_projection
            sal_proj = getattr(proj, 'salary_projection', None)
            prev_emp = getattr(proj, 'previous_employer_income', None)
            oth_inc = getattr(proj, 'other_income_aggregation', None)
            deduct = tds_res.deduction_calculation
            tax_inc = tds_res.taxable_income
            slab = tds_res.income_tax_slab
            rebate = tds_res.rebate_engine
            surcharge = tds_res.surcharge_engine
            cess_obj = tds_res.health_education_cess
            monthly_obj = tds_res.monthly_tds_distribution

            contract = self.contract_id or (emp.version_id if hasattr(emp, 'version_id') else False)
            from ..services.tds.payroll_period_service import PayrollPeriodService
            from ..services.tds.previous_employer_income_service import PreviousEmployerIncomeService
            period_svc = PayrollPeriodService(self.env)
            # Pass eval_date so mid-year joiners with Form 12B get correct period count (not 12)
            total_fy_months = period_svc.calculate_total_periods_in_fy(emp, fy, eval_date=eval_date)
            rem_periods_count = period_svc.calculate_remaining_periods(emp, fy, eval_date=eval_date)

            # Resolve previous employer income (salary + TDS) for PDF display.
            prev_emp_svc = PreviousEmployerIncomeService(self.env)
            prev_emp_res_pdf = prev_emp_svc.aggregate_previous_employer_income(emp, fy) if fy else None
            prev_employer_salary_pdf = float(getattr(prev_emp_res_pdf, 'taxable_salary', 0.0) or 0.0) if prev_emp_res_pdf else 0.0
            prev_employer_tds_pdf = float(getattr(prev_emp_res_pdf, 'tds_deducted', 0.0) or 0.0) if prev_emp_res_pdf else 0.0

            rem_months = getattr(sal_proj, 'months_remaining', max(0, rem_periods_count - 1))

            b_tot = getattr(sal_proj, 'total_basic', 0.0) if sal_proj else 0.0
            if b_tot == 0.0 and contract:
                b_tot = ytd_map.get('BASIC', 0.0) + (float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0) * total_fy_months)

            hra_tot = getattr(sal_proj, 'total_hra', 0.0) if sal_proj else 0.0
            hra_ex = getattr(deduct, 'hra_exemption', 0.0) if deduct else 0.0

            da_tot = getattr(sal_proj, 'total_da', 0.0) if sal_proj else 0.0
            if da_tot == 0.0 and contract and getattr(contract, 'da', 0.0):
                da_tot = ytd_map.get('DA', 0.0) + (float(getattr(contract, 'da', 0.0) or 0.0) * total_fy_months)

            lta_tot = getattr(sal_proj, 'total_lta', 0.0) if sal_proj else 0.0
            lta_ex = getattr(deduct, 'lta_exemption', 0.0) if deduct else 0.0

            def _get_projected_component(code, field_name):
                monthly_val = float(getattr(contract, field_name, 0.0) or 0.0) if contract and hasattr(contract, field_name) else 0.0
                line = self.line_ids.filtered(lambda l: (l.code or '').upper() == code)
                curr_val = float(line[0].total or 0.0) if line else monthly_val
                ytd_val = ytd_map.get(code, 0.0)
                if self.state in ('done', 'paid'):
                    val = ytd_val + (monthly_val * rem_months)
                else:
                    val = ytd_val + curr_val + (monthly_val * max(0, rem_months - 1))
                if not past_slips and self.state not in ('done', 'paid'):
                    val = monthly_val * total_fy_months
                return max(0.0, val)

            fixed_tot = _get_projected_component('FIXED', 'fixed_allowance')
            std_tot = _get_projected_component('STD_ALW', 'standard_allowance')
            perf_tot = _get_projected_component('PERF_BONUS', 'performance_bonus')
            ret_tot = _get_projected_component('RETENTION_BONUS', 'retention_bonus')
            conv_tot = getattr(sal_proj, 'total_conveyance', 0.0) if sal_proj else _get_projected_component('CONV', 'travel_allowance')
            med_tot = getattr(sal_proj, 'total_medical', 0.0) if sal_proj else _get_projected_component('MED', 'medical_allowance')
            meal_tot = _get_projected_component('MEAL', 'meal_allowance')
            phone_tot = _get_projected_component('BENEFIT_PHONE', 'benefit_phone')
            internet_tot = _get_projected_component('BENEFIT_INTERNET', 'benefit_internet')
            meal_voucher_tot = _get_projected_component('BENEFIT_MEAL', 'benefit_meal_vouchers')
            transport_tot = _get_projected_component('BENEFIT_TRANSPORT', 'benefit_transport')

            tax_comp_income = []
            if b_tot > 0:
                tax_comp_income.append({'head': 'Basic Salary', 'annual': b_tot, 'exempt': 0.0, 'taxable': b_tot})
            if hra_tot > 0:
                tax_comp_income.append({'head': 'House Rent Allowance', 'annual': hra_tot, 'exempt': hra_ex, 'taxable': max(0.0, hra_tot - hra_ex)})

            if da_tot > 0:
                tax_comp_income.append({'head': 'Dearness Allowance', 'annual': da_tot, 'exempt': 0.0, 'taxable': da_tot})
            if fixed_tot > 0:
                tax_comp_income.append({'head': 'Fixed Allowance', 'annual': fixed_tot, 'exempt': 0.0, 'taxable': fixed_tot})
            if std_tot > 0:
                tax_comp_income.append({'head': 'Standard Allowance', 'annual': std_tot, 'exempt': 0.0, 'taxable': std_tot})
            if lta_tot > 0:
                tax_comp_income.append({'head': 'Leave Travel Allowance', 'annual': lta_tot, 'exempt': lta_ex, 'taxable': max(0.0, lta_tot - lta_ex)})
            if perf_tot > 0:
                tax_comp_income.append({'head': 'Performance Bonus', 'annual': perf_tot, 'exempt': 0.0, 'taxable': perf_tot})
            if ret_tot > 0:
                tax_comp_income.append({'head': 'Retention Bonus', 'annual': ret_tot, 'exempt': 0.0, 'taxable': ret_tot})
            if conv_tot > 0:
                tax_comp_income.append({'head': 'Conveyance Allowance', 'annual': conv_tot, 'exempt': 0.0, 'taxable': conv_tot})
            if med_tot > 0:
                tax_comp_income.append({'head': 'Medical Allowance', 'annual': med_tot, 'exempt': 0.0, 'taxable': med_tot})
            if meal_tot > 0:
                tax_comp_income.append({'head': 'Meal Allowance', 'annual': meal_tot, 'exempt': 0.0, 'taxable': meal_tot})
            if phone_tot > 0:
                tax_comp_income.append({'head': 'Phone Subscription', 'annual': phone_tot, 'exempt': 0.0, 'taxable': phone_tot})
            if internet_tot > 0:
                tax_comp_income.append({'head': 'Internet Subscription', 'annual': internet_tot, 'exempt': 0.0, 'taxable': internet_tot})
            if meal_voucher_tot > 0:
                tax_comp_income.append({'head': 'Meal Vouchers', 'annual': meal_voucher_tot, 'exempt': 0.0, 'taxable': meal_voucher_tot})
            if transport_tot > 0:
                tax_comp_income.append({'head': 'Company Transport', 'annual': transport_tot, 'exempt': 0.0, 'taxable': transport_tot})

            # In-Service Leave Encashment (Taxable salary earnings under Income-tax Act, 2025)
            leave_encash_tot = float(getattr(sal_proj, 'total_leave_encashment', 0.0) or 0.0) if sal_proj else 0.0
            if leave_encash_tot <= 0.0:
                le_line = self.line_ids.filtered(lambda l: (l.code or '').upper() in (
                    'LEAVE_ENCASH', 'ENCASHMENT', 'LEAVE_ENCASHMENT'
                ))
                if le_line:
                    leave_encash_tot = sum(float(l.total or 0.0) for l in le_line)
                elif hasattr(self, 'hds_in_has_approved_leave_encashment') and self.hds_in_has_approved_leave_encashment():
                    leave_encash_tot = float(self.hds_in_compute_in_service_leave_encashment() or 0.0)
            if leave_encash_tot > 0.0:
                tax_comp_income.append({'head': 'In-Service Leave Encashment', 'annual': leave_encash_tot, 'exempt': 0.0, 'taxable': leave_encash_tot})

            # Exit Leave Encashment (Settlement payout under Section 10(10AA) / Income-tax Act, 2025)
            exit_encash_tot = float(getattr(sal_proj, 'total_exit_leave_encash', 0.0) or 0.0) if sal_proj else 0.0
            if exit_encash_tot <= 0.0:
                exit_le_line = self.line_ids.filtered(lambda l: (l.code or '').upper() in (
                    'EXIT_LEAVE_ENCASH', 'LEAVE_ENCASH_EXIT'
                ))
                if exit_le_line:
                    exit_encash_tot = sum(float(l.total or 0.0) for l in exit_le_line)
            if exit_encash_tot > 0.0:
                if sal_proj and hasattr(sal_proj, 'exempt_exit_leave_encash'):
                    exempt_leave = float(sal_proj.exempt_exit_leave_encash or 0.0)
                    taxable_leave = float(sal_proj.taxable_exit_leave_encash or 0.0)
                else:
                    ceiling = 2500000.0
                    settlement = False
                    if 'final.settlement' in self.env:
                        settlement = self.env['final.settlement'].search([
                            ('payslip_id', '=', self.id),
                            ('state', '!=', 'cancel'),
                        ], limit=1)
                        if not settlement and self.employee_id:
                            settlement = self.env['final.settlement'].search([
                                ('employee_id', '=', self.employee_id.id),
                                ('state', '!=', 'cancel'),
                            ], limit=1)
                    if settlement and settlement.leave_encash_exemption_amount is not False and settlement.leave_encash_exemption_amount is not None and settlement.leave_encash_exemption_amount > 0.0:
                        ceiling = float(settlement.leave_encash_exemption_amount)
                    else:
                        try:
                            ceiling = float(self.env['hr.rule.parameter']._get_parameter_value(
                                'hds_in_leave_encashment_statutory_ceiling', self.date_to or fields.Date.today()
                            ) or self.env['hr.rule.parameter']._get_parameter_value(
                                'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', self.date_to or fields.Date.today()
                            ) or 2500000.0)
                        except Exception:
                            ceiling = 2500000.0
                    exempt_leave = min(exit_encash_tot, ceiling)
                    taxable_leave = max(0.0, exit_encash_tot - ceiling)

                head_label = 'Leave Encashment [Sec 10(10AA)]' if exempt_leave > 0.0 or (sal_proj and getattr(sal_proj, 'exempt_exit_leave_encash', 0.0) > 0.0) else 'Leave Encashment (Settlement)'
                tax_comp_income.append({'head': head_label, 'annual': exit_encash_tot, 'exempt': exempt_leave, 'taxable': taxable_leave})

            # Statutory Gratuity [Income-tax Act, 2025 / Payment of Gratuity Act, 1972]
            gratuity_tot = float(getattr(sal_proj, 'total_gratuity', 0.0) or getattr(sal_proj, 'ytd_gratuity', 0.0) or 0.0) if sal_proj else 0.0
            if gratuity_tot <= 0.0:
                grat_line = self.line_ids.filtered(lambda l: (l.code or '').upper() == 'GRATUITY')
                if grat_line:
                    gratuity_tot = sum(float(l.total or 0.0) for l in grat_line)
            if gratuity_tot > 0.0:
                if sal_proj and hasattr(sal_proj, 'exempt_gratuity'):
                    exempt_grat = float(sal_proj.exempt_gratuity or 0.0)
                    taxable_grat = float(sal_proj.taxable_gratuity or 0.0)
                else:
                    ceiling = 2000000.0
                    if 'final.settlement' in self.env:
                        settlement = self.env['final.settlement'].search([
                            ('payslip_id', '=', self.id),
                            ('state', '!=', 'cancel'),
                        ], limit=1)
                        if not settlement and self.employee_id:
                            settlement = self.env['final.settlement'].search([
                                ('employee_id', '=', self.employee_id.id),
                                ('state', '!=', 'cancel'),
                            ], limit=1)
                        if settlement and settlement.gratuity_exemption_amount is not False and settlement.gratuity_exemption_amount is not None:
                            ceiling = float(settlement.gratuity_exemption_amount)
                    if ceiling == 2000000.0:
                        try:
                            ceiling = float(self.env['hr.rule.parameter']._get_parameter_value(
                                'hds_in_gratuity_statutory_ceiling', self.date_to or fields.Date.today()
                            ) or 2000000.0)
                        except Exception:
                            ceiling = 2000000.0
                    exempt_grat = min(gratuity_tot, ceiling)
                    taxable_grat = max(0.0, gratuity_tot - ceiling)
                tax_comp_income.append({
                    'head': 'Statutory Gratuity [Income-tax Act, 2025]',
                    'annual': gratuity_tot,
                    'exempt': exempt_grat,
                    'taxable': taxable_grat
                })

            # Remaining unaccounted allowances from TDS projection engine
            engine_alw_tot = getattr(sal_proj, 'total_allowances', 0.0) if sal_proj else 0.0
            accounted_alw = fixed_tot + std_tot + perf_tot + ret_tot + conv_tot + med_tot + meal_tot + phone_tot + internet_tot + meal_voucher_tot + transport_tot
            remaining_alw = max(0.0, engine_alw_tot - accounted_alw)
            if remaining_alw > 0.01:
                tax_comp_income.append({'head': 'Special / Other Allowance', 'annual': remaining_alw, 'exempt': 0.0, 'taxable': remaining_alw})

            engine_prev_sal = float(getattr(prev_emp, 'taxable_salary', 0.0) or 0.0) if prev_emp else 0.0
            prev_emp_val = engine_prev_sal if engine_prev_sal > 0 else prev_employer_salary_pdf
            if prev_emp_val == 0 and prev_employer_salary_pdf > 0:
                prev_emp_val = prev_employer_salary_pdf
            if prev_emp_val > 0:
                tax_comp_income.append({'head': 'Previous Employer Salary (Form 12B)', 'annual': prev_emp_val, 'exempt': 0.0, 'taxable': prev_emp_val})

            # Section 17(2)(vii) Employer Contribution Perquisite (EPF + NPS + Superannuation > ₹7,50,000)
            sec_17_2_vii_val = float(getattr(proj, 'sec_17_2_vii_perquisite', 0.0) or 0.0) if proj else 0.0
            if sec_17_2_vii_val <= 0.0 and proj:
                engine_salary_check = float(getattr(proj, 'projected_annual_salary', 0.0) or 0.0)
                interim_salary = sum(i['taxable'] for i in tax_comp_income)
                if engine_salary_check > interim_salary + 0.01:
                    sec_17_2_vii_val = round(engine_salary_check - interim_salary, 2)

            if sec_17_2_vii_val > 0.0:
                ann_epf = float(getattr(proj, 'total_annual_employer_epf', 0.0) or 0.0) if proj else 0.0
                ann_nps = float(getattr(proj, 'actual_employer_nps', 0.0) or 0.0) if proj else 0.0
                if ann_epf > 0 and ann_nps > 0:
                    note_desc = 'Excess Employer PF & NPS over ₹7,50,000'
                elif ann_nps > 0:
                    note_desc = 'Excess Employer NPS over ₹7,50,000'
                elif ann_epf > 0:
                    note_desc = 'Excess Employer PF over ₹7,50,000'
                else:
                    note_desc = 'Excess contributions over ₹7,50,000 limit'

                tax_comp_income.append({
                    'head': 'Employer Contribution Perquisite [Sec 17(2)(vii)]',
                    'annual': sec_17_2_vii_val,
                    'exempt': 0.0,
                    'taxable': sec_17_2_vii_val,
                    'is_perquisite': True,
                    'note': note_desc
                })

            # Resolve Tax Regime
            regime_code = 'new'
            regime_name = 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'
            if tds_res and getattr(tds_res, 'regime_code', False):
                regime_code = str(tds_res.regime_code).lower()
                regime_name = getattr(tds_res, 'regime_name', 'New Tax Regime Income-tax Act, 2025 — Section 202(1)' if regime_code == 'new' else 'Old Tax Regime')
            else:
                emp_reg = False
                if fy:
                    emp_reg = self.env['tds.employee.tax.regime'].sudo().search([
                        ('employee_id', '=', emp.id),
                        ('financial_year_id', '=', fy.id)
                    ], limit=1)
                if emp_reg and emp_reg.regime_id:
                    regime_code = (emp_reg.regime_id.code or 'new').lower()
                    regime_name = emp_reg.regime_id.name
                else:
                    default_reg = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
                    if default_reg:
                        regime_code = 'new'
                        regime_name = default_reg.name

            is_new_regime = (regime_code == 'new')
            regime_display = 'New Tax Regime Income-tax Act, 2025 — Section 202(1)' if is_new_regime else 'Old Tax Regime'
            regime_header = 'NEW REGIME' if is_new_regime else 'OLD REGIME'

            decl = self.env['tds.employee.declaration'].search([
                ('employee_id', '=', emp.id),
                ('state', '!=', 'rejected')
            ], order='id desc', limit=1)

            oth_inc_val = getattr(oth_inc, 'total_other_income', 0.0) if oth_inc else 0.0
            fp_gross = float(getattr(oth_inc, 'family_pension_gross', 0.0) or 0.0) if oth_inc else 0.0
            fp_ded = float(getattr(oth_inc, 'family_pension_deduction', 0.0) or 0.0) if oth_inc else 0.0
            fp_net = float(getattr(oth_inc, 'family_pension_net', 0.0) or 0.0) if oth_inc else 0.0
            if not fp_gross and decl:
                fp_gross = float(getattr(decl, 'decl_57iia_family_pension', 0.0) or (next((l.declared_amount for l in getattr(decl, 'declaration_line_ids', []) if l.category == '57iia'), 0.0)) or 0.0)
                if fp_gross > 0:
                    fp_ded = min(fp_gross / 3.0, 25000.0)
                    fp_net = max(0.0, fp_gross - fp_ded)

            if fp_gross > 0:
                tax_comp_income.append({
                    'head': 'Family Pension Income [Sec 93(1)(d)]',
                    'annual': fp_gross,
                    'exempt': fp_ded,
                    'taxable': fp_net
                })
                remaining_other = max(0.0, oth_inc_val - fp_net)
                if remaining_other > 0:
                    tax_comp_income.append({
                        'head': 'Declared Other Income',
                        'annual': remaining_other,
                        'exempt': 0.0,
                        'taxable': remaining_other
                    })
            elif oth_inc_val > 0:
                tax_comp_income.append({'head': 'Declared Other Income', 'annual': oth_inc_val, 'exempt': 0.0, 'taxable': oth_inc_val})

            gti_annual = sum(i['annual'] for i in tax_comp_income)
            gti_exempt = sum(i['exempt'] for i in tax_comp_income)
            gti_taxable = sum(i['taxable'] for i in tax_comp_income)
            engine_gti = float(getattr(proj, 'gross_total_income', 0.0) or 0.0) if proj else 0.0
            if engine_gti > gti_taxable + 0.01:
                unitemized_diff = round(engine_gti - gti_taxable, 2)
                tax_comp_income.append({
                    'head': 'Employer Contribution Perquisite [Sec 17(2)(vii)]',
                    'annual': unitemized_diff,
                    'exempt': 0.0,
                    'taxable': unitemized_diff,
                    'is_perquisite': True,
                    'note': 'Excess of employer contributions over statutory ceiling'
                })
                gti_annual += unitemized_diff
                gti_taxable += unitemized_diff
            elif engine_gti > 0.0:
                gti_taxable = engine_gti

            std_ded = getattr(deduct, 'standard_deduction', 0.0) if deduct else 0.0
            if not std_ded and not is_new_regime:
                std_ded = 50000.0
            elif not std_ded and is_new_regime:
                std_ded = 75000.0

            c6a = getattr(deduct, 'chapter_6a_deductions', None) if deduct else None

            if is_new_regime:
                sec_80ccd2 = float(getattr(deduct, 'employer_nps_80ccd2', 0.0) or 0.0) if deduct else 0.0
                if not sec_80ccd2 and decl:
                    sec_80ccd2 = float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or (next((l.declared_amount for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80ccd2'), 0.0)) or 0.0)

                sec_80cch = float(getattr(c6a, 'section_80cch', 0.0) or 0.0) if c6a else 0.0
                if not sec_80cch and decl:
                    sec_80cch = float(getattr(decl, 'decl_80cch_agniveer', 0.0) or (next((l.declared_amount for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80cch'), 0.0)) or 0.0)

                tax_comp_deductions = []
                if std_ded > 0:
                    tax_comp_deductions.append({'name': 'Standard Deduction [u/s 16(ia)]', 'amount': std_ded})
                if sec_80ccd2 > 0:
                    tax_comp_deductions.append({'name': 'Employer NPS Contribution [Section 124]', 'amount': sec_80ccd2})
                if sec_80cch > 0:
                    tax_comp_deductions.append({'name': 'Agniveer Corpus Fund [Section 80CCH]', 'amount': sec_80cch})
                other_ded = max(0.0, float(getattr(deduct, 'other_approved_deductions', 0.0) or 0.0) - sec_80cch)
                if other_ded > 0:
                    tax_comp_deductions.append({'name': 'Other Approved Deductions', 'amount': other_ded})
            else:
                tax_comp_deductions = []
                if std_ded > 0:
                    tax_comp_deductions.append({'name': 'Standard Deduction [u/s 16(ia)]', 'amount': std_ded})

                pt_16iii = float(getattr(deduct, 'professional_tax_16iii', 0.0) or 0.0) if deduct else 0.0
                if not pt_16iii and not is_new_regime:
                    from ..services.tds.professional_tax_deduction_service import ProfessionalTaxDeductionService
                    pt_svc = ProfessionalTaxDeductionService(self.env)
                    pt_16iii = pt_svc.calculate_projected_professional_tax_for_fy(emp, fy, payslip=self, eval_date=eval_date)
                if pt_16iii > 0:
                    tax_comp_deductions.append({'name': 'Professional Tax [Sec 16(iii)]', 'amount': pt_16iii})

                hra_ex = float(getattr(deduct, 'hra_exemption', 0.0) or 0.0) if deduct else 0.0
                if hra_ex > 0:
                    tax_comp_deductions.append({'name': 'HRA Exemption [Sec 10(13A)]', 'amount': hra_ex})

                lta_ex = float(getattr(deduct, 'lta_exemption', 0.0) or 0.0) if deduct else 0.0
                if lta_ex > 0:
                    tax_comp_deductions.append({'name': 'LTA Exemption [Sec 10(5)]', 'amount': lta_ex})

                sec_24b = float(getattr(deduct, 'home_loan_interest_24b', 0.0) or 0.0) if deduct else 0.0
                if not sec_24b and decl:
                    sec_24b = float(getattr(decl, 'decl_24b_self_interest', 0.0) or 0.0)
                if sec_24b > 0:
                    tax_comp_deductions.append({'name': 'Section 24(b) (Home Loan Interest)', 'amount': sec_24b})

                sec_80eea = float(getattr(deduct, 'section_80eea_deduction', getattr(c6a, 'section_80eea', 0.0)) or 0.0) if deduct else 0.0
                if sec_80eea > 0:
                    tax_comp_deductions.append({'name': 'Section 80EEA (First-Time Home Buyer)', 'amount': sec_80eea})

                sec_80c = float(getattr(c6a, 'section_80c', 0.0) or 0.0) if c6a else 0.0
                if not sec_80c and decl:
                    sec_80c = min(150000.0, float(getattr(decl, 'decl_80c_total_declared', 0.0) or 0.0))
                if sec_80c > 0:
                    tax_comp_deductions.append({'name': 'Section 80C (PPF/LIC/EPF/etc)', 'amount': sec_80c})

                sec_80d = float(getattr(c6a, 'section_80d', 0.0) or 0.0) if c6a else 0.0
                if not sec_80d and decl:
                    sec_80d = float(getattr(decl, 'decl_80d_total_declared', 0.0) or 0.0)
                if sec_80d > 0:
                    tax_comp_deductions.append({'name': 'Section 80D (Health Insurance)', 'amount': sec_80d})

                sec_80ccd1b = float(getattr(c6a, 'section_80ccd1b', 0.0) or 0.0) if c6a else 0.0
                if not sec_80ccd1b and decl:
                    sec_80ccd1b = float(getattr(decl, 'decl_80ccd1b_nps', 0.0) or 0.0)
                if sec_80ccd1b > 0:
                    tax_comp_deductions.append({'name': 'Section 80CCD(1B) (NPS)', 'amount': sec_80ccd1b})

                sec_80ccd2 = float(getattr(deduct, 'employer_nps_80ccd2', 0.0) or 0.0) if deduct else 0.0
                if not sec_80ccd2 and decl:
                    sec_80ccd2 = float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or 0.0)
                if sec_80ccd2 > 0:
                    tax_comp_deductions.append({'name': 'Employer NPS Contribution [Section 124]', 'amount': sec_80ccd2})

                sec_80e = float(getattr(c6a, 'section_80e', 0.0) or 0.0) if c6a else 0.0
                if sec_80e > 0:
                    tax_comp_deductions.append({'name': 'Section 80E (Education Loan)', 'amount': sec_80e})

                sec_80g = float(getattr(c6a, 'section_80g', 0.0) or 0.0) if c6a else 0.0
                if sec_80g > 0:
                    tax_comp_deductions.append({'name': 'Section 80G (Donations)', 'amount': sec_80g})

                sec_80tta = float(getattr(c6a, 'section_80tta_80ttb', 0.0) or 0.0) if c6a else 0.0
                if sec_80tta > 0:
                    tax_comp_deductions.append({'name': 'Section 80TTA/TTB (Savings Interest)', 'amount': sec_80tta})

                sec_80dd = float(getattr(c6a, 'section_80dd', 0.0) or 0.0) if c6a else 0.0
                if sec_80dd > 0:
                    tax_comp_deductions.append({'name': 'Section 80DD (Disabled Dependent)', 'amount': sec_80dd})

                sec_80u = float(getattr(c6a, 'section_80u', 0.0) or 0.0) if c6a else 0.0
                if sec_80u > 0:
                    tax_comp_deductions.append({'name': 'Section 80U (Person with Disability)', 'amount': sec_80u})

                sec_80gg = float(getattr(c6a, 'section_80gg', 0.0) or 0.0) if c6a else 0.0
                if sec_80gg > 0:
                    tax_comp_deductions.append({'name': 'Section 80GG (Rent Paid)', 'amount': sec_80gg})

                sec_80cch = float(getattr(c6a, 'section_80cch', 0.0) or 0.0) if c6a else 0.0
                if sec_80cch > 0:
                    tax_comp_deductions.append({'name': 'Agniveer Corpus Fund [Sec 80CCH]', 'amount': sec_80cch})

                other_ded = float(getattr(deduct, 'other_approved_deductions', 0.0) or 0.0) if deduct else 0.0
                if other_ded > 0:
                    tax_comp_deductions.append({'name': 'Other Approved Deductions', 'amount': other_ded})

            # Filter out any zero deductions
            tax_comp_deductions = [d for d in tax_comp_deductions if float(d.get('amount', 0.0) or 0.0) > 0.001]

            if deduct and getattr(deduct, 'total_allowable_deductions', 0.0) > 0:
                total_tax_deductions = float(deduct.total_allowable_deductions)
            else:
                total_tax_deductions = sum(d['amount'] for d in tax_comp_deductions)

            net_taxable_income = getattr(tax_inc, 'net_taxable_income', max(0.0, gti_taxable - total_tax_deductions))
            base_tax = getattr(slab, 'base_tax_liability', 0.0) if slab else 0.0
            tax_after_rebate = getattr(rebate, 'tax_after_rebate', base_tax) if rebate else base_tax
            rebate_applied = getattr(rebate, 'rebate_applied', 0.0) if rebate else 0.0

            surcharge_rate = float(getattr(surcharge, 'surcharge_rate_pct', getattr(surcharge, 'surcharge_rate', 0.0)) or 0.0)
            surcharge_amount = float(getattr(surcharge, 'surcharge_amount', 0.0) or 0.0)
            surcharge_before_relief = float(getattr(surcharge, 'surcharge_before_relief', surcharge_amount) or 0.0)
            marginal_relief = float(getattr(surcharge, 'marginal_relief', 0.0) or 0.0)
            is_surcharge_applicable = bool(getattr(surcharge, 'is_applicable', (surcharge_amount > 0 or surcharge_rate > 0)))
            tax_plus_surcharge = float(getattr(surcharge, 'tax_plus_surcharge', tax_after_rebate + surcharge_amount) or 0.0)

            cess_val = getattr(cess_obj, 'cess_amount', 0.0) if cess_obj else 0.0
            total_annual_tax = getattr(tds_res, 'total_annual_tax_liability', tax_plus_surcharge + cess_val)

            current_month_tds = float(getattr(monthly_obj, 'current_month_tds', 0.0) or 0.0) if monthly_obj else 0.0
            ytd_current_tds_only = float(getattr(monthly_obj, 'ytd_tds_deducted', 0.0) or 0.0) if monthly_obj else 0.0
            tds_recovered_ytd = ytd_current_tds_only + current_month_tds
            remaining_tds_liability = max(0.0, round(float(total_annual_tax or 0.0) - float(prev_employer_tds_pdf or 0.0) - float(tds_recovered_ytd or 0.0), 2))

            eng_rem_periods = int(getattr(monthly_obj, 'remaining_payroll_periods', 0) or 0) if monthly_obj else 0
            if eng_rem_periods <= 0:
                eng_rem_periods = period_svc.calculate_remaining_periods(emp, fy, eval_date=eval_date)
            remaining_months = max(0, eng_rem_periods - 1)

            if remaining_months > 0 and remaining_tds_liability > 0:
                projected_monthly_tds = round(remaining_tds_liability / remaining_months, 2)
            else:
                projected_monthly_tds = 0.0

            tax_rows = [
                (inc['head'], inc['annual'], 0.0, inc['exempt'], inc['taxable'])
                for inc in tax_comp_income
            ]

            investments = []
            hra_declarations = []
            if decl and not is_new_regime:
                c6a_val = getattr(decl, 'decl_80c_total_declared', 0.0) or 0.0
                if c6a_val > 0:
                    investments.append(('Provident Fund & Specified Investments (80C)', c6a_val))
                if getattr(decl, 'decl_80d_total_declared', 0.0) > 0:
                    investments.append(('Medical Insurance Premium (80D)', decl.decl_80d_total_declared))
                if getattr(decl, 'decl_24b_self_interest', 0.0) > 0:
                    investments.append(('Housing Loan - Interest (24b)', decl.decl_24b_self_interest))

                if decl.decl_hra_annual_rent > 0:
                    rent_from_dt = joining_date if (joining_date and fy and fy.start_date and joining_date > fy.start_date) else (fy.start_date if fy else None)
                    hra_declarations.append({
                        'type': 'HRA - Rent Payments',
                        'from_date': rent_from_dt.strftime('%d-%b-%Y') if rent_from_dt else '',
                        'to_date': fy.end_date.strftime('%d-%b-%Y') if fy and fy.end_date else '',
                        'rent_month': round(decl.decl_hra_annual_rent / float(total_fy_months or 12), 2),
                        'metro': 'Y' if decl.decl_hra_is_metro else 'N'
                    })

        return {
            'month_str': month_str,
            'emp_no': emp_no,
            'location': location,
            'joining_date': joining_date.strftime('%d-%b-%Y') if joining_date else 'N/A',
            'dob': dob.strftime('%d-%b-%Y') if dob else 'N/A',
            'gender': gender,
            'pan': pan,
            'aadhaar': aadhaar,
            'epf_no': epf_no,
            'esic_no': esic_no,
            'uan': uan,
            'std_days': std_days,
            'days_worked': days_worked,
            'lop_days': lop_days,
            'lop_rev_days': lop_rev_days,
            'payment_mode': payment_mode,
            'bank_name': bank_name,
            'acc_no': acc_no,
            'earnings_lines': earnings_lines,
            'deductions_lines': deductions_lines,
            'total_earnings': total_earnings,
            'total_deductions': total_deductions,
            'net_salary': net_salary,
            'show_tds_block': show_tds_block,
            'tds_res': tds_res,
            'tax_rows': tax_rows,
            'tax_comp_income': tax_comp_income,
            'tax_comp_deductions': tax_comp_deductions,
            'total_tax_deductions': total_tax_deductions,
            'gti_annual': gti_annual,
            'gti_exempt': gti_exempt,
            'gti_taxable': gti_taxable,
            'net_taxable_income': net_taxable_income,
            'base_tax': base_tax,
            'income_tax': tax_after_rebate,
            'tax_after_rebate': tax_after_rebate,
            'rebate_applied': rebate_applied,
            'surcharge': surcharge_amount,
            'surcharge_amount': surcharge_amount,
            'surcharge_rate': surcharge_rate,
            'surcharge_before_relief': surcharge_before_relief,
            'marginal_relief': marginal_relief,
            'is_surcharge_applicable': is_surcharge_applicable,
            'tax_plus_surcharge': tax_plus_surcharge,
            'cess': cess_val,
            'total_annual_tax': total_annual_tax,
            'current_month_tds': current_month_tds,
            'prev_employer_tds': prev_employer_tds_pdf,
            'tds_recovered_ytd': tds_recovered_ytd,
            'remaining_tds_liability': remaining_tds_liability,
            'remaining_months': remaining_months,
            'projected_monthly_tds': projected_monthly_tds,
            'pf_wage': pf_wage,
            'investments': investments,
            'hra_declarations': hra_declarations,
            'decl': decl,
            'regime_code': regime_code,
            'regime_display': regime_display,
            'regime_header': regime_header,
        }

