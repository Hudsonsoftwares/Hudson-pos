# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class HrRuleParameter(models.Model):
    """Rule Parameter allows dynamic, date-versioned statutory configurations without modifying code."""
    _name = 'hr.rule.parameter'
    _description = 'Salary Rule Parameter'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, index=True)
    category = fields.Char(string='Category')
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        default=lambda self: self.env['hr.payroll.structure']._default_country_id(),
        domain=lambda self: self.env['hr.payroll.structure']._get_payroll_country_domain(),
        help="Country of applicability for this rule parameter."
    )
    description = fields.Text(string='Description')
    parameter_version_ids = fields.One2many(
        'hr.rule.parameter.value',
        'rule_parameter_id',
        string='Values by Date'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code, country_id)', 'The code of the rule parameter must be unique per country!'),
    ]

    def _get_parameter_value(self, code_or_date, date=None):
        """Retrieve the parameter value valid for the specified date.
        Supports both record-level call: record._get_parameter_value(date)
        and model-level call: env['hr.rule.parameter']._get_parameter_value(code, date)
        """
        if self:
            param = self.ensure_one()
            eval_date = date or code_or_date
        else:
            code = code_or_date
            eval_date = date
            param = self.search([('code', '=', code)], limit=1)
            if not param:
                return False

        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.to_date(eval_date)

        for version in param.parameter_version_ids.sorted(key=lambda v: v.date_from, reverse=True):
            if version.date_from <= eval_date:
                try:
                    return safe_eval(version.parameter_value)
                except Exception:
                    return version.parameter_value
        return False

    @api.model
    def get_parameter(self, code, date=None, as_decimal=False, **kwargs):
        """Standard parameter retrieval helper."""
        val = self._get_parameter_value(code, date)
        if val is False:
            return 0.0
        try:
            num = float(val)
            return (num / 100.0) if as_decimal else num
        except (ValueError, TypeError):
            return val


class HrRuleParameterValue(models.Model):
    """Date-versioned value for a Rule Parameter."""
    _name = 'hr.rule.parameter.value'
    _description = 'Salary Rule Parameter Value'
    _order = 'date_from desc'

    rule_parameter_id = fields.Many2one(
        'hr.rule.parameter',
        string='Parameter',
        ondelete='cascade'
    )
    parameter_id = fields.Many2one(
        'hr.rule.parameter',
        string='Parameter',
        ondelete='cascade'
    )
    date_from = fields.Date(string='From Date', required=True)
    parameter_value = fields.Text(
        string='Value (Python Expression)',
        required=True,
        help="Evaluated via safe_eval (e.g. 15000, 0.12, {'A': 100}) or stored as raw text"
    )
    description = fields.Text(string='Description')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'parameter_id' in vals and 'rule_parameter_id' not in vals:
                vals['rule_parameter_id'] = vals['parameter_id']
            elif 'rule_parameter_id' in vals and 'parameter_id' not in vals:
                vals['parameter_id'] = vals['rule_parameter_id']
        return super().create(vals_list)

    def write(self, vals):
        if 'parameter_id' in vals and 'rule_parameter_id' not in vals:
            vals['rule_parameter_id'] = vals['parameter_id']
        elif 'rule_parameter_id' in vals and 'parameter_id' not in vals:
            vals['parameter_id'] = vals['rule_parameter_id']
        return super().write(vals)

    @api.constrains('parameter_value')
    def _check_parameter_value(self):
        for record in self:
            if not record.parameter_value:
                continue
            try:
                safe_eval(record.parameter_value)
            except Exception:
                # Raw strings / non-python literals are permitted as text parameters
                pass
