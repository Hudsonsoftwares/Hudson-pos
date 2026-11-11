from odoo import fields, models, tools


# Salary rule codes, as used by the payroll dashboard (hds.payroll.dashboard)
TDS_CODES = ('HDS_IN_TDS', 'TDS', 'INCOME_TAX', 'IT')
PT_CODES = ('PT', 'PROF_TAX')
EMPLOYEE_EPF_CODES = ('PF', 'EPF', 'EE_PF')
EMPLOYEE_ESIC_CODES = ('ESIC_EE', 'EE_ESI')
EMPLOYEE_LWF_CODES = ('LWF_EE', 'EE_LWF', 'LWF')
HRA_CODES = ('HRA',)


class HdsPayrollAnalysis(models.Model):
    """Payroll analysis: one row per validated / paid payslip (read-only SQL view).

    Same scope as the payroll dashboard: validated and paid payslips, payslips flagged as
    duplicates are excluded and, for the same employee and period, the paid payslip (else the
    latest one) is kept. CTC = gross + employer statutory contributions.
    Used by the Payroll spreadsheet dashboard and the Payroll Analysis report.
    """
    _name = 'hds.payroll.analysis'
    _description = 'Payroll Analysis'
    _auto = False
    _rec_name = 'employee_id'
    _order = 'date desc, employee_id'

    payslip_id = fields.Many2one('hr.payslip', string='Payslip', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Pay Run', readonly=True)
    payment_mode_id = fields.Many2one('hds.payment.mode', string='Payment Mode', readonly=True)
    state = fields.Selection([('done', 'Validated'), ('paid', 'Paid')], string='Status', readonly=True)
    date = fields.Date(string='Payroll Month', readonly=True)
    date_to = fields.Date(string='Period End', readonly=True)
    tax_regime = fields.Selection([('new', 'New Regime'), ('old', 'Old Regime')], string='Tax Regime', readonly=True)

    basic_wage = fields.Monetary(string='Basic', readonly=True)
    hra = fields.Monetary(string='HRA', readonly=True)
    gross_wage = fields.Monetary(string='Gross', readonly=True)
    employer_epf = fields.Monetary(string='Employer EPF', readonly=True)
    employer_edli_admin = fields.Monetary(string='Employer EDLI & Admin', readonly=True)
    employer_esic = fields.Monetary(string='Employer ESIC', readonly=True)
    employer_lwf = fields.Monetary(string='Employer LWF', readonly=True)
    employer_statutory = fields.Monetary(string='Employer Statutory', readonly=True)
    ctc = fields.Monetary(string='CTC', readonly=True)
    employee_epf = fields.Monetary(string='Employee EPF', readonly=True)
    employee_esic = fields.Monetary(string='Employee ESIC', readonly=True)
    employee_lwf = fields.Monetary(string='Employee LWF', readonly=True)
    professional_tax = fields.Monetary(string='Professional Tax', readonly=True)
    tds = fields.Monetary(string='TDS', readonly=True)
    net_wage = fields.Monetary(string='Net Pay', readonly=True)

    @staticmethod
    def _sum_codes(codes):
        quoted = ', '.join("'%s'" % code for code in codes)
        return f"SUM(CASE WHEN UPPER(l.code) IN ({quoted}) THEN ABS(l.total) ELSE 0 END)"

    def _query(self):
        return f"""
            WITH ranked AS (
                SELECT p.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.employee_id, p.date_from, p.date_to
                           ORDER BY CASE WHEN p.state = 'paid' THEN 1 ELSE 0 END DESC, p.id DESC
                       ) AS rank_in_period
                  FROM hr_payslip p
                 WHERE p.state IN ('done', 'paid')
                   AND COALESCE(p.has_duplicate_payslip, FALSE) = FALSE
            ),
            line_totals AS (
                SELECT l.slip_id,
                       {self._sum_codes(HRA_CODES)} AS hra,
                       {self._sum_codes(EMPLOYEE_EPF_CODES)} AS employee_epf,
                       {self._sum_codes(EMPLOYEE_ESIC_CODES)} AS employee_esic,
                       {self._sum_codes(EMPLOYEE_LWF_CODES)} AS employee_lwf,
                       {self._sum_codes(PT_CODES)} AS professional_tax,
                       {self._sum_codes(TDS_CODES)} AS tds
                  FROM hr_payslip_line l
                 GROUP BY l.slip_id
            )
            SELECT r.id AS id,
                   r.id AS payslip_id,
                   r.employee_id,
                   v.department_id,
                   v.job_id,
                   r.company_id,
                   c.currency_id,
                   r.payslip_run_id,
                   r.hds_in_payment_mode AS payment_mode_id,
                   r.state,
                   r.date_from AS date,
                   r.date_to,
                   -- Same rule as hr.employee._compute_current_fy_regime, for the tax year of the payslip:
                   -- company policy new / old, else the employee's choice for that tax year, else the
                   -- statutory default (new regime)
                   CASE WHEN c.hds_in_default_tax_regime IN ('new', 'old') THEN c.hds_in_default_tax_regime
                        ELSE COALESCE(employee_regime.code, 'new') END AS tax_regime,
                   COALESCE(r.basic_wage, 0) AS basic_wage,
                   COALESCE(lt.hra, 0) AS hra,
                   COALESCE(r.gross_wage, 0) AS gross_wage,
                   COALESCE(r.hds_in_employer_epf, 0) AS employer_epf,
                   COALESCE(r.hds_in_employer_edli, 0) + COALESCE(r.hds_in_employer_epf_admin, 0) AS employer_edli_admin,
                   COALESCE(r.hds_in_employer_esic, 0) AS employer_esic,
                   COALESCE(r.hds_in_employer_lwf, 0) AS employer_lwf,
                   COALESCE(r.hds_in_total_employer_statutory, 0) AS employer_statutory,
                   COALESCE(r.gross_wage, 0) + COALESCE(r.hds_in_total_employer_statutory, 0) AS ctc,
                   COALESCE(lt.employee_epf, 0) AS employee_epf,
                   COALESCE(lt.employee_esic, 0) AS employee_esic,
                   COALESCE(lt.employee_lwf, 0) AS employee_lwf,
                   COALESCE(lt.professional_tax, 0) AS professional_tax,
                   COALESCE(lt.tds, 0) AS tds,
                   COALESCE(r.net_wage, 0) AS net_wage
              FROM ranked r
              LEFT JOIN line_totals lt ON lt.slip_id = r.id
              LEFT JOIN hr_version v ON v.id = r.contract_id
              LEFT JOIN res_company c ON c.id = r.company_id
              LEFT JOIN LATERAL (
                    SELECT regime.code
                      FROM tds_employee_tax_regime emp_regime
                      JOIN tds_financial_year fy ON fy.id = emp_regime.financial_year_id
                      JOIN tds_tax_regime regime ON regime.id = emp_regime.regime_id
                     WHERE emp_regime.employee_id = r.employee_id
                       AND fy.start_date <= r.date_from
                       AND fy.end_date >= r.date_from
                     ORDER BY emp_regime.id DESC
                     LIMIT 1
              ) employee_regime ON TRUE
             WHERE r.rank_in_period = 1
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({self._query()})")
