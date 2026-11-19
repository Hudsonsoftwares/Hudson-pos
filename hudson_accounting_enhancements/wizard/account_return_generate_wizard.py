from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountReturnGenerateWizard(models.TransientModel):
    _name = 'account.return.generate.wizard'
    _description = "Generate Tax Return"

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    available_type_ids = fields.Many2many('account.return.type', compute='_compute_available_type_ids')
    type_id = fields.Many2one('account.return.type', string="Return Type", required=True,
                              domain="[('id', 'in', available_type_ids)]")
    date_from = fields.Date(string="Dates", required=True)
    date_to = fields.Date(required=True)
    warning_message = fields.Char(compute='_compute_warning')
    is_blocking = fields.Boolean(compute='_compute_warning')

    @api.depends('company_id')
    def _compute_available_type_ids(self):
        for wizard in self:
            wizard.available_type_ids = self.env['account.return.type']._get_available_types(wizard.company_id)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env['res.company'].browse(res.get('company_id')) or self.env.company
        if 'type_id' in fields_list and not res.get('type_id'):
            types = self.env['account.return.type']._get_available_types(company)
            if types:
                res['type_id'] = types[0].id
        if res.get('type_id') and not res.get('date_from'):
            res.update(self._default_period(self.env['account.return.type'].browse(res['type_id']), company))
        return res

    @api.model
    def _default_period(self, rtype, company):
        """ The most recent finished period without a return, else the current one. """
        today = fields.Date.context_today(self)
        date_from, date_to = rtype._get_previous_period(company, today)
        Return = self.env['account.return'].with_context(active_test=False)
        if Return.search_count([('type_id', '=', rtype.id), ('company_id', '=', company.id),
                                ('date_from', '=', date_from), ('date_to', '=', date_to)]):
            date_from, date_to = rtype._get_period(company, today)
        return {'date_from': date_from, 'date_to': date_to}

    @api.onchange('type_id')
    def _onchange_type_id(self):
        if self.type_id:
            self.update(self._default_period(self.type_id, self.company_id))

    @api.depends('type_id', 'date_from', 'date_to', 'company_id')
    def _compute_warning(self):
        for wizard in self:
            message, blocking = False, False
            if wizard.type_id and wizard.date_from and wizard.date_to:
                if wizard.date_from > wizard.date_to:
                    message, blocking = _("The start date must be before the end date."), True
                elif self.env['account.return'].with_context(active_test=False).search_count([
                    ('type_id', '=', wizard.type_id.id), ('company_id', '=', wizard.company_id.id),
                    ('date_from', '=', wizard.date_from), ('date_to', '=', wizard.date_to),
                ]):
                    message, blocking = _("A return already exists for this period."), True
                elif (wizard.date_from, wizard.date_to) != wizard.type_id._get_period(
                        wizard.company_id, wizard.date_from):
                    message = _("These dates don't match the %(periodicity)s periodicity of this return type.",
                                periodicity=dict(wizard.type_id._fields['periodicity']._description_selection(
                                    self.env)).get(wizard.type_id.periodicity, '').lower())
            else:
                blocking = True
            wizard.warning_message = message
            wizard.is_blocking = blocking

    def action_generate(self):
        self.ensure_one()
        if self.is_blocking:
            raise UserError(self.warning_message or _("Select a return type and a period."))
        ret = self.env['account.return'].create({
            'type_id': self.type_id.id,
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        return ret.action_review()
