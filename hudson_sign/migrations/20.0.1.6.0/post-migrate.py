def migrate(cr, version):
    """Templates made on the fly to sign a document of the Documents app are not
    reusable templates: keep them out of Sign > Templates."""
    cr.execute("""
        UPDATE hudson_sign_template
           SET active = FALSE
         WHERE dms_file_id IS NOT NULL
           AND active
    """)
