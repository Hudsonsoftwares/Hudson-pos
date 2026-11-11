# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'TestUAEJurisdictions')
class TestUAEJurisdictions(TransactionCase):
    """
    Automated verification for UAE Jurisdictions master data audit and update.
    Ensures 7 Mainland jurisdictions and 43 Free Zones across all 7 Emirates,
    verifying exact counts, critical corrections (IFZA in Dubai, RAK INC naming),
    data integrity, and cascading company resolution.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Jurisdiction = cls.env['uae.payroll.jurisdiction']
        cls.LabourAuthority = cls.env['uae.labour.authority']
        cls.Emirate = cls.env['uae.emirate']
        cls.Company = cls.env['res.company']

    def test_01_total_jurisdictions_count(self):
        """Verify exactly 50 jurisdictions exist (7 Mainland + 43 Free Zones)."""
        total = self.Jurisdiction.search_count([])
        mainland_count = self.Jurisdiction.search_count([('jurisdiction_type', '=', 'mainland')])
        free_zone_count = self.Jurisdiction.search_count([('jurisdiction_type', '=', 'free_zone')])

        self.assertEqual(mainland_count, 7, "Must have exactly 7 Mainland jurisdictions (one per Emirate).")
        self.assertEqual(free_zone_count, 43, "Must have exactly 43 Free Zone jurisdictions.")
        self.assertEqual(total, 50, "Total jurisdictions in master must be exactly 50.")

    def test_02_mainland_jurisdictions_completeness(self):
        """Verify each of the 7 UAE Emirates has exactly one Mainland jurisdiction under MOHRE."""
        expected_mainland = [
            ('AE_MAINLAND_AUH', 'Mainland Abu Dhabi', 'AUH'),
            ('AE_MAINLAND_DXB', 'Mainland Dubai', 'DXB'),
            ('AE_MAINLAND_SHJ', 'Mainland Sharjah', 'SHJ'),
            ('AE_MAINLAND_AJM', 'Mainland Ajman', 'AJM'),
            ('AE_MAINLAND_UAQ', 'Mainland Umm Al Quwain', 'UAQ'),
            ('AE_MAINLAND_RAK', 'Mainland Ras Al Khaimah', 'RAK'),
            ('AE_MAINLAND_FUJ', 'Mainland Fujairah', 'FUJ'),
        ]

        mohre = self.LabourAuthority.search([('code', '=', 'MOHRE')], limit=1)
        self.assertTrue(mohre, "MOHRE Labour Authority must exist.")

        for code, name, emirate_code in expected_mainland:
            jur = self.Jurisdiction.search([('code', '=', code)])
            self.assertEqual(len(jur), 1, f"Mainland jurisdiction {code} must exist uniquely.")
            self.assertEqual(jur.name, name, f"Mainland {code} name mismatch.")
            self.assertEqual(jur.jurisdiction_type, 'mainland', f"{code} type must be mainland.")
            self.assertEqual(jur.emirate_id.code, emirate_code, f"{code} emirate must be {emirate_code}.")
            self.assertEqual(jur.labour_authority_id.code, 'MOHRE', f"{code} authority must be MOHRE.")

    def test_03_abu_dhabi_free_zones(self):
        """Verify Abu Dhabi Free Zones (6)."""
        expected_codes = {
            'AE_FZ_ADGM': 'ADGM Free Zone',
            'AE_FZ_MASDAR': 'Masdar City Free Zone',
            'AE_FZ_TWFOUR54': 'twofour54 Free Zone',
            'AE_FZ_ADAFZ': 'Abu Dhabi Airports Free Zone',
            'AE_FZ_KEZAD': 'KEZAD',
            'AE_FZ_ADIC': 'Abu Dhabi Industrial City',
        }
        auh_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'AUH'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(auh_fz), 6, "Abu Dhabi must have exactly 6 Free Zones.")
        for code, name in expected_codes.items():
            jur = auh_fz.filtered(lambda j: j.code == code)
            self.assertEqual(len(jur), 1, f"Abu Dhabi FZ {code} must exist.")
            self.assertEqual(jur.name, name)
            self.assertTrue(jur.labour_authority_id, f"{code} must have a governing labour authority.")

    def test_04_dubai_free_zones(self):
        """Verify Dubai Free Zones (23 unique)."""
        expected_codes = {
            'AE_FZ_DIFC': 'DIFC Free Zone',
            'AE_FZ_DMCC': 'DMCC Free Zone',
            'AE_FZ_JAFZA': 'JAFZA Free Zone',
            'AE_FZ_DAFZA': 'Dubai Airport Free Zone (DAFZA)',
            'AE_FZ_DSO': 'Dubai Silicon Oasis',
            'AE_FZ_DUBAI_SOUTH': 'Dubai South Free Zone',
            'AE_FZ_IFZA': 'IFZA Free Zone',
            'AE_FZ_DIC': 'Dubai Internet City',
            'AE_FZ_DMC': 'Dubai Media City',
            'AE_FZ_DKP': 'Dubai Knowledge Park',
            'AE_FZ_DPC': 'Dubai Production City',
            'AE_FZ_DSC': 'Dubai Studio City',
            'AE_FZ_DSP': 'Dubai Science Park',
            'AE_FZ_D3': 'Dubai Design District',
            'AE_FZ_DHCC': 'Dubai Healthcare City',
            'AE_FZ_MEYDAN': 'Meydan Free Zone',
            'AE_FZ_IHC': 'International Humanitarian City',
            'AE_FZ_DCC': 'Dubai CommerCity',
            'AE_FZ_DIAC': 'Dubai International Academic City',
            'AE_FZ_EXPO_CITY': 'Expo City Dubai',
            'AE_FZ_DWTC': 'Dubai World Trade Centre Free Zone',
            'AE_FZ_DAZ': 'Dubai Auto Zone',
            'AE_FZ_DMCITY': 'Dubai Maritime City',
        }
        dxb_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'DXB'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(dxb_fz), 23, "Dubai must have exactly 23 Free Zones.")
        for code, name in expected_codes.items():
            jur = dxb_fz.filtered(lambda j: j.code == code)
            self.assertEqual(len(jur), 1, f"Dubai FZ {code} must exist uniquely.")
            self.assertEqual(jur.name, name)
            self.assertTrue(jur.labour_authority_id, f"{code} must have a governing labour authority.")

    def test_05_critical_ifza_correction(self):
        """Critical IFZA check: IFZA must be in Dubai, NOT in Fujairah."""
        ifza = self.Jurisdiction.search([('code', '=', 'AE_FZ_IFZA')])
        self.assertEqual(len(ifza), 1, "IFZA record must exist uniquely with code AE_FZ_IFZA.")
        self.assertEqual(ifza.emirate_id.code, 'DXB', "IFZA must be located in Dubai (DXB).")
        self.assertNotEqual(ifza.emirate_id.code, 'FUJ', "IFZA must NOT be located in Fujairah (FUJ).")
        self.assertEqual(ifza.jurisdiction_type, 'free_zone')

        # Verify no IFZA record in Fujairah
        fuj_ifza = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'FUJ'),
            ('name', 'ilike', 'IFZA'),
        ])
        self.assertFalse(fuj_ifza, "No IFZA record should exist under Fujairah.")

    def test_06_sharjah_free_zones(self):
        """Verify Sharjah Free Zones (5)."""
        expected_codes = {
            'AE_FZ_SAIF': 'Sharjah Airport International Free Zone (SAIF Zone)',
            'AE_FZ_HAMRIYAH': 'Hamriyah Free Zone',
            'AE_FZ_SHAMS': 'Sharjah Media City (SHAMS)',
            'AE_FZ_SPCFZ': 'Sharjah Publishing City Free Zone',
            'AE_FZ_SRTIP': 'Sharjah Research Technology and Innovation Park (SRTIP)',
        }
        shj_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'SHJ'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(shj_fz), 5, "Sharjah must have exactly 5 Free Zones.")
        for code, name in expected_codes.items():
            jur = shj_fz.filtered(lambda j: j.code == code)
            self.assertEqual(len(jur), 1, f"Sharjah FZ {code} must exist.")
            self.assertEqual(jur.name, name)

    def test_07_ajman_and_uaq_free_zones(self):
        """Verify Ajman (2) and Umm Al Quwain (1) Free Zones."""
        ajm_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'AJM'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(ajm_fz), 2, "Ajman must have exactly 2 Free Zones.")
        self.assertSetEqual(set(ajm_fz.mapped('code')), {'AE_FZ_AJMAN', 'AE_FZ_AMC'})

        uaq_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'UAQ'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(uaq_fz), 1, "UAQ must have exactly 1 Free Zone.")
        self.assertEqual(uaq_fz.code, 'AE_FZ_UAQFTZ')
        self.assertEqual(uaq_fz.name, 'Umm Al Quwain Free Trade Zone')

    def test_08_ras_al_khaimah_and_rak_inc_correction(self):
        """Verify RAK Free Zones (3) and critical RAK INC naming/deduplication."""
        rak_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'RAK'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(rak_fz), 3, "RAK must have exactly 3 Free Zones.")
        self.assertSetEqual(set(rak_fz.mapped('code')), {'AE_FZ_RAKEZ', 'AE_FZ_RAKMC', 'AE_FZ_RAK_INC'})

        rak_inc = rak_fz.filtered(lambda j: j.code == 'AE_FZ_RAK_INC')
        self.assertEqual(rak_inc.name, 'Ras Al Khaimah Innovation City (RAK INC)')
        self.assertIn('RAK Digital Assets Oasis / RAK DAO', rak_inc.description or '')

        # Ensure no separate duplicate records for RAK DAO
        dao_records = self.Jurisdiction.search([
            ('name', 'in', ['RAK Digital Assets Oasis', 'RAK DAO']),
        ])
        self.assertFalse(dao_records, "No separate duplicate records should exist for RAK DAO.")

    def test_09_fujairah_free_zones(self):
        """Verify Fujairah Free Zones (3)."""
        expected_codes = {
            'AE_FZ_FFZ': 'Fujairah Free Zone',
            'AE_FZ_CREATIVE_CITY': 'Creative City Fujairah',
            'AE_FZ_FOIZ': 'Fujairah Oil Industry Zone',
        }
        fuj_fz = self.Jurisdiction.search([
            ('emirate_id.code', '=', 'FUJ'),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(fuj_fz), 3, "Fujairah must have exactly 3 Free Zones.")
        for code, name in expected_codes.items():
            jur = fuj_fz.filtered(lambda j: j.code == code)
            self.assertEqual(len(jur), 1, f"Fujairah FZ {code} must exist.")
            self.assertEqual(jur.name, name)

    def test_10_data_integrity_constraints(self):
        """Verify all jurisdictions adhere to integrity rules (unique code, non-null emirate, type, authority)."""
        all_jurisdictions = self.Jurisdiction.search([])
        codes = set()
        for jur in all_jurisdictions:
            self.assertTrue(jur.code, f"Jurisdiction {jur.name} must have a code.")
            self.assertNotIn(jur.code, codes, f"Duplicate jurisdiction code found: {jur.code}")
            codes.add(jur.code)

            self.assertTrue(jur.emirate_id, f"Jurisdiction {jur.code} must have an Emirate.")
            self.assertIn(jur.jurisdiction_type, ['mainland', 'free_zone'], f"Jurisdiction {jur.code} has invalid type.")
            self.assertTrue(jur.labour_authority_id, f"Jurisdiction {jur.code} must have a governing Labour Authority.")

    def test_11_cascading_selection_and_company_resolution(self):
        """
        Verify cascading filter capabilities:
        - Emirate + Mainland -> exactly 1 Mainland jurisdiction
        - Emirate + Free Zone -> only the respective Emirate's Free Zones
        - Setting jurisdiction on res.company auto-resolves emirate, type, and labour authority.
        """
        auh = self.Emirate.search([('code', '=', 'AUH')], limit=1)
        dxb = self.Emirate.search([('code', '=', 'DXB')], limit=1)

        # Cascading filter: AUH + mainland
        auh_mainland = self.Jurisdiction.search([
            ('emirate_id', '=', auh.id),
            ('jurisdiction_type', '=', 'mainland'),
        ])
        self.assertEqual(len(auh_mainland), 1)
        self.assertEqual(auh_mainland.code, 'AE_MAINLAND_AUH')

        # Cascading filter: AUH + free_zone
        auh_fz = self.Jurisdiction.search([
            ('emirate_id', '=', auh.id),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(auh_fz), 6)

        # Cascading filter: DXB + free_zone
        dxb_fz = self.Jurisdiction.search([
            ('emirate_id', '=', dxb.id),
            ('jurisdiction_type', '=', 'free_zone'),
        ])
        self.assertEqual(len(dxb_fz), 23)

        # Test Company resolution
        difc = self.Jurisdiction.search([('code', '=', 'AE_FZ_DIFC')], limit=1)
        test_company = self.Company.create({
            'name': 'Test DIFC Co',
            'uae_jurisdiction_id': difc.id,
        })
        self.assertEqual(test_company.uae_emirate_id, dxb, "Company emirate should auto-resolve to Dubai.")
        self.assertEqual(test_company.uae_jurisdiction_type, 'free_zone', "Company type should auto-resolve to Free Zone.")
        self.assertEqual(test_company.uae_labour_authority_id.code, 'DIFC_AUTH', "Company labour authority should auto-resolve to DIFC Authority.")
