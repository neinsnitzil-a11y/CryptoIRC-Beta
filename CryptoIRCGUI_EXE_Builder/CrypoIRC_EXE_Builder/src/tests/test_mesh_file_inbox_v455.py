"""File inbox UX source and safe encrypted download semantics (offline)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from mesh_gui import MeshGUI
from vaultmesh.file_transfer import FileTransfers, list_saved_downloads

class FileInboxChecks(unittest.TestCase):
    def test_gui_inbox_commands_are_present(self):
        src=Path(__file__).resolve().parents[1]
        ui=(src/'mesh_gui.py').read_text(encoding='utf8')
        worker=(src/'mesh_bridge.py').read_text(encoding='utf8')
        for text in ('Receive / Download Files','Download Selected','Downloaded Files',
                     'Preview Image / Text / ZIP','Open Downloads Folder'):
            self.assertIn(text,ui)
        self.assertIn("action == 'refresh_files'",worker)
        self.assertIn("'saved': list_saved_downloads(node.root)",worker)
    def test_inbox_selection_and_explicit_accept(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            node=SimpleNamespace(root=Path(d))
            files=FileTransfers(node)
            files.pending['a'*24]={'when':time.monotonic(),'name':'readme.md','size':5,'sender':'Bob','content':b'hello'}
            files.pending['b'*24]={'when':time.monotonic()+1,'name':'folder.zip','size':3,'sender':'Alice','chunks':{}}
            offers=files.offer_rows()
            self.assertTrue(offers[0]['ready'])
            self.assertFalse(offers[1]['ready'])
            self.assertFalse((Path(d)/'downloads').exists())
            self.assertEqual(files.resolve_offer('1'),'a'*24)
            self.assertEqual(files.accept('a'*24).read_bytes(),b'hello')
            self.assertEqual(list_saved_downloads(Path(d))[0]['name'],'readme.md')
            with self.assertRaises(ValueError):files.accept('b'*24)

if __name__=='__main__':unittest.main()
