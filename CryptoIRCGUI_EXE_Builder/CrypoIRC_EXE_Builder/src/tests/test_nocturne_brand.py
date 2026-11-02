"""Visual rebranding integration checks; no credentials or real payments needed."""
import unittest
from pathlib import Path
from brand_theme import ASSET_DIR, PURPLE, GREEN
from professional_ui import validated_wallet_parameters

class NocturneBrandTests(unittest.TestCase):
    def test_brand_files_ship_locally(self):
        for filename in ('tor_round.png','skull_purple.png','skull_green.png','hazard_red.png','CRYPTO_NOCTURNE.ico'):
            with self.subTest(filename=filename):
                self.assertTrue((ASSET_DIR/filename).is_file())
    def test_visual_colors(self):
        self.assertEqual(PURPLE,'#b363ff')
        self.assertEqual(GREEN,'#47fca3')
    def test_fiat_never_goes_through_seed_creation(self):
        with self.assertRaises(ValueError):
            validated_wallet_parameters('Fiat','USD','1','24','0',False)

if __name__=='__main__': unittest.main()
