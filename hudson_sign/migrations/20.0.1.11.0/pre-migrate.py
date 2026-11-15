def migrate(cr, version):
    """"By SMS" was never available: those roles have no extra authentication."""
    cr.execute("UPDATE hudson_sign_template_role SET auth_method = 'none' WHERE auth_method = 'sms'")
