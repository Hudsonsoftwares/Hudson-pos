# -*- coding: utf-8 -*-
import calendar
import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Salary rule codes of the income tax (TDS) deducted on a payslip, as used by the payroll dashboard
TDS_RULE_CODES = ('TDS', 'INCOME_TAX', 'IT', 'HDS_IN_TDS')

# Fields that can still change on a deposited (Done) challan
_DONE_WRITABLE_FIELDS = {'state'}


def _default_period_start(model):
    today = fields.Date.context_today(model)
    return today.replace(day=1) - relativedelta(months=1)


def _default_period_end(model):
    return fields.Date.context_today(model).replace(day=1) - relativedelta(days=1)


class HdsTdsChallan(models.Model):
    """TDS challan (ITNS 281): income tax deducted from the salaries paid in a period and
    deposited with the government. The TDS amount is the TDS of the payslips imported in it."""
    _name = 'hds.tds.challan'
    _description = 'TDS Challan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(string='Challan', compute='_compute_name', store=True)
    date_from = fields.Date(string='Challan Period', required=True, tracking=True,
                            default=lambda self: _default_period_start(self))
    date_to = fields.Date(string='Period End', required=True, tracking=True,
                          default=lambda self: _default_period_end(self))
    paid_date = fields.Date(string='Paid Date', tracking=True, default=fields.Date.context_today,
                            help="Date the tax was deposited with the bank.")
    challan_number = fields.Char(string='Challan Number', tracking=True,
                                 help="Challan serial number (5 digits) printed on the bank counterfoil.")
    bsr_code = fields.Char(string='BSR Code', tracking=True,
                           help="BSR code (7 digits) of the bank branch where the tax was deposited.")
    minor_head = fields.Selection([
        ('200', '200 - TDS payable by taxpayer'),
        ('400', '400 - TDS regular assessment'),
    ], string='Minor Head', default='200', required=True, tracking=True,
        help="200: TDS deducted and paid by the deductor. 400: tax demanded under regular assessment.")
    payment_mode = fields.Selection([
        ('transfer_voucher', 'Transfer Voucher'),
        ('bank_challan', 'Bank Challan'),
    ], string='Mode of Payment', default='bank_challan', required=True, tracking=True,
        help="Transfer Voucher: book entry (government deductors). Bank Challan: deposited in a bank.")
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency')
    financial_year_id = fields.Many2one('tds.financial.year', string='Tax Year',
                                        compute='_compute_financial_year_id', store=True, index=True)
    line_ids = fields.One2many('hds.tds.challan.line', 'challan_id', string='Challan Lines')
    line_count = fields.Integer(string='Payslips', compute='_compute_amounts', store=True)
    tds_amount = fields.Monetary(string='TDS Amount', compute='_compute_amounts', store=True, tracking=True)
    penalty_amount = fields.Monetary(string='Penalty', tracking=True)
    interest_amount = fields.Monetary(string='Interest', tracking=True)
    total_paid = fields.Monetary(string='Total Paid', compute='_compute_amounts', store=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], string='State', default='draft', required=True, copy=False, tracking=True)

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for challan in self:
            start, end = challan.date_from, challan.date_to
            if not start or not end:
                challan.name = _('New Challan')
            elif (start.day == 1 and (start.year, start.month) == (end.year, end.month)
                  and end.day == calendar.monthrange(end.year, end.month)[1]):
                challan.name = _('TDS Challan %s', start.strftime('%b %Y'))
            else:
                challan.name = _('TDS Challan %(start)s - %(end)s',
                                 start=start.strftime('%d %b %Y'), end=end.strftime('%d %b %Y'))

    @api.depends('date_from')
    def _compute_financial_year_id(self):
        FinancialYear = self.env['tds.financial.year'].with_context(active_test=False)
        for challan in self:
            challan.financial_year_id = challan.date_from and FinancialYear.search([
                ('start_date', '<=', challan.date_from),
                ('end_date', '>=', challan.date_from),
            ], limit=1)

    @api.depends('line_ids.tds_amount', 'penalty_amount', 'interest_amount')
    def _compute_amounts(self):
        for challan in self:
            challan.line_count = len(challan.line_ids)
            challan.tds_amount = sum(challan.line_ids.mapped('tds_amount'))
            challan.total_paid = challan.tds_amount + (challan.penalty_amount or 0.0) + (challan.interest_amount or 0.0)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for challan in self:
            if challan.date_from and challan.date_to and challan.date_to < challan.date_from:
                raise ValidationError(_("The challan period cannot end before it starts."))

    @api.constrains('challan_number', 'bsr_code')
    def _check_bank_references(self):
        for challan in self:
            if challan.challan_number and not re.fullmatch(r'\d{5}', challan.challan_number.strip()):
                raise ValidationError(_("The Challan Number must be the 5-digit serial number of the challan."))
            if challan.bsr_code and not re.fullmatch(r'\d{7}', challan.bsr_code.strip()):
                raise ValidationError(_("The BSR Code must be the 7-digit code of the bank branch."))

    @api.constrains('penalty_amount', 'interest_amount')
    def _check_extra_amounts(self):
        for challan in self:
            if (challan.penalty_amount or 0.0) < 0 or (challan.interest_amount or 0.0) < 0:
                raise ValidationError(_("Penalty and Interest cannot be negative."))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def write(self, vals):
        locked = set(vals) - _DONE_WRITABLE_FIELDS
        if locked and any(challan.state == 'done' for challan in self):
            raise UserError(_("A deposited (Done) TDS challan cannot be changed. Reset it to Draft first."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(challan.state == 'done' for challan in self):
            raise UserError(_("A deposited (Done) TDS challan cannot be deleted. Reset it to Draft first."))

    # ------------------------------------------------------------------
    # Payslips of the challan
    # ------------------------------------------------------------------
    def _eligible_payslip_domain(self):
        """Paid payslips of the company whose salary period starts within the challan period (the
        April pay run goes to the April challan, however late it is marked paid). Refunds and
        payslips flagged as duplicates are left out, as in the payroll analysis."""
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'paid'),
            ('credit_note', '=', False),
            ('has_duplicate_payslip', '=', False),
            ('date_from', '>=', self.date_from),
            ('date_from', '<=', self.date_to),
        ]

    def _get_importable_payslips(self):
        """Paid payslips of the period, with TDS, that are not in any challan yet."""
        self.ensure_one()
        used = self.env['hds.tds.challan.line'].sudo().search([]).mapped('payslip_id')
        payslips = self.env['hr.payslip'].search(self._eligible_payslip_domain() + [('id', 'not in', used.ids)])
        return payslips.filtered(lambda slip: slip._hds_in_challan_tds_amount() > 0)

    def _check_draft(self):
        if any(challan.state != 'draft' for challan in self):
            raise UserError(_("Payslips can only be imported into a Draft TDS challan."))

    def action_import_payslips(self):
        self.ensure_one()
        self._check_draft()
        list_view = self.env.ref('hudson_in_payroll.hds_tds_challan_import_payslip_list')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Payslips'),
            'res_model': 'hr.payslip',
            'view_mode': 'list',
            'views': [(list_view.id, 'list')],
            'domain': [('id', 'in', self._get_importable_payslips().ids)],
            'context': {'hds_tds_challan_id': self.id, 'create': False, 'edit': False, 'delete': False},
            'target': 'new',
            'help': _('<p class="o_view_nocontent_smiling_face">No payslips to import</p>'
                      '<p>Paid payslips with TDS whose salary period starts within the challan period '
                      'and that are not in another challan appear here.</p>'),
        }

    def _add_payslips(self, payslips):
        """Add payslips to the challan, re-checking that each one can still be imported."""
        self.ensure_one()
        self._check_draft()
        importable = self._get_importable_payslips()
        rejected = payslips - importable
        if rejected:
            raise UserError(_(
                "These payslips cannot be added to the challan (not paid, salary period outside the "
                "challan period, without TDS, of another company or already in a challan):\n%s",
                "\n".join(rejected.mapped('display_name'))))
        self.env['hds.tds.challan.line'].create([
            {'challan_id': self.id, 'payslip_id': payslip.id} for payslip in payslips
        ])

    def action_done(self):
        for challan in self:
            missing = [label for field, label in (
                ('challan_number', _('Challan Number')),
                ('bsr_code', _('BSR Code')),
                ('paid_date', _('Paid Date')),
            ) if not challan[field]]
            if missing:
                raise UserError(_("Fill in %s before marking the challan as Done.", ", ".join(missing)))
            if not challan.line_ids:
                raise UserError(_("Import the payslips of the period before marking the challan as Done."))
            eligible = self.env['hr.payslip'].search(challan._eligible_payslip_domain())
            invalid = challan.line_ids.mapped('payslip_id') - eligible
            if invalid:
                raise UserError(_(
                    "These payslips are no longer paid payslips of the challan period. Remove them from the "
                    "challan or correct the period:\n%s", "\n".join(invalid.mapped('display_name'))))
        self._check_form_138_not_done()
        self.write({'state': 'done'})

    def action_draft(self):
        if not self.env.user.has_group('hudson_payroll_base.group_payroll_manager'):
            raise UserError(_("Only payroll managers can reset a deposited TDS challan to Draft."))
        self._check_form_138_not_done()
        self.write({'state': 'draft'})

    def _get_form_138(self):
        """Form 138 (quarterly return) of the quarter in which the challan period starts."""
        self.ensure_one()
        return self.env['hds.form.138'].search([
            ('company_id', '=', self.company_id.id),
            ('date_from', '<=', self.date_from),
            ('date_to', '>=', self.date_from),
        ], limit=1)

    def _check_form_138_not_done(self):
        for challan in self:
            form = challan._get_form_138()
            if form.state == 'done':
                raise UserError(_("%(challan)s is part of %(form)s, which is Done. Set the Form 138 to Draft first.",
                                  challan=challan.display_name, form=form.display_name))

    def action_form_138(self):
        """Open the Form 138 of the challan's quarter (its tax year's quarters are created if needed)."""
        self.ensure_one()
        form = self._get_form_138()
        if not form:
            if not self.financial_year_id:
                raise UserError(_("No Tax Year covers %s. Create it in Payroll > Configuration > TDS Financial Years.",
                                  self.date_from))
            self.env['hds.form.138']._ensure_quarters(self.financial_year_id, self.company_id)
            form = self._get_form_138()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hds.form.138',
            'res_id': form.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class HdsTdsChallanLine(models.Model):
    """A payslip whose TDS is deposited with the challan."""
    _name = 'hds.tds.challan.line'
    _description = 'TDS Challan Line'
    _order = 'paid_date, employee_id, id'

    challan_id = fields.Many2one('hds.tds.challan', string='Challan', required=True, ondelete='cascade', index=True)
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='challan_id.company_id', store=True, string='Company')
    currency_id = fields.Many2one(related='challan_id.currency_id', string='Currency')
    employee_id = fields.Many2one(related='payslip_id.employee_id', store=True, string='Employee')
    pan = fields.Char(related='payslip_id.employee_id.hds_in_pan', string='PAN')
    paid_date = fields.Date(related='payslip_id.payment_date', store=True, string='Paid Date')
    net_wage = fields.Monetary(related='payslip_id.net_wage', store=True, string='Net Wage')
    gross_wage = fields.Monetary(related='payslip_id.gross_wage', store=True, string='Amount Paid')
    deposit_date = fields.Date(related='challan_id.paid_date', string='Deposit Date')
    tds_amount = fields.Monetary(string='Total TDS', compute='_compute_tds_amount', store=True)

    @api.depends('payslip_id.line_ids.code', 'payslip_id.line_ids.total')
    def _compute_tds_amount(self):
        for line in self:
            line.tds_amount = line.payslip_id._hds_in_challan_tds_amount()

    @api.constrains('payslip_id')
    def _check_payslip_once(self):
        for line in self:
            other = self.sudo().search([('payslip_id', '=', line.payslip_id.id), ('id', '!=', line.id)], limit=1)
            if other:
                raise ValidationError(_("Payslip %(slip)s is already in %(challan)s.",
                                        slip=line.payslip_id.display_name, challan=other.challan_id.display_name))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(line.challan_id.state == 'done' for line in self):
            raise UserError(_("Payslips cannot be removed from a deposited (Done) TDS challan."))


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    hds_in_challan_tds_amount = fields.Monetary(string='TDS', compute='_compute_hds_in_challan_tds_amount')

    def _hds_in_challan_tds_amount(self):
        self.ensure_one()
        return sum(abs(line.total) for line in self.line_ids if (line.code or '').upper() in TDS_RULE_CODES)

    def _compute_hds_in_challan_tds_amount(self):
        for slip in self:
            slip.hds_in_challan_tds_amount = slip._hds_in_challan_tds_amount()

    def action_hds_add_to_tds_challan(self):
        """Import Payslips dialog: add the selected payslips to the challan that opened it."""
        challan = self.env['hds.tds.challan'].browse(self.env.context.get('hds_tds_challan_id')).exists()
        if not challan:
            raise UserError(_("Open the Import Payslips dialog from a TDS challan."))
        challan._add_payslips(self)
        return {'type': 'ir.actions.act_window_close'}

    def _hds_in_tds_challan_lines(self):
        if not self.ids:
            return self.env['hds.tds.challan.line']
        return self.env['hds.tds.challan.line'].sudo().search([('payslip_id', 'in', self.ids)])

    def _hds_in_release_from_tds_challans(self, operation, reason):
        """A payslip in a deposited challan cannot be cancelled, reset, deleted or un-paid; in a draft
        challan it is removed from the challan (it is no longer a paid payslip of the period)."""
        lines = self._hds_in_tds_challan_lines()
        deposited = lines.filtered(lambda line: line.challan_id.state == 'done')
        if deposited:
            raise UserError(_(
                "You cannot %(operation)s these payslips: their TDS is deposited with a Done TDS challan. "
                "Reset the challan to Draft first.\n%(details)s",
                operation=operation,
                details="\n".join(f"{line.payslip_id.display_name} ({line.challan_id.display_name})" for line in deposited)))
        for challan in lines.mapped('challan_id'):
            removed = lines.filtered(lambda line: line.challan_id == challan)
            challan.sudo().message_post(body=_("Payslips removed from the challan (%(reason)s): %(slips)s",
                                               reason=reason,
                                               slips=", ".join(removed.mapped('payslip_id.display_name'))))
        lines.sudo().unlink()

    def action_payslip_cancel(self):
        self._hds_in_release_from_tds_challans(_('cancel'), _('payslip cancelled'))
        return super().action_payslip_cancel()

    def action_payslip_draft(self):
        self._hds_in_release_from_tds_challans(_('reset to draft'), _('payslip reset to draft'))
        return super().action_payslip_draft()

    def unlink(self):
        self._hds_in_release_from_tds_challans(_('delete'), _('payslip deleted'))
        return super().unlink()

    def write(self, vals):
        # A payslip that stops being paid (e.g. the pay run's Revert Paid) leaves its draft challan
        # and cannot while its TDS is deposited; a deposited payslip's paid date cannot change.
        if self.ids and 'state' in vals and vals['state'] != 'paid':
            self.filtered(lambda slip: slip.state == 'paid')._hds_in_release_from_tds_challans(
                _('revert the payment of'), _('payment reverted'))
        if self.ids and 'payment_date' in vals:
            new_date = fields.Date.to_date(vals['payment_date'])
            deposited = self._hds_in_tds_challan_lines().filtered(
                lambda line: line.challan_id.state == 'done' and line.payslip_id.payment_date != new_date)
            if deposited:
                raise UserError(_(
                    "The payment date of these payslips cannot change: their TDS is deposited with a Done TDS "
                    "challan. Reset the challan to Draft first.\n%s",
                    "\n".join(f"{line.payslip_id.display_name} ({line.challan_id.display_name})" for line in deposited)))
        return super().write(vals)
