#!/usr/bin/env python3
"""Movie bitrate: 4K UHD at 150 Mbit/s instead of 100 (docs/RE_MOVIE.md section 6.1 and "Movie bitrate layer"). Data only, four
words, no code. Layer it with --extra after v033b (it reads no other layer and touches no other layer's bytes):

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v034_movie/edits.json --version 0.34a \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra v033b=patches/v033b/build.py --extra movie_bitrate=patches/movie_bitrate/build.py

Edits (all main, section 2):
  B  bitrate table 0x60539b84 (u32 bit/s, [mode][fps][quality]): mode 1 (4K UHD, media 1), quality column 2 (F, the only 4K
     column), 30p 0x60539bfc, 25p 0x60539c0c, 24p 0x60539c1c: 100 000 000 -> 150 000 000. 4K has no 60p / 50p cells (0 in
     stock, still 0). The table's only readers are the encoder setter 0x603d1620 (`add 0x60539b84,d0` at 0x603d16e9) and the
     size calculator 0x603d79b3 (`add 0x60539b84,d2` at 0x603d7b52), which feeds the per-file split and the remaining-time
     estimate, so the encoder, the 4 GB split and the estimate all move together.
  C  ulMaxBitrate 0x603d19db `mov 105000000,d0` (imm32 0x603d19dd) -> 157 500 000: 150 M plus the stock 5 % (100 -> 105).
     The instruction is shared: every mode that is neither C4K (250 M) nor FHD with picture type 1 (200 M) takes it, so FHD
     SF/F/N, HD, the small sizes and high-speed movie get the same new ceiling. Their target bitrates do not change.

Why these values (rationale, docs/RE_MOVIE.md "Movie bitrate layer"):
  - 4K is always H.264 level 5.1 (venc_h264_prog_init 0x6131b45f: 2160 lines -> 5.1 at any bitrate), whose High-profile
    limit is 300 Mbit/s, so 150 M target / 157.5 M ceiling sit at half of it. ulMaxCodeSize (4K 0x2f7600 = 3.1 MB a frame)
    is a constant, not derived from the bitrate; at 150 M the mean frame is 625 KB (stock I-frames 470-660 KB at 100 M).
  - FHD is left at stock: SF 50 M is the top of the 4.1/4.2 band (> 50 M -> level 5 when the encoder reads the target), and
    which AVSCA word the level reads is not proven. Any FHD target up to the new ceiling stays inside the level the encoder
    picks either way, but a 1080-line level-5 encode is a path stock reaches only through picture type 1 (ALL-I). This
    build's FHD 60p SF clip answers the question (L4.2: target read; L5.1: ceiling read), then FHD can follow.
  - GOP stays 0.5 s (0x603d18d2/dc/e6/f0 untouched): it is not needed for the bitrate, and one change per flash.

User note (draft, for the release notes when the lead ships it):
  4K movies record at about 150 Mbit/s (video) instead of 100 Mbit/s, in 30p, 25p and 24p. Full HD, HD and high-speed movie
  keep their bitrates. A 4K file now splits about every 3 min 20 s (stock 5 min 20 s) because each file still stops just
  under 4 GB; the recording itself continues into the next file as before. The remaining-time display shows about two thirds
  of the stock 4K time (the card fills 1.5 times faster: 19.5 MB/s instead of 13.1). Use a V30 (or faster) card for 4K: the
  camera writes about 19.5 MB/s; a card that cannot keep up stops the recording with a card error rather than damaging
  the file.

apply(spec, version) -> spec (adds 4 edits and spec["movie_bitrate"]). Refuses if another layer holds any of the bytes.
Alternative: patches/movie_quality (4K F 100 M / SF 150 M / N 60 M chosen per slot in the slot editor); use one of the two.
"""
import argparse, copy, hashlib, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = 'patches/movie_bitrate'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


CL = _load('crash_log_build_mb', ROOT / 'patches/crash_log/build.py')
ST, KH, B3 = CL.ST, CL.KH, CL.B3
BASE, STOCK = CL.BASE, CL.STOCK

TABLE, ROWS, ROW = 0x60539b84, 11, 0x50              # u32 [mode 0..10] x 0x50 + [fps 60,50,30,25,24] x 0x10 + [quality col] x 4
BUF_TABLE, BUF_LEN = 0x60539ef4, 11 * 0x3c            # buffer table the split subtracts (read only by 0x603d79b3; unchanged)
OLD_4K, NEW_4K = 100_000_000, 150_000_000
CELLS = {30: TABLE + 1 * ROW + 2 * 0x10 + 2 * 4,     # 0x60539bfc
         25: TABLE + 1 * ROW + 3 * 0x10 + 2 * 4,     # 0x60539c0c
         24: TABLE + 1 * ROW + 4 * 0x10 + 2 * 4}     # 0x60539c1c
CEIL_AT, OLD_CEIL, NEW_CEIL = 0x603d19db, 105_000_000, 157_500_000    # fc cc imm32: mov imm32,d0
CEIL_NEXT = bytes.fromhex('f81204')                  # mov d0,(4,a2): ulMaxBitrate (video word 1 = block word 25)
SETTER = (0x603d1620, 0x603d1b17)                    # encoder video setter (linear decode for the branch scan)
READERS = {0x603d16eb: 'encoder setter 0x603d1620: add 0x60539b84,d0 (0x603d16e9)',
           0x603d7b54: 'size calculator 0x603d79b3: add 0x60539b84,d2 (0x603d7b52)'}
# abs32 words that fall inside the table's range by coincidence: each is the imm32 tail of a `mov imm32,d0` (fc cc ..) whose
# opcode byte cc happens to be the low byte, or a call's displacement (flash alias): pinned by their bytes.
PINS = {0x6060241a: 'cc9d5360', 0x60602879: 'cc9d5360', 0x60602a58: 'cc9d5360', 0x60602bae: 'cc9d5360',
        0x60602d9e: 'cc9d5360', 0x60602f97: 'cc9d5360', 0x6041eb16: 'cd9bbb80'}


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def overlaps(spec, lo, hi):
    return [e['addr'] for e in spec['edits'] if e['kind'] == '0x100' and not e['addr'].startswith('off:')
            and int(e['addr'], 16) < hi and lo < int(e['addr'], 16) + len(e['new']) // 2]


def check_stock(stock):
    for fps, a in CELLS.items():
        if u32(stock, a) != OLD_4K:
            raise SystemExit(f'4K {fps}p cell {a:#x} is not 100 M in stock')
    for k in (0, 1):                                  # 4K 60p / 50p: no cell (0 in every column)
        if any(u32(stock, TABLE + ROW + k * 0x10 + 4 * c) for c in range(4)):
            raise SystemExit('4K 60p/50p cells are not empty')
    if stock[CEIL_AT - BASE:CEIL_AT + 2 - BASE] != b'\xfc\xcc' or u32(stock, CEIL_AT + 2) != OLD_CEIL \
            or stock[CEIL_AT + 6 - BASE:CEIL_AT + 9 - BASE] != CEIL_NEXT:
        raise SystemExit('ceiling site differs from stock')
    if stock.count(struct.pack('<I', OLD_CEIL)) != 1:
        raise SystemExit('105 000 000 is not unique in the image')
    for a, why in READERS.items():
        if u32(stock, a) != TABLE or stock[a - 2 - BASE] != 0xfc or stock[a - 1 - BASE] not in (0xc0, 0xc2):
            raise SystemExit(f'table reader {a:#x} differs ({why})')


def table_refs(im, stock):
    """Every abs32 (four aliases) and d16/d32 branch into the table must be one of the two readers' base words or a pin."""
    off = KH.sec(stock, 2)[2]
    data = [(TABLE, BUF_TABLE + BUF_LEN)]            # bytes of the two tables that happen to read as cc/dd encodings
    hits = CL.refs(im, TABLE, TABLE + ROWS * ROW, off, allow=data)
    left = [(k, a) for k, a in hits if not (k == 'abs32' and a in READERS and u32(im, a) == TABLE)
            and not (a in PINS and im[a - BASE:a + 4 - BASE].hex() == PINS[a])]
    if left:
        raise SystemExit(f'unexpected references into the bitrate table: {[(k, hex(a)) for k, a in left[:6]]}')
    for a in CELLS.values():                          # nothing at all points at the edited words (computed index only)
        if [r for r in CL.refs(im, a, a + 4, off, allow=data) if r[1] not in PINS]:
            raise SystemExit(f'reference to the table word {a:#x}')
    return len(hits)


def ceiling_scan(im, stock):
    ins = B3.disasm(im[SETTER[0] - BASE:SETTER[1] - BASE], SETTER[0], SETTER[1])
    at = {a for a, _, _ in ins}
    if CEIL_AT not in at or CEIL_AT + 6 not in at or any(CEIL_AT < a < CEIL_AT + 6 for a in at):
        raise SystemExit('ceiling site is not one whole instruction in the linear decode of 0x603d1620')
    inside = [(a, op, t) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
              if (op[0] in 'bjl' or op.startswith('call')) and CEIL_AT < int(t, 16) < CEIL_AT + 6]
    far = CL.refs(im, CEIL_AT + 1, CEIL_AT + 6, KH.sec(stock, 2)[2])
    if inside or far:
        raise SystemExit(f'references into the ceiling immediate: {inside[:3]} {far[:3]}')
    into = [a for a, op, args in ins if (op[0] == 'b' or op.startswith('jmp')) and hex(CEIL_AT) in args]
    return len(ins), [hex(a) for a in into]


def apply(spec, version='0.34a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'movie_bitrate' in spec:
        raise SystemExit('movie_bitrate already applied')
    check_stock(stock)
    tsha = hashlib.sha256(stock[TABLE - BASE:TABLE + ROWS * ROW - BASE]).hexdigest()[:16]
    bsha = hashlib.sha256(stock[BUF_TABLE - BASE:BUF_TABLE + BUF_LEN - BASE]).hexdigest()[:16]
    im = ST.img_of(spec, stock)
    if im[TABLE - BASE:BUF_TABLE + BUF_LEN - BASE] != stock[TABLE - BASE:BUF_TABLE + BUF_LEN - BASE] \
            or im[CEIL_AT - BASE:CEIL_AT + 9 - BASE] != stock[CEIL_AT - BASE:CEIL_AT + 9 - BASE]:
        raise SystemExit('another layer changed the tables or the ceiling instruction')
    for lo, hi in [(a, a + 4) for a in CELLS.values()] + [(CEIL_AT, CEIL_AT + 6)]:
        if overlaps(spec, lo, hi):
            raise SystemExit(f'{lo:#x}: overlaps edit {overlaps(spec, lo, hi)}')
    n_refs = table_refs(im, stock)
    n_ins, into = ceiling_scan(im, stock)
    for fps, a in sorted(CELLS.items(), reverse=True):
        spec['edits'].append(dict(kind='0x100', addr=hex(a), expect=struct.pack('<I', OLD_4K).hex(), new=struct.pack('<I', NEW_4K).hex(),
                                  source=SRC, why=f'movie_bitrate: 4K UHD {fps}p (table 0x60539b84 mode 1, column F) 100 M -> 150 M bit/s'))
    spec['edits'].append(dict(kind='0x100', addr=hex(CEIL_AT + 2), expect=struct.pack('<I', OLD_CEIL).hex(), new=struct.pack('<I', NEW_CEIL).hex(),
                              source=SRC, why='movie_bitrate: ulMaxBitrate 0x603d19db mov 105000000,d0 -> 157500000 (non-C4K, non-ALL-I FHD modes)'))
    spec['movie_bitrate'] = dict(built_by=SRC, version=version,
                                 cells={f'{k}p': hex(v) for k, v in sorted(CELLS.items(), reverse=True)}, old=OLD_4K, new=NEW_4K,
                                 ceiling=dict(site=hex(CEIL_AT), imm=hex(CEIL_AT + 2), old=OLD_CEIL, new=NEW_CEIL, branched_from=into,
                                              site_scan=f'{n_ins} instructions of {SETTER[0]:#x}'),
                                 table_sha16=tsha, buffer_table_sha16=bsha, table_refs=f'{n_refs} hits: the 2 readers + {len(PINS)} pinned coincidences')
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34a')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['movie_bitrate']))
