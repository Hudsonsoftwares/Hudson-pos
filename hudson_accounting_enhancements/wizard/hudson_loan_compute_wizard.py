from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date
from dateutil.relativedelta import relativedelta
import math

def get_dcf(d1, d2, method):
    if d2 <= d1:
        return 0.0
    if method == 'a360':
        return (d2 - d1).days / 360.0
    elif method == 'a365f':
        return (d2 - d1).days / 365.0
    elif method in ['30a', '30u', '30e', '30e_isda']:
        y1, m1, d1_day = d1.year, d1.month, d1.day
        y2, m2, d2_day = d2.year, d2.month, d2.day
        
        if method == '30a': # 30/360 US
            if d1_day == 31: d1_day = 30
            if d2_day == 31 and d1_day >= 30: d2_day = 30
        elif method == '30u': # 30U/360
            if d1_day == 31: d1_day = 30
            if d2_day == 31 and d1_day == 30: d2_day = 30
        elif method in ['30e', '30e_isda']: # 30E/360
            if d1_day == 31: d1_day = 30
            if d2_day == 31: d2_day = 30
            
        days = (y2 - y1) * 360 + (m2 - m1) * 30 + (d2_day - d1_day)
        return max(0.0, days / 360.0)
    elif method in ['aa_isda', 'aa_afb']:
        # Actual/Actual Simplified
        y1, y2 = d1.year, d2.year
        if y1 == y2:
            days_in_year = 366 if (y1 % 4 == 0 and (y1 % 100 != 0 or y1 % 400 == 0)) else 365
            return max(0.0, (d2 - d1).days / float(days_in_year))
        else:
            days_in_y1 = 366 if (y1 % 4 == 0 and (y1 % 100 != 0 or y1 % 400 == 0)) else 365
            days_in_y2 = 366 if (y2 % 4 == 0 and (y2 % 100 != 0 or y2 % 400 == 0)) else 365
            d1_end_of_year = date(y1, 12, 31)
            days_1 = (d1_end_of_year - d1).days + 1
            d2_start_of_year = date(y2, 1, 1)
            days_2 = (d2 - d2_start_of_year).days
            return max(0.0, (days_1 / float(days_in_y1)) + max(0, y2 - y1 - 1) + (days_2 / float(days_in_y2)))
            
    return max(0.0, (d2 - d1).days / 360.0)

class HudsonLoanComputeWizard(models.TransientModel):
    _name = 'hudson.loan.compute.wizard'
    _description = 'Compute New Loan'

    loan_id = fields.Many2one('hudson.loan', required=True)
    amount = fields.Monetary(string='Loan Amount', currency_field='currency_id', required=True)
    interest_rate = fields.Float(string='Interest Rate (%)', required=True, default=1.00)
    term_years = fields.Integer(string='Loan Term (years)', required=True, default=1)
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    
    payment_type = fields.Selection([
        ('end', 'End of Month'),
        ('anniversary', 'At Anniversary')
    ], string='Payment', default='end', required=True)
    
    first_payment_date = fields.Date(string='First Payment Date')
    
    compounding_method = fields.Selection([
        ('30a', '30A/360'),
        ('30u', '30U/360'),
        ('30e', '30E/360'),
        ('30e_isda', '30E/360 ISDA'),
        ('a360', 'A/360'),
        ('a365f', 'A/365F'),
        ('aa_isda', 'A/A ISDA'),
        ('aa_afb', 'A/A AFB')
    ], string='Compounding Method', default='30e', required=True)

    currency_id = fields.Many2one('res.currency', related='loan_id.currency_id')

    line_ids = fields.One2many('hudson.loan.compute.wizard.line', 'wizard_id', string='Preview')

    @api.onchange('payment_type', 'start_date')
    def _onchange_payment_type_and_start_date(self):
        if self.start_date:
            if self.payment_type == 'anniversary':
                if not self.first_payment_date or self.first_payment_date < self.start_date:
                    self.first_payment_date = self.start_date + relativedelta(months=1)
            elif self.payment_type == 'end':
                end_of_current = self.start_date + relativedelta(day=31)
                if end_of_current > self.start_date:
                    self.first_payment_date = end_of_current
                else:
                    self.first_payment_date = self.start_date + relativedelta(months=1, day=31)

    @api.onchange('first_payment_date')
    def _onchange_first_payment_date(self):
        if self.payment_type == 'anniversary' and self.first_payment_date and self.start_date:
            if self.first_payment_date < self.start_date:
                self.first_payment_date = self.start_date

    def _get_payment_dates(self):
        self.ensure_one()
        periods = self.term_years * 12
        if periods <= 0 or not self.start_date:
            return []

        start_date = self.start_date
        dates = []

        if self.payment_type == 'end':
            end_of_current_month = start_date + relativedelta(day=31)
            if end_of_current_month > start_date:
                base_date = end_of_current_month
            else:
                base_date = start_date + relativedelta(months=1, day=31)
            
            for i in range(periods):
                d = base_date + relativedelta(months=i, day=31)
                dates.append(d)
        else:
            first_date = self.first_payment_date or (start_date + relativedelta(months=1))
            if first_date < start_date:
                first_date = start_date
                
            for i in range(periods):
                d = first_date + relativedelta(months=i)
                dates.append(d)
                
        return dates

    def _get_amortization_lines(self):
        self.ensure_one()
        if self.amount <= 0 or self.term_years <= 0 or self.interest_rate <= 0 or not self.start_date:
            return []

        dates = self._get_payment_dates()
        if not dates:
            return []

        principal = self.amount
        annual_rate = self.interest_rate / 100.0
        periods = len(dates)
        
        # Helper to get the end balance for a given PMT guess
        def get_end_balance(pmt_guess):
            balance = principal
            d1 = self.start_date
            for d2 in dates:
                dcf = get_dcf(d1, d2, self.compounding_method)
                interest = max(0.0, balance * annual_rate * dcf)
                balance += interest - pmt_guess
                d1 = d2
            return balance

        # Secant Method to find exact PMT
        monthly_rate = annual_rate / 12.0
        guess = (monthly_rate * principal) / (1 - math.pow(1 + monthly_rate, -periods)) if monthly_rate > 0 else (principal / periods)
        
        pmt0 = guess * 0.9
        pmt1 = guess * 1.1
        for _ in range(50):
            f0 = get_end_balance(pmt0)
            f1 = get_end_balance(pmt1)
            if abs(f1) < 0.001 or abs(f1 - f0) < 1e-9:
                break
            pmt_next = pmt1 - f1 * (pmt1 - pmt0) / (f1 - f0)
            pmt0 = pmt1
            pmt1 = pmt_next
            
        final_pmt = pmt1
        
        lines = []
        balance = principal
        d1 = self.start_date
        
        for i, d2 in enumerate(dates):
            dcf = get_dcf(d1, d2, self.compounding_method)
            interest = max(0.0, balance * annual_rate * dcf)
            principal_payment = max(0.0, final_pmt - interest)
            
            if i == periods - 1:
                principal_payment = balance
                final_pmt = principal_payment + interest
            
            balance = max(0.0, balance - principal_payment)
            
            lines.append((0, 0, {
                'date': d2,
                'principal': principal_payment,
                'interest': interest,
                'payment': final_pmt,
                'balance': balance
            }))
            d1 = d2
            
        return lines

    @api.onchange('amount', 'interest_rate', 'term_years', 'start_date', 'compounding_method', 'payment_type', 'first_payment_date')
    def _compute_schedule_preview(self):
        for wizard in self:
            wizard.line_ids = [(5, 0, 0)] + wizard._get_amortization_lines()

    def action_apply(self):
        self.ensure_one()
        if self.payment_type == 'anniversary' and self.first_payment_date and self.first_payment_date < self.start_date:
            raise UserError(_("First payment date cannot be earlier than the loan start date."))
        lines_to_create = self._get_amortization_lines()
        self.loan_id.write({
            'amount_borrowed': self.amount,
            'duration': self.term_years * 12,
            'date': self.start_date,
            'line_ids': [(5, 0, 0)] + lines_to_create
        })
        return {'type': 'ir.actions.act_window_close'}


class HudsonLoanComputeWizardLine(models.TransientModel):
    _name = 'hudson.loan.compute.wizard.line'
    _description = 'Compute New Loan Line'
    _order = 'date asc'

    wizard_id = fields.Many2one('hudson.loan.compute.wizard', ondelete='cascade')
    date = fields.Date(string='Date')
    principal = fields.Monetary(string='Principal', currency_field='currency_id')
    interest = fields.Monetary(string='Interest', currency_field='currency_id')
    payment = fields.Monetary(string='Payment', currency_field='currency_id')
    balance = fields.Monetary(string='Balance', currency_field='currency_id')
    
    currency_id = fields.Many2one(related='wizard_id.currency_id')
