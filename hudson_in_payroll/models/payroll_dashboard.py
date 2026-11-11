# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import datetime, date, timedelta
# pyrefly: ignore [missing-import]
from markupsafe import escape
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class HdsPayrollDashboard(models.Model):
    """
    Enterprise Indian HR & Payroll Dashboard Model.
    Provides real-time company-wide metrics, period controls, statutory compliance tracking,
    action required alerts, employee data health, and historical payroll cost trends.
    """
    _name = 'hds.payroll.dashboard'
    _description = 'Indian HR & Payroll Dashboard'

    name = fields.Char(string="Dashboard Name", default="Payroll Dashboard")
    financial_year_id = fields.Many2one('tds.financial.year', string="Tax Year", default=lambda self: self._default_financial_year())
    payroll_month_num = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Payroll Month", default=lambda self: str(fields.Date.context_today(self).month))

    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)

    # 1. Primary KPI Metrics
    total_payroll_cost = fields.Monetary(string="Total Payroll Cost", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_gross_pay = fields.Monetary(string="Total Gross Pay", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_net_pay = fields.Monetary(string="Total Net Wage", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_net_paid = fields.Monetary(string="Disbursed Net Pay", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_net_payable = fields.Monetary(string="Net Pay Due (Payable)", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_basic_wage = fields.Monetary(string="Total Basic Wage", currency_field='currency_id', compute='_compute_dashboard_metrics')
    avg_net_wage = fields.Monetary(string="Avg Net Wage", currency_field='currency_id', compute='_compute_dashboard_metrics')
    avg_basic_wage = fields.Monetary(string="Avg Basic Wage", currency_field='currency_id', compute='_compute_dashboard_metrics')
    avg_hours_per_day = fields.Float(string="Avg Hours/Day", compute='_compute_dashboard_metrics')
    fte_count = fields.Float(string="FTE", compute='_compute_dashboard_metrics')
    active_employee_count = fields.Integer(string="Active Employees", compute='_compute_dashboard_metrics')
    tds_this_month = fields.Monetary(string="TDS This Month", currency_field='currency_id', compute='_compute_dashboard_metrics')
    pending_actions_count = fields.Integer(string="Pending Actions", compute='_compute_dashboard_metrics')

    # 2. Action Required Counters
    missing_pan_count = fields.Integer(string="Missing PAN Count", compute='_compute_dashboard_metrics')
    missing_bank_count = fields.Integer(string="Missing Bank Count", compute='_compute_dashboard_metrics')
    pending_declarations_count = fields.Integer(string="Pending Declarations Count", compute='_compute_dashboard_metrics')
    attendance_pending_count = fields.Integer(string="Attendance Pending Count", compute='_compute_dashboard_metrics')
    draft_slips_count = fields.Integer(string="Draft Payslips Count", compute='_compute_dashboard_metrics')
    verify_slips_count = fields.Integer(string="To Validate Payslips Count", compute='_compute_dashboard_metrics')
    unconfirmed_slips_count = fields.Integer(string="Unconfirmed Payslips Count", compute='_compute_dashboard_metrics')
    missing_salary_count = fields.Integer(string="Missing Salary Info Count", compute='_compute_dashboard_metrics')

    # 3. Employee Data Health Percentages
    pan_health_pct = fields.Float(string="PAN Completeness %", compute='_compute_dashboard_metrics')
    bank_health_pct = fields.Float(string="Bank Details Completeness %", compute='_compute_dashboard_metrics')
    aadhaar_health_pct = fields.Float(string="Aadhaar Completeness %", compute='_compute_dashboard_metrics')
    contact_health_pct = fields.Float(string="Emergency Contact Completeness %", compute='_compute_dashboard_metrics')

    # 4. Tax Regime Distribution
    old_regime_count = fields.Integer(string="Old Regime Employees", compute='_compute_dashboard_metrics')
    new_regime_count = fields.Integer(string="New Regime Employees", compute='_compute_dashboard_metrics')
    tds_ytd_total = fields.Monetary(string="TDS YTD Total", currency_field='currency_id', compute='_compute_dashboard_metrics')

    # 5. Statutory Liabilities
    epf_total_liability = fields.Monetary(string="EPF Total Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    esic_total_liability = fields.Monetary(string="ESIC Total Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    pt_total_liability = fields.Monetary(string="Professional Tax Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_employer_liability = fields.Monetary(string="Employer EPF Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_er_share_amount = fields.Monetary(string="Employer EPF Share (3.67%)", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_er_eps_amount = fields.Monetary(string="Employer EPS (8.33%)", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_er_edli_amount = fields.Monetary(string="Employer EDLI (0.5%)", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_er_admin_amount = fields.Monetary(string="Employer EPF Admin (0.5%)", currency_field='currency_id', compute='_compute_dashboard_metrics')
    esic_employer_liability = fields.Monetary(string="Employer ESIC Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    lwf_employer_liability = fields.Monetary(string="Employer LWF Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_employer_statutory_liability = fields.Monetary(string="Total Employer Statutory Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    epf_ee_liability = fields.Monetary(string="Employee EPF Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    esic_ee_liability = fields.Monetary(string="Employee ESIC Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    lwf_total_liability = fields.Monetary(string="Total LWF Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')
    total_statutory_liability = fields.Monetary(string="Total Statutory Compliance Liability", currency_field='currency_id', compute='_compute_dashboard_metrics')

    # 6. Statutory Compliance & Identifier Status
    epf_complete_count = fields.Integer(string="EPF Complete UAN Count", compute='_compute_dashboard_metrics')
    epf_missing_count = fields.Integer(string="EPF Missing UAN Count", compute='_compute_dashboard_metrics')
    esic_complete_count = fields.Integer(string="ESIC Complete IP Count", compute='_compute_dashboard_metrics')
    esic_missing_count = fields.Integer(string="ESIC Missing IP Count", compute='_compute_dashboard_metrics')
    lwf_complete_count = fields.Integer(string="LWF Complete Number Count", compute='_compute_dashboard_metrics')
    lwf_missing_count = fields.Integer(string="LWF Missing Number Count", compute='_compute_dashboard_metrics')
    statutory_data_errors_count = fields.Integer(string="Statutory Data Errors Count", compute='_compute_dashboard_metrics')
    statutory_ready_count = fields.Integer(string="Statutory Ready Count", compute='_compute_dashboard_metrics')

    # 7. Workforce Movement
    new_joiners_count = fields.Integer(string="New Joiners Count", compute='_compute_dashboard_metrics')
    exits_count = fields.Integer(string="Exits Count", compute='_compute_dashboard_metrics')

    # 8. Final Settlements Due KPI & Status Breakdown
    final_settlements_due_count = fields.Integer(string="Final Settlements Due This Month", compute='_compute_dashboard_metrics')
    final_settlement_draft_count = fields.Integer(string="Draft Settlements", compute='_compute_dashboard_metrics')
    final_settlement_review_count = fields.Integer(string="Under Review Settlements", compute='_compute_dashboard_metrics')
    final_settlement_approved_count = fields.Integer(string="Approved Settlements", compute='_compute_dashboard_metrics')
    final_settlement_paid_count = fields.Integer(string="Paid Settlements", compute='_compute_dashboard_metrics')
    final_settlement_amount = fields.Monetary(string="Net Settlement Amount", currency_field='currency_id', compute='_compute_dashboard_metrics')
    no_contract_count = fields.Integer(string="Employees Without Running Contract", compute='_compute_dashboard_metrics')

    # 9. Rich HTML Dashboard Canvas
    dashboard_html = fields.Html(string="Dashboard Canvas", compute='_compute_dashboard_html', store=False, sanitize=False)

    @api.model
    def get_period_search_data(self):
        """Data for the dashboard's control-panel period search (months, tax years, current
        selection and the defaults used when a facet is removed). Read-only."""
        dash = self.env.ref('hudson_in_payroll.hds_payroll_dashboard_singleton', raise_if_not_found=False)             or self.search([], limit=1)
        Fy = self.env['tds.financial.year']
        today = fields.Date.context_today(self)
        fys = Fy.search([], order='start_date desc', limit=10)
        default_fy = Fy.search([('start_date', '<=', today), ('end_date', '>=', today)], limit=1) or fys[:1]
        current_fy = (dash.financial_year_id if dash else Fy) or default_fy

        def _fy_vals(fy):
            name = fy.name or ''
            return {
                'id': fy.id,
                'name': name,
                'short': name.replace('Tax Year:', '').strip() or name,
                'start_year': fy.start_date.year if fy.start_date else today.year,
                'end_year': fy.end_date.year if fy.end_date else today.year,
            }

        fy_list = [_fy_vals(fy) for fy in fys]
        if current_fy and current_fy.id not in [f['id'] for f in fy_list]:
            fy_list.append(_fy_vals(current_fy))
        return {
            'months': [{'value': value, 'name': label} for value, label in self._fields['payroll_month_num'].selection],
            'fys': fy_list,
            'month': (dash.payroll_month_num if dash else False) or str(today.month),
            'fy_id': current_fy.id if current_fy else False,
            'default_month': str(today.month),
            'default_fy_id': default_fy.id if default_fy else False,
            'today_month': today.month,
            'today_year': today.year,
        }

    @api.model
    def _default_financial_year(self):
        today = fields.Date.context_today(self)
        fy = self.env['tds.financial.year'].search([
            ('start_date', '<=', today), ('end_date', '>=', today)
        ], limit=1)
        if not fy:
            fy = self.env['tds.financial.year'].search([], order='id desc', limit=1)
        return fy.id if fy else False

    @staticmethod
    def _has_pan(emp):
        for f in ('hds_in_pan', 'pan_no', 'pan'):
            val = getattr(emp, f, False)
            if val and str(val).strip():
                return True
        partner = getattr(emp, 'work_contact_id', False) or getattr(emp, 'address_home_id', False)
        if partner:
            p_pan = getattr(partner, 'pan', False) or getattr(partner, 'vat', False)
            if p_pan and str(p_pan).strip():
                return True
        return False

    @staticmethod
    def _has_bank_account(emp):
        if getattr(emp, 'bank_account_id', False):
            return True
        if getattr(emp, 'primary_bank_account_id', False):
            return True
        if getattr(emp, 'bank_account_ids', False):
            return bool(emp.bank_account_ids)
        if getattr(getattr(emp, 'work_contact_id', None), 'bank_account_id', False):
            return True
        if getattr(getattr(emp, 'address_home_id', None), 'bank_account_id', False):
            return True
        return False

    def _hds_employee_movements(self, kind, month_start, month_end):
        """Employees who joined ('joiners', active employees) or left ('exits') in the period. Exits include
        archived employees (a departed employee is normally archived, with its contract versions)."""
        Employee = self.env['hr.employee']
        if kind == 'joiners':
            date_field = next((f for f in ('first_contract_date', 'hds_in_doj', 'joining_date') if f in Employee._fields), None)
        else:
            date_field = next((f for f in ('departure_date', 'hds_in_dol', 'resign_date') if f in Employee._fields), None)
            Employee = Employee.with_context(active_test=False)
        if not date_field:
            return self.env['hr.employee']
        return Employee.search([(date_field, '>=', month_start), (date_field, '<=', month_end)])

    def _hds_month_payslips(self, month_start, month_end):
        """Payslips counted by the dashboard for a period: validated or paid, of the active companies.
        Split non-overlapping payslips (e.g. 1-15 and 16-30) are all counted, while duplicate payslips
        (same employee and period) are counted once, to avoid double-counting payroll costs."""
        all_slips = self.env['hr.payslip'].search([
            ('date_from', '<=', month_end),
            ('date_to', '>=', month_start),
            ('state', 'in', ('done', 'paid')),
            ('company_id', 'in', self.env.companies.ids),
        ])
        state_priority = {'paid': 2, 'done': 1}
        unique_slips = {}
        for slip in all_slips.sorted(key=lambda s: (state_priority.get(s.state, 0), -(s.id or 0)), reverse=True):
            if getattr(slip, 'has_duplicate_payslip', False):
                continue
            key = (slip.employee_id.id, slip.date_from, slip.date_to)
            if key not in unique_slips:
                unique_slips[key] = slip
        return self.env['hr.payslip'].browse([s.id for s in unique_slips.values()])

    @staticmethod
    def _has_aadhaar(emp):
        for f in ('hds_in_aadhaar', 'aadhaar_no', 'identification_id'):
            val = getattr(emp, f, False)
            if val and str(val).strip():
                return True
        return False

    @staticmethod
    def _has_emergency_contact(emp):
        for f in ('emergency_contact', 'emergency_phone'):
            val = getattr(emp, f, False)
            if val and str(val).strip():
                return True
        return False

    @api.depends('financial_year_id', 'payroll_month_num')
    def _compute_dashboard_metrics(self):
        for rec in self:
            if not rec.financial_year_id:
                rec.financial_year_id = rec._default_financial_year()
            today = fields.Date.context_today(self)
            m_num = int(rec.payroll_month_num or today.month)
            year = today.year
            try:
                if rec.financial_year_id and getattr(rec.financial_year_id, 'start_date', False):
                    fy_s_year = rec.financial_year_id.start_date.year
                    fy_e_year = rec.financial_year_id.end_date.year
                    year = fy_s_year if m_num >= 4 else fy_e_year
            except Exception as err:
                _logger.warning("Safely handled Financial Year date resolution error in dashboard compute: %s", err)
                year = today.year

            month_start = date(year, m_num, 1)
            month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])

            # Active Employees & Data Health
            emp_model = self.env['hr.employee']
            active_emps = emp_model.search([('active', '=', True)])
            tot_emp = len(active_emps) or 1
            rec.active_employee_count = len(active_emps)

            pan_count = len(active_emps.filtered(lambda e: self._has_pan(e)))
            bank_count = len(active_emps.filtered(lambda e: self._has_bank_account(e)))
            aadhaar_count = len(active_emps.filtered(lambda e: self._has_aadhaar(e)))
            contact_count = len(active_emps.filtered(lambda e: self._has_emergency_contact(e)))

            rec.missing_pan_count = len(active_emps.filtered(lambda e: not self._has_pan(e)))
            rec.missing_bank_count = len(active_emps.filtered(lambda e: not self._has_bank_account(e)))
            rec.pan_health_pct = round((pan_count / tot_emp) * 100.0, 1)
            rec.bank_health_pct = round((bank_count / tot_emp) * 100.0, 1)
            rec.aadhaar_health_pct = round((aadhaar_count / tot_emp) * 100.0, 1)
            rec.contact_health_pct = round((contact_count / tot_emp) * 100.0, 1)

            # Statutory Compliance & Identifier Evaluation
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)

            epf_complete = 0
            epf_missing = 0
            esic_complete = 0
            esic_missing = 0
            lwf_complete = 0
            lwf_missing = 0
            stat_errors = set()
            stat_ready = set()

            for emp in active_emps:
                res = comp_service.validate_employee_all(emp)
                if getattr(emp, 'hds_in_epf_applicable', False):
                    if res['epf_valid']:
                        epf_complete += 1
                    else:
                        epf_missing += 1
                        stat_errors.add(emp.id)

                if getattr(emp, 'hds_in_esic_applicable', False):
                    if res['esic_valid']:
                        esic_complete += 1
                    else:
                        esic_missing += 1
                        stat_errors.add(emp.id)

                if getattr(emp, 'hds_in_lwf_applicable', False):
                    if res['lwf_valid']:
                        lwf_complete += 1
                    else:
                        lwf_missing += 1
                        stat_errors.add(emp.id)

                if not res['pan_valid'] or not res['bank_valid']:
                    stat_errors.add(emp.id)

                if res['is_compliant']:
                    stat_ready.add(emp.id)

            rec.epf_complete_count = epf_complete
            rec.epf_missing_count = epf_missing
            rec.esic_complete_count = esic_complete
            rec.esic_missing_count = esic_missing
            rec.lwf_complete_count = lwf_complete
            rec.lwf_missing_count = lwf_missing
            rec.statutory_data_errors_count = len(stat_errors)
            rec.statutory_ready_count = len(stat_ready)

            # Contract & Salary info missing count (safely guarded)
            rec.missing_salary_count = len(active_emps.filtered(lambda e: not getattr(e, 'contract_id', False) or float(getattr(getattr(e, 'contract_id', None), 'wage', 0.0) or 0.0) <= 0.0))

            # New Joiners & Exits for period
            rec.new_joiners_count = len(self._hds_employee_movements('joiners', month_start, month_end))
            rec.exits_count = len(self._hds_employee_movements('exits', month_start, month_end))

            rec.no_contract_count = len(self._employees_without_contract(month_start, month_end)[0])

            # Final Settlements Due for period (hudson_in_final_settlement: Draft -> Approved, paid via its payslip)
            settlement_domain = self._final_settlement_domain(month_start, month_end)
            if settlement_domain is not None:
                settlements = self.env['final.settlement'].search(settlement_domain)
                paid = settlements.filtered(lambda s: s.state == 'approved' and s.payslip_id.state in ('done', 'paid'))
                rec.final_settlements_due_count = len(settlements)
                rec.final_settlement_draft_count = len(settlements.filtered(lambda s: s.state == 'draft'))
                rec.final_settlement_review_count = 0  # no review stage in the settlement lifecycle
                rec.final_settlement_approved_count = len(settlements.filtered(lambda s: s.state == 'approved') - paid)
                rec.final_settlement_paid_count = len(paid)
                rec.final_settlement_amount = sum(settlements.mapped('net_settlement_amount'))
            else:
                rec.final_settlements_due_count = 0
                rec.final_settlement_draft_count = 0
                rec.final_settlement_review_count = 0
                rec.final_settlement_approved_count = 0
                rec.final_settlement_paid_count = 0
                rec.final_settlement_amount = 0.0

            # Payslips and Payroll Financial Metrics for period (Company-aware, Confirmed/Paid Slips only)
            company_domain = [('company_id', 'in', self.env.companies.ids)]
            slips = self._hds_month_payslips(month_start, month_end)

            # Unconfirmed slips (Draft & To Validate) - count actual payslips requiring validation for selected month
            unconfirmed_domain = [
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', 'in', ('draft', 'verify')),
            ] + company_domain
            unconfirmed_slips = self.env['hr.payslip'].search(unconfirmed_domain)

            rec.draft_slips_count = len(unconfirmed_slips.filtered(lambda s: s.state == 'draft'))
            rec.verify_slips_count = len(unconfirmed_slips.filtered(lambda s: s.state == 'verify'))
            rec.unconfirmed_slips_count = rec.draft_slips_count + rec.verify_slips_count
            rec.attendance_pending_count = rec.unconfirmed_slips_count

            tot_gross = 0.0
            tot_net = 0.0
            tot_net_payable = 0.0
            tot_net_paid = 0.0
            tot_basic = 0.0
            tot_tds = 0.0
            tot_epf = 0.0
            tot_ee_epf = 0.0
            tot_esi = 0.0
            tot_ee_esi = 0.0
            tot_pt = 0.0
            tot_lwf = 0.0
            tot_er_epf = 0.0
            tot_er_epf_share = 0.0
            tot_er_eps = 0.0
            tot_er_edli = 0.0
            tot_er_admin = 0.0
            tot_er_esic = 0.0
            tot_er_lwf = 0.0
            tot_employer_cost = 0.0
            tot_hours = 0.0
            tot_days = 0.0

            for slip in slips:
                gross_val = float(getattr(slip, 'gross_amount', None) or getattr(slip, 'gross_wage', 0.0) or 0.0)
                net_val = float(getattr(slip, 'net_amount', None) or getattr(slip, 'net_wage', 0.0) or 0.0)
                if not gross_val:
                    for line in slip.line_ids:
                        if (line.code or '').upper() == 'GROSS':
                            gross_val = abs(float(line.total or 0.0))
                            break
                if not net_val:
                    for line in slip.line_ids:
                        if (line.code or '').upper() == 'NET':
                            net_val = abs(float(line.total or 0.0))
                            break

                contract_wage = float(getattr(slip.contract_id, 'wage', 0.0) or 0.0) if slip.contract_id else 0.0
                if gross_val <= 0.0 and contract_wage > 0.0:
                    gross_val = contract_wage
                if net_val <= 0.0 and contract_wage > 0.0 and not slip.line_ids:
                    net_val = contract_wage

                tot_gross += gross_val
                tot_net += net_val
                if slip.state == 'paid':
                    tot_net_paid += net_val
                else:
                    tot_net_payable += net_val

                codes = set((l.code or '').upper() for l in slip.line_ids)
                has_er_epf = 'EMPLOYER_EPF' in codes or 'ER_PF' in codes

                slip_employer_contrib = 0.0
                slip_er_epf = 0.0
                slip_er_esic = 0.0
                slip_er_lwf = 0.0

                for line in slip.line_ids:
                    code = (line.code or '').upper()
                    amt = abs(float(line.total or 0.0))
                    rule = line.salary_rule_id

                    if code == 'BASIC':
                        tot_basic += amt
                    elif code in ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS'):
                        tot_tds += amt
                    elif code in ('PT', 'PROF_TAX'):
                        tot_pt += amt

                    # EPF Statutory Liabilities (Combined EE + ER for compliance records)
                    if code in ('PF', 'EPF', 'EE_PF'):
                        tot_ee_epf += amt
                        tot_epf += amt
                    elif code in ('EMPLOYER_EPF', 'ER_PF'):
                        tot_epf += amt
                    elif not has_er_epf and code in ('EPS', 'EPF_SHARE'):
                        tot_epf += amt
                    elif code in ('EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                        tot_epf += amt

                    # Employer EPF Share Only (Pure 12% EPF/EPS contribution)
                    if code in ('EMPLOYER_EPF', 'ER_PF'):
                        slip_er_epf += amt
                    elif not has_er_epf and code in ('EPS', 'EPF_SHARE'):
                        slip_er_epf += amt

                    # Statutory Employer EPF Breakdown components
                    if code == 'EPF_SHARE':
                        tot_er_epf_share += amt
                    elif code == 'EPS':
                        tot_er_eps += amt
                    elif code == 'EDLI':
                        tot_er_edli += amt
                    elif code in ('EPF_ADMIN', 'EDLI_ADMIN'):
                        tot_er_admin += amt
                    elif not ('EPS' in codes or 'EPF_SHARE' in codes) and code in ('EMPLOYER_EPF', 'ER_PF'):
                        tot_er_epf_share += amt

                    # ESIC Statutory Liabilities (Combined EE + ER)
                    if code in ('ESIC_EE', 'EE_ESI'):
                        tot_ee_esi += amt
                        tot_esi += amt
                    elif code in ('ESIC_ER', 'ER_ESI'):
                        tot_esi += amt
                    elif code == 'ESI' and 'ESIC_EE' not in codes and 'ESIC_ER' not in codes:
                        tot_ee_esi += round(amt * 0.75 / 4.0, 2)
                        tot_esi += amt

                    # Employer ESIC Share Only (3.25% contribution)
                    if code in ('ESIC_ER', 'ER_ESI'):
                        slip_er_esic += amt
                    elif code == 'ESI' and 'ESIC_EE' not in codes and 'ESIC_ER' not in codes:
                        slip_er_esic += round(amt * 3.25 / 4.0, 2)

                    # LWF Share
                    if code in ('LWF_EE', 'EE_LWF', 'LWF'):
                        tot_lwf += amt
                    if code in ('LWF_ER', 'ER_LWF'):
                        slip_er_lwf += amt
                        tot_lwf += amt

                    # Employer Cost Contribution (Employer EPF, EDLI, EPF Admin, Employer ESIC, Employer LWF)
                    if getattr(rule, 'hds_in_contributes_to_employer_cost', False):
                        slip_employer_contrib += amt
                    elif code in ('EMPLOYER_EPF', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN', 'ESIC_ER', 'LWF_ER'):
                        slip_employer_contrib += amt
                    elif not has_er_epf and code in ('EPS', 'EPF_SHARE'):
                        slip_employer_contrib += amt

                tot_employer_cost += slip_employer_contrib
                tot_er_epf += slip_er_epf
                tot_er_esic += slip_er_esic
                tot_er_lwf += slip_er_lwf

                for wd in slip.worked_days_line_ids:
                    tot_hours += float(wd.number_of_hours or 0.0)
                    tot_days += float(wd.number_of_days or 0.0)

            rec.total_payroll_cost = (tot_gross + tot_employer_cost) if (tot_gross > 0 or tot_employer_cost > 0) else tot_net
            rec.total_gross_pay = tot_gross
            rec.total_net_pay = tot_net
            rec.total_net_paid = tot_net_paid
            rec.total_net_payable = tot_net_payable
            rec.total_basic_wage = tot_basic
            rec.avg_net_wage = (tot_net / len(slips)) if slips else 0.0
            rec.avg_basic_wage = (tot_basic / len(slips)) if slips else 0.0
            rec.avg_hours_per_day = round(tot_hours / tot_days, 1) if tot_days > 0 else 8.0
            rec.fte_count = float(len(slips)) if slips else float(tot_emp)
            rec.tds_this_month = tot_tds
            rec.epf_total_liability = tot_epf
            rec.epf_ee_liability = tot_ee_epf
            rec.esic_total_liability = tot_esi
            rec.esic_ee_liability = tot_ee_esi
            rec.pt_total_liability = tot_pt
            rec.lwf_total_liability = tot_lwf
            rec.epf_employer_liability = tot_er_epf
            rec.epf_er_share_amount = tot_er_epf_share
            rec.epf_er_eps_amount = tot_er_eps
            rec.epf_er_edli_amount = tot_er_edli
            rec.epf_er_admin_amount = tot_er_admin
            rec.esic_employer_liability = tot_er_esic
            rec.lwf_employer_liability = tot_er_lwf
            rec.total_employer_statutory_liability = tot_er_epf + tot_er_edli + tot_er_admin + tot_er_esic + tot_er_lwf
            rec.total_statutory_liability = tot_tds + tot_epf + tot_esi + tot_pt + tot_lwf

            # YTD TDS computation for FY
            fy_start = rec.financial_year_id.start_date if rec.financial_year_id else date(year, 4, 1)
            ytd_slips = self.env['hr.payslip'].search([
                ('date_from', '>=', fy_start),
                ('date_to', '<=', month_end),
                ('state', 'in', ('done', 'paid')),
            ] + company_domain)
            ytd_slips_by_emp_period = {}
            state_priority = {'paid': 2, 'done': 1}
            for ys in ytd_slips.sorted(key=lambda s: (state_priority.get(s.state, 0), -(s.id or 0)), reverse=True):
                if getattr(ys, 'has_duplicate_payslip', False):
                    continue
                key = (ys.employee_id.id, ys.date_from)
                if key not in ytd_slips_by_emp_period:
                    ytd_slips_by_emp_period[key] = ys
            ytd_tds_val = 0.0
            for ys in ytd_slips_by_emp_period.values():
                for line in ys.line_ids:
                    if (line.code or '').upper() in ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS'):
                        ytd_tds_val += abs(float(line.total or 0.0))
            rec.tds_ytd_total = ytd_tds_val

            # Tax Declarations & Regime Distribution
            decl_model = self.env['tds.employee.declaration']
            rec.pending_declarations_count = decl_model.search_count(
                self._pending_declaration_domain(rec.financial_year_id)
            )
            rec.old_regime_count = self.env['hr.employee'].search_count([
                ('active', '=', True),
                ('hds_in_tax_regime', '=', 'old')
            ])
            rec.new_regime_count = self.env['hr.employee'].search_count([
                ('active', '=', True),
                ('hds_in_tax_regime', '=', 'new')
            ])

            # Total Action Required Items
            rec.pending_actions_count = rec.missing_pan_count + rec.missing_bank_count + rec.pending_declarations_count + rec.attendance_pending_count + rec.missing_salary_count

    @api.onchange('payroll_month_num', 'financial_year_id')
    def _onchange_period_controls(self):
        self._compute_dashboard_metrics()
        self._compute_dashboard_html()

    @api.model
    def _employees_without_contract(self, month_start, month_end):
        """Active employees with no contract running on any day of the payroll month.

        A contract runs in the month when one of the employee's versions has
        contract_date_start <= month_end and (no contract_date_end or contract_date_end >= month_start).
        Returns (employees, info) where info maps employee id -> (reason, date):
        'none' (never had a contract), 'ended' (last contract ended before the month)
        or 'future' (next contract starts after the month).
        """
        employees = self.env['hr.employee'].search([('active', '=', True)])
        if not employees:
            return employees, {}
        Version = self.env['hr.version'].sudo()
        running = Version.search([
            ('employee_id', 'in', employees.ids),
            ('contract_date_start', '!=', False),
            ('contract_date_start', '<=', month_end),
            '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', month_start),
        ])
        missing = employees - running.employee_id
        info = {}
        if missing:
            contracts = Version.search([
                ('employee_id', 'in', missing.ids),
                ('contract_date_start', '!=', False),
            ])
            for emp in missing:
                emp_contracts = contracts.filtered(lambda v, emp=emp: v.employee_id == emp)
                future = [v.contract_date_start for v in emp_contracts if v.contract_date_start > month_end]
                ended = [v.contract_date_end for v in emp_contracts if v.contract_date_end and v.contract_date_end < month_start]
                if future:
                    info[emp.id] = ('future', min(future))
                elif ended:
                    info[emp.id] = ('ended', max(ended))
                else:
                    info[emp.id] = ('none', False)
        return missing, info

    @api.model
    def _leave_encashment_model(self):
        """Leave encashment requests model, or None when the current user cannot read it
        (the dashboard section is then hidden instead of raising an access error)."""
        if 'hds.leave.encashment.request' not in self.env:
            return None
        model = self.env['hds.leave.encashment.request']
        try:
            model.check_access('read')
        except AccessError:
            return None
        return model

    @api.model
    def _leave_encashment_domain(self, states=None, date_from=None, date_to=None):
        """Leave encashment requests of the selected companies raised in the payroll month
        (request date between date_from and date_to), optionally limited to some statuses.
        Shared by the dashboard section and its click-through lists so both always agree."""
        domain = [('company_id', 'in', self.env.companies.ids)]
        if states:
            domain.append(('state', 'in', list(states)))
        if date_from:
            domain.append(('request_date', '>=', date_from))
        if date_to:
            domain.append(('request_date', '<=', date_to))
        return domain

    @api.model
    def _relieving_employees(self, month_start, month_end):
        """Employees relieving in the payroll month, for the Final Settlement Planner.

        Relieving date (first available, in this priority):
          1. resignation approved last working day, 2. resignation requested last working day,
          3. employee departure date, 4. notice period end date,
          5. contract end date (only when no later contract follows it, i.e. not renewed).
        Archived employees are included (they may already be archived but still need settling).

        Returns a list of dicts sorted by relieving date:
          employee, lwd, lwd_source, sources [(label, date)], resignation, settlement,
          status ('not_started' | 'draft' | 'approved' | 'paid').
        """
        Employee = self.env['hr.employee'].with_context(active_test=False)
        company_ids = self.env.companies.ids
        in_month = lambda d: bool(d) and month_start <= d <= month_end
        candidates = {}  # employee id -> {label: date}

        def _add(emp, label, value):
            if emp and in_month(value) and (not emp.company_id or emp.company_id.id in company_ids):
                candidates.setdefault(emp.id, {})[label] = value

        # 1-2. Resignations (not cancelled)
        resignations = {}
        if 'hr.resignation' in self.env:
            Resignation = self.env['hr.resignation']
            try:
                Resignation.check_access('read')
                res_records = Resignation.search([
                    ('state', '!=', 'cancel'),
                    ('company_id', 'in', company_ids),
                    '|',
                    '&', ('approved_revealing_date', '>=', month_start), ('approved_revealing_date', '<=', month_end),
                    '&', ('approved_revealing_date', '=', False),
                    '&', ('expected_revealing_date', '>=', month_start), ('expected_revealing_date', '<=', month_end),
                ], order='id desc')
            except AccessError:
                res_records = Resignation
            for res in res_records:
                emp = res.employee_id.with_context(active_test=False)
                if emp.id in resignations:
                    continue
                resignations[emp.id] = res
                if res.approved_revealing_date:
                    _add(emp, 'Resignation (approved LWD)', res.approved_revealing_date)
                else:
                    _add(emp, 'Resignation (requested LWD)', res.expected_revealing_date)

        # 3-4. Departure date / notice period end on the employee
        emp_domain = [('company_id', 'in', company_ids)]
        dep_domain = [('departure_date', '>=', month_start), ('departure_date', '<=', month_end)]
        for emp in Employee.search(emp_domain + dep_domain):
            _add(emp, 'Departure date', emp.departure_date)
        if 'notice_period_end_date' in Employee._fields:
            for emp in Employee.search(emp_domain + [('notice_period_end_date', '>=', month_start), ('notice_period_end_date', '<=', month_end)]):
                _add(emp, 'Notice period ends', emp.notice_period_end_date)

        # 5. Contract end (skip renewed contracts)
        Version = self.env['hr.version'].sudo()
        company_employee_ids = Employee.search(emp_domain).ids  # includes archived employees
        ending = Version.search([
            ('contract_date_end', '>=', month_start),
            ('contract_date_end', '<=', month_end),
            ('employee_id', 'in', company_employee_ids),
        ])
        for version in ending:
            renewed = Version.search_count([
                ('employee_id', '=', version.employee_id.id),
                ('contract_date_start', '>', version.contract_date_end),
            ])
            if not renewed:
                _add(version.employee_id.with_context(active_test=False), 'Contract ends', version.contract_date_end)

        if not candidates:
            return []

        priority = ['Resignation (approved LWD)', 'Resignation (requested LWD)', 'Departure date', 'Notice period ends', 'Contract ends']
        settlements = self.env['final.settlement']
        if 'final.settlement' in self.env:
            try:
                settlements.check_access('read')
                settlements = settlements.search([
                    ('employee_id', 'in', list(candidates)),
                    ('state', '!=', 'cancel'),
                ], order='last_working_day desc, id desc')
            except AccessError:
                settlements = self.env['final.settlement']

        result = []
        employees = Employee.browse(list(candidates))
        for emp in employees:
            dates = candidates[emp.id]
            lwd_source = next(label for label in priority if label in dates)
            lwd = dates[lwd_source]
            emp_settlements = settlements.filtered(lambda s, emp=emp: s.employee_id.id == emp.id)
            # The settlement for this exit: same LWD if any, else the latest one on or after the month start
            settlement = emp_settlements.filtered(lambda s, lwd=lwd: s.last_working_day == lwd)[:1] or \
                emp_settlements.filtered(lambda s: s.last_working_day and s.last_working_day >= month_start)[:1]
            if not settlement:
                status = 'not_started'
            elif settlement.state == 'approved' and settlement.payslip_id.state in ('done', 'paid'):
                status = 'paid'
            elif settlement.state == 'approved':
                status = 'approved'
            else:
                status = 'draft'
            result.append({
                'employee': emp,
                'lwd': lwd,
                'lwd_source': lwd_source,
                'sources': [(label, dates[label]) for label in priority if label in dates],
                'resignation': resignations.get(emp.id),
                'settlement': settlement,
                'status': status,
            })
        result.sort(key=lambda r: (r['lwd'], (r['employee'].name or '').lower()))
        return result

    @api.model
    def _pending_declaration_domain(self, financial_year=None):
        """Tax declarations awaiting verification for the selected tax year and companies.
        Shared by the Action Center count, its card click and the header button."""
        domain = [
            ('state', 'in', ('submitted', 'proof_submitted', 'proof_under_review')),
            ('company_id', 'in', self.env.companies.ids),
        ]
        if financial_year:
            domain.append(('financial_year_id', '=', financial_year.id))
        return domain

    def _month_declaration_domain(self, kind, financial_year, month_start, month_end):
        """Tax declarations of the selected tax year at a stage of the month (Tax Declarations card):
        'pending' - proofs submitted in the month, awaiting HR verification;
        'declared' - plan submitted in the month, awaiting the employee's proofs;
        'draft' - created in the month, not submitted yet."""
        domain = [('company_id', 'in', self.env.companies.ids)]
        if financial_year:
            domain.append(('financial_year_id', '=', financial_year.id))
        in_month = lambda field: [(field, '>=', month_start), (field, '<=', month_end)]
        if kind == 'pending':
            # Proofs submitted before the proof date was recorded: the declaration's submission date
            return domain + [('state', 'in', ('submitted', 'proof_submitted', 'proof_under_review')),
                             '|', '&'] + in_month('proof_submission_date') + [
                             '&', ('proof_submission_date', '=', False)] + in_month('submission_date')
        if kind == 'declared':
            return domain + [('state', '=', 'declared')] + in_month('submission_date')
        next_month = month_end + timedelta(days=1)
        return domain + [('state', '=', 'draft'), ('create_date', '>=', fields.Datetime.to_datetime(month_start)),
                         ('create_date', '<', fields.Datetime.to_datetime(next_month))]

    @api.model
    def _final_settlement_domain(self, month_start, month_end):
        """Final settlements due in the period: not cancelled, last working day in the month,
        within the selected companies. Shared by the KPI counts, the card click and the header
        button so they always agree. None when hudson_in_final_settlement is not installed."""
        if 'final.settlement' not in self.env:
            return None
        return [
            ('state', '!=', 'cancel'),
            ('last_working_day', '>=', month_start),
            ('last_working_day', '<=', month_end),
            ('company_id', 'in', self.env.companies.ids),
        ]

    @api.depends('payroll_month_num', 'financial_year_id')
    def _compute_dashboard_html(self):
        for rec in self:
            rec._compute_dashboard_metrics()
            currency_symbol = rec.currency_id.symbol or '₹'
            month_name = dict(rec._fields['payroll_month_num'].selection).get(rec.payroll_month_num)                 or calendar.month_name[fields.Date.context_today(self).month]
            fy_name = rec.financial_year_id.name if rec.financial_year_id else 'Not set'

            # Fetch New Joiners for selected month
            today = fields.Date.context_today(self)
            m_num = int(rec.payroll_month_num or today.month)
            year = today.year
            if rec.financial_year_id and rec.financial_year_id.start_date:
                fy_s_year = rec.financial_year_id.start_date.year
                fy_e_year = rec.financial_year_id.end_date.year
                year = fy_s_year if m_num >= 4 else fy_e_year

            month_start = date(year, m_num, 1)
            month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])

            # 6-Month Payroll Trend Visualizer Data (Payrun Styled)
            state_priority = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
            company_domain = [('company_id', 'in', self.env.companies.ids)]
            trend_data = []
            for i in range(5, -1, -1):
                t_month = (m_num - i - 1) % 12 + 1
                t_year = year if (m_num - i) > 0 else year - 1
                t_m_name = calendar.month_abbr[t_month]
                t_start = date(t_year, t_month, 1)
                t_end = date(t_year, t_month, calendar.monthrange(t_year, t_month)[1])

                t_domain = [
                    ('date_from', '<=', t_end),
                    ('date_to', '>=', t_start),
                    ('state', 'in', ('paid', 'done')),
                ] + company_domain
                t_all_slips = self.env['hr.payslip'].search(t_domain)
                t_unique = {}
                for s in t_all_slips.sorted(key=lambda s: (state_priority.get(s.state, 0), -(s.id or 0)), reverse=True):
                    if getattr(s, 'has_duplicate_payslip', False):
                        continue
                    key = (s.employee_id.id, s.date_from, s.date_to)
                    if key not in t_unique:
                        t_unique[key] = s

                t_gross = 0.0
                t_er_epf = 0.0
                t_er_esic = 0.0
                t_admin = 0.0
                t_er_lwf = 0.0
                t_worked_days = 0.0

                for s in t_unique.values():
                    gross_val = float(getattr(s, 'gross_amount', None) or getattr(s, 'gross_wage', 0.0) or 0.0)
                    if not gross_val:
                        for line in s.line_ids:
                            if (line.code or '').upper() == 'GROSS':
                                gross_val = abs(float(line.total or 0.0))
                                break
                    if not gross_val:
                        net_val = float(getattr(s, 'net_amount', None) or getattr(s, 'net_wage', 0.0) or 0.0)
                        if not net_val:
                            for line in s.line_ids:
                                if (line.code or '').upper() == 'NET':
                                    net_val = abs(float(line.total or 0.0))
                                    break
                        gross_val = net_val

                    t_gross += gross_val

                    for wd in s.worked_days_line_ids:
                        code = (wd.code or '').upper()
                        if 'SHORT' not in code and 'UNPAID' not in code and 'LOP' not in code:
                            t_worked_days += float(wd.number_of_days or 0.0)

                    codes = set((l.code or '').upper() for l in s.line_ids)
                    has_er_epf = 'EMPLOYER_EPF' in codes or 'ER_PF' in codes

                    for line in s.line_ids:
                        code = (line.code or '').upper()
                        amt = abs(float(line.total or 0.0))
                        if code in ('EMPLOYER_EPF', 'ER_PF'):
                            t_er_epf += amt
                        elif not has_er_epf and code in ('EPS', 'EPF_SHARE'):
                            t_er_epf += amt
                        elif code == 'ESIC_ER':
                            t_er_esic += amt
                        elif code in ('EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                            t_admin += amt
                        elif code == 'LWF_ER':
                            t_er_lwf += amt

                t_cost = t_gross + t_er_epf + t_er_esic + t_admin + t_er_lwf

                trend_data.append({
                    'month_num': t_month,
                    'year': t_year,
                    'month_name': t_m_name,
                    'gross': t_gross,
                    'er_epf': t_er_epf,
                    'er_esic': t_er_esic,
                    'admin': t_admin,
                    'er_lwf': t_er_lwf,
                    'emp_count': len(set(s.employee_id.id for s in t_unique.values())),
                    # Processed payslips (one per employee and period) by state
                    'paid_slip_count': sum(1 for s in t_unique.values() if s.state == 'paid'),
                    'validated_slip_count': sum(1 for s in t_unique.values() if s.state == 'done'),
                    'worked_days': t_worked_days,
                    'avg_days': round(t_worked_days / max(len(set(s.employee_id.id for s in t_unique.values())), 1), 1) if t_unique else 0.0,
                    'cost': t_cost,
                    'is_current': (t_month == m_num and t_year == year),
                    'date_from': str(t_start),
                    'date_to': str(t_end),
                })

            # Current month of the six (header payslip counts)
            trend_current = next((d for d in trend_data if d['is_current']), trend_data[-1] if trend_data else None)

            # ---------- Display helpers (presentation only; every value comes from the computed fields) ----------
            def _pct(part, whole):
                return max(0.0, min(100.0, (part or 0.0) * 100.0 / whole)) if whole else 0.0

            def _money(value):
                return f"{currency_symbol} {(value or 0.0):,.2f}"

            card_click = 'role="button" tabindex="0" onclick="window.hdsCardClick &amp;&amp; window.hdsCardClick(this, \'{0}\')" data-card-type="{0}"'

            # ---------- Odoo list-view building blocks for the dashboard sections ----------
            def _badge(tone, label):
                return f'<span class="hds-o-badge hds-tone-{tone}">{label}</span>'

            def _record_attrs(record_id, model):
                return (f'role="button" tabindex="0" onclick="window.hdsRecordClick &amp;&amp; '
                        f'window.hdsRecordClick(this, \'{record_id}\', \'{model}\')" data-card-type="hr_employee_record" '
                        f'data-record-id="{record_id}" data-record-model="{model}"')

            def _btn(ctype, label, primary=False, title=''):
                title_attr = f' title="{title}"' if title else ''
                return (f'<button type="button" {card_click.format(ctype)}{title_attr} '
                        f'class="btn btn-sm {"btn-primary" if primary else "btn-secondary"} o_hds_dashboard_card_clickable">{label}</button>')

            def _empty(icon, title, hint, tone='green'):
                return (f'<div class="hds-o-empty hds-tone-{tone}"><i class="oi" data-icon="{icon}"></i>'
                        f'<div><b>{title}</b><span>{hint}</span></div></div>')

            def _section(title, sub, actions_html, body_html):
                return f"""<div class="hds-o-sheet hds-o-list-card hds-o-section">
                    <div class="hds-o-section-head">
                        <div>
                            <div class="hds-o-section-title">{title}</div>
                            <div class="hds-o-list-hint">{sub}</div>
                        </div>
                        <div class="hds-o-section-actions">{actions_html}</div>
                    </div>
                    {body_html}
                </div>"""

            ctc = rec.total_payroll_cost
            gross_pct = _pct(rec.total_gross_pay, ctc)
            paid_pct = _pct(rec.total_net_paid, rec.total_net_pay)
            tds_share_pct = _pct(rec.tds_this_month, rec.tds_ytd_total)
            # Government remittance = employer AND employee statutory shares + TDS + PT
            # (EPF EE+ER incl. EDLI/Admin, ESIC EE+ER, LWF EE+ER), i.e. total_statutory_liability.
            statutory_total = rec.total_statutory_liability
            # Areas of the Employee Data Health section
            health_values = [rec.pan_health_pct, rec.bank_health_pct, rec.contact_health_pct]
            health_avg = round(sum(health_values) / len(health_values), 1)

            def _money_html(value):
                """Currency with a muted symbol and smaller paise: <small>₹</small> 183,250<small>.00</small>."""
                whole, _sep, paise = f"{(value or 0.0):,.2f}".partition('.')
                return f'<span class="hds-cur">{currency_symbol}</span>{whole}<span class="hds-dec">.{paise}</span>'

            # Employees without a running contract in the payroll month
            no_contract_emps, no_contract_info = self._employees_without_contract(month_start, month_end)
            nc_reason_meta = {
                'none': ('rose', 'block', 'No contract'),
                'ended': ('orange', 'event_busy', 'Contract ended'),
                'future': ('sky', 'event_upcoming', 'Starts later'),
            }
            nc_total = len(no_contract_emps)
            # Cards (one per reason) are built with the other Odoo cards below

            # Leave encashment requests (Time Off -> Leave Encashment Management)
            encash_model = self._leave_encashment_model()
            leave_encash_html = ''
            if encash_model is not None:
                le_today = fields.Date.context_today(self)
                le_new_since = le_today - timedelta(days=7)

                def _le_stats(states):
                    # Requests raised in the selected payroll month
                    reqs = encash_model.search(self._leave_encashment_domain(states, month_start, month_end))
                    return reqs, sum(reqs.mapped('requested_days')), sum(reqs.mapped('projected_amount'))

                le_pending, le_pending_days, le_pending_amt = _le_stats(('submitted',))
                le_approved, le_approved_days, le_approved_amt = _le_stats(('approved',))
                le_draft, le_draft_days, le_draft_amt = _le_stats(('draft',))
                le_paid, le_paid_days, le_paid_amt = _le_stats(('paid',))
                le_new_count = len(le_pending.filtered(lambda r: r.request_date and r.request_date >= le_new_since))

                # In workflow order: draft, pending approval, approved, paid
                le_tiles = [
                    ('leave_encashment_draft', 'slate', 'edit', 'Draft (not submitted)', le_draft, le_draft_days, le_draft_amt),
                    ('leave_encashment_submitted', 'amber', 'schedule', 'Pending approval', le_pending, le_pending_days, le_pending_amt),
                    ('leave_encashment_approved', 'sky', 'check_circle', 'Approved – awaiting payroll', le_approved, le_approved_days, le_approved_amt),
                    ('leave_encashment_paid', 'green', 'payments', 'Paid / processed', le_paid, le_paid_days, le_paid_amt),
                ]
                le_sub = f"{len(le_pending)} to approve &middot; {len(le_approved)} to process in payroll"
                if le_new_count:
                    le_sub += f" &middot; {le_new_count} new"
                # Section cards (one per request state) are built with the other Odoo cards below

            # Final settlement planner: employees relieving in the payroll month
            relieving_rows = self._relieving_employees(month_start, month_end)
            rel_status_meta = {
                'not_started': ('rose', 'block', 'Settlement not started'),
                'draft': ('amber', 'edit', 'Settlement in draft'),
                'approved': ('sky', 'check_circle', 'Approved – awaiting payment'),
                'paid': ('green', 'payments', 'Settled & paid'),
            }
            rel_counts = {key: 0 for key in rel_status_meta}
            for row in relieving_rows:
                rel_counts[row['status']] += 1

            # Planner cards (one per settlement status) are built with the other Odoo cards below

            # Data completeness grading (also used by the statutory compliance rows)
            def _health_level(value):
                """Display grading of a completeness % -> (tone, label)."""
                if value >= 75:
                    return 'green', 'Healthy'
                if value >= 40:
                    return 'amber', 'Needs work'
                return 'rose', 'Critical'

            # Statutory identifier compliance rings
            # (card type, scheme, identifier, badge tone, complete, missing)
            identifiers = [
                ('epf_status', 'EPF', 'UAN / PF No', 'indigo', rec.epf_complete_count, rec.epf_missing_count),
                ('esic_status', 'ESIC', 'IP Number', 'sky', rec.esic_complete_count, rec.esic_missing_count),
                ('lwf_status', 'LWF', 'Registration', 'purple', rec.lwf_complete_count, rec.lwf_missing_count),
            ]

            # Compliance cards are built with the other Odoo cards below
            ids_done = sum(i[4] for i in identifiers)
            ids_missing = sum(i[5] for i in identifiers)
            ids_pct = _pct(ids_done, ids_done + ids_missing)
            ids_tone, ids_level = _health_level(ids_pct)
            weakest_id = min(identifiers, key=lambda i: _pct(i[4], i[4] + i[5]))

            # ---------- Odoo-style top of the dashboard (header sheet, KPI cards, issue cards, data health list) ----------
            fy_short = (fy_name or '').replace('Tax Year:', '').strip() or fy_name
            processed_emps = trend_current['emp_count'] if trend_current else 0
            paid_slips = trend_current['paid_slip_count'] if trend_current else 0
            validated_slips = trend_current['validated_slip_count'] if trend_current else 0
            # Header "Payslips" field: the month's payslips by stage, as labelled status chips
            slip_chips = [
                ('attendance_exceptions', 'slate', rec.draft_slips_count, 'Draft', 'Payslips still in draft'),
                ('attendance_exceptions', 'amber', rec.verify_slips_count, 'To validate', 'Payslips waiting for validation'),
                ('total_net_pay', 'sky', validated_slips, 'Validated', 'Validated payslips, salary not yet paid'),
                ('total_net_pay', 'green', paid_slips, 'Paid', 'Payslips with salary paid'),
            ]
            slip_chips_html = "".join(
                f'<span {card_click.format(ctype)} class="hds-o-chip hds-tone-{tone}{" is-zero" if not count else ""} o_hds_dashboard_card_clickable" '
                f'title="{tip} &middot; {month_name} {year}"><b>{count}</b>{label}</span>'
                for ctype, tone, count, label, tip in slip_chips
            )

            # Header month navigator: previous / next month (crossing into the adjacent tax year when
            # it exists), a month picker for the selected tax year, and "This Month".
            Fy = self.env['tds.financial.year']
            cur_fy = rec.financial_year_id

            def _fy_of(day):
                if cur_fy and cur_fy.start_date and cur_fy.end_date and cur_fy.start_date <= day <= cur_fy.end_date:
                    return cur_fy
                return Fy.search([('start_date', '<=', day), ('end_date', '>=', day)], limit=1)

            def _nav_call(month, fy):
                return f"window.hdsUpdatePeriod &amp;&amp; window.hdsUpdatePeriod('{month}', {fy.id if fy else 'null'})"

            prev_day = month_start - timedelta(days=1)
            next_day = month_end + timedelta(days=1)
            prev_fy, next_fy = _fy_of(prev_day), _fy_of(next_day)
            nav_today = fields.Date.context_today(self)
            today_fy = Fy.search([('start_date', '<=', nav_today), ('end_date', '>=', nav_today)], limit=1)
            is_current_period = m_num == nav_today.month and year == nav_today.year
            month_labels = dict(rec._fields['payroll_month_num'].selection)
            month_options_html = "".join(
                f'<option value="{num}"{" selected" if num == m_num else ""}>'
                f'{month_labels.get(str(num), num)} {(fy_s_year if num >= 4 else fy_e_year) if cur_fy and cur_fy.start_date else year}</option>'
                for num in (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)
            )
            prev_title = f"Previous month ({prev_day.strftime('%B %Y')})" if prev_fy else 'No tax year configured for the previous month'
            next_title = f"Next month ({next_day.strftime('%B %Y')})" if next_fy else 'No tax year configured for the next month'
            period_nav_html = f"""<div class="hds-o-period-nav" role="group" aria-label="Payroll month">
                        <button type="button" class="btn btn-secondary" title="Go to the current payroll month"
                                {'disabled="disabled"' if is_current_period or not today_fy else f'onclick="{_nav_call(nav_today.month, today_fy)}"'}>This Month</button>
                        <div class="btn-group" role="group">
                            <button type="button" class="btn btn-secondary hds-o-nav-arrow" title="{prev_title}" aria-label="Previous month"
                                    {f'onclick="{_nav_call(prev_day.month, prev_fy)}"' if prev_fy else 'disabled="disabled"'}><i class="oi oi-fw" data-icon="arrow_back_ios_new"></i></button>
                            <select class="form-select hds-o-month-select" aria-label="Payroll month" title="Choose the payroll month"
                                    onchange="window.hdsUpdatePeriod &amp;&amp; window.hdsUpdatePeriod(this.value, null)">{month_options_html}</select>
                            <button type="button" class="btn btn-secondary hds-o-nav-arrow" title="{next_title}" aria-label="Next month"
                                    {f'onclick="{_nav_call(next_day.month, next_fy)}"' if next_fy else 'disabled="disabled"'}><i class="oi oi-fw" data-icon="arrow_forward_ios"></i></button>
                        </div>
                    </div>"""

            def _kpi(ctype, label, badge_html, value_html, bar_pct, bar_tone, foot, extra_attrs=''):
                return f"""<div {card_click.format(ctype)} {extra_attrs} class="hds-o-kpi o_hds_dashboard_card_clickable">
                        <div class="hds-o-kpi-head"><span>{label}</span>{badge_html}</div>
                        <div class="hds-o-kpi-value">{value_html}</div>
                        <div class="hds-o-bar hds-tone-{bar_tone}"><div style="width: {max(0.0, min(100.0, bar_pct)):.1f}%;"></div></div>
                        <div class="hds-o-kpi-foot">{foot}</div>
                    </div>"""

            period_attrs = f'data-month-num="{m_num}" data-year="{year}" data-date-from="{month_start}" data-date-to="{month_end}"'
            # Final settlements due = employees relieving in the month (same rows as the planner), so an
            # employee whose settlement has not been created yet is counted too
            fs_due = len(relieving_rows)
            fs_open = fs_due - rel_counts['paid']
            if rel_counts['not_started']:
                fs_badge = _badge('rose', f"{rel_counts['not_started']} not started")
            elif fs_open:
                fs_badge = _badge('amber', f'{fs_open} pending')
            else:
                fs_badge = _badge('green', 'Clear')
            fs_paid_pct = _pct(rel_counts['paid'], fs_due) if fs_due else 100.0
            kpi_cards_html = (
                _kpi('ctc_breakdown', 'Total Payroll Cost (CTC)', _badge('cyan', 'CTC'), _money_html(ctc),
                     gross_pct, 'purple',
                     f"Gross {_money(rec.total_gross_pay)} + Statutory {_money(rec.total_employer_statutory_liability)}",
                     period_attrs)
                + _kpi('net_breakdown', 'Net Salary',_badge('green' if paid_pct >= 100 else 'amber', f'{paid_pct:.0f}% paid'),
                       _money_html(rec.total_net_pay), paid_pct, 'green',
                       f"Paid {_money(rec.total_net_paid)} &middot; Due {_money(rec.total_net_payable)}", period_attrs)
                + _kpi('govt_deposit', 'Govt Deposit', _badge('indigo', 'Statutory'), _money_html(statutory_total),
                       tds_share_pct, 'indigo',
                       f"TDS this month {_money(rec.tds_this_month)} &middot; YTD TDS {_money(rec.tds_ytd_total)}")
                + _kpi('relieving_employees', 'Final Settlements', fs_badge,
                       f'{fs_due}<span class="hds-dec"> due</span>', fs_paid_pct, 'green',
                       f"Not started {rel_counts['not_started']} &middot; Draft {rel_counts['draft']} &middot; "
                       f"Approved {rel_counts['approved']} &middot; Paid {rel_counts['paid']}")
            )

            def _issue(title, badge_html, btn_ctype, btn_label, btn_primary, note, rows, link, bar_pct, bar_tone, foot):
                rows_html = "".join(f'<div class="hds-o-kv"><span>{k}</span><b>{v}</b></div>' for k, v in rows)
                link_html = f'<span {card_click.format(link[0])} class="hds-o-link o_hds_dashboard_card_clickable">{link[1]}</span>' if link else ''
                return f"""<div class="hds-o-issue">
                        <div class="hds-o-issue-head"><span class="hds-o-issue-title">{title}</span>{badge_html}</div>
                        <div class="hds-o-issue-body">
                            <div class="hds-o-issue-main">
                                <button type="button" {card_click.format(btn_ctype)} class="btn {'btn-primary' if btn_primary else 'btn-secondary'} hds-o-issue-btn o_hds_dashboard_card_clickable">{btn_label}</button>
                                {f'<div class="hds-o-issue-note">{note}</div>' if note else ''}
                            </div>
                            <div class="hds-o-issue-side">{rows_html}{link_html}</div>
                        </div>
                        <div class="hds-o-issue-foot">
                            <div class="hds-o-bar hds-tone-{bar_tone}"><div style="width: {max(0.0, min(100.0, bar_pct)):.1f}%;"></div></div>
                            <span>{foot}</span>
                        </div>
                    </div>"""

            def _plural(count, word):
                return f"{count} {word}{'' if count == 1 else 's'}"

            # PAN and bank details are shown once, in the Employee Data Health section
            active_count = rec.active_employee_count
            # Tax declarations of the selected month, by stage (each count opens its declarations)
            Declaration = self.env['tds.employee.declaration']
            decl_count, decl_declared, decl_draft = (
                Declaration.search_count(self._month_declaration_domain(kind, rec.financial_year_id, month_start, month_end))
                for kind in ('pending', 'declared', 'draft'))

            def _count_link(ctype, count):
                return f'<span {card_click.format(ctype)} class="hds-o-link o_hds_dashboard_card_clickable">{count}</span>'
            # Tax regime of the active employees (same counts as the Statutory Compliance regime card)
            if rec.new_regime_count and rec.old_regime_count:
                tds_regime_badge = _badge('indigo', f'New {rec.new_regime_count} &middot; Old {rec.old_regime_count}')
            elif rec.old_regime_count:
                tds_regime_badge = _badge('indigo', 'Old Regime')
            elif rec.new_regime_count:
                tds_regime_badge = _badge('indigo', 'New Regime')
            else:
                tds_regime_badge = ''
            issues_html = (
                _issue('TDS This Month', tds_regime_badge, 'tds_breakdown',
                         'TDS Slips', False, '',
                         [('TDS this month', _money(rec.tds_this_month)), ('Year to date', _money(rec.tds_ytd_total))],
                         None, tds_share_pct, 'indigo', f'{tds_share_pct:.0f}% of YTD')
                + _issue('Joiners This Month', _badge('sky', 'Joiners'), 'new_joiners',
                         _plural(rec.new_joiners_count, 'Employee'), bool(rec.new_joiners_count), '',
                         [('Joined this month', rec.new_joiners_count), ('Active employees', rec.active_employee_count)],
                         ('new_joiners', 'View joiners'),
                         _pct(rec.new_joiners_count, rec.active_employee_count), 'sky',
                         f'{_pct(rec.new_joiners_count, rec.active_employee_count):.0f}% of active')
                + _issue('Exits This Month', _badge('rose', 'Exits') if rec.exits_count else _badge('green', 'None'), 'exits',
                         _plural(rec.exits_count, 'Employee'), bool(rec.exits_count), '',
                         [('Exits this month', rec.exits_count), ('Final settlements due', fs_due)],
                         ('final_settlements_due', 'Final settlements'),
                         fs_paid_pct, 'purple', f'{fs_due} due')
                + _issue('Tax Declarations', _badge('amber', 'Pending') if decl_count else _badge('green', 'Clear'),
                         'decl_pending', _plural(decl_count, 'Declaration'), bool(decl_count),
                         f'{month_name} {year} &middot; Tax year {escape(fy_short)}',
                         [('Pending verification', _count_link('decl_pending', decl_count)),
                          ('Awaiting proofs', _count_link('decl_declared', decl_declared)),
                          ('Not submitted', _count_link('decl_draft', decl_draft))],
                         None,
                         0.0 if decl_count else 100.0, 'amber' if decl_count else 'green',
                         f'{decl_count} to review' if decl_count else 'Nothing to review')
            )

            # Employee data health as Odoo cards (same layout as the issue cards)
            active_emps_list = self.env['hr.employee'].search([('active', '=', True)])
            # (card type, area, used for, completeness %, missing count, "with" label, "without" label)
            health_rows = [
                ('missing_pan', 'PAN', 'TDS rate, Form 16', rec.pan_health_pct, rec.missing_pan_count,
                 'With PAN', 'Without PAN'),
                ('missing_bank', 'Bank Details', 'Salary advice file', rec.bank_health_pct, rec.missing_bank_count,
                 'With bank account', 'Without bank account'),
                ('contact_health', 'Emergency Contact', 'HR records', rec.contact_health_pct,
                 len(active_emps_list.filtered(lambda e: not self._has_emergency_contact(e))),
                 'With contact', 'Without contact'),
            ]
            weakest = min(health_rows, key=lambda r: r[3])
            healthy_areas = sum(1 for r in health_rows if r[3] >= 75)

            def _health_status(row):
                tone, level = _health_level(row[3])
                if row is weakest and row[3] < 75:
                    return 'rose', 'Weakest'
                return tone, level

            health_cards_html = "".join(
                _issue(area, _badge(*_health_status(row)), ctype, _plural(missing, 'Employee'), bool(missing),
                       '',
                       [(with_label, len(active_emps_list) - missing), (without_label, missing)],
                       (ctype, 'Open employees'), pct, _health_level(pct)[0], f'{pct:.1f}% complete')
                for row in health_rows
                for ctype, area, _used_for, pct, missing, with_label, without_label in [row]
            )
            health_tone = _health_level(health_avg)[0]
            data_health_html = _section(
                'Employee Data Health',
                f'Data completeness <b class="hds-tone-{health_tone}">{health_avg:.0f}%</b> &middot; '
                f'{healthy_areas} of {len(health_rows)} areas healthy &middot; {len(active_emps_list)} active employees',
                '',
                f'<div class="hds-o-issues hds-o-section-cards">{health_cards_html}</div>',
            )

            # Odoo card listing records (employee avatar, name, a detail line under the name), up to 3 then
            # "+N more". Records are employees by default; for other models emp_of gives the employee shown,
            # and link_of(item) -> (record id, model, tooltip) when each item opens a different record.
            def _people_card(title, badge_html, items, date_of, ctype, note, empty_label, bar_tone, total, total_label,
                             noun='Employee', model='hr.employee', emp_of=None, open_title='Open employee', link_of=None):
                shown = items[:3]
                rows = []
                for item in shown:
                    emp = emp_of(item) if emp_of else item
                    rec_id, rec_model, rec_title = link_of(item) if link_of else (item.id, model, open_title)
                    rows.append((f'<span {_record_attrs(rec_id, rec_model)} class="hds-o-kv-emp o_hds_dashboard_card_clickable" title="{rec_title}">'
                                 f'<img src="/web/image/hr.employee/{emp.id}/avatar_128" alt="" loading="lazy"/>'
                                 f'<span class="hds-o-kv-emp-text"><span class="hds-o-link">{escape(emp.name or "")}</span>'
                                 f'<small>{date_of(item)}</small></span></span>', ''))
                if len(items) > len(shown):
                    rows.append((f'<span class="hds-o-muted">+{len(items) - len(shown)} more</span>', ''))
                if not items:
                    rows.append((f'<span class="hds-o-muted">{empty_label}</span>', ''))
                count = len(items)
                return _issue(title, badge_html, ctype, _plural(count, noun), bool(count), note, rows,
                              (ctype, 'View all') if len(items) > len(shown) else None,
                              _pct(count, total), bar_tone, f'{count} of {total} {total_label}')

            # Employees without a running contract: one card per reason (counts only; the button opens
            # the employees of that reason with their contract dates)
            def _nc_card(reason, title, note, empty_label):
                tone = nc_reason_meta[reason][0]
                count = sum(1 for info in no_contract_info.values() if info[0] == reason)
                return _issue(title, _badge(tone, 'Action needed') if count else _badge('green', 'Clear'),
                              f'no_running_contract_{reason}', _plural(count, 'Employee'), bool(count),
                              note if count else empty_label, [], None,
                              _pct(count, active_count), tone if count else 'green', f'{count} of {active_count} active')

            if nc_total:
                nc_body_html = '<div class="hds-o-issues hds-o-section-cards">' + (
                    _nc_card('none', 'No Contract', f'No contract on record, so no payslip for {month_name} {year}',
                             'Every employee has a contract')
                    + _nc_card('ended', 'Contract Ended', f'Last contract ended before {month_name} {year}',
                               'No ended contracts')
                    + _nc_card('future', 'Starts Later', f'First contract starts after {month_name} {year}',
                               'No contracts starting later')
                ) + '</div>'
            else:
                nc_body_html = _empty('check_circle', 'Every active employee has a running contract',
                                      f'All {rec.active_employee_count} active employees are covered for {month_name} {year}.')

            # Final settlement planner: one card per settlement status of the employees relieving this month
            # status -> (card type, title, badge when it has employees, badge when empty, note prefix, empty text)
            rel_cards = [
                ('draft', 'relieving_settlement_draft', 'Settlement In Draft', ('amber', 'To approve'), ('green', 'Clear'),
                 'to review and approve', 'No settlement in draft'),
                ('approved', 'relieving_settlement_approved', 'Approved – To Pay', ('sky', 'To pay'), ('green', 'Clear'),
                 'approved, waiting for payment', 'Nothing waiting for payment'),
                ('paid', 'relieving_settlement_paid', 'Settled &amp; Paid', ('green', 'Done'), ('slate', 'None'),
                 'settled and paid', 'No settlement paid yet'),
            ]
            # Counts only: the button opens the settlements with their amount breakdown
            rel_cards_html = ""
            for status, ctype, title, full_badge, empty_badge, note, empty_label in rel_cards:
                count = sum(1 for r in relieving_rows if r['status'] == status)
                rel_cards_html += _issue(
                    title, _badge(*(full_badge if count else empty_badge)), ctype, _plural(count, 'Employee'), bool(count),
                    note[:1].upper() + note[1:] if count else empty_label, [], None,
                    _pct(count, len(relieving_rows)), rel_status_meta[status][0] if count else empty_badge[0],
                    f'{count} of {len(relieving_rows)} relieving')
            if relieving_rows:
                rel_body_html = f'<div class="hds-o-issues hds-o-section-cards">{rel_cards_html}</div>'
            else:
                rel_body_html = _empty('check_circle', f'No employees relieving in {month_name} {year}',
                                       'Employees whose resignation, notice period, departure or contract ends this month will appear here with their settlement dates.')
            relieving_html = _section(
                'Relieving This Month &bull; Final Settlement Planner',
                f"{len(relieving_rows)} relieving in {month_name} {year} &middot; {rel_counts['draft']} in draft &middot; "
                f"{rel_counts['approved']} to pay &middot; {rel_counts['paid']} paid",
                _btn('relieving_employees', 'View all'),
                rel_body_html,
            )

            # Leave encashment requests of the month: one card per state
            if encash_model is not None:
                le_total = sum(len(tile[4]) for tile in le_tiles)

                # state card type -> (badge when it has requests, badge when empty, note, empty text)
                le_badges = {
                    'leave_encashment_draft': (('slate', 'Not submitted'), ('slate', 'None'),
                                               'Not submitted by the employee yet', 'No draft requests'),
                    'leave_encashment_submitted': (('amber', 'Action needed'), ('green', 'Clear'),
                                                   'Waiting for approval', 'Nothing waiting for approval'),
                    'leave_encashment_approved': (('sky', 'To process'), ('green', 'Clear'),
                                                  'Paid with the next payslip', 'Nothing waiting for payroll'),
                    'leave_encashment_paid': (('green', 'Done'), ('slate', 'None'),
                                              'Paid through the payslip', 'Nothing paid yet'),
                }

                # Counts only: the button opens the requests with their days and amounts
                def _le_card(ctype, tone, _icon, label, reqs, _days, _amount):
                    full_badge, empty_badge, note, empty_label = le_badges[ctype]
                    return _issue(
                        label, _badge(*(full_badge if reqs else empty_badge)), ctype, _plural(len(reqs), 'Request'),
                        bool(reqs), note if reqs else empty_label, [], None,
                        _pct(len(reqs), le_total), tone if reqs else 'slate', f'{len(reqs)} of {le_total} requests')

                if le_total:
                    le_body_html = ('<div class="hds-o-issues hds-o-section-cards hds-o-cards-4">'
                                    + "".join(_le_card(*tile) for tile in le_tiles) + '</div>')
                else:
                    le_body_html = _empty('check_circle', f'No leave encashment requests in {month_name} {year}',
                                          'Requests submitted by employees for this payroll month will appear here for approval.')
                leave_encash_html = _section(
                    f'Leave Encashment Requests &bull; {month_name} {year}',
                    le_sub,
                    _btn('leave_encashment', 'Open Leave Encashment Management',
                         title='Time Off &gt; Management &gt; Leave Encashment Management'),
                    le_body_html,
                )

            no_contract_html = _section(
                'Employees Without Running Contract',
                (f"{nc_total} active employee{'' if nc_total == 1 else 's'} not covered &middot; no payslip can be generated for "
                 f"{'this employee' if nc_total == 1 else 'them'} in {month_name} {year} until a contract covering the month is added")
                if nc_total else f"All active employees are covered for {month_name} {year}",
                _btn('no_running_contract', 'View all'),
                nc_body_html,
            )

            # Statutory compliance: one card per statutory identifier
            weakest_id_pct = _pct(weakest_id[4], weakest_id[4] + weakest_id[5])
            compliance_cards_html = ""
            for ctype, scheme, identifier, _badge_tone, done, missing in identifiers:
                applicable = done + missing
                pct = _pct(done, applicable)
                tone, level = _health_level(pct)
                if not applicable:
                    badge_html = _badge('slate', 'Not applicable')
                elif ctype == weakest_id[0] and pct < 75:
                    badge_html = _badge('rose', 'Weakest')
                else:
                    badge_html = _badge(tone, level)
                compliance_cards_html += _issue(
                    f'{scheme} <span class="hds-o-tag">{identifier}</span>', badge_html, ctype,
                    _plural(missing, 'Employee'), bool(missing),
                    f'{done} of {applicable} applicable employee{"" if applicable == 1 else "s"} complete'
                    if applicable else f'No employee is {scheme}-applicable',
                    [(f'With {identifier}', done), (f'Without {identifier}', missing)],
                    None, pct, tone if applicable else 'slate', f'{pct:.1f}% complete')
            compliance_section_html = _section(
                'Statutory Compliance',
                f'Identifier compliance <b class="hds-tone-{ids_tone}">{ids_pct:.0f}%</b> ({ids_level}) &middot; '
                f'{ids_done} complete &middot; {ids_missing} missing &middot; {rec.active_employee_count} active employees &middot; '
                f'<span {card_click.format(weakest_id[0])} class="hds-o-link o_hds_dashboard_card_clickable">Lowest: {weakest_id[1]} ({weakest_id_pct:.0f}%)</span>',
                '',
                f'<div class="hds-o-issues hds-o-section-cards">{compliance_cards_html}</div>',
            )

            rec.dashboard_html = f"""
            <div class="o_hds_dashboard_root hds-dash hds-odoo" data-hds-dashboard-root="true" data-month-num="{m_num}" data-year="{year}" data-date-from="{month_start}" data-date-to="{month_end}">

                <!-- HEADER SHEET -->
                <div class="hds-o-sheet hds-o-header">
                    <div class="hds-o-header-main">
                        <div class="hds-o-header-title">
                            <small>Payslip Batch</small>
                            <h1>{month_name} {year} Payroll</h1>
                        </div>
                        {period_nav_html}
                    </div>
                    <div class="hds-o-header-fields">
                        <div class="hds-o-field" title="{month_start.strftime('%d/%m/%Y')} &rarr; {month_end.strftime('%d/%m/%Y')}">
                            <span class="hds-o-field-icon"><i class="oi" data-icon="today"></i></span>
                            <div><label>Period</label><span>{month_start.strftime('%d %b')} &rarr; {month_end.strftime('%d %b %Y')}</span></div>
                        </div>
                        <div class="hds-o-field">
                            <span class="hds-o-field-icon"><i class="oi" data-icon="calendar_today"></i></span>
                            <div><label>Tax Year</label><span>{escape(fy_short)}</span></div>
                        </div>
                        <div {card_click.format('active_employee_count')} class="hds-o-field o_hds_dashboard_card_clickable" title="Active employees as of today">
                            <span class="hds-o-field-icon"><i class="oi" data-icon="group"></i></span>
                            <div><label>Employees</label><span class="hds-o-field-link">{rec.active_employee_count} active</span></div>
                        </div>
                        <div class="hds-o-field">
                            <span class="hds-o-field-icon"><i class="oi" data-icon="description"></i></span>
                            <div><label>Payslips</label><div class="hds-o-chips">{slip_chips_html}</div></div>
                        </div>
                    </div>
                </div>

                <!-- KPI CARDS -->
                <div class="hds-o-kpis">
                    {kpi_cards_html}
                </div>

                <!-- ISSUE CARDS -->
                <div class="hds-o-issues hds-o-cards-4">
                    {issues_html}
                </div>

                <!-- EMPLOYEE DATA HEALTH -->
                {data_health_html}

                <!-- RELIEVING THIS MONTH / FINAL SETTLEMENT PLANNER -->
                {relieving_html}

                <!-- EMPLOYEES WITHOUT RUNNING CONTRACT -->
                {no_contract_html}

                <!-- LEAVE ENCASHMENT REQUESTS -->
                {leave_encash_html}

                <!-- STATUTORY COMPLIANCE -->
                {compliance_section_html}

                <!-- INLINE DETAILS CONTAINER -->
                <div id="hds_dashboard_inline_details" class="hds-inline-panel" style="display: none;"></div>

            </div>
            """


    @api.model
    def set_dashboard_period_and_get_html(self, dashboard_id=None, month_num=None, fy_id=None):
        """
        Updates the dashboard singleton with the newly chosen month and/or financial year,
        recalculates all financial metrics, statutory compliance liabilities, and HTML canvas,
        and returns the compiled HTML directly so the frontend can dynamically swap the DOM
        instantly without reloading the browser window.
        """
        rec = self.browse(dashboard_id) if dashboard_id else self.search([], limit=1)
        if not rec:
            rec = self.create({'name': 'Payroll Dashboard'})

        vals = {}
        if month_num is not None and str(month_num).strip():
            clean_m = str(month_num).strip().replace('"', '').replace("'", "")
            if clean_m.isdigit() and 1 <= int(clean_m) <= 12:
                vals['payroll_month_num'] = clean_m

        if fy_id is not None and str(fy_id).strip():
            clean_fy = str(fy_id).strip().replace('"', '').replace("'", "")
            if clean_fy.isdigit() and int(clean_fy) > 0:
                vals['financial_year_id'] = int(clean_fy)

        if vals:
            rec.write(vals)

        self.env.invalidate_all()
        rec._compute_dashboard_metrics()
        rec._compute_dashboard_html()

        return {
            'html': rec.dashboard_html,
            'payroll_month_num': rec.payroll_month_num,
            'financial_year_id': rec.financial_year_id.id if rec.financial_year_id else False,
            'financial_year_name': rec.financial_year_id.name if rec.financial_year_id else '',
            'active_employee_count': rec.active_employee_count,
            'total_gross_pay': rec.total_gross_pay,
            'total_net_pay': rec.total_net_pay,
            'total_payroll_cost': rec.total_payroll_cost,
        }

    @api.model
    def set_dashboard_period(self, dashboard_id=None, month_num=None, fy_id=None):
        """
        Updates the dashboard singleton with the newly chosen month and/or financial year,
        recalculates all financial metrics, statutory compliance liabilities, and HTML canvas,
        and returns the updated data.
        """
        return self.set_dashboard_period_and_get_html(dashboard_id=dashboard_id, month_num=month_num, fy_id=fy_id)

    def action_refresh_dashboard(self):
        self.ensure_one()
        self.env.invalidate_all()
        self._compute_dashboard_metrics()
        self._compute_dashboard_html()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_missing_pan_employees(self):
        return self.get_card_action(card_type='missing_pan')

    def action_view_missing_bank_employees(self):
        return self.get_card_action(card_type='missing_bank')

    def action_view_pending_declarations(self):
        return self.get_card_action(card_type='pending_declarations')

    def action_view_new_joiners(self):
        return self.get_card_action(card_type='new_joiners')

    def write(self, vals):
        res = super().write(vals)
        if 'payroll_month_num' in vals or 'financial_year_id' in vals:
            self.env.invalidate_all()
        return res

    def web_read(self, specification: dict) -> list[dict]:
        self.env.invalidate_all()
        for rec in self:
            rec._compute_dashboard_metrics()
            rec._compute_dashboard_html()
        return super().web_read(specification)

    def read(self, fields=None, load='_classic_read'):
        self.env.invalidate_all()
        for rec in self:
            rec._compute_dashboard_metrics()
            rec._compute_dashboard_html()
        return super().read(fields=fields, load=load)

    @api.model
    def get_card_action(self, dashboard_id=None, card_type=None, month_num=None, fy_id=None, date_from=None, date_to=None):
        """
        Returns an ir.actions.act_window action dict for Odoo web client
        to navigate to the corresponding list view in the current window.
        Odoo breadcrumbs will allow returning to the Payroll Dashboard smoothly.

        date_from / date_to: period of the clicked element itself (e.g. a past month bar in the
        trend chart). When both are valid they replace the dashboard's selected payroll month.
        """
        rec = self.browse(dashboard_id) if dashboard_id else self.search([], limit=1)
        today = fields.Date.context_today(self)
        m_num = int(month_num or (rec.payroll_month_num if rec else today.month) or today.month)

        fy = rec.financial_year_id if (rec and rec.financial_year_id) else (self.env['tds.financial.year'].browse(fy_id) if fy_id else None)
        if not fy:
            fy = self.env['tds.financial.year'].search([('start_date', '<=', today), ('end_date', '>=', today)], limit=1)
        if not fy:
            fy = self.env['tds.financial.year'].search([], order='id desc', limit=1)

        year = today.year
        if fy and getattr(fy, 'start_date', False):
            year = fy.start_date.year if m_num >= 4 else fy.end_date.year

        month_start = date(year, m_num, 1)
        month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])

        # Period of the clicked element (trend chart bar of another month)
        try:
            clicked_from = fields.Date.to_date(date_from) if date_from else None
            clicked_to = fields.Date.to_date(date_to) if date_to else None
        except (TypeError, ValueError):
            clicked_from = clicked_to = None
        if clicked_from and clicked_to and clicked_from <= clicked_to:
            month_start, month_end = clicked_from, clicked_to
            m_num, year = clicked_from.month, clicked_from.year

        month_name = calendar.month_name[m_num]
        active_emps = self.env['hr.employee'].search([('active', '=', True)])

        # 1. Statutory Compliance Dedicated List View
        if card_type in ('epf_liability', 'esic_liability', 'lwf_liability', 'total_employer_statutory', 'edli_admin_liability', 'total_statutory'):
            list_view = self.env.ref('hudson_in_payroll.view_hr_payslip_list_employer_statutory', raise_if_not_found=False)
            views = [[list_view.id, 'list'], [False, 'form']] if list_view else [[False, 'list'], [False, 'form']]
            title_map = {
                'epf_liability': f"Statutory Compliance — EPF (12%) ({month_name} {year})",
                'edli_admin_liability': f"Statutory Compliance — EDLI & EPF Admin (1%) ({month_name} {year})",
                'esic_liability': f"Statutory Compliance — ESIC (4%) ({month_name} {year})",
                'lwf_liability': f"Statutory Compliance — LWF Share ({month_name} {year})",
                'total_employer_statutory': f"Statutory Compliance Summary — Employer Share ({month_name} {year})",
                'total_statutory': f"Total Statutory Compliance Summary ({month_name} {year})",
            }
            period_domain = [
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ]
            if 'company_id' in self.env['hr.payslip']._fields:
                period_domain.append(('company_id', 'in', self.env.companies.ids))
            return {
                'type': 'ir.actions.act_window',
                'name': title_map.get(card_type, f"Statutory Compliance Summary — {month_name} {year}"),
                'res_model': 'hr.payslip',
                'view_mode': 'list,form',
                'views': views,
                'domain': period_domain,
                'target': 'current',
            }

        # Govt Deposit / CTC / TDS: the payslips of the dashboard total, with its breakdown
        breakdown_lists = {
            'govt_deposit': ('hudson_in_payroll.view_hr_payslip_list_govt_deposit', 'Govt Deposit'),
            'ctc_breakdown': ('hudson_in_payroll.view_hr_payslip_list_ctc', 'Total Payroll Cost (CTC)'),
            'tds_breakdown': ('hudson_in_payroll.view_hr_payslip_list_tds', 'TDS This Month'),
            'net_breakdown': ('hudson_in_payroll.view_hr_payslip_list_net', 'Net Salary'),
        }
        if card_type in breakdown_lists:
            view_xmlid, title = breakdown_lists[card_type]
            list_view = self.env.ref(view_xmlid)
            return {
                'type': 'ir.actions.act_window',
                'name': f"{title} — {month_name} {year}",
                'res_model': 'hr.payslip',
                'view_mode': 'list,form',
                'views': [[list_view.id, 'list'], [False, 'form']],
                'domain': [('id', 'in', self._hds_month_payslips(month_start, month_end).ids)],
                'target': 'current',
            }

        # 2. Payslips / Total Payroll Cost / Net Salary / TDS This Month / Liabilities
        if card_type in ('total_payroll_cost', 'total_net_pay', 'tds_this_month', 'tds_withholding', 'pt_liability'):
            title_map = {
                'total_payroll_cost': f"Total Payroll Cost Slips — {month_name} {year}",
                'total_net_pay': f"Net Salary Disbursement — {month_name} {year}",
                'tds_this_month': f"TDS Withholding Slips — {month_name} {year}",
                'tds_withholding': f"TDS Withholding Slips — {month_name} {year}",
                'pt_liability': f"Professional Tax Slips — {month_name} {year}",
            }
            period_domain = [
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ]
            if 'company_id' in self.env['hr.payslip']._fields:
                period_domain.append(('company_id', 'in', self.env.companies.ids))
            return {
                'type': 'ir.actions.act_window',
                'name': title_map.get(card_type, 'Payslips'),
                'res_model': 'hr.payslip',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': period_domain,
                'target': 'current',
            }

        # 2. Draft / Attendance Exceptions -> Payslips to Validate
        if card_type == 'attendance_exceptions':
            # Always the selected payroll month (same domain as draft_slips_count / verify_slips_count),
            # so an empty month opens an empty list instead of every draft payslip of other months.
            company_filter = [('company_id', 'in', self.env.companies.ids)] if 'company_id' in self.env['hr.payslip']._fields else []
            domain = [('date_from', '<=', month_end), ('date_to', '>=', month_start), ('state', 'in', ('draft', 'verify'))] + company_filter
            return {
                'type': 'ir.actions.act_window',
                'name': f"Payslips to Validate — {month_name} {year}",
                'res_model': 'hr.payslip',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        # 3. Missing PAN
        if card_type in ('missing_pan', 'pan_health'):
            missing_emps = active_emps.filtered(lambda e: not self._has_pan(e))
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing PAN',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', missing_emps.ids)],
                'target': 'current',
            }

        # 4. Missing Bank
        if card_type in ('missing_bank', 'bank_health'):
            missing_emps = active_emps.filtered(lambda e: not self._has_bank_account(e))
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing Bank Details',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', missing_emps.ids)],
                'target': 'current',
            }

        # 5. Pending Declarations / TDS YTD
        if card_type in ('pending_declarations', 'tds_ytd'):
            return {
                'type': 'ir.actions.act_window',
                'name': 'Pending Tax Declarations',
                'res_model': 'tds.employee.declaration',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': self._pending_declaration_domain(fy),
                'target': 'current',
            }

        # Tax Declarations card: the declarations of the month at each stage (same as its counts)
        declaration_lists = {
            'decl_pending': ('pending', 'Declarations Pending Verification'),
            'decl_declared': ('declared', 'Declarations Awaiting Proofs'),
            'decl_draft': ('draft', 'Declarations Not Submitted'),
        }
        if card_type in declaration_lists:
            kind, title = declaration_lists[card_type]
            return {
                'type': 'ir.actions.act_window',
                'name': f"{title} — {month_name} {year}",
                'res_model': 'tds.employee.declaration',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': self._month_declaration_domain(kind, fy, month_start, month_end),
                'target': 'current',
            }

        # 6. New Joiners / Exits of the month (same employees as the dashboard counts)
        if card_type in ('new_joiners', 'exits'):
            kind = 'joiners' if card_type == 'new_joiners' else 'exits'
            employees = self._hds_employee_movements(kind, month_start, month_end)
            # By ids, archived leavers included (the web client opens the action without its context)
            domain = [('id', 'in', employees.ids), ('active', 'in', (True, False))]
            return {
                'type': 'ir.actions.act_window',
                'name': f"{'New Joiners' if kind == 'joiners' else 'Exits'} — {month_name} {year}",
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        # 7. Final Settlements
        if card_type and card_type.startswith('leave_encashment'):
            encash_model = self._leave_encashment_model()
            if encash_model is not None:
                state_map = {
                    'leave_encashment_submitted': (('submitted',), 'Pending Approval'),
                    'leave_encashment_approved': (('approved',), 'Approved — Awaiting Payroll'),
                    'leave_encashment_draft': (('draft',), 'Draft'),
                    'leave_encashment_paid': (('paid',), 'Paid'),
                }
                states, label = state_map.get(card_type, (None, None))
                period = f"{month_name} {year}"
                return {
                    'type': 'ir.actions.act_window',
                    'name': f"Leave Encashment Requests — {label} ({period})" if label else f"Leave Encashment Requests — {period}",
                    'res_model': 'hds.leave.encashment.request',
                    'view_mode': 'list,form',
                    'views': [[self.env.ref('hudson_in_payroll.view_hds_leave_encashment_request_list_breakdown').id, 'list'],
                              [False, 'form']],
                    'domain': self._leave_encashment_domain(states, month_start, month_end),
                    'target': 'current',
                }

        if card_type and card_type.startswith('relieving'):
            rows = self._relieving_employees(month_start, month_end)
            period = f"{month_name} {year}"
            if card_type in ('relieving_settlement_draft', 'relieving_settlement_approved', 'relieving_settlement_paid'):
                status = card_type.rsplit('_', 1)[-1]
                settlement_ids = [r['settlement'].id for r in rows if r['status'] == status and r['settlement']]
                labels = {'draft': 'Draft', 'approved': 'Approved — Awaiting Payment', 'paid': 'Paid'}
                # Amount breakdown list (Final Settlement module)
                breakdown_view = self.env.ref('hudson_in_final_settlement.view_final_settlement_list_breakdown',
                                              raise_if_not_found=False)
                return {
                    'type': 'ir.actions.act_window',
                    'name': f"Final Settlements {labels[status]} — Relieving {period}",
                    'res_model': 'final.settlement',
                    'view_mode': 'list,form',
                    'views': [[breakdown_view.id if breakdown_view else False, 'list'], [False, 'form']],
                    'domain': [('id', 'in', settlement_ids)],
                    'target': 'current',
                }
            if card_type == 'relieving_not_started':
                emp_ids = [r['employee'].id for r in rows if r['status'] == 'not_started']
                name = f"Relieving {period} — Settlement Not Started"
            else:
                emp_ids = [r['employee'].id for r in rows]
                name = f"Employees Relieving — {period}"
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                # archived (already relieved) employees are included
                'domain': [('id', 'in', emp_ids), ('active', 'in', [True, False])],
                'target': 'current',
            }

        if card_type and card_type.startswith('no_running_contract'):
            no_contract, no_contract_info = self._employees_without_contract(month_start, month_end)
            reason = card_type.removeprefix('no_running_contract').lstrip('_')
            titles = {'none': 'No Contract', 'ended': 'Contract Ended', 'future': 'Contract Starts Later'}
            if reason in titles:
                no_contract = no_contract.filtered(lambda emp: no_contract_info[emp.id][0] == reason)
            list_view = self.env.ref('hudson_in_payroll.view_hr_employee_list_contract_status')
            return {
                'type': 'ir.actions.act_window',
                'name': (f"{titles[reason]} — {month_name} {year}" if reason in titles
                         else f"Employees Without Running Contract — {month_name} {year}"),
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[list_view.id, 'list'], [False, 'form']],
                'domain': [('id', 'in', no_contract.ids)],
                'target': 'current',
            }

        if card_type == 'final_settlements_due':
            settlement_domain = self._final_settlement_domain(month_start, month_end)
            if settlement_domain is not None:
                return {
                    'type': 'ir.actions.act_window',
                    'name': f"Final Settlements Due — {month_name} {year}",
                    'res_model': 'final.settlement',
                    'view_mode': 'list,form',
                    'views': [[False, 'list'], [False, 'form']],
                    'domain': settlement_domain,
                    'target': 'current',
                }
            return {
                'type': 'ir.actions.act_window',
                'name': 'Exited / Inactive Employees',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('active', '=', False)],
                'target': 'current',
            }

        # 8. Tax Regimes
        if card_type == 'old_regime':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees in Old Tax Regime',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': ['&', ('active', '=', True), ('hds_in_tax_regime', '=', 'old')],
                'target': 'current',
            }
        if card_type == 'new_regime':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees in New Tax Regime Income-tax Act, 2025 — Section 202(1)',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': ['&', ('active', '=', True), ('hds_in_tax_regime', '=', 'new')],
                'target': 'current',
            }

        # 9. Statutory Applicability (EPF / ESIC / LWF / Readiness - Filter Missing Only)
        if card_type == 'epf_status':
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            epf_missing = active_emps.filtered(lambda e: getattr(e, 'hds_in_epf_applicable', False) and not comp_service.validate_employee_epf(e)[0])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing EPF UAN',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', epf_missing.ids)],
                'target': 'current',
            }
        if card_type == 'esic_status':
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            esic_missing = active_emps.filtered(lambda e: getattr(e, 'hds_in_esic_applicable', False) and not comp_service.validate_employee_esic(e)[0])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing ESIC IP Number',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', esic_missing.ids)],
                'target': 'current',
            }
        if card_type == 'lwf_status':
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            lwf_missing = active_emps.filtered(lambda e: getattr(e, 'hds_in_lwf_applicable', False) and not comp_service.validate_employee_lwf(e)[0])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing LWF Registration',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', lwf_missing.ids)],
                'target': 'current',
            }
        if card_type in ('readiness_status', 'statutory_errors'):
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            error_emps = active_emps.filtered(lambda e: not comp_service.validate_employee_all(e)['is_compliant'])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees with Statutory Data Errors',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', error_emps.ids)],
                'target': 'current',
            }

        # 10. Aadhaar / Emergency Contact Health
        if card_type == 'aadhaar_health':
            missing_emps = active_emps.filtered(lambda e: not self._has_aadhaar(e))
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing Aadhaar',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', missing_emps.ids)],
                'target': 'current',
            }
        if card_type == 'contact_health':
            missing_emps = active_emps.filtered(lambda e: not self._has_emergency_contact(e))
            return {
                'type': 'ir.actions.act_window',
                'name': 'Employees Missing Emergency Contact',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', missing_emps.ids)],
                'target': 'current',
            }

        # 11. General pending actions / Default Active Employees
        return {
            'type': 'ir.actions.act_window',
            'name': 'Active Employees',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('active', '=', True)],
            'target': 'current',
        }

    @api.model
    def get_card_details(self, dashboard_id=None, card_type=None, month_num=None, fy_id=None):
        """
        Fetches structured records for the clicked dashboard card to display inline
        on the current page without navigating to a new page.
        """
        if isinstance(dashboard_id, str) and not card_type:
            card_type = dashboard_id
            dashboard_id = self.id if self else None
        rec = self.browse(dashboard_id) if (isinstance(dashboard_id, int) and dashboard_id) else (self if self and len(self) == 1 else self.search([], limit=1))
        today = fields.Date.context_today(self)
        m_num = int(month_num or (rec.payroll_month_num if rec else today.month) or today.month)

        fy = rec.financial_year_id if (rec and rec.financial_year_id) else (self.env['tds.financial.year'].browse(fy_id) if fy_id else None)
        if not fy:
            fy = self.env['tds.financial.year'].search([('start_date', '<=', today), ('end_date', '>=', today)], limit=1)
        if not fy:
            fy = self.env['tds.financial.year'].search([], order='id desc', limit=1)

        year = today.year
        if fy and getattr(fy, 'start_date', False):
            year = fy.start_date.year if m_num >= 4 else fy.end_date.year

        month_start = date(year, m_num, 1)
        month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])
        month_name = calendar.month_name[m_num]
        currency_symbol = (rec.currency_id.symbol if rec and rec.currency_id else self.env.company.currency_id.symbol) or '₹'

        emp_model = self.env['hr.employee']
        active_emps = emp_model.search([('active', '=', True)])

        columns = []
        rows = []
        title = "Details"
        badge = ""

        # 1. Payslips / Total Payroll Cost / Net Salary
        if card_type in ('total_payroll_cost', 'total_net_pay', 'payslips'):
            title = f"Total Payroll Cost Slips — {month_name} {year}" if card_type == 'total_payroll_cost' else f"Net Salary Disbursement — {month_name} {year}"
            period_domain = [
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ]
            if 'company_id' in self.env['hr.payslip']._fields:
                period_domain.append(('company_id', 'in', self.env.companies.ids))
            slips = self.env['hr.payslip'].search(period_domain, order='date_to desc, id desc')
            badge = f"{len(slips)} Payslips"
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'number', 'label': 'Slip Ref'},
                {'key': 'period', 'label': 'Period'},
                {'key': 'basic', 'label': 'Basic'},
                {'key': 'gross', 'label': 'Gross Wage'},
                {'key': 'net', 'label': 'Net Wage'},
                {'key': 'state', 'label': 'State'},
                {'key': 'action', 'label': 'Action'}
            ]
            for s in slips[:100]:
                basic_val = float(getattr(s, 'basic_wage', 0.0) or 0.0)
                gross_val = float(getattr(s, 'gross_amount', None) or getattr(s, 'gross_wage', 0.0) or 0.0)
                net_val = float(getattr(s, 'net_amount', None) or getattr(s, 'net_wage', 0.0) or 0.0)
                state_lbl = dict(s._fields['state'].selection).get(s.state, s.state) if 'state' in s._fields else s.state
                rows.append({
                    'id': s.id,
                    'model': 'hr.payslip',
                    'cells': {
                        'employee': s.employee_id.name if s.employee_id else 'N/A',
                        'number': s.number or s.name or 'Draft',
                        'period': f"{s.date_from.strftime('%d %b')} - {s.date_to.strftime('%d %b')}" if s.date_from and s.date_to else '',
                        'basic': f"{currency_symbol} {basic_val:,.2f}",
                        'gross': f"{currency_symbol} {gross_val:,.2f}",
                        'net': f"<b>{currency_symbol} {net_val:,.2f}</b>",
                        'state': f"<span class='badge bg-secondary'>{state_lbl}</span>",
                        'action': 'View Slip'
                    },
                    'action_label': 'View Slip'
                })

        # 2. Active Workforce
        elif card_type in ('active_employee_count', 'workforce'):
            title = "Active Workforce Overview"
            badge = f"{len(active_emps)} Employees"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'job', 'label': 'Job Position'},
                {'key': 'pan', 'label': 'PAN Status'},
                {'key': 'bank', 'label': 'Bank Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for e in active_emps[:100]:
                has_pan = bool(getattr(e, 'hds_in_pan', False) or getattr(e, 'pan_no', False) or getattr(e, 'pan', False))
                has_bank = self._has_bank_account(e)
                rows.append({
                    'id': e.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': e.name,
                        'dept': e.department_id.name if e.department_id else '-',
                        'job': e.job_id.name if e.job_id else '-',
                        'pan': '<span class="text-success fw-semibold">✔ Valid</span>' if has_pan else '<span class="text-danger fw-semibold">✖ Missing</span>',
                        'bank': '<span class="text-success fw-semibold">✔ Registered</span>' if has_bank else '<span class="text-warning fw-semibold">✖ Missing</span>',
                        'action': 'View Profile'
                    },
                    'action_label': 'View Profile'
                })

        # 3. Missing PAN
        elif card_type in ('missing_pan', 'pan_health'):
            missing = active_emps.filtered(lambda e: not self._has_pan(e))
            title = "Employees Missing PAN (Action Required)"
            badge = f"{len(missing)} Employees"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'job', 'label': 'Job Position'},
                {'key': 'impact', 'label': 'Statutory Impact'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = [{
                'id': e.id,
                'model': 'hr.employee',
                'cells': {
                    'name': e.name,
                    'dept': e.department_id.name if e.department_id else '-',
                    'job': e.job_id.name if e.job_id else '-',
                    'impact': '<span class="text-danger fw-bold">20% Flat TDS (u/s 206AA)</span>',
                    'action': 'Add PAN'
                },
                'action_label': 'Add PAN'
            } for e in missing]

        # 4. Missing Bank Details
        elif card_type in ('missing_bank', 'bank_health'):
            missing = active_emps.filtered(lambda e: not self._has_bank_account(e))
            title = "Employees Missing Bank Details (Action Required)"
            badge = f"{len(missing)} Employees"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'job', 'label': 'Job Position'},
                {'key': 'impact', 'label': 'Disbursement Impact'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = [{
                'id': e.id,
                'model': 'hr.employee',
                'cells': {
                    'name': e.name,
                    'dept': e.department_id.name if e.department_id else '-',
                    'job': e.job_id.name if e.job_id else '-',
                    'impact': '<span class="text-warning fw-bold">Salary Advice Batch Blocked</span>',
                    'action': 'Add Bank Details'
                },
                'action_label': 'Add Bank Details'
            } for e in missing]

        # 5. Pending Declarations
        elif card_type == 'pending_declarations':
            title = "Pending Tax Declarations"
            decls = self.env['tds.employee.declaration'].search([
                ('state', 'in', ('submitted', 'proof_submitted', 'proof_under_review'))
            ], order='id desc')
            badge = f"{len(decls)} Pending"
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'fy', 'label': 'Financial Year'},
                {'key': 'regime', 'label': 'Regime'},
                {'key': 'total', 'label': 'Total Declared'},
                {'key': 'state', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = [{
                'id': d.id,
                'model': 'tds.employee.declaration',
                'cells': {
                    'employee': d.employee_id.name if d.employee_id else '-',
                    'fy': d.financial_year_id.name if d.financial_year_id else '-',
                    'regime': (dict(d._fields['tax_regime'].selection).get(d.tax_regime) if 'tax_regime' in d._fields else d.tax_regime) or 'N/A',
                    'total': f"{currency_symbol} {float(getattr(d, 'total_declared_amount', 0.0) or getattr(d, 'total_verified_amount', 0.0) or 0.0):,.2f}",
                    'state': f"<span class='badge bg-warning text-dark'>{d.state}</span>",
                    'action': 'Review Declaration'
                },
                'action_label': 'Review Declaration'
            } for d in decls]

        # 6. Payslips Pending Validation (Draft & To Validate)
        elif card_type == 'attendance_exceptions':
            title = f"Payslips to Validate — {month_name} {year}"
            company_filter = [('company_id', 'in', self.env.companies.ids)] if 'company_id' in self.env['hr.payslip']._fields else []
            slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', 'in', ('draft', 'verify')),
            ] + company_filter)

            draft_count = len(slips.filtered(lambda s: s.state == 'draft'))
            verify_count = len(slips.filtered(lambda s: s.state == 'verify'))
            badge = f"Draft: {draft_count} | To Validate: {verify_count}"
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'number', 'label': 'Slip Ref'},
                {'key': 'period', 'label': 'Period'},
                {'key': 'status', 'label': 'Stage'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = [{
                'id': s.id,
                'model': 'hr.payslip',
                'cells': {
                    'employee': s.employee_id.name if s.employee_id else '-',
                    'number': s.number or s.name or 'Draft',
                    'period': f"{s.date_from.strftime('%d %b')} - {s.date_to.strftime('%d %b')}" if s.date_from and s.date_to else '',
                    'status': f"<span class='badge' style='background: {'#64748b' if s.state == 'draft' else '#8b5cf6'}; color: #fff; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;'>{'Draft' if s.state == 'draft' else 'To Validate'}</span>",
                    'action': 'Verify / Confirm'
                },
                'action_label': 'Verify / Confirm'
            } for s in slips]

        # 7. Final Settlements Due
        elif card_type == 'final_settlements_due':
            title = f"Final Settlements Due — {month_name} {year}"
            settlements = self.env['final.settlement'] if 'final.settlement' in self.env else []
            if 'final.settlement' in self.env:
                settlements = self.env['final.settlement'].search([
                    ('state', '!=', 'cancel'),
                    ('last_working_day', '>=', month_start),
                    ('last_working_day', '<=', month_end),
                ], order='last_working_day desc')
            badge = f"{len(settlements)} Settlements Due"
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'lwd', 'label': 'Last Working Day'},
                {'key': 'net', 'label': 'Net Settlement'},
                {'key': 'state', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for fs in settlements:
                net_amt = float(getattr(fs, 'net_payable', None) or getattr(fs, 'total_settlement', 0.0) or 0.0)
                st = dict(fs._fields['state'].selection).get(fs.state, fs.state) if 'state' in fs._fields else fs.state
                rows.append({
                    'id': fs.id,
                    'model': 'final.settlement',
                    'cells': {
                        'employee': fs.employee_id.name if fs.employee_id else '-',
                        'lwd': fs.last_working_day.strftime('%d %b %Y') if fs.last_working_day else '-',
                        'net': f"<b>{currency_symbol} {net_amt:,.2f}</b>",
                        'state': f"<span class='badge bg-secondary'>{st}</span>",
                        'action': 'Review Settlement'
                    },
                    'action_label': 'Review Settlement'
                })

        # 8. New Joiners
        elif card_type == 'new_joiners':
            title = f"New Joiners — {month_name} {year}"
            emp_fields = emp_model._fields
            join_field = next((f for f in ('joining_date', 'date_of_joining', 'hds_in_doj', 'first_contract_date', 'contract_date_start', 'create_date') if f in emp_fields), None)
            joiners = emp_model.search([
                (join_field, '>=', month_start),
                (join_field, '<=', month_end),
            ], order=f'{join_field} desc') if join_field else emp_model
            badge = f"{len(joiners)} Joiners"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'doj', 'label': 'Joining Date'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'pan', 'label': 'PAN Status'},
                {'key': 'bank', 'label': 'Bank Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for j in joiners:
                j_date_val = getattr(j, join_field, False) if join_field else False
                j_date = j_date_val.strftime('%d %b %Y') if (j_date_val and hasattr(j_date_val, 'strftime')) else '-'
                has_pan = bool(getattr(j, 'hds_in_pan', False) or getattr(j, 'pan_no', False) or getattr(j, 'pan', False))
                has_bank = self._has_bank_account(j)
                rows.append({
                    'id': j.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': j.name,
                        'doj': j_date,
                        'dept': j.department_id.name if j.department_id else '-',
                        'pan': '<span class="text-success">✔ Complete</span>' if has_pan else '<span class="text-danger fw-bold">✖ Missing</span>',
                        'bank': '<span class="text-success">✔ Complete</span>' if has_bank else '<span class="text-warning fw-bold">✖ Missing</span>',
                        'action': 'View Profile'
                    },
                    'action_label': 'View Profile'
                })

        # 9. All Pending Actions
        elif card_type == 'pending_actions':
            title = "All Pending Verification & Compliance Issues"
            for e in active_emps:
                issues = []
                has_pan = bool(getattr(e, 'hds_in_pan', False) or getattr(e, 'pan_no', False) or getattr(e, 'pan', False))
                has_bank = self._has_bank_account(e)
                if not has_pan:
                    issues.append('Missing PAN')
                if not has_bank:
                    issues.append('Missing Bank Details')
                if issues:
                    rows.append({
                        'id': e.id,
                        'model': 'hr.employee',
                        'cells': {
                            'name': e.name,
                            'dept': e.department_id.name if e.department_id else '-',
                            'issues': ", ".join(issues),
                            'severity': '<span class="badge bg-danger">High</span>' if 'Missing PAN' in issues else '<span class="badge bg-warning text-dark">Medium</span>',
                            'action': 'Fix Now'
                        },
                        'action_label': 'Fix Now'
                    })
            badge = f"{len(rows)} Issues Pending"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'issues', 'label': 'Pending Issue(s)'},
                {'key': 'severity', 'label': 'Severity'},
                {'key': 'action', 'label': 'Action'}
            ]

        # 10. EPF Status / Missing
        elif card_type in ('epf_status', 'epf_missing', 'epf_complete'):
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            epf_emps = active_emps.filtered(lambda e: getattr(e, 'hds_in_epf_applicable', False))
            title = "Employees Missing EPF (UAN / PF No)"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'uan', 'label': 'UAN Number'},
                {'key': 'pf_no', 'label': 'PF Code / No'},
                {'key': 'validity', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for e in epf_emps:
                valid, reason = comp_service.validate_employee_epf(e)
                if valid:
                    continue
                uan = getattr(e, 'hds_in_uan', '') or getattr(e, 'uan', '') or '-'
                pf = getattr(e, 'hds_in_pf_no', '') or getattr(e, 'pf_no', '') or '-'
                rows.append({
                    'id': e.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': e.name,
                        'uan': uan,
                        'pf_no': pf,
                        'validity': f'<span class="text-danger fw-bold">✖ {reason}</span>',
                        'action': 'Update EPF'
                    },
                    'action_label': 'Update EPF'
                })
            badge = f"{len(rows)} Employees Missing UAN"

        # Dedicated EPF Contribution & Liability Drilldown
        elif card_type in ('epf_liability', 'edli_admin_liability'):
            title = f"EPF Contribution & Statutory Liability — {month_name} {year}"
            period_slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ], order='id desc')
            seen_emp = set()
            slips = []
            for s in period_slips:
                if s.employee_id.id not in seen_emp:
                    seen_emp.add(s.employee_id.id)
                    slips.append(s)
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'basic', 'label': 'Basic / PF Wage'},
                {'key': 'ee_epf', 'label': 'EE Share (12%)'},
                {'key': 'er_epf', 'label': 'ER Share (12%)'},
                {'key': 'edli_admin', 'label': 'Admin & EDLI (1%)'},
                {'key': 'total', 'label': 'Total EPF Dues'},
                {'key': 'action', 'label': 'Action'}
            ]
            for s in slips:
                ee_p = 0.0
                er_p = 0.0
                admin_edli = 0.0
                basic_w = 0.0
                for l in s.line_ids:
                    c = (l.code or '').upper()
                    amt = abs(float(l.total or 0.0))
                    if c == 'BASIC': basic_w = amt
                    elif c in ('PF', 'EPF', 'EE_PF'): ee_p += amt
                    elif c in ('EMPLOYER_EPF', 'ER_PF', 'EPS', 'EPF_SHARE'): er_p += amt
                    elif c in ('EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'): admin_edli += amt
                if ee_p > 0 or er_p > 0 or admin_edli > 0:
                    rows.append({
                        'id': s.id,
                        'model': 'hr.payslip',
                        'cells': {
                            'employee': s.employee_id.name if s.employee_id else '-',
                            'basic': f"{currency_symbol} {basic_w:,.2f}",
                            'ee_epf': f"{currency_symbol} {ee_p:,.2f}",
                            'er_epf': f"{currency_symbol} {er_p:,.2f}",
                            'edli_admin': f"{currency_symbol} {admin_edli:,.2f}",
                            'total': f"<b>{currency_symbol} {(ee_p + er_p + admin_edli):,.2f}</b>",
                            'action': 'View Payslip'
                        },
                        'action_label': 'View Payslip'
                    })
            badge = f"{len(rows)} Employees with EPF"

        # 11. ESIC Status / Missing
        elif card_type in ('esic_status', 'esic_missing', 'esic_complete'):
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            esic_emps = active_emps.filtered(lambda e: getattr(e, 'hds_in_esic_applicable', False))
            title = "Employees Missing ESIC (IP Number)"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'ip_no', 'label': 'ESIC IP Number'},
                {'key': 'dispensary', 'label': 'Dispensary'},
                {'key': 'validity', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for e in esic_emps:
                valid, reason = comp_service.validate_employee_esic(e)
                if valid:
                    continue
                ip = getattr(e, 'hds_in_esic_ip', '') or getattr(e, 'esic_no', '') or '-'
                disp = getattr(e, 'hds_in_esic_dispensary', '') or '-'
                rows.append({
                    'id': e.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': e.name,
                        'ip_no': ip,
                        'dispensary': disp,
                        'validity': f'<span class="text-danger fw-bold">✖ {reason}</span>',
                        'action': 'Update ESIC'
                    },
                    'action_label': 'Update ESIC'
                })
            badge = f"{len(rows)} Employees Missing IP"

        # Dedicated Employer ESIC (3.25%) Drilldown
        elif card_type == 'esic_liability':
            title = f"Statutory Compliance — Employer ESIC Share (3.25%) — {month_name} {year}"
            period_slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ], order='id desc')
            seen_emp = set()
            slips = []
            for s in period_slips:
                if s.employee_id.id not in seen_emp:
                    seen_emp.add(s.employee_id.id)
                    slips.append(s)
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'wage', 'label': 'Gross / ESIC Wage'},
                {'key': 'er_esic', 'label': 'Employer ESIC (3.25%)'},
                {'key': 'state', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for s in slips:
                er_e = 0.0
                for l in s.line_ids:
                    c = (l.code or '').upper()
                    amt = abs(float(l.total or 0.0))
                    if c in ('ESIC_ER', 'ER_ESI'): er_e += amt
                    elif c == 'ESI':
                        er_e += round(amt * 3.25 / 4.0, 2)
                gross_w = float(getattr(s, 'gross_amount', None) or getattr(s, 'gross_wage', 0.0) or 0.0)
                if er_e > 0:
                    rows.append({
                        'id': s.id,
                        'model': 'hr.payslip',
                        'cells': {
                            'employee': s.employee_id.name if s.employee_id else '-',
                            'wage': f"{currency_symbol} {gross_w:,.2f}",
                            'er_esic': f"<b style='color: #38bdf8;'>{currency_symbol} {er_e:,.2f}</b>",
                            'state': s.state.title(),
                            'action': 'View Payslip'
                        },
                        'action_label': 'View Payslip'
                    })
            badge = f"{len(rows)} Employees with Employer ESIC"

        # 12. LWF Status
        elif card_type in ('lwf_status', 'lwf_missing', 'lwf_complete'):
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            lwf_emps = active_emps.filtered(lambda e: getattr(e, 'hds_in_lwf_applicable', False))
            title = "Employees Missing LWF Registration"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'state', 'label': 'State'},
                {'key': 'validity', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            for e in lwf_emps:
                valid, reason = comp_service.validate_employee_lwf(e)
                if valid:
                    continue
                st = getattr(e, 'hds_in_lwf_state_id', None)
                st_name = st.name if st else '-'
                rows.append({
                    'id': e.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': e.name,
                        'state': st_name,
                        'validity': f'<span class="text-danger fw-bold">✖ {reason}</span>',
                        'action': 'Update LWF'
                    },
                    'action_label': 'Update LWF'
                })
            badge = f"{len(rows)} Employees Missing LWF"

        # 13. Data Readiness & Compliance Issues
        elif card_type in ('readiness_status', 'statutory_errors'):
            from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
            comp_service = StatutoryComplianceValidationService(self.env)
            title = "Employees with Incomplete Compliance Data"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'pan', 'label': 'PAN'},
                {'key': 'bank', 'label': 'Bank'},
                {'key': 'epf', 'label': 'EPF'},
                {'key': 'esic', 'label': 'ESIC'},
                {'key': 'issues', 'label': 'Missing Information / Action Needed'},
                {'key': 'action', 'label': 'Action'}
            ]
            for e in active_emps:
                res = comp_service.validate_employee_all(e)
                if res['is_compliant']:
                    continue
                err_badges = []
                if not res['pan_valid']:
                    err_badges.append("<span class='badge' style='background: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; font-size: 10.5px; margin-right: 4px; padding: 2px 7px; border-radius: 4px; font-weight: 600;'>Missing PAN</span>")
                if not res['bank_valid']:
                    err_badges.append("<span class='badge' style='background: #ffedd5; color: #ea580c; border: 1px solid #fdba74; font-size: 10.5px; margin-right: 4px; padding: 2px 7px; border-radius: 4px; font-weight: 600;'>Missing Bank</span>")
                if not res['epf_valid'] and getattr(e, 'hds_in_epf_applicable', False):
                    err_badges.append("<span class='badge' style='background: #f3e8ff; color: #9333ea; border: 1px solid #d8b4fe; font-size: 10.5px; margin-right: 4px; padding: 2px 7px; border-radius: 4px; font-weight: 600;'>Missing UAN</span>")
                if not res['esic_valid'] and getattr(e, 'hds_in_esic_applicable', False):
                    err_badges.append("<span class='badge' style='background: #e0e7ff; color: #4f46e5; border: 1px solid #c7d2fe; font-size: 10.5px; margin-right: 4px; padding: 2px 7px; border-radius: 4px; font-weight: 600;'>Missing IP</span>")
                if not res['lwf_valid'] and getattr(e, 'hds_in_lwf_applicable', False):
                    err_badges.append("<span class='badge' style='background: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; font-size: 10.5px; margin-right: 4px; padding: 2px 7px; border-radius: 4px; font-weight: 600;'>Missing LWF</span>")
                issues_html = "".join(err_badges) if err_badges else "<span class='text-muted'>-</span>"

                rows.append({
                    'id': e.id,
                    'model': 'hr.employee',
                    'cells': {
                        'name': e.name,
                        'pan': '<span class="text-success fw-bold">✔</span>' if res['pan_valid'] else '<span class="text-danger fw-bold">✖</span>',
                        'bank': '<span class="text-success fw-bold">✔</span>' if res['bank_valid'] else '<span class="text-danger fw-bold">✖</span>',
                        'epf': '<span class="text-success fw-bold">✔</span>' if res['epf_valid'] else '<span class="text-danger fw-bold">✖</span>',
                        'esic': '<span class="text-success fw-bold">✔</span>' if res['esic_valid'] else '<span class="text-danger fw-bold">✖</span>',
                        'issues': issues_html,
                        'action': 'Fix Profile'
                    },
                    'action_label': 'Fix Profile'
                })
            badge = f"{len(rows)} Employees with Incomplete Info"

        # 14. Old / New Tax Regimes
        elif card_type in ('old_regime', 'new_regime'):
            regime = 'old' if card_type == 'old_regime' else 'new'
            regime_title = "Old Tax Regime (With Exemptions)" if regime == 'old' else "New Tax Regime Income-tax Act, 2025 — Section 202(1)"
            reg_emps = active_emps.filtered(lambda e: getattr(e, 'hds_in_tax_regime', 'new') == regime)
            title = f"Employees in {regime_title}"
            badge = f"{len(reg_emps)} Employees"
            columns = [
                {'key': 'name', 'label': 'Employee'},
                {'key': 'dept', 'label': 'Department'},
                {'key': 'pan', 'label': 'PAN'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = [{
                'id': e.id,
                'model': 'hr.employee',
                'cells': {
                    'name': e.name,
                    'dept': e.department_id.name if e.department_id else '-',
                    'pan': getattr(e, 'hds_in_pan', False) or getattr(e, 'pan_no', False) or '-',
                    'action': 'View Profile'
                },
                'action_label': 'View Profile'
            } for e in reg_emps]

        # 15. Aadhaar / Emergency Contact
        elif card_type == 'aadhaar_health':
            missing = active_emps.filtered(lambda e: not self._has_aadhaar(e))
            title = "Employees Missing Aadhaar"
            badge = f"{len(missing)} Employees"
            columns = [{'key': 'name', 'label': 'Employee'}, {'key': 'dept', 'label': 'Department'}, {'key': 'action', 'label': 'Action'}]
            rows = [{'id': e.id, 'model': 'hr.employee', 'cells': {'name': e.name, 'dept': e.department_id.name if e.department_id else '-', 'action': 'Add Aadhaar'}, 'action_label': 'Add Aadhaar'} for e in missing]

        elif card_type == 'contact_health':
            missing = active_emps.filtered(lambda e: not self._has_emergency_contact(e))
            title = "Employees Missing Emergency Contact"
            badge = f"{len(missing)} Employees"
            columns = [{'key': 'name', 'label': 'Employee'}, {'key': 'dept', 'label': 'Department'}, {'key': 'action', 'label': 'Action'}]
            rows = [{'id': e.id, 'model': 'hr.employee', 'cells': {'name': e.name, 'dept': e.department_id.name if e.department_id else '-', 'action': 'Add Contact'}, 'action_label': 'Add Contact'} for e in missing]

        # 16. TDS Withholding (Section 192)
        elif card_type in ('tds_this_month', 'tds_withholding', 'tds_ytd'):
            title = f"TDS Withholding Slips (Income Tax Sec 192) — {month_name} {year}"
            period_slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ], order='id desc')
            seen_emp = set()
            slips = []
            for s in period_slips:
                if s.employee_id.id not in seen_emp:
                    seen_emp.add(s.employee_id.id)
                    slips.append(s)
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'regime', 'label': 'Tax Regime'},
                {'key': 'gross', 'label': 'Gross Wage'},
                {'key': 'tds', 'label': 'Monthly TDS Deducted'},
                {'key': 'state', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = []
            for s in slips:
                emp = s.employee_id
                regime = (getattr(emp, 'hds_in_tax_regime', 'new') or 'new').title()
                tds_amt = 0.0
                for l in s.line_ids:
                    if (l.code or '').upper() in ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS'):
                        tds_amt += abs(float(l.total or 0.0))
                gross_w = float(getattr(s, 'gross_amount', None) or getattr(s, 'gross_wage', 0.0) or 0.0)
                if tds_amt > 0 or len(slips) <= 10:
                    rows.append({
                        'id': s.id,
                        'model': 'hr.payslip',
                        'cells': {
                            'employee': emp.name if emp else '-',
                            'regime': f'<span class="badge bg-secondary">{regime}</span>',
                            'gross': f"{currency_symbol} {gross_w:,.2f}",
                            'tds': f"<b style='color: #818cf8;'>{currency_symbol} {tds_amt:,.2f}</b>",
                            'state': s.state.title(),
                            'action': 'View Payslip'
                        },
                        'action_label': 'View Payslip'
                    })
            badge = f"{len([r for r in rows if '0.00' not in r['cells']['tds']])} Employees with TDS"

        # 17. Professional Tax (PT)
        elif card_type == 'pt_liability':
            title = f"Professional Tax (PT) Liabilities — {month_name} {year}"
            period_slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ], order='id desc')
            seen_emp = set()
            slips = []
            for s in period_slips:
                if s.employee_id.id not in seen_emp:
                    seen_emp.add(s.employee_id.id)
                    slips.append(s)
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'gross', 'label': 'Gross Wage'},
                {'key': 'pt', 'label': 'PT Deducted'},
                {'key': 'state', 'label': 'Status'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = []
            for s in slips:
                pt_amt = 0.0
                for l in s.line_ids:
                    if (l.code or '').upper() in ('PT', 'PROF_TAX'):
                        pt_amt += abs(float(l.total or 0.0))
                gross_w = float(getattr(s, 'gross_amount', None) or getattr(s, 'gross_wage', 0.0) or 0.0)
                if pt_amt > 0 or len(slips) <= 10:
                    rows.append({
                        'id': s.id,
                        'model': 'hr.payslip',
                        'cells': {
                            'employee': s.employee_id.name if s.employee_id else '-',
                            'gross': f"{currency_symbol} {gross_w:,.2f}",
                            'pt': f"<b style='color: #fbbf24;'>{currency_symbol} {pt_amt:,.2f}</b>",
                            'state': s.state.title(),
                            'action': 'View Payslip'
                        },
                        'action_label': 'View Payslip'
                    })
            badge = f"{len(rows)} Payslips"

        # 18. Total Statutory Compliance Liability Summary
        elif card_type in ('total_statutory', 'total_employer_statutory'):
            title = f"Total Statutory Compliance Breakdown — {month_name} {year}"
            period_slips = self.env['hr.payslip'].search([
                ('date_from', '<=', month_end),
                ('date_to', '>=', month_start),
                ('state', '!=', 'cancel'),
            ], order='id desc')
            seen_emp = set()
            slips = []
            for s in period_slips:
                if s.employee_id.id not in seen_emp:
                    seen_emp.add(s.employee_id.id)
                    slips.append(s)
            columns = [
                {'key': 'employee', 'label': 'Employee'},
                {'key': 'epf', 'label': 'EPF Total'},
                {'key': 'esic', 'label': 'ESIC Total (4%)'},
                {'key': 'tds', 'label': 'TDS (Sec 192)'},
                {'key': 'pt_lwf', 'label': 'PT & LWF'},
                {'key': 'total', 'label': 'Total Statutory'},
                {'key': 'action', 'label': 'Action'}
            ]
            rows = []
            for s in slips:
                s_epf = 0.0
                s_esi = 0.0
                s_tds = 0.0
                s_pt_lwf = 0.0
                for l in s.line_ids:
                    c = (l.code or '').upper()
                    amt = abs(float(l.total or 0.0))
                    if c in ('PF', 'EPF', 'EE_PF', 'EMPLOYER_EPF', 'ER_PF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                        s_epf += amt
                    elif c in ('ESIC_EE', 'EE_ESI', 'ESIC_ER', 'ER_ESI', 'ESI'):
                        s_esi += amt
                    elif c in ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS'):
                        s_tds += amt
                    elif c in ('PT', 'PROF_TAX', 'LWF_EE', 'LWF_ER', 'LWF'):
                        s_pt_lwf += amt
                s_tot = s_epf + s_esi + s_tds + s_pt_lwf
                if s_tot > 0 or len(slips) <= 10:
                    rows.append({
                        'id': s.id,
                        'model': 'hr.payslip',
                        'cells': {
                            'employee': s.employee_id.name if s.employee_id else '-',
                            'epf': f"{currency_symbol} {s_epf:,.2f}",
                            'esic': f"{currency_symbol} {s_esi:,.2f}",
                            'tds': f"{currency_symbol} {s_tds:,.2f}",
                            'pt_lwf': f"{currency_symbol} {s_pt_lwf:,.2f}",
                            'total': f"<b style='color: #c084fc;'>{currency_symbol} {s_tot:,.2f}</b>",
                            'action': 'View Payslip'
                        },
                        'action_label': 'View Payslip'
                    })
            badge = f"{len(rows)} Employees with Statutory Dues"

        # Fallback
        else:
            title = f"Dashboard Metric Overview — {card_type or 'General'}"
            badge = f"{len(active_emps)} Employees"
            columns = [{'key': 'name', 'label': 'Name'}, {'key': 'action', 'label': 'Action'}]
            rows = [{'id': e.id, 'model': 'hr.employee', 'cells': {'name': e.name, 'action': 'View'}, 'action_label': 'View'} for e in active_emps[:50]]

        return {
            'card_type': card_type,
            'title': title,
            'badge': badge,
            'columns': columns,
            'rows': rows,
            'empty_message': f"No records found for {title}.",
        }


    def action_view_missing_pan_employees(self):
        self.ensure_one()
        return {
            'name': _('Employees Missing PAN'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': ['&', ('active', '=', True), '|', ('hds_in_pan', '=', False), ('hds_in_pan', '=', '')],
            'target': 'current',
        }

    def action_view_missing_bank_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True)])
        missing_ids = [e.id for e in active_emps if not self._has_bank_account(e)]
        return {
            'name': _('Employees Missing Bank Account'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', missing_ids)],
            'target': 'current',
        }

    def action_view_epf_missing_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_epf_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        missing_ids = [e.id for e in active_emps if not comp_service.validate_employee_epf(e)[0]]
        return {
            'name': _('EPF: Employees Missing UAN / Invalid UAN'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', missing_ids)],
            'target': 'current',
        }

    def action_view_epf_complete_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_epf_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        complete_ids = [e.id for e in active_emps if comp_service.validate_employee_epf(e)[0]]
        return {
            'name': _('EPF: Employees with Complete UAN'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', complete_ids)],
            'target': 'current',
        }

    def action_view_esic_missing_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_esic_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        missing_ids = [e.id for e in active_emps if not comp_service.validate_employee_esic(e)[0]]
        return {
            'name': _('ESIC: Employees Missing IP Number / Invalid IP'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', missing_ids)],
            'target': 'current',
        }

    def action_view_esic_complete_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_esic_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        complete_ids = [e.id for e in active_emps if comp_service.validate_employee_esic(e)[0]]
        return {
            'name': _('ESIC: Employees with Complete IP Number'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', complete_ids)],
            'target': 'current',
        }

    def action_view_lwf_missing_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_lwf_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        missing_ids = [e.id for e in active_emps if not comp_service.validate_employee_lwf(e)[0]]
        return {
            'name': _('LWF: Employees Missing Registration Number'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', missing_ids)],
            'target': 'current',
        }

    def action_view_lwf_complete_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True), ('hds_in_lwf_applicable', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        complete_ids = [e.id for e in active_emps if comp_service.validate_employee_lwf(e)[0]]
        return {
            'name': _('LWF: Employees with Complete Number'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', complete_ids)],
            'target': 'current',
        }

    def action_view_statutory_error_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        error_ids = [e.id for e in active_emps if not comp_service.validate_employee_all(e)['is_compliant']]
        return {
            'name': _('Employees with Statutory Data Errors'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', error_ids)],
            'target': 'current',
        }

    def action_view_statutory_ready_employees(self):
        self.ensure_one()
        active_emps = self.env['hr.employee'].search([('active', '=', True)])
        from ..services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        comp_service = StatutoryComplianceValidationService(self.env)
        ready_ids = [e.id for e in active_emps if comp_service.validate_employee_all(e)['is_compliant']]
        return {
            'name': _('Employees Ready for Statutory Payroll Processing'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', ready_ids)],
            'target': 'current',
        }

    def action_view_pending_declarations(self):
        self.ensure_one()
        return {
            'name': _('Pending Tax Declarations'),
            'type': 'ir.actions.act_window',
            'res_model': 'tds.employee.declaration',
            'view_mode': 'list,form',
            'domain': self._pending_declaration_domain(self.financial_year_id),
            'target': 'current',
        }

    def action_view_new_joiners(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        m_num = int(self.payroll_month_num or today.month)
        year = today.year
        if self.financial_year_id and self.financial_year_id.start_date:
            fy_s_year = self.financial_year_id.start_date.year
            fy_e_year = self.financial_year_id.end_date.year
            year = fy_s_year if m_num >= 4 else fy_e_year
        month_start = date(year, m_num, 1)
        month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])

        emp_fields = self.env['hr.employee']._fields
        join_field = next((f for f in ('joining_date', 'date_of_joining', 'hds_in_doj', 'first_contract_date', 'contract_date_start', 'create_date') if f in emp_fields), None)

        domain = [(join_field, '>=', month_start), (join_field, '<=', month_end)] if join_field else []

        return {
            'name': _('New Joiners'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_view_final_settlements_due(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        m_num = int(self.payroll_month_num or today.month)
        year = today.year
        if self.financial_year_id and self.financial_year_id.start_date:
            fy_s_year = self.financial_year_id.start_date.year
            fy_e_year = self.financial_year_id.end_date.year
            year = fy_s_year if m_num >= 4 else fy_e_year
        month_start = date(year, m_num, 1)
        month_end = date(year, m_num, calendar.monthrange(year, m_num)[1])

        month_name = dict(self._fields['payroll_month_num'].selection).get(self.payroll_month_num, '')
        return {
            'name': _('Final Settlements Due (%s)') % month_name,
            'type': 'ir.actions.act_window',
            'res_model': 'final.settlement',
            'view_mode': 'list,form',
            'domain': self._final_settlement_domain(month_start, month_end) or [],
            'target': 'current',
        }
