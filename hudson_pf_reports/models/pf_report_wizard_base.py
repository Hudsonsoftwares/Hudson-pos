# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import date
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class HdsPfReportWizardBase(models.AbstractModel):
    _name = 'hds.pf.report.wizard.base'
    _description = 'Base PF Statutory Report Wizard'

    @api.model
    def _default_year(self):
        return fields.Date.today().year

    @api.model
    def _default_month(self):
        return str(fields.Date.today().month)

    year = fields.Integer(
        string='Year',
        default=_default_year,
        required=True
    )
    month = fields.Selection([
        ('1', 'January'),
        ('2', 'February'),
        ('3', 'March'),
        ('4', 'April'),
        ('5', 'May'),
        ('6', 'June'),
        ('7', 'July'),
        ('8', 'August'),
        ('9', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string='Month', default=_default_month, required=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Optional filter by department."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Optional filter by specific employee."
    )
    payslip_state = fields.Selection([
        ('all', 'All States (Draft, Verify, Done, Paid)'),
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
    ], string='Payslip Status', default='all', required=True)

    generated_on_date = fields.Date(
        string='Generated On Date',
        default=fields.Date.today,
        readonly=True
    )

    def _get_date_range(self):
        self.ensure_one()
        year = int(self.year)
        month = int(self.month)
        last_day = calendar.monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to = date(year, month, last_day)
        return date_from, date_to

    def _get_month_label(self):
        self.ensure_one()
        month_dict = dict(self._fields['month'].selection)
        return f"{month_dict.get(self.month, '')}-{self.year}"

    def _get_confirmed_payslips(self, extra_domain=None):
        self.ensure_one()
        date_from, date_to = self._get_date_range()

        state_sel = getattr(self, 'payslip_state', 'all')
        if state_sel == 'done':
            states = ['done']
        elif state_sel == 'paid':
            states = ['paid']
        elif state_sel == 'confirmed':
            states = ['done', 'paid']
        else:
            states = ['draft', 'verify', 'done', 'paid']

        domain = [
            ('state', 'in', states),
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
        ]
        if self.employee_id:
            domain.append(('employee_id', '=', self.employee_id.id))
        if self.department_id:
            domain.append(('employee_id.department_id', '=', self.department_id.id))
        if extra_domain:
            domain.extend(extra_domain)

        all_slips = self.env['hr.payslip'].search(domain, order='date_to desc, id desc')
        # Deduplicate per employee preferring paid > done > verify > draft
        priority = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
        best_slip_by_emp = {}
        for slip in all_slips:
            emp_id = slip.employee_id.id
            if emp_id not in best_slip_by_emp:
                best_slip_by_emp[emp_id] = slip
            else:
                curr_prio = priority.get(slip.state, 0)
                best_prio = priority.get(best_slip_by_emp[emp_id].state, 0)
                if curr_prio > best_prio:
                    best_slip_by_emp[emp_id] = slip

        return self.env['hr.payslip'].browse([s.id for s in best_slip_by_emp.values()])

    def action_print_pdf(self):
        self.ensure_one()
        report_action = self.env.ref('hudson_pf_reports.action_report_pf_register', raise_if_not_found=False)
        if report_action:
            return report_action.report_action(self)
        raise _("PDF report action not found.")

    @api.model
    def _get_pf_line_amounts(self, payslip):
        """
        Dynamically extracts PF components from a confirmed payslip.
        Logs every line code, name, category, and total to server log for verification.
        Supports standard and custom rule code naming conventions:
        - Employee EPF: EPF, PF, EPF_DED, EMPLOYEE_EPF, EE_EPF, PF_DED, EPF_EE
        - Employer EPF Share: EMPLOYER_EPF_SHARE, EPF_ER_SHARE, EPF_ER, ER_EPF
        - Employer EPS: EMPLOYER_EPS, EPS, EPS_SHARE, ER_EPS, PENSION, EMPLOYER_PENSION
        - Employer EPF Total (12%): EMPLOYER_EPF, EPF_ER_TOTAL, EMPLOYER_EPF_TOTAL
        - EDLI: EDLI, EMPLOYER_EDLI, EDLI_CONT, ER_EDLI
        - Admin Charges: EDLI_ADMIN_TOTAL, EPF_ADMIN, EDLI_ADMIN, ADMIN_CHARGES, PF_ADMIN, EPF_ADMIN_CHARGE
        - Total Employer Cost: EMPLOYER_PF_TOTAL_COST, EMPLOYER_PF_COST, PF_EMP_COST, TOTAL_EMPLOYER_COST
        """
        lines = payslip.line_ids

        # Debug logging requested by user
        _logger.info("================================================================================")
        _logger.info("=== HDS PF REPORT DEBUG LOG FOR PAYSLIP ID: %s ===", payslip.id)
        _logger.info("=== Employee: %s | State: %s | Period: %s to %s ===", payslip.employee_id.name, payslip.state, payslip.date_from, payslip.date_to)
        _logger.info("--------------------------------------------------------------------------------")
        for line in lines:
            cat_code = line.category_id.code if line.category_id else 'None'
            _logger.info("  Line Code: %-25s | Name: %-35s | Total: %10.2f | Category: %s", line.code, line.name, line.total, cat_code)
        _logger.info("================================================================================")

        # 1. PF Contribution Wage
        pf_wage_line = lines.filtered(lambda l: l.code in ('PF_WAGE', 'PF_WAGE_BASE', 'PF_CONTRIBUTION_WAGE', 'PF_WAGE_ELIGIBLE'))
        if pf_wage_line:
            pf_wage = abs(pf_wage_line[0].total)
        else:
            pf_wage = payslip.hds_in_get_pf_contribution_wage()

        # 2. Employee EPF Deduction
        ee_epf_lines = lines.filtered(lambda l: l.code in ('EPF', 'PF', 'EPF_DED', 'EMPLOYEE_EPF', 'EE_EPF', 'PF_DED', 'EPF_EE'))
        if ee_epf_lines:
            ee_epf = abs(sum(ee_epf_lines.mapped('total')))
        elif pf_wage > 0.0 and getattr(payslip.employee_id, 'hds_in_epf_applicable', False):
            ee_epf = round(pf_wage * 0.12, 2)
        else:
            ee_epf = 0.0

        # 2b. VPF (Voluntary PF) Deduction
        vpf_lines = lines.filtered(lambda l: l.code in ('VPF', 'EE_VPF', 'VOLUNTARY_PF', 'PF_VPF', 'EPF_VPF'))
        vpf = abs(sum(vpf_lines.mapped('total'))) if vpf_lines else 0.0

        # 3. Employer EPS Share
        er_eps_lines = lines.filtered(lambda l: l.code in ('EMPLOYER_EPS', 'EPS', 'EPS_SHARE', 'ER_EPS', 'PENSION', 'EMPLOYER_PENSION'))
        if er_eps_lines:
            er_eps = abs(sum(er_eps_lines.mapped('total')))
        elif pf_wage > 0.0 and getattr(payslip.employee_id, 'hds_in_epf_applicable', False):
            eps_applicable = getattr(payslip.employee_id, 'hds_in_eps_applicable', True)
            if eps_applicable:
                eps_limit = self.env['hr.rule.parameter'].get_pf_parameter('EPS_WAGE_CEILING', date=payslip.date_to) or 15000.0
                er_eps = round(min(pf_wage, eps_limit) * 0.0833, 2)
            else:
                er_eps = 0.0
        else:
            er_eps = 0.0

        # 4. Employer EPF Share (3.67%)
        er_epf_share_lines = lines.filtered(lambda l: l.code in ('EMPLOYER_EPF_SHARE', 'EPF_ER_SHARE', 'EPF_ER', 'ER_EPF'))
        if er_epf_share_lines:
            er_epf = abs(sum(er_epf_share_lines.mapped('total')))
        else:
            er_epf_total_lines = lines.filtered(lambda l: l.code in ('EMPLOYER_EPF', 'EPF_ER_TOTAL', 'EMPLOYER_EPF_TOTAL'))
            if er_epf_total_lines:
                total_er_epf = abs(sum(er_epf_total_lines.mapped('total')))
                er_epf = max(0.0, total_er_epf - er_eps)
            elif pf_wage > 0.0 and getattr(payslip.employee_id, 'hds_in_epf_applicable', False):
                total_er_epf = round(pf_wage * 0.12, 2)
                er_epf = max(0.0, round(total_er_epf - er_eps, 2))
            else:
                er_epf = 0.0

        # 5. EDLI
        edli_lines = lines.filtered(lambda l: l.code in ('EDLI', 'EMPLOYER_EDLI', 'EDLI_CONT', 'ER_EDLI'))
        if edli_lines:
            edli = abs(sum(edli_lines.mapped('total')))
        elif pf_wage > 0.0 and getattr(payslip.employee_id, 'hds_in_epf_applicable', False) and getattr(payslip.employee_id, 'hds_in_edli_applicable', True):
            edli_limit = self.env['hr.rule.parameter'].get_pf_parameter('EDLI_WAGE_CEILING', date=payslip.date_to) or 15000.0
            edli_rate = self.env['hr.rule.parameter'].get_pf_parameter('EDLI_RATE', date=payslip.date_to, as_decimal=True) or 0.005
            edli = round(min(pf_wage, edli_limit) * edli_rate, 2)
        else:
            edli = 0.0

        # 6. Admin Charges
        admin_lines = lines.filtered(lambda l: l.code in ('EDLI_ADMIN_TOTAL', 'EPF_ADMIN', 'EDLI_ADMIN', 'ADMIN_CHARGES', 'PF_ADMIN', 'EPF_ADMIN_CHARGE'))
        if admin_lines:
            admin = abs(sum(admin_lines.mapped('total')))
        elif pf_wage > 0.0 and getattr(payslip.employee_id, 'hds_in_epf_applicable', False):
            admin_rate = self.env['hr.rule.parameter'].get_pf_parameter('EPF_ADMIN_RATE', date=payslip.date_to, as_decimal=True) or 0.005
            admin = round(pf_wage * admin_rate, 2)
        else:
            admin = 0.0

        # 7. Total Employer Statutory Cost
        cost_lines = lines.filtered(lambda l: l.code in ('EMPLOYER_PF_TOTAL_COST', 'EMPLOYER_PF_COST', 'PF_EMP_COST', 'TOTAL_EMPLOYER_COST'))
        if cost_lines:
            total_cost = abs(sum(cost_lines.mapped('total')))
        else:
            total_cost = er_epf + er_eps + edli + admin

        _logger.info("=== EXTRACTED PF VALUES FOR PAYSLIP %s: Wage: %s | EE EPF: %s | VPF: %s | ER EPF: %s | ER EPS: %s | EDLI: %s | Admin: %s | Total Cost: %s ===",
                     payslip.id, pf_wage, ee_epf, vpf, er_epf, er_eps, edli, admin, total_cost)

        return {
            'pf_wage': pf_wage,
            'ee_epf': ee_epf,
            'vpf': vpf,
            'er_epf': er_epf,
            'er_eps': er_eps,
            'edli': edli,
            'admin': admin,
            'total_cost': total_cost,
        }
