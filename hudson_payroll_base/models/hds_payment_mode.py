# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class HdsPaymentMode(models.Model):
    """
    Configurable Payment Mode master, shared by every payroll localization.
    HR Admins can create, edit, or deactivate payment modes from
    Payroll Settings → Configure Payment Modes.
    The selected mode is stored on the Employee and auto-populated on Payslips.
    """
    _name = 'hds.payment.mode'
    _description = 'Payroll Payment Mode'
    _order = 'sequence, name'

    @api.model
    def _auto_init(self):
        # Upgrade of databases created before payment modes had a company. On a new install the
        # table does not exist yet (the ORM creates it with the column), so there is nothing to do.
        if tools.sql.table_exists(self.env.cr, self._table):
            try:
                with self.env.cr.savepoint():
                    self.env.cr.execute("""
                        ALTER TABLE hds_payment_mode
                        ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES res_company(id) ON DELETE SET NULL;
                    """)
                    # Update user-created custom modes (not seeded IDs 1-5) to default company if null
                    self.env.cr.execute("""
                        UPDATE hds_payment_mode
                        SET company_id = (SELECT id FROM res_company ORDER BY id ASC LIMIT 1)
                        WHERE id NOT IN (1, 2, 3, 4, 5) AND company_id IS NULL;
                    """)
            except Exception:
                pass
        return super()._auto_init()

    name = fields.Char(
        string="Payment Mode",
        required=True,
        translate=False,
        help="Display label for this payment mode (e.g. 'NEFT / RTGS', 'Cash')."
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Short internal code (e.g. 'neft_rtgs', 'cash'). Used for logic branching."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        index=True,
        help="Company to which this payment mode belongs. If left empty, it is available across all companies."
    )
    is_cash = fields.Boolean(
        string="Is Cash Mode",
        default=False,
        help="If checked, bank account / account number fields will be hidden on the payslip "
             "since cash payment does not involve bank details."
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display ordering in dropdown lists."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive this payment mode without deleting it."
    )
    notes = fields.Text(
        string="Notes",
        help="Optional internal notes about this payment mode."
    )

    @api.constrains('code', 'company_id')
    def _check_code_company_uniq(self):
        for rec in self:
            domain = [('code', '=', rec.code), ('id', '!=', rec.id)]
            if rec.company_id:
                domain.append(('company_id', '=', rec.company_id.id))
            else:
                domain.append(('company_id', '=', False))
            if self.search_count(domain):
                raise ValidationError(_("A payment mode with code '%(code)s' already exists for this company scope.", code=rec.code))
