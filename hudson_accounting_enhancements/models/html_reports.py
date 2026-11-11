from odoo import models

class AccountCommonReport(models.TransientModel):
    _inherit = "account.common.report"

    def check_report_html(self):
        action = self.check_report()
        if isinstance(action, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'hudson_dynamic_reports.dynamic_report',
                'name': 'Dynamic Report',
                'params': {
                    'wizard_id': self.id,
                    'model_name': self._name,
                    'data': action.get('data', {}),
                }
            }
        return action

class AccountTaxReportWizard(models.TransientModel):
    _inherit = "account.tax.report.wizard"

    def check_report_html(self):
        action = self.check_report()
        if isinstance(action, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'hudson_dynamic_reports.dynamic_report',
                'name': 'Dynamic Report',
                'params': {
                    'wizard_id': self.id,
                    'model_name': self._name,
                    'data': action.get('data', {}),
                }
            }
        return action

class AccountDayBookReport(models.TransientModel):
    _inherit = "account.daybook.report"

    def check_report_html(self):
        action = self.check_report()
        if isinstance(action, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'hudson_dynamic_reports.dynamic_report',
                'name': 'Dynamic Report',
                'params': {
                    'wizard_id': self.id,
                    'model_name': self._name,
                    'data': action.get('data', {}),
                }
            }
        return action

class AccountCashBookReport(models.TransientModel):
    _inherit = "account.cashbook.report"

    def check_report_html(self):
        action = self.check_report()
        if isinstance(action, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'hudson_dynamic_reports.dynamic_report',
                'name': 'Dynamic Report',
                'params': {
                    'wizard_id': self.id,
                    'model_name': self._name,
                    'data': action.get('data', {}),
                }
            }
        return action

class AccountBankBookReport(models.TransientModel):
    _inherit = "account.bankbook.report"

    def check_report_html(self):
        action = self.check_report()
        if isinstance(action, dict):
            return {
                'type': 'ir.actions.client',
                'tag': 'hudson_dynamic_reports.dynamic_report',
                'name': 'Dynamic Report',
                'params': {
                    'wizard_id': self.id,
                    'model_name': self._name,
                    'data': action.get('data', {}),
                }
            }
        return action

