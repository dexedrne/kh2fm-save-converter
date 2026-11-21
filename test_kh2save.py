"""All fixtures are generated here, including the one-pixel PNG and PS2 filesystem."""
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import kh2save as k


def campaign():
    data = bytearray(k.SIZE)
    data[:8] = k.HEADER
    data[12:14] = bytes((4, 9))
    data[0x24ff] = 12
    struct.pack_into('<I', data, 0x2444, 60 * 3661)
    struct.pack_into('<I', data, 0x2498, 2)
    struct.pack_into('<I', data, 8, k.checksum(data))
    return bytes(data)


def chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))


def steam_png():
    size = (k.DATA + k.COUNT * k.SIZE + 1023) // 1024 * 1024
    card = bytearray(size)
    card[:16] = hashlib.md5(b'765611980000000001', usedforsecurity=False).digest()
    name = k.PREFIX + b'SYS'
    card[16:16+len(name)] = name
    struct.pack_into('<I', card, 96, 1024)
    for i in range(256):
        card[i] ^= 17 + i % 16
    card[k.DATA:k.DATA+8] = b'KH2SJP\x01\0'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0)
    return (k.PNG + chunk(b'IHDR', ihdr) + chunk(b'sqEX', card)
            + chunk(b'IDAT', zlib.compress(bytes(2))) + chunk(b'IEND', b''))


def image(payload):
    raw = bytearray(8192 * 1024)
    raw[:28] = b'Sony PS2 Memory Card Format '
    struct.pack_into('<3H', raw, 40, 512, 2, 16)
    base = 40
    struct.pack_into('<4I', raw, 48, 8192, base, 8192-base, 0)
    struct.pack_into('<I', raw, 80, 1)
    for i in range(32):
        struct.pack_into('<I', raw, 1024+4*i, 2+i)

    def entry(cluster, half, mode, name, size, start):
        pos = (base+cluster)*1024 + half*512
        struct.pack_into('<H2xI', raw, pos, mode, size)
        struct.pack_into('<I', raw, pos+16, start)
        for field in (8, 24):
            struct.pack_into('<6BH', raw, pos+field, 0, 0, 0, 12, 1, 1, 2020)
        raw[pos+64:pos+64+len(name)] = name

    name = k.PREFIX + b'04'
    entry(0, 0, 0x8020, b'.', 2, 0)
    entry(0, 1, 0x8020, name, 1, 1)
    entry(1, 0, 0x8010, name, len(payload), 2)
    chain = list(range(2, 70, 2)) + list(range(3, 70, 2))
    for i, cluster in enumerate(chain):
        pos = (base+cluster)*1024
        block = payload[1024*i:1024*(i+1)]
        raw[pos:pos+len(block)] = block
    for cluster, link in [(0, 0xffffffff), (1, 0xffffffff)] + list(zip(chain, chain[1:]+[0xffffffff])):
        struct.pack_into('<I', raw, 2048+4*cluster, 0x80000000 | link)
    return raw


class ConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = campaign()
        cls.save = k.Save(k.PREFIX+b'04', 123, 456, cls.data)
        cls.png = steam_png()

    def test_known_checkpoint_form_reward(self):
        data = bytearray(self.data)
        data[0x36c0] = 6
        data[0x367b] = 1
        struct.pack_into('<H', data, 0x32f4, 484)
        struct.pack_into('<H', data, 0x332c, 484)
        with patch.object(k, 'KNOWN_SAVE', hashlib.sha256(data).hexdigest()):
            result = k.migrate_nmc_checkpoint(data)
        self.assertEqual(result[0x36c0], 4)
        self.assertEqual(result[0x36ca], 8)
        self.assertEqual(result[0x367b], 0)
        self.assertEqual(result[0x36b8], 1)
        self.assertEqual(struct.unpack_from('<H', result, 0x333e), (0x81a7,))
        self.assertEqual(struct.unpack_from('<H', result, 0x337c), (0x823b,))
        self.assertEqual(result[0x337e:0x339c], bytes(30))
        self.assertEqual(struct.unpack_from('<H', result, 0x32f4), (0,))
        self.assertEqual(struct.unpack_from('<H', result, 0x3364), (480,))
        self.assertEqual(result[0x32f6:0x333e], data[0x32f6:0x333e])
        self.assertEqual(result[0x3366:0x336c], data[0x3366:0x336c])

    def test_fragmented_image_and_bad_fat(self):
        raw = image(self.data)
        self.assertEqual(k.read_card(raw)[0].data, self.data)
        struct.pack_into('<I', raw, 2048+8, 0x80000002)
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            k.read_card(raw)

    def test_ecc(self):
        self.assertEqual(k.ecc(bytes(128)), bytes((0x77, 127, 127)))
        self.assertEqual(k.ecc(b'\x01'+bytes(127)), bytes((0x70, 0, 127)))
        raw = image(self.data)
        pages = []
        for pos in range(0, len(raw), 512):
            block = raw[pos:pos+512]
            codes = b''.join(k.ecc(block[n:n+128]) for n in range(0, 512, 128))
            pages.append(block + codes + bytes(4))
        ecc_image = bytearray(b''.join(pages))
        self.assertEqual(k.read_card(ecc_image)[0].data, self.data)
        ecc_image[512] ^= 1
        with self.assertRaisesRegex(ValueError, 'ECC'):
            k.read_card(ecc_image)

    def test_occupancy_and_preservation(self):
        first = k.insert(self.png, self.save, 99)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            k.insert(first, self.save, 99)
        for slot in (0, 100):
            with self.assertRaisesRegex(ValueError, '1..99'):
                k.insert(first, self.save, slot)
        updated = k.insert(first, self.save, 5)
        start, end = k.container(updated)
        card = updated[start:end]
        self.assertEqual(k.directory(card, '76561198000000000'), {99: 1, 5: 2})
        with self.assertRaisesRegex(ValueError, 'account folder'):
            k.directory(card, '76561198000000001')
        allowed = [(start+16+2*k.ROW, k.ROW), (start+k.DATA+2*k.SIZE, k.SIZE), (end, 4)]
        restored = bytearray(updated)
        for offset, size in allowed:
            restored[offset:offset+size] = first[offset:offset+size]
        self.assertEqual(restored, first)
        self.assertEqual(k.insert(updated, self.save, 5, True), updated)

    def test_corrupt_existing_save_and_png(self):
        png = k.insert(self.png, self.save, 7)
        a, b = k.container(png)
        for offset, message in [(a+16, 'system'), (a+k.DATA, 'system'),
                                (a+k.DATA+k.SIZE+4, 'header'), (a+k.DATA+k.SIZE+100, 'checksum')]:
            altered = bytearray(png[a:b])
            altered[offset-a] ^= 1
            with self.assertRaisesRegex(ValueError, message):
                k.insert(png[:a-8]+chunk(b'sqEX', altered)+png[b+4:], self.save, 9)
        with self.assertRaisesRegex(ValueError, 'CRC'):
            k.insert(png[:-1]+bytes([png[-1]^1]), self.save, 9)

    def test_backup_and_replacement_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root/'KHIIFM_WW.png'
            target.write_bytes(self.png)
            args = SimpleNamespace(into=target, card=root/'card.ps2', slot=3, out=None,
                                   replace=False, nmc_rmc=False)
            args.card.touch()
            with patch.object(k, 'write_new', side_effect=OSError('backup failed')):
                with self.assertRaisesRegex(OSError, 'backup failed'):
                    k.convert(args, self.save)
            self.assertEqual(set(root.iterdir()), {target, args.card})
            with patch.object(k.os, 'replace', side_effect=OSError('replace failed')):
                with self.assertRaisesRegex(OSError, 'replace failed'):
                    k.convert(args, self.save)
            self.assertEqual(target.read_bytes(), self.png)
            backup, = root.glob('*.bak')
            self.assertEqual(backup.read_bytes(), self.png)
            lock = root/'KHIIFM_WW.png.lock'
            lock.touch()
            with self.assertRaisesRegex(ValueError, 'lock'):
                k.convert(args, self.save)
            self.assertTrue(lock.exists())

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            card = root/'Folder Card'
            card.mkdir()
            (card/'BASLUS-21005-00').mkdir()
            cmd = [sys.executable, str(Path(k.__file__))]
            def run(*args, ok=True):
                result = subprocess.run(cmd+list(map(str, args)), capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok, result.stderr)
                return result.stdout if ok else result.stderr
            self.assertIn('US/EU', run('list', card, ok=False))
            folder = card/self.save.name.decode()
            folder.mkdir()
            source = folder/folder.name
            source.write_bytes(self.data)
            self.assertIn('5\t'+folder.name+'\thb09\t12\t1:01:01\t2 (Proud)', run('list', card))
            pc = root/'pc.png'
            pc.write_bytes(self.png)
            args = ['convert', card, '--source', 5, '--into', pc, '--slot', 4]
            self.assertIn('source card', run(*args, '--out', card/'new.png', ok=False))
            out = root/'new.png'
            run(*args, '--out', out)
            self.assertEqual(pc.read_bytes(), self.png)
            self.assertIn('already exists', run(*args, '--out', out, ok=False))
            run(*args)
            self.assertEqual(pc.read_bytes(), out.read_bytes())
            backups = list(root.glob('pc.png.*.bak'))
            self.assertEqual(len(backups), 2)
            self.assertTrue(all(b.read_bytes() == self.png for b in backups))
            self.assertIn('occupied', run(*args, ok=False))
            run(*args, '--replace')
            self.assertEqual(source.read_bytes(), self.data)
            self.assertEqual(len(list(root.glob('*.bak'))), 3)


if __name__ == '__main__':
    unittest.main()
