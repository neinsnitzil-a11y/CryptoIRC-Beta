"""Python 3.12 installer regression tests; no real network activity or wallet writes."""
from pathlib import Path
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_runtime as ins


class InstallerTests(unittest.TestCase):
    def test_explicit_python_314_rejected(self):
        with patch.dict(os.environ, {'VAULTFORGE_PYTHON': 'python3.14'}), \
             patch.object(ins, 'python_version', return_value=(3, 14)):
            with self.assertRaisesRegex(RuntimeError, 'must be CPython 3.12'):
                ins.choose_python()

    def test_explicit_python_313_rejected(self):
        with patch.dict(os.environ, {'VAULTFORGE_PYTHON': 'python3.13'}), \
             patch.object(ins, 'python_version', return_value=(3, 13)):
            with self.assertRaisesRegex(RuntimeError, 'must be CPython 3.12'):
                ins.choose_python()

    def test_explicit_managed_python_312_accepted(self):
        target = '/some/private/python/3.12/bin/python'
        with patch.dict(os.environ, {'VAULTFORGE_PYTHON': target}), \
             patch.object(ins, 'python_version', return_value=(3, 12)):
            self.assertEqual(ins.choose_python(), ([target], (3, 12)))

    def test_no_312_explains_launcher_auto_installs(self):
        with patch.dict(os.environ, {'VAULTFORGE_PYTHON': ''}), \
             patch.object(ins, 'python_version', return_value=(3, 14)):
            with self.assertRaisesRegex(RuntimeError, 'download a local Python 3.12 automatically'):
                ins.choose_python()

    def test_system_314_not_selected_if_312_exists(self):
        with patch.dict(os.environ, {'VAULTFORGE_PYTHON': ''}), \
             patch.object(ins, 'python_version', side_effect=lambda x: (3, 12) if x == ['python3.12'] else (3, 14)):
            self.assertEqual(ins.choose_python(), (['python3.12'], (3, 12)))

    def test_old_venv_backup_name_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / '.venv'
            (Path(root) / '.venv.incompatible-backup-1').mkdir()
            self.assertEqual(ins.get_backup_path(folder).name, '.venv.incompatible-backup-2')

    def test_existing_312_venv_reused(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / '.venv'
            py = ins.venv_exe(folder)
            py.parent.mkdir(parents=True)
            py.touch()
            with patch.object(ins, 'ROOT', Path(root)), \
                 patch.object(ins, 'python_version', return_value=(3, 12)), \
                 patch.object(ins, 'run') as run, redirect_stdout(io.StringIO()):
                self.assertEqual(ins.ensure_venv(['/managed/python3.12']), py)
                run.assert_not_called()

    def test_old_314_venv_preserved_and_recreated_with_uv_312(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / '.venv'
            py = ins.venv_exe(folder)
            py.parent.mkdir(parents=True)
            py.write_text('old python', encoding='utf-8')
            (folder / 'do_not_delete.txt').write_text('old environment data', encoding='utf-8')

            def fake_run(argv):
                self.assertEqual(argv, ['/fake/uv', 'venv', '--python', '/managed/python3.12', str(folder)])
                newpy = ins.venv_exe(folder)
                newpy.parent.mkdir(parents=True)
                newpy.write_text('new python', encoding='utf-8')

            def fake_version(cmd):
                p = Path(cmd[0])
                return (3, 14) if p.is_file() and p.read_text(encoding='utf-8') == 'old python' else (3, 12)

            with patch.dict(os.environ, {'VAULTFORGE_UV': '/fake/uv'}), \
                 patch.object(ins, 'ROOT', Path(root)), \
                 patch.object(ins, 'python_version', side_effect=fake_version), \
                 patch.object(ins, 'run', side_effect=fake_run) as run, redirect_stdout(io.StringIO()):
                self.assertTrue(ins.ensure_venv(['/managed/python3.12']).is_file())
                run.assert_called_once()
            self.assertEqual((Path(root) / '.venv.incompatible-backup-1/do_not_delete.txt').read_text(), 'old environment data')

    def test_uv_pip_restricts_coincurve_binary(self):
        with patch.dict(os.environ, {'VAULTFORGE_UV': '/fake/uv'}), \
             patch.object(ins, 'run') as run:
            ins.install_dependencies(Path('/fake/.venv/bin/python'))
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:7], ['/fake/uv', 'pip', 'install', '--python', '/fake/.venv/bin/python', '--only-binary', 'coincurve'])
        self.assertIn('-r', cmd)

    def test_main_312_runs_tests_and_selftest(self):
        with patch.dict(os.environ, {'VAULTFORGE_UV': '/fake/uv'}), \
             patch.object(ins, 'choose_python', return_value=(['/managed/python3.12'], (3,12))), \
             patch.object(ins, 'ensure_venv', return_value=Path('/fake/.venv/bin/python')), \
             patch.object(ins, 'install_dependencies') as deps, \
             patch.object(ins, 'run') as run, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(ins.main(), 0)
            deps.assert_called_once()
        commands = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any('--self-test' in cmd for cmd in commands))
        self.assertTrue(any('unittest' in cmd for cmd in commands))

    def test_dependency_pin_avoids_broken_coincurve_release(self):
        req = (Path(__file__).resolve().parents[1] / 'requirements.txt').read_text(encoding='utf-8')
        self.assertIn('coincurve==20.0.0', req)
        self.assertNotIn('coincurve==21.0.0', req)

    def test_start_launcher_auto_installs_if_wrong_python(self):
        root = Path(__file__).resolve().parents[1]
        if (root / 'start_linux.sh').exists():
            script = (root / 'start_linux.sh').read_text(encoding='utf-8')
            self.assertIn('sys.version_info[:2] == (3,12)', script)
            self.assertIn('./install_linux.sh', script)
            self.assertIn('exec .venv/bin/python -I vaultforge.py', script)
        else:
            script = (root / 'START_WINDOWS.bat').read_text(encoding='utf-8')
            self.assertIn('INSTALL_WINDOWS.bat', script)
            self.assertIn('vaultforge.py', script)


    def test_wrapper_contents_include_automatic_python_install(self):
        root = Path(__file__).resolve().parents[1]
        unix = root / 'install_linux.sh'
        win = root / 'install_windows.ps1'
        self.assertTrue(unix.is_file() != win.is_file(), 'Platform folders must be independent')
        if unix.is_file():
            content = unix.read_text(encoding='utf-8')
            self.assertIn('python install 3.12', content)
            self.assertIn('python find 3.12 --managed-python', content)
            self.assertIn('UV_PYTHON_INSTALL_DIR', content)
            self.assertIn('start_linux.sh', (root / 'README.md').read_text())
        else:
            content = win.read_text(encoding='utf-8')
            self.assertIn('python install 3.12', content)
            self.assertIn('python find 3.12 --managed-python', content)
            self.assertIn('UV_PYTHON_INSTALL_DIR', content)
            self.assertIn('install_windows.ps1', (root / 'INSTALL_WINDOWS.bat').read_text())


if __name__ == '__main__':
    unittest.main()
