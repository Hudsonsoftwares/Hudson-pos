def migrate(cr, version):
    """ Budgets follow Odoo Enterprise: Draft -> Open -> Done. The "Confirmed" (to approve) step is gone: those
    budgets are open, as the validated ones (the "validate" value is now labelled "Open"). """
    if not version:
        return
    cr.execute("UPDATE account_budget SET state = 'validate' WHERE state = 'confirm'")
    cr.execute("UPDATE account_budget_line SET budget_state = 'validate' WHERE budget_state = 'confirm'")
