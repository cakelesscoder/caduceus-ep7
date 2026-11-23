#!/usr/bin/env python3
"""Caduceus user-side builder for the Olympus E-P7 firmware 1.1 patches.

We do not redistribute OM Digital Solutions firmware. This script downloads the
stock 1.1 update from OM's own server (or uses a copy you already have), checks
its SHA-256, applies a release's edit list (releases/<ver>/edits.json) and
writes the update files for your SD card. Every output hash must match the
release's SHA256SUMS exactly, otherwise nothing is written.

  python3 caduceus.py build --release v0.15 [--out DIR] [--stock FILE]
                           [--owner-name NAME] [--owner-phone PHONE] [--no-owner]
  python3 caduceus.py verify DIR
  python3 caduceus.py list

Python 3.10+, standard library only. Never talks to a camera.

Container format (scrambled "OE" blocks: byte inversion + 16-byte lane
permutation, additive 32-bit checksum) as documented publicly by Altsoph and
mx3 in CHDK forum thread 2471
(https://chdk.setepontos.com/d/2471-olympus-emjustylus-series-fw-analysis).
This is a small independent implementation; it was cross-checked against
fishcu's oly_container.py (https://github.com/fishcu/oly_fw_analysis), which the
Caduceus project used during development.
"""
import re, argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = Path(os.environ.get('CADUCEUS_RELEASES') or ROOT / 'releases')   # override: testing only

STOCK_NAME = 'OLY_E_142_1100_0000_0000.BIN'
STOCK_SHA = '9d1610124ad98f6edae4540182205f06c9c703d9033ef0c4f19847193f95eaeb'
STOCK_SIZE = 111017984
CATALOG = 'https://fw01.om-digitalsolutions.net/ww_inform/fcache.do'
MAIN_BASE = 0x60020020          # CPU address of main-component payload byte 0
CARD_NAME = 'E1429999.BIN'      # E-P7 SD-update file name
# release SHA256SUMS name -> output path (relative to the output directory)
OUTPUTS = {
    'patched.pkg.bin': f'DCOLYMP/{CARD_NAME}',
    'restore-stock.pkg.bin': f'restore/{CARD_NAME}',
}


class Refuse(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- container
LANES = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)
INV = bytes(i ^ 0xFF for i in range(256))


def decode(data):
    out = bytearray(len(data))
    for o, i in enumerate(LANES):
        out[o::16] = data[i::16].translate(INV)
    return bytes(out)


def encode(data):
    out = bytearray(len(data))
    for i, o in enumerate(LANES):
        out[o::16] = data[i::16].translate(INV)
    return bytes(out)


def sum32(data):
    w = array('I')
    if w.itemsize != 4:
        return sum(x for (x,) in struct.iter_unpack('<I', data)) & 0xFFFFFFFF
    w.frombytes(data)
    if sys.byteorder != 'little':
        w.byteswap()
    return sum(w) & 0xFFFFFFFF


def parse(data):
    """-> list of (offset, header, payload, trailer); payload decoded."""
    blocks, off, model = [], 0, None
    while off < len(data):
        if len(data) - off < 64:
            raise Refuse(f'container: truncated block at {off:#x}')
        hdr = data[off:off + 32]
        if hdr[:2] != b'OE' or struct.unpack_from('<I', hdr, 20)[0] == 0:
            raise Refuse(f'container: unsupported block at {off:#x}')
        model = model or hdr[2:4]
        size = struct.unpack_from('<I', hdr, 12)[0]
        end = off + size + 64
        if hdr[2:4] != model or not size or size % 16 or end > len(data):
            raise Refuse(f'container: bad block header at {off:#x}')
        trl = data[end - 32:end]
        if hdr[:28] != trl[:28] or hdr[28:] != b'\0' * 4:
            raise Refuse(f'container: header/trailer mismatch at {off:#x}')
        pay = decode(data[off + 32:end - 32])
        if (sum32(hdr) + sum32(pay) + sum32(trl)) & 0xFFFFFFFF:
            raise Refuse(f'container: checksum mismatch at {off:#x}')
        blocks.append((off, hdr, pay, trl))
        off = end
    return blocks


def kind(hdr):
    return struct.unpack_from('<H', hdr, 20)[0]


def reseal(hdr, pay, trl):
    t = bytearray(trl)
    t[28:] = b'\0' * 4
    struct.pack_into('<I', t, 28, -(sum32(hdr) + sum32(pay) + sum32(t)) & 0xFFFFFFFF)
    return bytes(t)


# ---------------------------------------------------------------- build
def apply_edits(spec, stock):
    """Same rules and checks as tools/build_package.py. -> (patched, restore)."""
    blocks = parse(stock)
    by_kind = {kind(h): (o, h, p, t) for o, h, p, t in blocks}
    kinds = [int(k, 16) for k in spec['components']]
    if (0x100 in kinds and kinds[0] != 0x100) or len(set(kinds)) != len(kinds) \
            or any(k not in by_kind for k in kinds):
        raise Refuse('edits.json: bad component list')
    pays = {k: bytearray(by_kind[k][2]) for k in kinds}
    spans, total = {}, 0
    for e in spec['edits']:
        k = int(e['kind'], 16)
        a = e['addr']
        if k not in pays:
            raise Refuse(f'edits.json: edit {a} targets a component not in the package')
        if a.startswith('off:'):
            off = int(a[4:], 16)
        elif k == 0x100:
            off = int(a, 16) - MAIN_BASE
        else:
            raise Refuse(f'edits.json: edit {a}: CPU address on a non-main component')
        exp, new = bytes.fromhex(e['expect']), bytes.fromhex(e['new'])
        if len(exp) != len(new) or not new or not 0 <= off <= len(pays[k]) - len(new):
            raise Refuse(f'edits.json: edit {a}: bad length or range')
        if any(off < y and x < off + len(new) for x, y in spans.get(k, [])):
            raise Refuse(f'edits.json: edit {a}: overlaps another edit')
        if by_kind[k][2][off:off + len(exp)] != exp:
            raise Refuse(f'edits.json: edit {a}: stock bytes differ from expected')
        spans.setdefault(k, []).append((off, off + len(new)))
        pays[k][off:off + len(new)] = new
        total += sum(x != y for x, y in zip(exp, new))
    parts = []
    for k in kinds:
        _, h, p, t = by_kind[k]
        np_ = bytes(pays[k])
        parts.append(h + encode(np_) + (reseal(h, np_, t) if np_ != p else t))
    patched = b''.join(parts)
    restore = b''.join(stock[o:o + 64 + len(p)] for o, h, p, t in (by_kind[k] for k in kinds))
    # re-verify outputs from scratch
    rp, rr = parse(patched), parse(restore)
    if [kind(b[1]) for b in rp] != kinds or [kind(b[1]) for b in rr] != kinds:
        raise Refuse('internal: output component list wrong')
    changed = 0
    for (_, h, p, t), (_, sh, sp, st), (_, rh, rpay, rt) in zip(rp, (by_kind[k] for k in kinds), rr):
        if h != sh or t[:28] != st[:28] or rh != sh or rpay != sp:
            raise Refuse('internal: output metadata/restore differs from stock')
        changed += sum(x != y for x, y in zip(p, sp))
    if changed != total:
        raise Refuse(f'internal: changed bytes {changed} != edited bytes {total}')
    return patched, restore


# ---------------------------------------------------------------- owner footer
# Releases with the owner_footer layer (patches/owner_footer, docs/OWNER_FOOTER.md) carry an all-zero owner block in the
# firmware image. When the user gives a name and/or phone, the build writes them into that block: one line at the bottom
# of every menu page, fixed until the firmware is rebuilt. Nothing personal is written anywhere else.
OWNER_MAGIC = 0x4f375045                 # 'EP7O'
OWNER_NAME_MAX, OWNER_PHONE_MAX, OWNER_UNITS = 24, 20, 46
# ASCII 0x20..0x7e glyph widths of the camera's text font (same in every language font); advance ~ width + 3
OWNER_WIDTHS = (10, 5, 8, 18, 15, 22, 19, 3, 8, 8, 12, 15, 4, 10, 4, 11, 18, 10, 17, 17, 18, 17, 18, 17, 19, 18, 4, 4, 12,
                15, 12, 15, 22, 19, 16, 17, 18, 15, 14, 19, 17, 4, 9, 17, 13, 21, 17, 19, 16, 19, 17, 16, 15, 17, 18, 23, 17,
                17, 16, 7, 11, 7, 13, 14, 8, 15, 14, 14, 14, 14, 9, 15, 13, 4, 7, 14, 3, 20, 13, 15, 14, 15, 8, 13, 9, 14, 14,
                21, 14, 15, 13, 8, 3, 8, 14)
OWNER_MAXPX = 620


def owner_text(name, phone):
    """Validate -> the one line the camera shows ('' = no footer). Raises Refuse with a reason."""
    name, phone = (name or '').strip(), (phone or '').strip()
    if any(not (0x20 <= ord(c) <= 0x7e) for c in name + phone):
        raise Refuse('owner name and phone: plain ASCII letters, digits and punctuation only (no accents or emoji)')
    if len(name) > OWNER_NAME_MAX:
        raise Refuse(f'owner name: at most {OWNER_NAME_MAX} characters')
    if len(phone) > OWNER_PHONE_MAX or not re.fullmatch(r'[0-9 +()\-]*', phone):
        raise Refuse(f'owner phone: at most {OWNER_PHONE_MAX} characters, digits, spaces and + - ( ) only')
    text = '  '.join(x for x in (name, phone) if x)
    px = sum(OWNER_WIDTHS[ord(c) - 0x20] + 3 for c in text)
    if px > OWNER_MAXPX:
        raise Refuse(f'owner line too wide for the screen (about {px} of {OWNER_MAXPX} px); shorten the name')
    return text


def owner_block(text, size):
    if not text:
        return bytes(size)
    b = struct.pack('<IHH', OWNER_MAGIC, len(text), 0) + text.encode('utf-16-le')
    if len(text) > OWNER_UNITS or len(b) + 2 > size:
        raise Refuse('owner line too long')
    return b + bytes(size - len(b))


def owner_spec(spec, text):
    """-> a copy of the release spec whose owner block holds text ('' -> the spec unchanged)."""
    if not text:
        return spec
    info = spec.get('owner_footer')
    if not info:
        raise Refuse('this release has no owner footer; build without --owner-name / --owner-phone')
    blk, n = int(info['block'], 16), info['block_len']
    out = json.loads(json.dumps(spec))
    for e in out['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16)
            new = bytearray.fromhex(e['new'])
            if a <= blk and blk + n <= a + len(new):
                if any(new[blk - a:blk - a + n]):
                    raise Refuse('internal: release owner block is not empty')
                new[blk - a:blk - a + n] = owner_block(text, n)
                e['new'] = new.hex()
                return out
    raise Refuse('internal: no edit holds the owner block')


def owner_unpatch(pkg, spec):
    """The package with the owner block zeroed again (used to check a personalised build against the release)."""
    info = spec.get('owner_footer')
    if not info:
        raise Refuse('release has no owner footer')
    blk, n = int(info['block'], 16) - MAIN_BASE, info['block_len']
    parts = []
    for o, h, p, t in parse(pkg):
        if kind(h) == 0x100:
            q = bytearray(p)
            q[blk:blk + n] = bytes(n)
            q = bytes(q)
            parts.append(h + encode(q) + reseal(h, q, t))
        else:
            parts.append(pkg[o:o + 64 + len(p)])
    return b''.join(parts)


def ask_owner(spec):
    """Interactive: two optional questions. No terminal -> no footer."""
    if 'owner_footer' not in spec or not (sys.stdin and sys.stdin.isatty()):
        return ''
    print('\nOptional owner footer: your name and phone shown in small text at the bottom of every camera menu page.\n'
          'It is fixed in the firmware: to change or remove it, build and flash again. Press Enter to skip.')
    while True:
        try:
            name = input(f'  Owner name (up to {OWNER_NAME_MAX} characters): ')
            phone = input(f'  Phone (up to {OWNER_PHONE_MAX}: digits, spaces, + - ( )): ')
        except (EOFError, OSError, RuntimeError):
            return ''
        try:
            text = owner_text(name, phone)
        except Refuse as e:
            print(f'  {e}. Try again.')
            continue
        if text:
            print(f'  The camera menus will show: {text}')
        return text


def get_owner(a, spec):
    if getattr(a, 'owner_name', None) or getattr(a, 'owner_phone', None):
        return owner_text(a.owner_name, a.owner_phone)
    if getattr(a, 'no_owner', False):
        return ''
    return ask_owner(spec)


# ---------------------------------------------------------------- download
def fetch_stock():
    t = time.strftime('%Y%m%d%H%M%S', time.gmtime())
    req = ("<?xml version='1.0' encoding='utf-8'?><firmware_demand><revision>0001</revision>"
           "<mac_address>00-00-00-00-00-00</mac_address><time>" + t + "</time><language>ENU</language>"
           "<application>FWUT</application><type>0000</type><version>00005000</version><os>WIN</os>"
           "<country_code>0001</country_code><hardwares><firmup_mode>0</firmup_mode><hardware_info>"
           "<hard_code>OLYE142000000000</hard_code><firmware_version>00001000</firmware_version>"
           "<serial_no>000000000</serial_no></hardware_info></hardwares></firmware_demand>")
    hdrs = {'User-Agent': 'Olympus', 'Content-Type': 'text/xml; Charset=UTF-8'}
    print('Asking OM Digital Solutions for the E-P7 1.1 firmware ...')
    try:
        with urllib.request.urlopen(urllib.request.Request(CATALOG, req.encode(), hdrs), timeout=60) as r:
            info = ET.fromstring(r.read()).find('.//firmware_info')
        if info is None or info.findtext('model_id') != '1420' or info.findtext('file_name') != STOCK_NAME:
            raise Refuse('OM server did not offer E-P7 firmware 1.1 (it may have moved). '
                         f'Download {STOCK_NAME} yourself and use --stock FILE.')
        url = info.findtext('url')
        print(f'Downloading {STOCK_NAME} from {url.split("/")[2]}')
        buf = bytearray()
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Olympus'}),
                                    timeout=120) as r:
            while chunk := r.read(1 << 20):
                buf += chunk
                print(f'\r  {len(buf) >> 20} / {STOCK_SIZE >> 20} MiB', end='', flush=True)
        print()
        return bytes(buf)
    except (OSError, ET.ParseError) as e:
        raise Refuse(f'download failed: {e}\nIf this keeps happening, download {STOCK_NAME} '
                     'another way and pass --stock FILE (see docs/INSTALL.md).')


# ---------------------------------------------------------------- releases
def read_sums(path):
    sums = {}
    for line in path.read_text().splitlines():
        if line.strip():
            h, name = line.split(maxsplit=1)
            sums[name.lstrip('*')] = h.lower()
    return sums


def releases():
    if not RELEASES.is_dir():
        return []
    return sorted(d.name for d in RELEASES.iterdir()
                  if (d / 'edits.json').is_file() and (d / 'SHA256SUMS').is_file()
                  and 'patched.pkg.bin' in read_sums(d / 'SHA256SUMS'))


def load_release(name):
    d = RELEASES / name
    if name not in releases():
        avail = ', '.join(r for r in releases() if r.startswith('v')) or 'none'
        raise Refuse(f'unknown release {name!r}. Available: {avail}')
    sums = read_sums(d / 'SHA256SUMS')
    spec_bytes = (d / 'edits.json').read_bytes()
    if 'edits.json' in sums and sha(spec_bytes) != sums['edits.json']:
        raise Refuse(f'releases/{name}/edits.json does not match releases/{name}/SHA256SUMS '
                     '(repository out of sync; update your copy).')
    # card files ship in the repository (our own data, not OM firmware)
    card = {}
    for n, h in sums.items():
        if n.startswith('card/'):
            f = d / n
            if not f.is_file():
                raise Refuse(f'missing releases/{name}/{n}')
            b = f.read_bytes()
            if sha(b) != h:
                raise Refuse(f'releases/{name}/{n} does not match SHA256SUMS')
            card[n[len('card/'):]] = b
    return json.loads(spec_bytes), sums, card


def cmd_build(a):
    out = Path(a.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refuse(f'{out} already exists and is not empty; choose another --out or remove it.')
    spec, sums, card = load_release(a.release)
    if a.stock:
        p = Path(a.stock)
        if not p.is_file():
            raise Refuse(f'--stock: no such file {p}')
        stock = p.read_bytes()
    else:
        stock = fetch_stock()
    if sha(stock) != STOCK_SHA:
        raise Refuse(f'stock firmware SHA-256 is {sha(stock)}\nexpected {STOCK_SHA}\n'
                     f'This is not the official E-P7 1.1 file {STOCK_NAME} ({STOCK_SIZE} bytes). Nothing written.')
    owner = a.owner if hasattr(a, 'owner') else get_owner(a, spec)
    print(f'Stock firmware OK. Applying {len(spec["edits"])} edits from releases/{a.release}/edits.json ...')
    patched, restore = apply_edits(spec, stock)
    for rel_name, data in (('patched.pkg.bin', patched), ('restore-stock.pkg.bin', restore)):
        if sha(data) != sums[rel_name]:
            raise Refuse(f'{rel_name}: built hash {sha(data)} != release {sums[rel_name]}. Nothing written.')
    if owner:                                   # same edits plus the owner block; must differ only inside that block
        mine, _ = apply_edits(owner_spec(spec, owner), stock)
        if mine == patched or owner_unpatch(mine, spec) != patched:
            raise Refuse('internal: owner footer build differs from the release outside the owner block. Nothing written.')
        patched = mine
        print('Owner footer added.')
    files = {OUTPUTS['patched.pkg.bin']: patched, OUTPUTS['restore-stock.pkg.bin']: restore}
    files.update(card)
    # write into a temp dir next to the target, then move into place
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.caduceus-', dir=out.parent))
    try:
        for rel, data in files.items():
            f = tmp / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        (tmp / 'SHA256SUMS').write_text(''.join(f'{sha(d)}  {r}\n' for r, d in sorted(files.items())))
        (tmp / 'RELEASE').write_text(a.release + '\n')
        if owner:
            (tmp / 'OWNER_FOOTER').write_text('This build has an owner footer (its text is only inside the firmware file).\n')
        if out.exists():
            out.rmdir()
        os.replace(tmp, out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f'\nCaduceus {a.release} written to {out}:')
    for r in sorted(files):
        print(f'  {r}')
    print('  SHA256SUMS\n' + ('Release hashes matched; the firmware file is the release plus your owner footer.' if owner else
                             'All hashes match the release.') + ' Next: docs/INSTALL.md (copy DCOLYMP/ and EP7MOD/ to the card;'
          ' keep restore/ on your computer).')
    return 0


def cmd_verify(a):
    d = Path(a.dir)
    man = d / 'SHA256SUMS'
    if not man.is_file():
        raise Refuse(f'{man} not found; is {d} a caduceus build directory?')
    sums, bad = read_sums(man), 0
    for rel, h in sorted(sums.items()):
        f = d / rel
        ok = f.is_file() and sha(f.read_bytes()) == h
        bad += not ok
        print(f'  {"OK  " if ok else "FAIL"}  {rel}')
    rel_name = (d / 'RELEASE').read_text().strip() if (d / 'RELEASE').is_file() else None
    if rel_name and rel_name in releases():
        rs = read_sums(RELEASES / rel_name / 'SHA256SUMS')
        want = {OUTPUTS[n]: h for n, h in rs.items() if n in OUTPUTS}
        want.update({n[len('card/'):]: h for n, h in rs.items() if n.startswith('card/')})
        fw = OUTPUTS['patched.pkg.bin']
        if (d / 'OWNER_FOOTER').is_file() and (d / fw).is_file() and sums.get(fw) == sha((d / fw).read_bytes()):
            spec = json.loads((RELEASES / rel_name / 'edits.json').read_text())
            if sha(owner_unpatch((d / fw).read_bytes(), spec)) == want.get(fw):
                want[fw] = sums[fw]             # personalised: the release firmware plus the owner block only
                print(f'  OK    {fw}: release firmware + owner block')
        if want != sums:
            bad += 1
            print(f'  FAIL  file list/hashes differ from releases/{rel_name}/SHA256SUMS')
        else:
            print(f'  OK    matches releases/{rel_name}/SHA256SUMS')
    else:
        print(f'  note: release {rel_name!r} not found here; checked the local manifest only')
    if bad:
        raise Refuse(f'{bad} problem(s). Do not flash these files; rebuild them.')
    print('All good.')
    return 0


def cmd_list(a):
    for r in releases():
        if r.startswith('v'):
            print(r)
    return 0


# ---------------------------------------------------------------- one-press mode
def vkey(name):
    """v0.29 < v0.29a < v0.29b < v0.30."""
    m = re.fullmatch(r'v(\d+(?:\.\d+)*)([a-z]?)', name)
    if not m:
        return (-1,)
    return tuple(int(x) for x in m.group(1).split('.')) + (ord(m.group(2)) - 96 if m.group(2) else 0,)


def latest_release():
    rs = [r for r in releases() if r.startswith('v')]
    if not rs:
        raise Refuse('no releases found next to caduceus.py (is the download complete?)')
    return max(rs, key=vkey)


def find_stock():
    """An already downloaded OM file next to the script, in cache/, or in Downloads."""
    here = Path(__file__).resolve().parent
    for p in (here / STOCK_NAME, here / 'cache' / STOCK_NAME, Path.home() / 'Downloads' / STOCK_NAME):
        try:
            if p.is_file() and p.stat().st_size == STOCK_SIZE:
                return p
        except OSError:
            pass
    return None


def _scan_cards(found):
    if os.name == 'nt':
        import ctypes, string
        for L in string.ascii_uppercase:
            r = Path(f'{L}:\\')
            try:
                if ctypes.windll.kernel32.GetDriveTypeW(f'{L}:\\') == 2 and (r / 'DCIM').is_dir():
                    found.append(r)
            except OSError:
                pass
        return
    user = os.environ.get('USER', '')
    for base in (Path('/Volumes'), Path('/media') / user, Path('/run/media') / user, Path('/media')):
        try:
            entries = list(base.iterdir()) if base.is_dir() else []
        except OSError:
            continue
        for r in entries:
            try:
                if r.is_dir() and (r / 'DCIM').is_dir() and r not in found:
                    found.append(r)
            except OSError:
                pass


def sd_cards(limit=10.0):
    """Mounted cards that look like camera cards (have a DCIM folder).
    CADUCEUS_CARD_DIRS (os.pathsep-separated) replaces the scan (for testing). The scan runs in a
    daemon thread with a time limit so a dead network/optical mount cannot hang us."""
    env = os.environ.get('CADUCEUS_CARD_DIRS')
    if env is not None:
        return [Path(x) for x in env.split(os.pathsep) if x and (Path(x) / 'DCIM').is_dir()]
    import threading
    found = []
    t = threading.Thread(target=_scan_cards, args=(found,), daemon=True)
    t.start()
    t.join(limit)
    if t.is_alive():
        print('  (card search took too long; skipped slow drives)')
    return list(found)


def ask(q, default=True):
    """y/n question; without an interactive terminal, answer no (never copy unasked)."""
    try:
        if not (sys.stdin and sys.stdin.isatty()):
            print(f'{q} -> no terminal to ask, so: no')
            return False
        a = input(f'{q} [{"Y/n" if default else "y/N"}] ').strip().lower()
    except (EOFError, OSError, RuntimeError):
        return False
    return default if not a else a.startswith('y')


def pause():
    """Keep a double-clicked window open (the launchers pause themselves and set CADUCEUS_LAUNCHER)."""
    if os.environ.get('CADUCEUS_LAUNCHER'):
        return
    try:
        if sys.stdin and sys.stdin.isatty():
            input('\nPress Enter to close...')
    except (EOFError, OSError, RuntimeError, KeyboardInterrupt):
        pass


def copy_synced(src, dst):
    """Copy src to dst and force the data out to the card (macOS in particular caches FAT writes, so a card
    pulled without ejecting can hold truncated files, which the camera's loader silently ignores)."""
    with open(src, 'rb') as i, open(dst, 'wb') as o:
        shutil.copyfileobj(i, o, 1 << 20)
        o.flush()
        try:
            if sys.platform == 'darwin':
                import fcntl
                fcntl.fcntl(o.fileno(), fcntl.F_FULLFSYNC)
            else:
                os.fsync(o.fileno())
        except (OSError, ImportError, AttributeError):
            pass


def copy_to_card(build, card):
    """DCOLYMP/E1429999.BIN + LOOKS.BIN always; BUNDLES.BIN, MOVIE.BIN and AP.BIN only if the card has none (they hold the user's settings)."""
    dco = card / 'DCOLYMP'
    try:
        dco.mkdir(exist_ok=True)
    except PermissionError:
        raise Refuse(f'not allowed to write to {card}.' + (
            ' On macOS: System Settings > Privacy & Security > Files and Folders (or Full Disk Access), allow '
            'Terminal to access Removable Volumes, then run this again, or drag the folders across in Finder.'
            if sys.platform == 'darwin' else ' Check the card is not write-locked (the small switch on the card).'))
    for old in dco.glob('*.BIN'):
        if old.name.upper() != 'E1429999.BIN':
            print(f'  note: {old} is another update file; remove it before flashing.')
    print('  copying the update (about 100 MB) ...')
    copy_synced(build / 'DCOLYMP' / 'E1429999.BIN', dco / 'E1429999.BIN')
    mod = card / 'EP7MOD'
    mod.mkdir(exist_ok=True)
    copy_synced(build / 'EP7MOD' / 'LOOKS.BIN', mod / 'LOOKS.BIN')
    check = ['DCOLYMP/E1429999.BIN', 'EP7MOD/LOOKS.BIN']
    if (mod / 'BUNDLES.BIN').exists():
        print('  kept your existing EP7MOD/BUNDLES.BIN (your saved looks)')
    else:
        copy_synced(build / 'EP7MOD' / 'BUNDLES.BIN', mod / 'BUNDLES.BIN')
        check.append('EP7MOD/BUNDLES.BIN')
    for name, what in (('MOVIE.BIN', 'Movie colour'), ('AP.BIN', 'AP Custom colour')):
        if (build / 'EP7MOD' / name).exists():
            if (mod / name).exists():
                print(f'  kept your existing EP7MOD/{name} (your {what} settings)')
            else:
                copy_synced(build / 'EP7MOD' / name, mod / name)
                check.append(f'EP7MOD/{name}')
    for rel in check:
        if sha((card / rel).read_bytes()) != sha((build / rel).read_bytes()):
            raise Refuse(f'copy check failed for {card / rel}; copy it again by hand. Do not flash.')
    print(f'  copied and checked on {card}')
    print('  IMPORTANT: eject the card from the computer (Finder eject button / Windows "Eject" / Unmount) before '
          'removing it, or the files can be cut short and the camera will quietly ignore them.')


def open_folder(p):
    """Show the folder without waiting for the file manager (xdg-open can block until the window closes,
    and a child holding our stdout pipe would keep a captured run hanging)."""
    try:
        if os.name == 'nt':
            os.startfile(p)
            return
        cmd = ['open', str(p)] if sys.platform == 'darwin' else ['xdg-open', str(p)]
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def build_matches(out, rel):
    """True if out is a complete build of rel whose files match releases/<rel>/SHA256SUMS."""
    try:
        if (out / 'RELEASE').read_text().strip() != rel:
            return False
        rs = read_sums(RELEASES / rel / 'SHA256SUMS')
        want = {OUTPUTS[n]: h for n, h in rs.items() if n in OUTPUTS}
        want.update({n[len('card/'):]: h for n, h in rs.items() if n.startswith('card/')})
        if read_sums(out / 'SHA256SUMS') != want:
            return False
        return all(sha((out / r).read_bytes()) == h for r, h in want.items())
    except (OSError, ValueError):
        return False


def cmd_easy(a):
    here = Path(__file__).resolve().parent
    rel = latest_release()
    print(f'Caduceus one-press build: {rel}\n')
    out = here / f'Caduceus-{rel}'
    owner = ask_owner(load_release(rel)[0])
    old = sorted(p.name for p in here.glob('Caduceus-v*') if p.is_dir() and p != out)
    if old:
        print(f'(older build folders, not used: {", ".join(old)})')
    if out.exists() and not owner and build_matches(out, rel):
        print(f'{out.name} already exists and matches the release.')
    else:
        if out.exists():
            if not (out / 'SHA256SUMS').is_file():
                raise Refuse(f'{out} exists but is not a Caduceus build; rename or delete it and run again.')
            n = 1
            while (stale := out.with_name(f'{out.name}.old{n}')).exists():
                n += 1
            os.replace(out, stale)
            print(f'{out.name} was out of date or incomplete; moved it to {stale.name} and rebuilding.')
        stock = find_stock()
        if stock is None:
            data = fetch_stock()
            if sha(data) == STOCK_SHA:  # keep it so a rebuild doesn't download again
                (here / 'cache').mkdir(exist_ok=True)
                (here / 'cache' / STOCK_NAME).write_bytes(data)
                stock = here / 'cache' / STOCK_NAME
        else:
            print(f'Using the OM file already on this computer: {stock}')
        cmd_build(argparse.Namespace(out=str(out), release=rel, stock=str(stock) if stock else None, owner=owner))
    print('\nLooking for a camera SD card ...')
    cards = sd_cards()
    copied = False
    if len(cards) == 1 and ask(f'Copy the update to the SD card at {cards[0]}?'):
        try:
            copy_to_card(out, cards[0])
            copied = True
        except (Refuse, OSError) as e:
            print(f'\nCould not copy to the card: {e}\nThe build itself is fine. Copy the DCOLYMP and EP7MOD folders by hand '
                  '(below), then eject the card properly.')
    if copied:
        print('\nNow eject the card, put it in the camera, then: full battery, hold OK and switch on.\n'
              'LED steady = writing (do not switch off), ~2 Hz blink = done. See docs/INSTALL.md.')
    else:
        if len(cards) > 1:
            print(f'Several camera cards found ({", ".join(map(str, cards))}); copy by hand.')
        elif not cards:
            print('No camera card found (a card formatted in the camera has a DCIM folder).')
        print(f'\nCopy the DCOLYMP and EP7MOD folders from {out} to the top level of your SD card\n'
              '(keep any EP7MOD/BUNDLES.BIN already on the card: it holds your saved looks).\n'
              'Keep the "restore" folder on your computer. Then follow docs/INSTALL.md "Flash".')
        open_folder(out)
    return 0


def main(argv=None):
    if sys.version_info < (3, 10):
        sys.exit('Python 3.10 or newer is required.')
    ap = argparse.ArgumentParser(prog='caduceus.py', description='Build Caduceus E-P7 firmware files locally.')
    sub = ap.add_subparsers(dest='cmd')
    b = sub.add_parser('build', help='download stock 1.1, apply a release, write card files')
    b.add_argument('--release', required=True, help='e.g. v0.15 (see: caduceus.py list)')
    b.add_argument('--out', default='out', help='new or empty output directory (default: out)')
    b.add_argument('--stock', help=f'use an already downloaded {STOCK_NAME} instead of downloading')
    b.add_argument('--owner-name', help=f'owner footer: name shown on the menu pages (up to {OWNER_NAME_MAX} ASCII characters)')
    b.add_argument('--owner-phone', help=f'owner footer: phone (up to {OWNER_PHONE_MAX}: digits, spaces, + - ( ))')
    b.add_argument('--no-owner', action='store_true', help='no owner footer and no questions')
    b.set_defaults(fn=cmd_build)
    v = sub.add_parser('verify', help='re-check a build directory')
    v.add_argument('dir')
    v.set_defaults(fn=cmd_verify)
    sub.add_parser('list', help='list available releases').set_defaults(fn=cmd_list)
    a = ap.parse_args(argv)
    for f in (sys.stdout, sys.stderr):  # progress shows up at once, even through a pipe
        try:
            f.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass
    easy = a.cmd is None  # double-click / no arguments: one-press mode
    if easy:
        a.fn = cmd_easy
    try:
        return a.fn(a)
    except Refuse as e:
        print(f'refused: {e}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('interrupted.', file=sys.stderr)
        return 130
    finally:
        if easy:
            pause()


if __name__ == '__main__':
    sys.exit(main())
