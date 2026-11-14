import sys
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from save_core import *

class SaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files=[path for path in DEFAULT_ROOT.rglob('*.msgpack')
                   if path.name in ('gameworld.msgpack', 'meta.msgpack')]
        cls.hashes={str(p):digest(p.read_bytes()) for p in cls.files}
        cls.source=next(DEFAULT_ROOT.rglob('gameworld.msgpack')).parent
    def test_1_all_originals_round_trip(self):
        for p in self.files:
            b=p.read_bytes();plain=decrypt(b);d=Document(plain)
            self.assertEqual(plain,d.render(),str(p))
            self.assertEqual(b,encrypt(d.render(),iv=b[6:22]),str(p))
    def test_2_types_and_validation(self):
        # map {float32: 1.5, uint64: max, ext: custom, arr: [true,null,"ok"]}
        b=b'\x84\xa1f\xca'+struct.pack('>f',1.5)+b'\xa1u\xcf'+struct.pack('>Q',2**64-1)+b'\xa1e\xd4\x04\x7f\xa1a\x93\xc3\xc0\xa2ok'
        d=Document(b);self.assertEqual(d.render(),b)
        d.stage(d.root.at('f'),'1.5');self.assertFalse(d.changes)
        d.stage(d.root.at('f'),'2.25');r=Document(d.render());self.assertEqual(r.root.at('f').code,0xca)
        self.assertEqual(r.root.at('u').value,2**64-1)
        self.assertEqual(r.root.at('e').value,b'\x04\x7f')
        for invalid in ['NaN','Infinity','1e999']:
            with self.assertRaises(ValueError):d.stage(d.root.at('f'),invalid)
        with self.assertRaises(ValueError):Document(b[:-1])
        bad=bytearray(self.files[0].read_bytes());bad[40]^=1
        with self.assertRaises(ValueError):decrypt(bad)
    @patch("subprocess.run", side_effect=AssertionError("Saving must not inspect or block the game process"))
    def test_3_save_restore_conflict_and_rollback(self, process_mock):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);slot=temp/'manual_test';shutil.copytree(self.source,slot)
            s=SaveSession(slot);n=s.world.root.at('playerModel','combat','cultivate_exp')
            s.world.stage(n,str(n.value+123))
            name=s.world.root.at('playerModel','playerName');s.world.stage(name,'测试角色')
            expected=s.world.render();backup=s.save(temp/'backups')
            r=SaveSession(slot);self.assertEqual(r.world.data,expected)
            self.assertEqual(r.meta.root.at('characterName').value,'测试角色')
            self.assertEqual((backup/'gameworld.msgpack').read_bytes(),s.original['gameworld.msgpack'])
            for p,node in s.world.nodes.items():
                if node.kind not in ('map','array') and p not in s.world.changes:
                    actual=r.world.nodes[p]
                    self.assertEqual(s.world.data[node.start:node.end],r.world.data[actual.start:actual.end],str(p))
            r.restore(backup,temp/'backups')
            self.assertEqual((slot/'gameworld.msgpack').read_bytes(),s.original['gameworld.msgpack'])
            self.assertEqual((slot/'meta.msgpack').read_bytes(),s.original['meta.msgpack'])
            s=SaveSession(slot);s.world.stage(s.world.root.at('playerModel','playerName'),'回滚测试')
            original_write=atomic_write
            def fail_second(path,data):
                if path.name=='meta.msgpack':raise IOError('simulated write failure')
                original_write(path,data)
            with patch('save_core.atomic_write',side_effect=fail_second):
                with self.assertRaises(IOError):s.save(temp/'backups')
            self.assertEqual((slot/'gameworld.msgpack').read_bytes(),s.original['gameworld.msgpack'])
            (slot/'meta.msgpack').write_bytes(b'changed externally')
            with self.assertRaises(RuntimeError):s.save(temp/'backups')
    @classmethod
    def tearDownClass(cls):
        for p in cls.files:
            # Real game can be running; report external changes instead of overwriting anything.
            if digest(p.read_bytes()) != cls.hashes[str(p)]:print('External save update during tests:',p)

if __name__=='__main__':unittest.main(verbosity=2)
