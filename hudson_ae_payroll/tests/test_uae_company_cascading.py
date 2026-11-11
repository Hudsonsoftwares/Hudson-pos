# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'TestUAECompanyCascading')
class TestUAECompanyCascading(TransactionCase):
    """
    Test suite for connected/cascading UAE jurisdiction configuration on res.company.
    Validates dynamic filtering, onchange clearing behavior, auto-resolution of
    Governing Labour Authority, and backend constraint validation.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env['res.company']
        cls.Jurisdiction = cls.env['uae.payroll.jurisdiction']
        cls.Emirate = cls.env['uae.emirate']
        cls.LabourAuthority = cls.env['uae.labour.authority']

        cls.auh = cls.Emirate.search([('code', '=', 'AUH')], limit=1)
        cls.dxb = cls.Emirate.search([('code', '=', 'DXB')], limit=1)
        cls.shj = cls.Emirate.search([('code', '=', 'SHJ')], limit=1)

        cls.mainland_auh = cls.Jurisdiction.search([('code', '=', 'AE_MAINLAND_AUH')], limit=1)
        cls.mainland_dxb = cls.Jurisdiction.search([('code', '=', 'AE_MAINLAND_DXB')], limit=1)
        cls.difc = cls.Jurisdiction.search([('code', '=', 'AE_FZ_DIFC')], limit=1)
        cls.adgm = cls.Jurisdiction.search([('code', '=', 'AE_FZ_ADGM')], limit=1)
        cls.masdar = cls.Jurisdiction.search([('code', '=', 'AE_FZ_MASDAR')], limit=1)
        cls.ifza = cls.Jurisdiction.search([('code', '=', 'AE_FZ_IFZA')], limit=1)

    def test_01_dynamic_jurisdiction_filtering(self):
        """
        Validate dynamic filtering criteria:
        WHERE emirate_id = company.uae_emirate_id AND jurisdiction_type = company.uae_jurisdiction_type
        """
        # Emirate = Abu Dhabi, Type = Mainland -> Mainland Abu Dhabi only
        auh_mainland = self.Jurisdiction.search([
            ('emirate_id', '=', self.auh.id),
            ('jurisdiction_type', '=', 'mainland'),
        ])
        self.assertEqual(len(auh_mainland), 1)
        self.assertEqual(auh_mainland.code, 'AE_MAINLAND_AUH')

        # Emirate = Abu Dhabi, Type = Free Zone -> Abu Dhabi Free Zones (ADGM, Masdar, twofour54, ADAFZ, KEZAD, ADIC)
        auh_fz = self.Jurisdiction.search([
            ('emirate_id', '=', self.auh.id),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(auh_fz), 6)
        self.assertIn(self.adgm, auh_fz)
        self.assertIn(self.masdar, auh_fz)

        # Emirate = Dubai, Type = Free Zone -> Dubai Free Zones (DIFC, DMCC, JAFZA, IFZA, etc.)
        dxb_fz = self.Jurisdiction.search([
            ('emirate_id', '=', self.dxb.id),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(dxb_fz), 23)
        self.assertIn(self.difc, dxb_fz)
        self.assertIn(self.ifza, dxb_fz)

    def test_02_onchange_emirate_clears_jurisdiction_and_authority(self):
        """
        When Emirate changes:
        If existing Jurisdiction belongs to another Emirate, automatically clear it.
        Clear/recompute the Governing Labour Authority.
        """
        company = self.Company.create({
            'name': 'Cascading Test Co DXB',
            'uae_emirate_id': self.dxb.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': self.difc.id,
        })
        self.assertEqual(company.uae_labour_authority_id.code, 'DIFC_AUTH')

        # Change Emirate to Abu Dhabi via Form to test UI onchange simulation
        from odoo.tests import Form
        with Form(company) as comp_form:
            comp_form.uae_emirate_id = self.auh
            # In UI Form, onchange triggers immediately upon setting field
            self.assertFalse(
                comp_form.uae_jurisdiction_id,
                "Jurisdiction must be cleared when changing to an Emirate that does not match."
            )
            self.assertFalse(
                comp_form.uae_labour_authority_id,
                "Labour authority must be cleared when jurisdiction is cleared."
            )

        # After saving form, company has new Emirate and cleared jurisdiction
        self.assertEqual(company.uae_emirate_id, self.auh)
        self.assertFalse(company.uae_jurisdiction_id)
        self.assertFalse(company.uae_labour_authority_id)

    def test_03_onchange_jurisdiction_type_clears_jurisdiction_and_authority(self):
        """
        When Jurisdiction Type changes:
        If its type does not match the new selection, automatically clear it.
        Clear/recompute the Governing Labour Authority.
        """
        company = self.Company.create({
            'name': 'Cascading Test Co AUH',
            'uae_emirate_id': self.auh.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': self.adgm.id,
        })
        self.assertEqual(company.uae_labour_authority_id.code, 'ADGM_AUTH')

        # Change Jurisdiction Type to Mainland via Form
        from odoo.tests import Form
        with Form(company) as comp_form:
            comp_form.uae_jurisdiction_type = 'mainland'
            self.assertFalse(
                comp_form.uae_jurisdiction_id,
                "Jurisdiction must be cleared when changing to a Jurisdiction Type that does not match."
            )
            self.assertFalse(
                comp_form.uae_labour_authority_id,
                "Labour authority must be cleared when jurisdiction is cleared."
            )

        # After saving form, company has mainland type and cleared jurisdiction
        self.assertEqual(company.uae_jurisdiction_type, 'mainland')
        self.assertFalse(company.uae_jurisdiction_id)
        self.assertFalse(company.uae_labour_authority_id)

    def test_04_onchange_jurisdiction_derives_authority_and_matches_hierarchy(self):
        """
        When Jurisdiction changes:
        Automatically derive: Jurisdiction -> governing_labour_authority_id.
        Ensure authority field is readonly.
        """
        company = self.Company.create({
            'name': 'Cascading Test Co Flow',
            'uae_emirate_id': self.dxb.id,
            'uae_jurisdiction_type': 'free_zone',
        })
        self.assertFalse(company.uae_jurisdiction_id)
        self.assertFalse(company.uae_labour_authority_id)

        # Select DIFC
        company.uae_jurisdiction_id = self.difc.id
        company._onchange_uae_jurisdiction_id()

        self.assertEqual(
            company.uae_labour_authority_id,
            self.difc.labour_authority_id,
            "Governing Labour Authority must auto-resolve from Jurisdiction."
        )
        self.assertEqual(company.uae_labour_authority_id.code, 'DIFC_AUTH')

        # Field property verification
        authority_field = self.Company._fields['uae_labour_authority_id']
        self.assertTrue(
            authority_field.readonly,
            "Governing Labour Authority must be read-only at Company level."
        )

    def test_05_backend_validation_rejects_mismatched_emirate(self):
        """
        Backend constraint must raise ValidationError if jurisdiction's emirate_id != company.uae_emirate_id.
        Tests API/RPC/direct database bypass.
        """
        # Attempt to save Company in Abu Dhabi with Dubai's DIFC Free Zone
        with self.assertRaises(ValidationError) as ctx:
            self.Company.create({
                'name': 'Invalid Emirate Co',
                'uae_emirate_id': self.auh.id,
                'uae_jurisdiction_type': 'free_zone',
                'uae_jurisdiction_id': self.difc.id,
            })
        self.assertIn("does not match company Emirate", str(ctx.exception))

        # Attempt to write invalid emirate to existing consistent company
        valid_co = self.Company.create({
            'name': 'Valid Then Modified Co',
            'uae_emirate_id': self.dxb.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': self.difc.id,
        })
        with self.assertRaises(ValidationError):
            valid_co.write({'uae_emirate_id': self.auh.id})

    def test_06_backend_validation_rejects_mismatched_jurisdiction_type(self):
        """
        Backend constraint must raise ValidationError if jurisdiction's jurisdiction_type != company.uae_jurisdiction_type.
        """
        # Attempt to save Company with Mainland type but Free Zone DIFC jurisdiction
        with self.assertRaises(ValidationError) as ctx:
            self.Company.create({
                'name': 'Invalid Type Co',
                'uae_emirate_id': self.dxb.id,
                'uae_jurisdiction_type': 'mainland',
                'uae_jurisdiction_id': self.difc.id,
            })
        self.assertIn("does not match company Jurisdiction Type", str(ctx.exception))

        # Attempt to write invalid type to existing company
        valid_co = self.Company.create({
            'name': 'Valid Then Modified Type Co',
            'uae_emirate_id': self.dxb.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': self.difc.id,
        })
        with self.assertRaises(ValidationError):
            valid_co.write({'uae_jurisdiction_type': 'mainland'})

    def test_07_valid_flow_and_auto_resolution(self):
        """
        Verify that completely valid flows succeed and auto-resolve authority across different Emirates.
        """
        # Abu Dhabi Mainland
        co_auh_ml = self.Company.create({
            'name': 'AUH Mainland Co',
            'uae_emirate_id': self.auh.id,
            'uae_jurisdiction_type': 'mainland',
            'uae_jurisdiction_id': self.mainland_auh.id,
        })
        self.assertEqual(co_auh_ml.uae_labour_authority_id.code, 'MOHRE')

        # Dubai Free Zone (IFZA)
        co_dxb_ifza = self.Company.create({
            'name': 'DXB IFZA Co',
            'uae_emirate_id': self.dxb.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': self.ifza.id,
        })
        self.assertEqual(co_dxb_ifza.uae_emirate_id.code, 'DXB')
        self.assertEqual(co_dxb_ifza.uae_labour_authority_id.code, 'IFZA_AUTH')
