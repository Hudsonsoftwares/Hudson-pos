# -*- coding: utf-8 -*-
import calendar
import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import BinaryBytes

QUARTERS = [('q1', 'Q1'), ('q2', 'Q2'), ('q3', 'Q3'), ('q4', 'Q4')]

# Income tax department state codes of the quarterly TDS return, by Odoo state code (India)
RETURN_STATE_CODES = {
    'AN': '01', 'AP': '02', 'AR': '03', 'AS': '04', 'BR': '05', 'CH': '06', 'DN': '07', 'DL': '09',
    'GA': '10', 'GJ': '11', 'HR': '12', 'HP': '13', 'JK': '14', 'KA': '15', 'KL': '16', 'LD': '17',
    'MP': '18', 'MH': '19', 'MN': '20', 'ML': '21', 'MZ': '22', 'NL': '23', 'OD': '24', 'OR': '24',
    'PY': '25', 'PB': '26', 'RJ': '27', 'SK': '28', 'TN': '29', 'TR': '30', 'UP': '31', 'WB': '32',
    'CG': '33', 'CT': '33', 'UK': '34', 'UT': '34', 'JH': '35', 'TS': '36', 'TG': '36', 'LA': '37',
    'IN_OC': '99', 'IN_OT': '99',
}

# Number of fields of each record of the text file (caret separated)
RECORD_LENGTHS = {'FH': 18, 'BH': 72, 'CD': 30, 'DD': 45}
PAN_NOT_AVAILABLE = 'PANNOTAVBL'


class HdsForm138(models.Model):
    """Quarterly TDS return (Form 138) of a tax year: the deposited TDS challans of the quarter and
    the text file of the return (FH, BH, CD and DD records)."""
    _name = 'hds.form.138'
    _description = 'Form 138 (Quarterly TDS Return)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Latest tax year first, its quarters in order (Q1, Q2, Q3, Q4)
    _order = 'financial_year_start desc, quarter, id'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency')
    financial_year_id = fields.Many2one('tds.financial.year', string='Financial Year', required=True,
                                        index=True, ondelete='restrict', tracking=True,
                                        default=lambda self: self._default_financial_year())
    financial_year_code = fields.Char(related='financial_year_id.code', string='Financial Year Code')
    financial_year_start = fields.Date(related='financial_year_id.start_date', store=True, string='Tax Year Start')
    quarter = fields.Selection(QUARTERS, string='Quarter', required=True, tracking=True,
                               default=lambda self: self._default_quarter())
    date_from = fields.Date(string='Quarter Period', compute='_compute_period', store=True)
    date_to = fields.Date(string='Quarter End', compute='_compute_period', store=True)
    due_date = fields.Date(string='Due Date', compute='_compute_due_date', store=True, readonly=False, tracking=True,
                           help="Last date to file the return: the month after the quarter (two months after the last quarter).")
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], string='State', default='draft',
                             required=True, copy=False, tracking=True)
    challan_ids = fields.Many2many('hds.tds.challan', string='Challans', compute='_compute_challans')
    challan_count = fields.Integer(string='Challan Count', compute='_compute_challans')
    statement_line_ids = fields.Many2many('hds.tds.challan.line', string='Regular Statement', compute='_compute_challans')
    tds_amount = fields.Monetary(string='TDS Amount', compute='_compute_challans')
    total_paid = fields.Monetary(string='Total Deposited', compute='_compute_challans')
    text_file = fields.Binary(string='Text File', attachment=True, copy=False, readonly=True)
    text_filename = fields.Char(string='Text File Name', copy=False, readonly=True)
    earlier_regular_statement = fields.Boolean(
        string='Earlier Regular Statement', tracking=True,
        help="Tick when a regular statement of this form was already filed for an earlier period.")
    previous_token_number = fields.Char(
        string='Previous Regular Statement Token No.', tracking=True,
        help="Token number (15-digit provisional receipt number) of the regular statement filed for the "
             "previous period.")

    @api.model
    def _default_financial_year(self):
        today = fields.Date.context_today(self)
        return self.env['tds.financial.year'].search([('start_date', '<=', today), ('end_date', '>=', today)], limit=1)

    @api.model
    def _default_quarter(self):
        # Quarter of today in the tax year (April-June is Q1)
        return 'q%d' % (((fields.Date.context_today(self).month - 4) % 12) // 3 + 1)

    @api.depends('financial_year_id.code', 'financial_year_id.name', 'quarter')
    def _compute_name(self):
        quarters = dict(QUARTERS)
        for form in self:
            year = form.financial_year_id.code or form.financial_year_id.name or ''
            form.name = ' '.join(part for part in (_('Form 138'), year, quarters.get(form.quarter, '')) if part)

    @api.depends('financial_year_id.start_date', 'quarter')
    def _compute_period(self):
        for form in self:
            start = form.financial_year_id.start_date
            if start and form.quarter:
                form.date_from = start + relativedelta(months=3 * (int(form.quarter[1]) - 1))
                form.date_to = form.date_from + relativedelta(months=3, days=-1)
            else:
                form.date_from = form.date_to = False

    @api.depends('date_to', 'quarter')
    def _compute_due_date(self):
        for form in self:
            if form.date_to:
                due_month = form.date_to + relativedelta(months=2 if form.quarter == 'q4' else 1)
                form.due_date = due_month.replace(day=calendar.monthrange(due_month.year, due_month.month)[1])
            else:
                form.due_date = False

    @api.depends('company_id', 'date_from', 'date_to')
    def _compute_challans(self):
        Challan = self.env['hds.tds.challan']
        for form in self:
            challans = Challan.search([
                ('company_id', '=', form.company_id.id),
                ('state', '=', 'done'),
                ('date_from', '>=', form.date_from),
                ('date_from', '<=', form.date_to),
            ], order='date_from, paid_date, id') if form.date_from and form.date_to else Challan
            form.challan_ids = challans
            form.challan_count = len(challans)
            form.statement_line_ids = challans.mapped('line_ids')
            form.tds_amount = sum(challans.mapped('tds_amount'))
            form.total_paid = sum(challans.mapped('total_paid'))

    @api.constrains('company_id', 'financial_year_id', 'quarter')
    def _check_unique_quarter(self):
        for form in self:
            duplicate = self.search_count([
                ('company_id', '=', form.company_id.id),
                ('financial_year_id', '=', form.financial_year_id.id),
                ('quarter', '=', form.quarter),
                ('id', '!=', form.id),
            ])
            if duplicate:
                raise ValidationError(_("%s already exists for this company.", form.name))

    @api.onchange('earlier_regular_statement')
    def _onchange_earlier_regular_statement(self):
        for form in self.filtered(lambda f: not f.earlier_regular_statement):
            form.previous_token_number = False

    @api.constrains('earlier_regular_statement', 'previous_token_number')
    def _check_previous_token_number(self):
        for form in self:
            token = (form.previous_token_number or '').strip()
            if token and not form.earlier_regular_statement:
                raise ValidationError(_("Tick Earlier Regular Statement to record a previous token number."))
            if token and not re.fullmatch(r'\d{15}', token):
                raise ValidationError(_("The Previous Regular Statement Token No. must be the 15-digit "
                                        "provisional receipt number."))

    def write(self, vals):
        locked = set(vals) - {'state', 'text_file', 'text_filename'}
        if locked and any(form.state == 'done' for form in self):
            raise UserError(_("A Done Form 138 cannot be changed. Set it to Draft first."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(form.state == 'done' for form in self):
            raise UserError(_("A Done Form 138 cannot be deleted. Set it to Draft first."))

    # ------------------------------------------------------------------
    # Quarters of a tax year
    # ------------------------------------------------------------------
    @api.model
    def _ensure_quarters(self, financial_year, company):
        """Create the missing quarters of a tax year for a company; returns the four quarters."""
        existing = self.search([('company_id', '=', company.id), ('financial_year_id', '=', financial_year.id)])
        missing = [code for code, _label in QUARTERS if code not in existing.mapped('quarter')]
        created = self.create([{
            'company_id': company.id, 'financial_year_id': financial_year.id, 'quarter': code,
        } for code in missing]) if missing else self.browse()
        return existing | created

    def action_generate_current_fy(self):
        # Control panel button: called with the selected records (usually none), works on the model
        today = fields.Date.context_today(self)
        financial_year = self.env['tds.financial.year'].search([
            ('start_date', '<=', today), ('end_date', '>=', today),
        ], limit=1)
        if not financial_year:
            raise UserError(_("No Tax Year covers today (%s). Create it in Payroll > Configuration > "
                              "TDS Financial Years first.", today))
        self._ensure_quarters(financial_year, self.env.company)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def action_done(self):
        if any(not form.challan_ids for form in self):
            raise UserError(_("There should be at least one challan to mark form as done."))
        missing_token = self.filtered(lambda f: f.earlier_regular_statement and not f.previous_token_number)
        if missing_token:
            raise UserError(_("Enter the Previous Regular Statement Token No. (Regular Statement tab) of %s, "
                              "or untick Earlier Regular Statement.", ", ".join(missing_token.mapped('name'))))
        self.write({'state': 'done'})

    def action_draft(self):
        if not self.env.user.has_group('hudson_payroll_base.group_payroll_manager'):
            raise UserError(_("Only payroll managers can set a Done Form 138 back to Draft."))
        # The text file belongs to the Done return; it is generated again once done
        self.write({'state': 'draft', 'text_file': False, 'text_filename': False})

    # ------------------------------------------------------------------
    # Text file
    # ------------------------------------------------------------------
    @staticmethod
    def _txt(value):
        return ' '.join(str(value or '').replace('^', ' ').split()) if value not in (None, False) else ''

    @staticmethod
    def _amount(value):
        return '%.2f' % (value or 0.0)

    @staticmethod
    def _date(value):
        return value.strftime('%d%m%Y') if value else ''

    @staticmethod
    def _record(record_type, values):
        """A record of RECORD_LENGTHS[record_type] fields, values given by position."""
        fields_list = [''] * RECORD_LENGTHS[record_type]
        for index, value in values.items():
            fields_list[index] = value
        fields_list[1] = record_type
        return '^'.join(fields_list)

    def _check_text_file_data(self):
        """List what is missing to build the return, so it can be completed before generating."""
        self.ensure_one()
        company = self.company_id
        missing = []
        for value, label in (
            (company.hds_in_tan, _('TAN')),
            (company.hds_in_company_pan, _('Company PAN')),
            (company.street, _('Company address (street)')),
            (company.city, _('Company city')),
            (company.state_id, _('Company state')),
            (company.zip, _('Company PIN code')),
            (company.email, _('Company email')),
            (company.hds_in_deductor_type, _('Deductor Type')),
            (company.hds_in_tds_responsible_name, _('Responsible Person')),
            (company.hds_in_tds_responsible_email, _('Responsible Person Email')),
        ):
            if not value:
                missing.append(label)
        if company.state_id and company.state_id.code not in RETURN_STATE_CODES:
            missing.append(_('Income tax state code for %s', company.state_id.name))
        if not self.financial_year_id.start_date or not self.financial_year_id.end_date:
            missing.append(_('Tax Year dates'))
        if missing:
            raise UserError(_("Complete these details before generating the text file "
                              "(Payroll > Configuration > Settings, TDS section, and the company address):\n• %s",
                              "\n• ".join(missing)))

    def _build_text_file(self):
        self.ensure_one()
        company = self.company_id
        partner = company.partner_id
        fy = self.financial_year_id
        start_year, end_year = fy.start_date.year, fy.end_date.year
        financial_year = f'{start_year}{str(end_year)[-2:]}'
        assessment_year = f'{start_year + 1}{str(end_year + 1)[-2:]}'
        state_code = RETURN_STATE_CODES[company.state_id.code]
        country = self._txt(company.country_id.name)
        challans = self.challan_ids
        lines = []

        def add(record_type, values):
            values[0] = str(len(lines) + 1)
            lines.append(self._record(record_type, values))

        add('FH', {2: 'SL1', 3: 'R', 4: self._date(fields.Date.context_today(self)), 6: 'D',
                   7: self._txt(company.hds_in_tan).upper(), 8: '1', 9: 'Odoo'})
        add('BH', {
            2: '1', 3: str(len(challans)), 4: '138',
            12: self._txt(company.hds_in_tan).upper(), 14: self._txt(company.hds_in_company_pan).upper(),
            15: assessment_year, 16: financial_year, 17: dict(QUARTERS)[self.quarter],
            18: self._txt(company.name), 19: country,
            20: self._txt(company.street), 21: self._txt(company.street2), 22: self._txt(company.city),
            23: self._txt(company.state_id.name), 24: country, 25: state_code, 26: self._txt(company.zip),
            27: self._txt(company.email or partner.email), 31: company.hds_in_deductor_type,
            32: self._txt(company.hds_in_tds_responsible_name),
            33: self._txt(company.hds_in_tds_responsible_designation) or 'NA', 34: 'NA',
            36: self._txt(company.city), 37: self._txt(company.state_id.name), 38: country, 39: state_code,
            40: self._txt(company.zip), 41: self._txt(company.hds_in_tds_responsible_email), 42: country,
            46: self._amount(sum(challans.mapped('total_paid'))),
            # Regular statement filed for an earlier period (Y/N) and its token number
            51: 'Y' if self.earlier_regular_statement else 'N',
            52: self._txt(self.previous_token_number) if self.earlier_regular_statement else '',
        })
        for challan_no, challan in enumerate(challans, start=1):
            challan_lines = challan.line_ids.sorted(lambda line: (line.paid_date or fields.Date.today(), line.id))
            deductee_tds = sum(challan_lines.mapped('tds_amount'))
            add('CD', {
                2: '1', 3: str(challan_no), 4: str(len(challan_lines)), 5: 'N',
                # Challan amount break-up, in the challan's order: tax, surcharge (included in the
                # tax), interest, others (penalty); they add up to the total deposited
                7: self._amount(challan.tds_amount), 8: self._amount(0.0),
                9: self._amount(challan.interest_amount), 10: self._amount(challan.penalty_amount),
                11: self._amount(challan.total_paid), 12: 'C',
                14: self._txt(challan.bsr_code), 16: self._txt(challan.challan_number),
                18: self._date(challan.paid_date),
                20: self._amount(deductee_tds), 21: self._amount(deductee_tds), 22: challan.minor_head,
            })
            for deductee_no, line in enumerate(challan_lines, start=1):
                add('DD', {
                    2: '1', 3: str(challan_no), 4: str(deductee_no), 5: 'O',
                    7: self._txt(line.pan).upper() or PAN_NOT_AVAILABLE, 8: self._txt(line.employee_id.name),
                    14: '1002', 17: 'Y', 18: self._date(line.paid_date), 19: self._amount(line.gross_wage),
                    23: self._amount(line.tds_amount), 24: self._amount(line.tds_amount),
                    26: self._date(line.paid_date), 28: self._date(challan.paid_date), 31: 'C',
                })
        return '\n'.join(lines) + '\n'

    def action_generate_text_file(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Mark the Form 138 as Done before generating its text file."))
        if not self.challan_ids:
            raise UserError(_("There should be at least one challan to generate the text file."))
        self._check_text_file_data()
        content = self._build_text_file()
        fy = self.financial_year_id
        filename = f'{fy.start_date.year}{str(fy.end_date.year)[-2:]}{dict(QUARTERS)[self.quarter]}.txt'
        self.write({'text_file': BinaryBytes(content.encode('utf-8'), filename), 'text_filename': filename})
        self.message_post(body=_("Text file %s generated.", filename))
        return True
