def migrate(cr, version):
    """Templates are listed under "My Favorites" by default: existing templates
    start as favorites of their author."""
    cr.execute("""
        INSERT INTO hudson_sign_template_favorite_rel (template_id, user_id)
        SELECT id, COALESCE(author_id, create_uid)
          FROM hudson_sign_template
         WHERE COALESCE(author_id, create_uid) IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
