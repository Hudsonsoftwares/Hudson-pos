# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval


class HrSalaryRule(models.Model):
    """Salary Rule defines formula, condition, and category for calculating a payslip line."""
    _name = 'hr.salary.rule'
    _description = 'Salary Rule'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    sequence = fields.Integer(string='Sequence', default=5, required=True, index=True)
    active = fields.Boolean(default=True)
    category_id = fields.Many2one(
        'hr.salary.rule.category',
        string='Category',
        required=True,
        index=True
    )
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Salary Structure',
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        help="Eventual third party involved in the salary payment of this rule."
    )
    section_id = fields.Many2one(
        'hr.salary.rule.section',
        string='Salary Rule Section',
        index=True,
        help="Section under which this rule is grouped in salary structures."
    )
    condition_select = fields.Selection([
        ('none', 'Always True'),
        ('range', 'Range'),
        ('python', 'Python Expression'),
    ], string='Condition Type', default='none', required=True)
    condition_range = fields.Char(
        string='Range Based on',
        default='contract.wage',
        help="Compute attribute name, e.g. contract.wage"
    )
    condition_range_min = fields.Float(string='Minimum Range', default=0.0)
    condition_range_max = fields.Float(string='Maximum Range', default=0.0)
    condition_python = fields.Text(
        string='Python Condition',
        default='result = True',
        help="Applied condition. Set 'result = True' or 'result = False'."
    )
    amount_select = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('fix', 'Fixed Amount'),
        ('code', 'Python Code'),
    ], string='Amount Type', default='code', required=True)
    amount_fix = fields.Float(string='Fixed Amount', digits='Payroll')
    amount_percentage = fields.Float(string='Percentage (%)', digits='Payroll Rate')
    amount_percentage_base = fields.Char(
        string='Percentage based on',
        default='contract.wage',
        help="Base for calculation, e.g. contract.wage or rules.BASIC.total"
    )
    amount_python_compute = fields.Text(
        string='Python Code',
        default='result = contract.wage',
        help="Computation formula. Returns amount in 'result'."
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        related='struct_id.country_id',
        store=True,
        readonly=True
    )

    # Display Configuration
    appears_on_payslip = fields.Selection([
        ('always', 'Always'),
        ('never', 'Never'),
        ('non_zero', 'If Result is not zero'),
    ], string='Appears on Payslip', default='always',
       help="Specify when this rule will be displayed on printed payslip.")
    title_only = fields.Boolean(
        string='Title only',
        default=False,
        help="If checked, only the title will be displayed, without amount."
    )
    display_color = fields.Char(
        string='Color',
        default='#000000',
        help="Color for displaying this rule on payslips."
    )
    display_bold = fields.Boolean(string='Bold', default=False)
    display_italic = fields.Boolean(string='Italic', default=False)
    display_underline = fields.Boolean(string='Underline', default=False)
    display_indented = fields.Boolean(string='Indented', default=False)
    display_space_on_top = fields.Boolean(string='Space on top', default=False)
    display_name_note = fields.Char(
        string='Display Name',
        help="Additional info that will be printed below the rule"
    )

    note = fields.Text(string='Description')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=False,
        help="If set, this salary rule will only be available to the specified company. If empty, it is shared across all companies."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'appears_on_payslip' in vals:
                if vals['appears_on_payslip'] is True or vals['appears_on_payslip'] == 'True':
                    vals['appears_on_payslip'] = 'always'
                elif vals['appears_on_payslip'] is False or vals['appears_on_payslip'] == 'False':
                    vals['appears_on_payslip'] = 'never'
        return super().create(vals_list)

    def write(self, vals):
        if 'appears_on_payslip' in vals:
            if vals['appears_on_payslip'] is True or vals['appears_on_payslip'] == 'True':
                vals['appears_on_payslip'] = 'always'
            elif vals['appears_on_payslip'] is False or vals['appears_on_payslip'] == 'False':
                vals['appears_on_payslip'] = 'never'
        return super().write(vals)

    @api.constrains('code', 'struct_id', 'company_id')
    def _check_code_struct_unique(self):
        for rule in self:
            if rule.code and rule.struct_id:
                dup = self.search([
                    ('id', '!=', rule.id),
                    ('code', '=', rule.code),
                    ('struct_id', '=', rule.struct_id.id),
                    ('company_id', '=', rule.company_id.id),
                ], limit=1)
                if dup:
                    raise ValidationError(_(
                        "A rule with code '%(code)s' already exists in structure '%(struct)s' for this company scope!",
                        code=rule.code,
                        struct=rule.struct_id.name
                    ))

    def _satisfies_condition(self, localdict):
        """Evaluate if this rule condition is satisfied."""
        self.ensure_one()
        if self.condition_select == 'none':
            return True
        elif self.condition_select == 'range':
            try:
                val = safe_eval(self.condition_range, localdict)
                return self.condition_range_min <= val <= self.condition_range_max
            except Exception as e:
                raise UserError(_("Error evaluating condition range for rule %(rule)s: %(err)s") % {
                    'rule': self.name, 'err': str(e)
                })
        elif self.condition_select == 'python':
            try:
                eval_dict = dict(localdict)
                safe_eval(self.condition_python, eval_dict, mode='exec')
                return bool(eval_dict.get('result', False))
            except Exception as e:
                raise UserError(_("Error evaluating Python condition for rule %(rule)s: %(err)s") % {
                    'rule': self.name, 'err': str(e)
                })
        return False

    def _compute_rule(self, localdict):
        """Compute the rule amount and rate according to amount_select."""
        self.ensure_one()
        if self.amount_select == 'fix':
            try:
                return self.amount_fix, 100.0, 1.0
            except Exception as e:
                raise UserError(_("Error computing fixed amount for rule %(rule)s: %(err)s") % {
                    'rule': self.name, 'err': str(e)
                })
        elif self.amount_select == 'percentage':
            try:
                base_val = float(safe_eval(self.amount_percentage_base, localdict) or 0.0)
                return base_val, self.amount_percentage, 1.0
            except Exception as e:
                raise UserError(_("Error computing percentage for rule %(rule)s: %(err)s") % {
                    'rule': self.name, 'err': str(e)
                })
        elif self.amount_select == 'code':
            try:
                eval_dict = dict(localdict)
                safe_eval(self.amount_python_compute, eval_dict, mode='exec')
                amount = float(eval_dict.get('result', 0.0))
                rate = float(eval_dict.get('result_rate', 100.0))
                qty = float(eval_dict.get('result_qty', 1.0))
                return amount, rate, qty
            except Exception as e:
                raise UserError(_("Error computing Python code for rule %(rule)s: %(err)s") % {
                    'rule': self.name, 'err': str(e)
                })
        return 0.0, 100.0, 1.0
