from odoo import fields, models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    followup_company_id = fields.Many2one(
        'res.company', string='Follow-up Company', index='btree_not_null', readonly=True,
        help="The company whose follow-up created this activity: only its follow-up runs mark it as done.")

    def _auto_init(self):
        super()._auto_init()
        self.env.cr.execute("""
            ALTER TABLE mail_activity 
            ADD COLUMN IF NOT EXISTS followup_company_id INTEGER REFERENCES res_company(id) ON DELETE SET NULL
        """)
