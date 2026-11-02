"""Tests for incomplete ZIPs and isolated-mode unittest invocation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_runtime as ins

class ReleaseIntegrityTests(unittest.TestCase):
    def test_original_archive_contains_mesh_and_tests(self):
        ins.validate_bundle()  # tests are not optional for this official ZIP

    def test_missing_tests_reports_clear_early_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(ins, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'Incomplete VaultForge Mesh') as error:
                    ins.validate_bundle()
                self.assertIn('test_mesh_chat.py', str(error.exception))
                self.assertIn('fresh folder', str(error.exception))

    def test_installer_uses_explicit_absolute_test_paths(self):
        script = (Path(__file__).resolve().parents[1] / 'install_runtime.py').read_text()
        self.assertIn("'-s', str(tests_dir), '-t', str(ROOT)", script)
        self.assertIn('validate_bundle()', script)
        self.assertIn('Mesh Chat / automatic Python 3.12 installer', script)

    def test_missing_bundle_fails_before_installing_dependencies(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(ins, 'ROOT', Path(d)), \
                 patch.object(ins, 'choose_python') as choose:
                self.assertEqual(ins.main(), 1)
                choose.assert_not_called()

if __name__ == '__main__':
    unittest.main()
