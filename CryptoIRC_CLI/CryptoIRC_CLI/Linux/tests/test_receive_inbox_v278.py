import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from file_transfer import FileTransfers, list_saved_downloads

class ReceiveInboxTests(unittest.TestCase):
    def test_numeric_offer_selection_and_ready_status(self):
        import time
        node=SimpleNamespace(root=Path(tempfile.gettempdir()))
        t=FileTransfers(node)
        t.pending={ 'a'*24: {'when':10.,'name':'pic.png','size':3,'sender':'s1','content':b'png'},
                    'b'*24: {'when':20.,'name':'docs.zip','size':7,'sender':'s2','chunks':{}}}
        with patch.object(t,'prune',return_value=None):
            rows=t.offer_rows()
            self.assertEqual([r['name'] for r in rows],['pic.png','docs.zip'])
            self.assertEqual([r['ready'] for r in rows],[True,False])
            self.assertEqual(t.resolve_offer('1'),'a'*24)
            self.assertEqual(t.resolve_offer('b'*24),'b'*24)
            with self.assertRaises(ValueError):t.resolve_offer('3')
            with self.assertRaises(ValueError):t.resolve_offer('unknown')

    def test_saved_list_excludes_symlinks_and_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            saved=root/'downloads';saved.mkdir()
            (saved/'hello.png').write_bytes(b'hello')
            (saved/'folder').mkdir()
            target=root/'outside.txt';target.write_text('private')
            try:(saved/'linked.txt').symlink_to(target)
            except (OSError,NotImplementedError):pass
            rows=list_saved_downloads(root)
            self.assertEqual([r['name'] for r in rows],['hello.png'])
            self.assertEqual(rows[0]['size'],5)

    def test_download_accept_keeps_bytes_and_is_non_overwriting(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            t=FileTransfers(SimpleNamespace(root=root))
            meta={'when':time.monotonic(), 'name':'photo.png','size':3,
                  'sender':'sender', 'content':b'123'}
            t.pending={'c'*24:dict(meta)}
            path=t.accept(t.resolve_offer('1'))
            self.assertEqual(path.read_bytes(),b'123')
            self.assertEqual(path.name,'photo.png')
            t.pending={'d'*24:dict(meta)}
            path2=t.accept(t.resolve_offer('1'))
            self.assertEqual(path2.name,'1_photo.png')
            self.assertNotIn('d'*24,t.pending)

if __name__=='__main__':unittest.main()
