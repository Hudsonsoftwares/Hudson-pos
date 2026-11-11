def migrate(cr, version):
    """ The Knowledge integration moved to the optional helpdesk_management_pro_knowledge bridge.
    Odoo only auto-installs a new bridge when its dependencies get installed, not on upgrade:
    install it in this upgrade when Hudson Knowledge is already installed, so the Knowledge
    settings (and their data) are kept. """
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'hudson_knowledge' AND state = 'installed'")
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE ir_module_module SET state = 'to install'
        WHERE name = 'helpdesk_management_pro_knowledge' AND state = 'uninstalled'
    """)
