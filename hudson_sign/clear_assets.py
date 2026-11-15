env['ir.attachment'].search([('url', '=like', '/web/assets/%')]).unlink()
env.cr.commit()
print("ASSETS CLEARED SUCCESSFULLY!")
