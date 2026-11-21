#!/usr/bin/env python3
"""Import a Japanese Kingdom Hearts II Final Mix PS2 save into a Steam save."""
import argparse
import hashlib
import os
import re
import stat
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SIZE = 0x10FC0
ROW = 0x158
COUNT = 100  # The first physical entry is the system file.
DATA = 16 + COUNT * ROW
WORLDS = 'zz es tt di hb bb he al mu po lk lm dc wi nm wm ca tr eh'.split()
DIFFICULTY = ('Beginner', 'Standard', 'Proud', 'Critical')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def crc_table():
    table = []
    for value in range(256):
        c = value << 24
        for _ in range(255):  # runtime/autosave.c kh_save_crc
            c = ((c << 1) & 0xffffffff) ^ (0x04c11db7 if c >> 31 else 0)
        table.append(c)
    return table


PREFIX = b'BISLPM-66675FM-'
HEADER = b'KH2J\x3a\0\0\0'
TABLE = crc_table()
PNG = b'\x89PNG\r\n\x1a\n'
KNOWN_SAVE = 'cf73df0652fe392910338b694024e35f38387d053cea9a119faa6fa70289998d'
# PCSX2's 3 ECC parity bytes per 128-byte sector.
COLUMN = tuple(sum((bin(v & m).count('1') % 2) << bit
                   for bit, m in enumerate((85, 51, 15, 0, 170, 204, 240)))
               for v in range(256))


PARITY = tuple(bin(v).count('1') % 2 for v in range(256))


def ecc(data):
    col, lo, hi = 0x77, 127, 127
    for i, v in enumerate(data):
        col ^= COLUMN[v]
        if PARITY[v]:
            lo ^= 127 ^ i
            hi ^= i
    return bytes((col, lo, hi))


def u32(data, pos):
    return struct.unpack_from('<I', data, pos)[0]


def checksum(data):
    c = 0xffffffff
    for value in data[:8] + data[12:]:
        c = ((c << 8) & 0xffffffff) ^ TABLE[(c >> 24) ^ value]
    return c ^ 0xffffffff


@dataclass
class Save:
    name: bytes
    created: int
    modified: int
    data: bytes


def timestamp(entry, pos):
    # The PS2 memory-card filesystem records the console's Japan-standard clock.
    _, sec, minute, hour, day, month, year = struct.unpack_from('<6BH', entry, pos)
    return int(datetime(year, month, day, hour, minute, sec,
                        tzinfo=timezone(timedelta(hours=9))).timestamp())


def validate_save(data):
    require(len(data) == SIZE and data[:8] == HEADER, 'invalid KH2FM campaign header or size; '
            'only JP Final Mix is supported (US/EU KH2 uses a different format)')
    require(checksum(data) == u32(data, 8), 'invalid KH2FM campaign checksum')
    require(data[12] < len(WORLDS) and data[13] < 64 and u32(data, 0x2498) < 4,
            'invalid KH2FM campaign summary')


def read_card(raw):
    require(len(raw) >= 512 and raw[:28] == b'Sony PS2 Memory Card Format ', 'invalid PS2 superblock')
    page, ppc, erase = struct.unpack_from('<HHH', raw, 40)
    count, base, limit, root = struct.unpack_from('<4I', raw, 48)
    require((page, ppc, erase) == (512, 2, 16) and count in (8192, 16384, 32768, 65536),
            'expected a standard 8, 16, 32 or 64 MiB PS2 card')
    stride, remainder = divmod(len(raw), count * ppc)
    require(not remainder and stride in (512, 528), 'incorrect card image length')
    require(0 < base < count and 0 < limit <= count-base and root < limit, 'bad allocation bounds')

    def cluster(i, pages=ppc):
        require(0 <= i < count, 'cluster outside card')
        data = bytearray()
        for n in range(i*ppc, i*ppc+pages):
            start = n*stride
            block = raw[start:start+page]
            if stride > page:
                codes = b''.join(ecc(block[k:k+128]) for k in range(0, page, 128))
                require(codes == raw[start+page:start+page+12], f'ECC mismatch on page {n}')
            data.extend(block)
        return data

    sb = cluster(0, pages=1)
    fat = bytearray()
    reserved = {0}

    def metadata(i):
        require(0 < i < base and i not in reserved, 'invalid or shared FAT metadata cluster')
        reserved.add(i)
        return cluster(i)

    needed = (limit+255)//256
    for table in range((needed+255)//256):
        indirect = metadata(u32(sb, 80+4*table))
        for j in range(min(256, needed-table*256)):
            fat.extend(metadata(u32(indirect, 4*j)))

    claimed = set()

    def read_chain(i, length):
        require(0 < length <= limit*1024, 'invalid file or directory length')
        data = bytearray()
        while len(data) < length:
            require(i < limit and i not in claimed, 'invalid, cyclic or shared FAT chain')
            claimed.add(i)
            data.extend(cluster(base+i))
            link = u32(fat, 4*i)
            require(link & 0x80000000, 'unallocated FAT link')
            i = link & 0x7fffffff
        require(i == 0x7fffffff, 'unexpected extra FAT cluster')
        return bytes(data[:length])

    def entries(start, length):
        directory = read_chain(start, length*512)
        for pos in range(0, len(directory), 512):
            row = directory[pos:pos+512]
            mode, = struct.unpack_from('<H', row)
            if mode & 0x8000:
                yield row[64:96].split(b'\0', 1)[0], mode, row

    root_header = cluster(base+root)
    require(root_header[64:66] == b'.\0', 'missing root directory')
    saves = {}
    for name, mode, folder in entries(root, u32(root_header, 4)):
        if not re.fullmatch(PREFIX+rb'[0-9]{2}', name):
            continue
        require(mode & 0x20 and name not in saves, 'invalid or duplicate KH2 directory')
        files = [r for n, m, r in entries(u32(folder, 16), u32(folder, 4)) if n == name and m & 0x10]
        require(len(files) == 1, f'missing or duplicate file in {name.decode()}')
        row = files[0]
        data = read_chain(u32(row, 16), u32(row, 4))
        validate_save(data)
        saves[name] = Save(name, timestamp(row, 8), timestamp(row, 24), data)
    return [saves[n] for n in sorted(saves)]


def migrate_nmc_checkpoint(payload):
    # Other checkpoints can have different sets of completed mod events.
    if hashlib.sha256(payload).hexdigest() != KNOWN_SAVE:
        raise ValueError('the NMC migration only supports the documented checkpoint')
    data = bytearray(payload)
    rooms = {
        (2, 1): (0, 0, 1),
        (10, 0): (0, 0, 0), (10, 1): (0, 0, 0), (10, 2): (0, 1, 0),
        (10, 3): (0, 1, 0), (10, 4): (0, 1, 0), (10, 5): (3, 1, 0),
        (10, 7): (0, 0, 0), (10, 8): (0, 0, 0), (10, 9): (0, 0, 0),
        (11, 4): (1, 1, 0), (11, 7): (1, 1, 0),
        (18, 2): (0, 0, 6), (18, 3): (0, 0, 3),
    }
    for (world, room), selectors in rooms.items():
        struct.pack_into('<3H', data, 16+6*(64*world+room), *selectors)
    # PC 0x2809 clears the world initializer 0x282a. Only the earlier
    # prologue flag 0x800 sets it. Both have already run on this checkpoint.
    data[0x1c90 + 10*32 + 0x2a//8] &= ~(1 << (0x2a % 8))
    # tt28 event 808: PS2 Valor is the Bladeless equipment menu; PC awards Limit.
    data[0x36c0] &= ~(1 << 1)
    data[0x36ca] |= 1 << 3
    data[0x36b8] = 1  # Treasure 610 awards the first Limit command, Dual Shot.
    struct.pack_into('<H', data, 0x32f4, 0)  # Bladeless already holds the mirrored weapon.
    # Move the event's Midnight Roar from stock to the new Limit off hand.
    data[0x367b] -= 1
    struct.pack_into('<H', data, 0x3364, 480)
    # Preserve earned Bladeless skills and add its PC starting support ability.
    struct.pack_into('<H', data, 0x3334 + 2*5, 0x81a7)
    # The unearned PS2 Limit record has all four limits enabled. PC starts
    # with plrp row 15 plus Dual Shot from event 808 (matches native slot 3).
    limit_skills = (0x823d, 0x823e, 0x823f, 0x824b, 0x824d, 0x8052, 0x81a7, 0x80df, 0x823b)
    struct.pack_into('<24H', data, 0x336c, *limit_skills, *([0] * (24-len(limit_skills))))
    struct.pack_into('<I', data, 8, checksum(data))
    return bytes(data)


def inventory(path):
    if path.is_dir():
        saves = []
        for folder in sorted(path.iterdir()):
            if not re.fullmatch(r'BISLPM-66675FM-[0-9]{2}', folder.name):
                continue
            file = folder / folder.name
            data = file.read_bytes()
            validate_save(data)
            modified = int(file.stat().st_mtime)
            saves.append(Save(folder.name.encode('ascii'), modified, modified, data))
    else:
        saves = read_card(path.read_bytes())
    require(saves, 'no JP Final Mix campaign (SLPM-66675) found. Original US/EU KH2 '
            'saves use a different format. Other games and regions are unsupported.')
    return saves


def container(png):
    require(png.startswith(PNG), 'invalid PNG signature')
    pos = 8
    region = None
    while pos + 12 <= len(png):
        size, tag = struct.unpack_from('>I4s', png, pos)
        end = pos + 8 + size
        require(end + 4 <= len(png), 'truncated PNG')
        require(zlib.crc32(png[pos+4:end]) == struct.unpack_from('>I', png, end)[0],
                f'invalid PNG {tag!r} CRC')
        if pos == 8:
            require(tag == b'IHDR' and size == 13, 'missing PNG header')
        if tag == b'sqEX':
            require(region is None, 'duplicate sqEX')
            require(size == (DATA + COUNT * SIZE + 1023) // 1024 * 1024, 'wrong sqEX size')
            region = (pos+8, end)
        if tag == b'khXb':
            raise ValueError('custom port marker present; select a Steam save')
        if tag == b'IEND':
            require(size == 0 and end+4 == len(png) and region, 'invalid PNG ending or missing sqEX')
            return region
        pos = end + 4
    raise ValueError('missing PNG ending')


def directory(card, steam_id=None):
    # The first 256 bytes are account-encoded. Zero directory padding exposes
    # the repeating mask; only decode the fields needed to identify the system row.
    key = card[160:176]
    stamp = bytes(a ^ b for a, b in zip(card[:16], key))
    if steam_id is not None:
        expected = hashlib.md5((steam_id+'1').encode('ascii'), usedforsecurity=False).digest()
        require(stamp == expected, 'Steam account header does not match the account folder')
    header = bytes(card[i] ^ key[i % 16] for i in range(16, 256))
    require(header[:64] == (PREFIX+b'SYS').ljust(64, b'\0') and u32(header, 80) == 1024
            and card[DATA:DATA+8] == b'KH2SJP\x01\0',
            'invalid Steam system entry; save once in KH2FM first')
    rows = {}
    for physical in range(1, COUNT):
        offset = 16 + physical * ROW
        field = card[offset:offset+64]
        if not any(field):
            continue
        match = re.fullmatch(PREFIX + rb'([0-9]{2})\x00+', field)
        require(match and u32(card, offset+80) == SIZE, f'invalid Steam directory row {physical}')
        slot = 1 + int(match[1])
        require(slot < COUNT and slot not in rows, 'invalid or duplicate Steam slot')
        start = DATA + physical * SIZE
        validate_save(card[start:start+SIZE])
        rows[slot] = physical
    return rows


def insert(png, save, slot, replace=False, migrate=False, steam_id=None):
    require(1 <= slot < COUNT, 'Steam slot must be 1..99')
    start, end = container(png)
    card = bytearray(png[start:end])
    rows = directory(card, steam_id)
    require(replace or slot not in rows, f'Steam slot {slot} is occupied (use --replace)')
    physical = rows.get(slot)
    if physical is None:
        physical = next(i for i in range(1, COUNT) if i not in rows.values())
    name = PREFIX + f'{slot-1:02}'.encode('ascii')
    offset = 16 + physical * ROW
    row = bytearray(ROW)
    row[:len(name)] = name
    struct.pack_into('<qqI', row, 64, save.created, save.modified, SIZE)
    card[offset:offset+ROW] = row
    offset = DATA + physical * SIZE
    card[offset:offset+SIZE] = migrate_nmc_checkpoint(save.data) if migrate else save.data
    crc = struct.pack('>I', zlib.crc32(card, zlib.crc32(b'sqEX')))
    result = png[:start] + card + crc + png[end+4:]
    first, last = container(result)
    directory(result[first:last], steam_id)
    return result


def write_new(path, data):
    with path.open('xb') as f:
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            path.unlink()
            raise


def convert(args, save):
    target = args.into.resolve(strict=True)
    source = args.card.resolve(strict=True)
    paths = [target, (args.out or target).resolve()]
    require(all(path != source and source not in path.parents for path in paths),
            'destination is on the source card')
    require(args.out is None or not os.path.lexists(args.out), 'output already exists')
    if args.out:
        save_result(args, save, target)
        return
    lock = target.with_name(target.name + '.lock')
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        raise ValueError(f'conversion lock exists: {lock}')
    try:
        save_result(args, save, target)
    finally:
        lock.unlink()


def save_result(args, save, target):
    original = target.read_bytes()
    steam_id = target.parent.name if re.fullmatch(r'[0-9]{17}', target.parent.name) else None
    result = insert(original, save, args.slot, args.replace, args.nmc_rmc, steam_id)
    backup = target.with_name(target.name + datetime.now(timezone.utc).strftime('.%Y%m%dT%H%M%S.%fZ.bak'))
    write_new(backup, original)
    print(f'Backup: {backup}', flush=True)
    if args.out is not None:
        write_new(args.out, result)
        return
    f = tempfile.NamedTemporaryFile(dir=target.parent, delete=False)
    temp = Path(f.name)
    try:
        with f:
            f.write(result)
            f.flush()
            os.fsync(f.fileno())
        temp.chmod(stat.S_IMODE(target.stat().st_mode))
        require(target.read_bytes() == original, 'Steam save changed during conversion; retry with game closed')
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='list supported PS2 saves')
    listing.add_argument('card', type=Path)
    edit = commands.add_parser('convert', help='insert one source slot into an existing Steam save')
    edit.add_argument('card', type=Path)
    edit.add_argument('--source', required=True, type=int, help='PS2 slot number shown by list')
    edit.add_argument('--into', required=True, type=Path, help='existing KHIIFM_WW.png')
    edit.add_argument('--slot', required=True, type=int, help='destination Steam slot (1..99)')
    edit.add_argument('--out', type=Path, help='write a separate, new file')
    edit.add_argument('--replace', action='store_true', help='allow an occupied Steam slot')
    edit.add_argument('--nmc-rmc', action='store_true', help='apply the supported NMC checkpoint migration')
    args = parser.parse_args()
    saves = inventory(args.card)
    if args.command == 'list':
        print('PS2 slot\tFolder\tLocation\tLevel\tPlay time\tDifficulty')
    for save in saves:
        number = int(save.name[-2:]) + 1
        if args.command == 'list':
            p = save.data
            sec = u32(p, 0x2444) // 60
            difficulty = u32(p, 0x2498)
            print(number, save.name.decode(), f'{WORLDS[p[12]]}{p[13]:02}', p[0x24ff],
                  f'{sec//3600}:{sec//60%60:02}:{sec%60:02}',
                  f'{difficulty} ({DIFFICULTY[difficulty]})', sep='\t')
        elif args.source == number:
            convert(args, save)
            print(f'Wrote Steam slot {args.slot} to {args.out or args.into}')
            return
    if args.command == 'convert':
        raise ValueError(f'no supported PS2 save in slot {args.source}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, OverflowError) as exc:
        sys.exit(f'kh2save: {exc}')
