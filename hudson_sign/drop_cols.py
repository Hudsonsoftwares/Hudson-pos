env.cr.execute('ALTER TABLE hudson_sign_item_type DROP COLUMN IF EXISTS linked_to, DROP COLUMN IF EXISTS linked_field;')
env.cr.commit()
print("COLUMNS DROPPED SUCCESSFULLY!")
