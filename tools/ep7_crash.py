#!/usr/bin/env python3
"""Decode EP7MOD/CRASH.BIN, the crash record of patches/crash_log (docs/CRASH_LOG.md). Offline, reads the file only.

  .venv/bin/python -I tools/ep7_crash.py /path/to/CRASH.BIN [--spec generated/crash_log/edits.json]

The file is three slots of SLOT bytes, one per CPU; a slot without a record is zeros. For each record it prints the cause,
CPU, task, PC / SP / PSW and registers, where the PC lies (nearest stock symbol from docs/atlas.json, our claims from
docs/CODE_SPACE_MAP.md, and with --spec the edit and our own symbol), the code addresses on the interrupted stack, the last
entries of the stock capture-history ring and the grain record by field. The layout constants below are the format:
patches/crash_log/build.py takes them from here.
"""
import argparse, json, re, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- the format (version 1), little-endian words
MAGIC_OK, MAGIC_BUSY = b'CRSH', b'BRSH'    # complete (written last) / busy: the stub started on this CPU and did not finish (= OK - 1)
VERSION = 1
NCPU = 3
O_MAGIC, O_SUM = 0x00, 0x04                # the sum of the u32 words of BODY..SLOT
O_LATER, O_L_NMI, O_L_SYS, O_L_PC = 0x08, 0x0c, 0x10, 0x14   # NMI entries on this CPU after the record: count, the last one's cause and PC
BODY = 0x18
O_INFO = 0x18                              # version | cpu << 8 | flags << 16
O_NMI, O_SYS = 0x1c, 0x20                  # (0x8900) NMIINTREG, (0x8044) SYSERRREG
O_TID, O_TCB = 0x24, 0x28                  # task id (TCB +16, s16) or -1; this CPU's current-TCB pointer
O_XCODE = 0x2c                             # (0x8ff000b0): the code another CPU's NMI or a system-down request left for CPU0
O_SECT = 0x30                              # (0xa272e420) sections loaded
O_STATE = 0x34                             # (0x622cbcc0): HLS_EVENT task id (low half), card-table handle (high half)
O_P, O_GPTR = 0x38, 0x3c                   # heap P or 0; the word at P+1000 or 0
O_ABORT, O_RECBLK = 0x40, 0x44             # (0xa26a0a94) REC abort word, (0xa26a1ca8) REC working block
O_WMODE = 0x48                             # (0xa2716034) bus-window mode, 3 words (one per CPU)
O_ADDEC = 0x54                             # this CPU's address-decode error registers: ADDR, R DATA, W DATA, STATUS
O_SIZE = 0x64                              # SLOT
O_BUILD = 0x68                             # build_tag(version) of the firmware that wrote the record
O_FRAMES, FRAMES_LEN = 0x6c, 0xc0          # the three NMI frames, as this CPU reads them
O_RING0, RING_LEN = 0x12c, 0x448           # CPU0's capture-history ring
O_RINGN = 0x574                            # the faulting CPU's ring when it isn't CPU0, else zeros
O_GRAIN, GRAIN_LEN = 0x9bc, 0x80           # our grain record, else zeros
O_STACK, STACK_LEN = 0xa3c, 0x200          # the interrupted stack from the frame's SP, else zeros
SLOT = 0xc3c
FILE_LEN = NCPU * SLOT
F_TID, F_PH, F_PM, F_GP, F_GM, F_RN, F_STK = 1, 2, 4, 8, 16, 32, 64
FLAGS = {F_TID: 'task read', F_PH: 'card-table handle in range', F_PM: "P holds 'EP7B'", F_GP: 'grain record pointer in its pool', F_GM: "grain record holds 'GDIA'",
         F_RN: 'own ring copied', F_STK: 'stack copied'}
assert O_BUILD + 4 == O_FRAMES and O_FRAMES + FRAMES_LEN == O_RING0 and O_RING0 + RING_LEN == O_RINGN and O_RINGN + RING_LEN == O_GRAIN
assert O_GRAIN + GRAIN_LEN == O_STACK and O_STACK + STACK_LEN == SLOT and SLOT % 4 == 0
assert int.from_bytes(MAGIC_OK, 'little') - int.from_bytes(MAGIC_BUSY, 'little') == 1

IMAGE = (0x60020020, 0x6191ffe0)
NMI_BITS = {1: 'EXT_NMI', 2: 'WATCHDOG_TIMEROVER', 4: 'FATAL_SYSTEM_ERROR'}
SYS_BITS = {4: 'MISSA', 8: 'UNIMP', 0x20: 'MEM', 0x200: 'UNIMPEX'}
XCODE = {1: 'CPU1 took an NMI', 4: 'CPU2 took an NMI', 3: 'Heap Destroy', 2: 'CPU1 ADDEC', 5: 'CPU2 ADDEC', 0x10: 'ARM', 0x30: 'SCPU', 0x20: 'COMMON', 0x50: 'WiFi', 0x60: 'BLE'}
LETTER = {'F': 'REC_FILE', 'I': 'REC_IMAGE', 'M': 'REC_MAIN', 'P': 'REC_PREPRO', 'S': 'REC_SOUND', 'V': 'REC_VIEW', 'E': 'REC_EXT', 'v': 'REC_PRE_V1', 'i': 'REC_PRE_I1',
          'p': 'IMG_PRECON', 'B': 'REC_PROGRESS', 'm': 'REC_MAIN_CPU2', 'z': 'REC_PRE_V1_CPU2', 'x': 'REC_VIEW_CPU2', '?': 'another task'}
STAGE_NOTE = {**{(c, 60): 'begin' for c in 'IiF'}, **{(c, 62): 'end' for c in 'IiF'}, **{(c, 91): 'begin' for c in 'vV'}, **{(c, 93): 'end' for c in 'vV'},
              ('M', 101): 'dispatch'}     # stages whose meaning is known (RE_CAPTURE section 1)
G_STAGE = {0: 'no capture since power-on', 1: 'flag hook only (capture set up)', 2: 'work-list word reached', 3: 'blend returned / development waited', 4: 'pass: checks',
           5: 'pass: tables', 6: 'pass: writing rows', 7: 'pass finished'}
G_GUARD = {0: 'none', 1: 'flag: key', 2: 'flag: key high bytes', 3: 'flag: not COLOR', 4: 'flag: no profile, or Grain off', 5: 'flag: kind 0x2001', 6: 'flag: kind 0x2006',
           7: 'flag: kind 0x1008', 8: 'flag: kind 0x1006', 0x10: 'job: marker', 0x11: 'job: mode', 0x12: 'job: type', 0x13: 'job: key', 0x14: 'job: profile / level',
           0x15: 'blend error', 0x16: 'no 0x1000 record', 0x17: 'wait for the development request failed', 0x20: 'format', 0x21: 'x offset', 0x22: 'y offset', 0x23: 'width < 4',
           0x24: 'width > 5461', 0x25: 'width not a multiple of 4', 0x26: 'stride < width', 0x27: 'rows 0', 0x28: 'rows > 8192', 0x29: 'buffer too small',
           0x2a: 'bus below 0xa0000000', 0x2b: 'direct range overrun', 0x2c: 'bus from 0xe0000000', 0x2d: "bus in the mapper's refused 0xc0000000..0xc3ffffff",
           0x31: 'mapper refused', 0x32: 'buffer end past 0xdfffffff', 0x33: 'level not 1..3', 0x43: 'plain route: other job flags', 0x44: 'plain route: no shading bit',
           0x4f: 'plain route built'}
G_CLASS = {0: 'direct', 1: 'window', 2: 'window after a mode change', 3: 'refused'}
TASKS = [dict(enumerate('''- BOOT_CPU0 DCFPROC_SUB WIFI_REMOCON_THROUGH TPC_CAMC ADJ ADJSLF AUD_WATCH_DOG BAS_MAIN BAS_RCU_SRV BCHK_BATT BCHK_MAIN CAM_MAIN DPS_MAIN FACE_FD FACE_MAIN
FILECLBK FILEFGND FIRMUP_SRV HPROC_PROC IMG_PRECON LENS_FIRM_UP LENS_FLASH PER_CCD_TEMP_MAIN PER_IN SYS_WDT PLAY_IMAGE PLAY_LOAD PLAY_MAIN PLAY_SOUND REC_FILE REC_IMAGE REC_MAIN
REC_PREPRO REC_SOUND SAICAS SC_TTIMER SERV_MAIN STB_CHARGE TPC TPC_DATA UI_OUT USRSTART5 USRSTART2 USRSTART4 USRSTART3 USRSTART_LOAD PROCLOG DISP_FRAME AUD_LATE_RISER BTSTK_TSKID
BTTIM_TSKID BTEVU_TSKID BTAPL_TSKID BT_CTRL BTIAP_TSKID OBEX OBEX_ACP DISPLAY EFFECT EFFECT_EXE HIGHLEVEL_MAIN CA_MAIN PER_ROTATE PTPCOM PTPASYNC TPC_LANG C3D EYEFI PER_EYE_SENSOR
C3D_EXE_BRIDGE SPC_TIMER ISEQ_MAIN MDET_CALC_FLAME_VECTOR AVM_FILE_IF HDMITOP_CEC AUTOMATIC_DIMMER REC_PRE_I1 MOVP_MAIN MOVP_VIDEO MOVP_AUDIO MOVE_MAIN MOVE_VIDEO MOVE_AUDIO ALBM_MAIN
PER_SLOPE SPC_MAIN REC_PRE_V1 FIRMUP_CLI AUD_COPY_DATA AUD_MAIN TOUCHPANEL UI_IN PER_PCONT USR_FAST_APP BC_MAIN EXP_MOVIE FCS_MOVIE LENS_ASKDATA LENS_COMMAND LENS_MAIN PC_EVENT
PC_HOSTCOM PC_PCMRECLINK PC_PTP PC_UAM PC_USB PC_USBSRV REC_VIEW STB_EXTERNAL STB_SEQ TAKE_EXPOSE TAKE_FOCUS TAKE_FUNC TAKE_FUNC_CP TAKE_MAIN FIRMUP_LED REC_EXT ZOOM ISEQ_CPU
TAKE_MOV TPC_CAMC_FILEADD TAKE_MAIN_CP MOVE_TRIM MOVE_FILEREAD MOVE_FILEWRITE PLAY_DECODE PLAY_LOAD_DRAW TAKE_PROXY REC_PROGRESS MOVE_TIMELAPSE ACC_MAIN PLAY_SOUND_BGM ISEQ_SUB
ISEQ_SWPA_PROC ISEQ_SWPA_POS ACC_SENS_MAIN ICTLOG DBG_OUT CPUCONN_CPU0 CPUCALL_CPU0 S_SHELL U_SHELL PWR_STANDBY'''.split())),
         {1: 'BOOT_CPU1', 2: 'C3D_EXE', 3: 'SCHEAP_DEBUG', 4: 'C3D_UPDATE', 5: 'WIFI_MNGR', 6: 'WIFI_REMOCON_PROXY', 7: 'WIFI_RELEASE_PUSH', 8: 'IMGPRO_MDL_WORK', 9: 'AVM_COM',
          10: 'AVM_P1_VIDEO', 11: 'AVM_P2_VIDEO', 12: 'AVM_P1_AUDIO', 13: 'AVM_P2_AUDIO', 14: 'AVM_FILE_MAIN', 15: 'CONTEST_CPU1', 16: 'FACE_BEAUTY', 17: 'WIFI_REMOCON_CGI',
          18: 'WIFI_REMOCON_THROUGH_IS', 19: 'FILEISCAM', 20: 'WIFI_ISC_BSDAPI_RX', 21: 'WIFI_ISC_BSDAPI_TX', 22: 'USRSTART_LOAD_1', 23: 'WIFI_STREAM', 24: 'WIFI_STREAM_SND',
          25: 'WIFI_STREAM_PIC', 26: 'FCS_IMG_2NDCPU_MAIN', 27: 'BLE_HDLR', 28: 'SYS_CA9_PWR_MNG', 29: 'WIFI_ISC_HTTPD_CGI_TX', 30: 'WIFI_ISC_HTTPD_CGI_RX',
          31: 'WIFI_ISC_HTTPD_CGI_MAIN', 32: 'PTPIP', 33: 'PTPIP_CDC', 34: 'PTPIP_EVC', 35: 'WIFI_MNGR_REC', 36: 'BLE_MAIN_HDLR', 37: 'WIFI_MNGR_REBOOT', 39: 'CPUCONN_CPU1',
          40: 'CPUCALL_CPU1', 41: 'S_SHELL_CPU1', 42: 'ASH_RECEIVE_SHELL', 43: 'U_SHELL_CPU1', 71: 'AVM_DMY_AUDIO', 72: 'DSP0', 73: 'DSP1',
          **{44 + i: f'AVMDL_THREAD{i:02d}' for i in range(21)}},
         dict(enumerate('''- BOOT_CPU2 MVR_MAIN MVR_MOVIE CONTEST_CPU2 MVR_IMG1 MVR_CALC MVR_IMG2 MVR_ENC EXP_MOVIE2 MVR_IMG_POST MVR_WIFI MVR_RECVIEW AUD_LEVEL_MONITOR MDET_CALC_MAIN
MDET_EVENT_SEND_CPU2 WB_MOV SDET REC_MAIN_CPU2 REC_PRE_V1_CPU2 REC_VIEW_CPU2 USRSTART_LOAD_2 MOVP_AUDIO_SUB MVR_EXEC CPUCONN_CPU2 CPUCALL_CPU2 S_SHELL_CPU2 U_SHELL_CPU2
AVM_IF_VIDEO'''.split()))]
for _t in TASKS:                           # by CPU: names of the static tasks (tables 0x613ff240, 0x6140033a, 0x61400b18)
    _t.pop(0, None)


def build_tag(version):
    """The word the firmware build `version` leaves at O_BUILD."""
    return zlib.crc32(str(version).encode())


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def checksum(slot):
    return sum(struct.unpack_from(f'<{(SLOT - BODY) // 4}I', slot, BODY)) & 0xffffffff


def state(slot):
    """-> None (no record), 'busy', 'ok' or 'damaged' (complete, but the sum differs)."""
    m = bytes(slot[:4])
    if m == MAGIC_BUSY:
        return 'busy'
    if m != MAGIC_OK:
        return None
    return 'ok' if checksum(slot) == u32(slot, O_SUM) else 'damaged'


def bits(v, names):
    out = [n for b, n in names.items() if v & b]
    rest = v & ~sum(names)
    return ' | '.join(out + ([f'{rest:#x}'] if rest else [])) or 'none'


def task_name(cpu, tid, hls):
    if tid == 0xffffffff:
        return 'not read (bad TCB pointer)'
    t = tid & 0xffff
    if t & 0x8000:
        return f'{t - 0x10000} (no task: boot, idle or interrupt)'
    if cpu == 0 and hls and t == hls:
        return f'{t} HLS_EVENT'
    name = TASKS[cpu].get(t & 0xfff) if cpu < NCPU else None
    num = f'{t}' if t < 0x1000 else f'{t:#x}'
    return f'{num} {name}' if name else f'{num} (not a static task of CPU{cpu})'


# ---------------------------------------------------------------- where an address lies
class Where:
    def __init__(self, atlas=None, cmap=None, spec=None):
        self.stock, self.ours, self.claims, self.edits, self.version, self._syms = [], [], [], [], None, None
        if atlas and Path(atlas).is_file():
            for e in json.loads(Path(atlas).read_text())['symbols']:
                if e['kind'] in ('func', 'code', 'site'):
                    self.stock.append((int(e['addr'], 16), e['name']))
            self.stock.sort()
        if cmap and Path(cmap).is_file():
            for line in Path(cmap).read_text().splitlines():
                cells = [c.strip() for c in line.strip().strip('|').split('|')]
                if not line.startswith('|') or len(cells) < 2:
                    continue
                first = cells[0].replace('*', '')
                owner = re.sub(r'[*`]', '', cells[2] if len(cells) > 2 else cells[1])[:90]
                rs = [[int(a, 16), int(b, 16)] for a, b in re.findall(r'0x([0-9a-f]{8})\s*[–-]\s*0x([0-9a-f]{8})', first)]
                m = re.search(r'claim to 0x([0-9a-f]{8})', first)
                if rs and m:
                    rs[0][1] = max(rs[0][1], int(m.group(1), 16))
                self.claims += [(lo, hi, owner) for lo, hi in rs if lo < hi and IMAGE[0] <= lo < IMAGE[1]]
        if spec and Path(spec).is_file():
            s = json.loads(Path(spec).read_text())
            self.version = s.get('crash_log', {}).get('version')
            for e in s['edits']:
                if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
                    self.edits.append((int(e['addr'], 16), len(e['new']) // 2, e.get('source') or '?'))
            for layer, v in s.items():
                for key, d in (v.items() if isinstance(v, dict) else ()):
                    if 'symbols' in key and isinstance(d, dict):
                        for n, a in d.items():
                            if isinstance(a, str) and a.startswith('0x') and n[:1].isalpha() and n[:1] != '_':
                                self.ours.append((int(a, 16), n))
            self.ours = sorted(set(self.ours))

    @staticmethod
    def _near(tab, a):
        lo, hi = 0, len(tab)
        while lo < hi:
            mid = (lo + hi) // 2
            if tab[mid][0] <= a:
                lo = mid + 1
            else:
                hi = mid
        return tab[lo - 1] if lo else None

    def describe(self, a):
        if not IMAGE[0] <= a < IMAGE[1]:
            if a >> 28 in (6, 0xa):
                return 'RAM, not the main image'
            return 'not a main-image address'
        out = []
        ed = [(lo, n, src) for lo, n, src in self.edits if lo <= a < lo + n]
        cl = sorted((hi - lo, lo, hi, own) for lo, hi, own in self.claims if lo <= a < hi)
        s = self._near(self.syms(), a)
        if s:
            out.append(f'{s[1]}+{a - s[0]:#x}' + (' (far: the function itself has no name here)' if a - s[0] > 0x1000 else ''))
        if ed:
            out.append(f'OURS: edit {ed[0][0]:#x} ({ed[0][2]})')
        if cl:
            out.append('in our claim ' + '; '.join(f'{lo:#x}-{hi:#x} {own}' for _, lo, hi, own in cl[:2]))
        if not ed and not cl:
            out.append('stock code' + ('' if self.edits else ' (by the claim map; give --spec to check against the build)'))
        return ', '.join(out)

    def syms(self):
        """The atlas symbols with the spec's own on top (the build's addresses win)."""
        if self._syms is None:
            self._syms = sorted({**dict(self.stock), **dict(self.ours)}.items())
        return self._syms


# ---------------------------------------------------------------- one record
def ring(r, last=40):
    tail, head = u16(r, 0) & 255, u16(r, 2) & 255
    n = (head - tail) & 255
    out = []
    for k in range(max(0, n - last), n):
        e = r[8 + 4 * ((tail + k) & 255):][:4]
        c = chr(e[0]) if 32 <= e[0] < 127 else '?'
        out.append((c, e[1], u16(e, 2)))
    over = (u16(r, 6) - u16(r, 4)) & 15
    return tail, head, n, out, over


def grain(g, flags):
    if not flags & F_GP:
        return ['  not copied: ' + ('no card table (P)' if not flags & F_PH else 'the pointer at P+1000 is not in the record pool (no capture with Grain yet, or a bad pointer)')]
    b = lambda o: g[o]
    out = [f"  magic {bytes(g[:4])!r}" + ('' if flags & F_GM else "  (NOT 'GDIA': the fields below are not ours)")]
    st, gd, cnt = b(5), b(4), u16(g, 8)
    out.append(f'  stage {st} ({G_STAGE.get(st, "?")})   guard {gd:#04x} ({G_GUARD.get(gd, "?")})   level {b(38)}')
    out.append(f'  rows done {u16(g, 14)} of {u16(g, 22)}   rows split at a window edge {b(61)}   reached: flag hook {cnt >> 8 & 15}, work-list word {cnt >> 4 & 15}, pass {cnt & 15}')
    out.append(f'  capture: COLOR{b(39)}  mode {b(60)}  kind {u16(g, 58):#06x}   job: flags {u32(g, 48):#010x}  type {u16(g, 52):#06x}  class {b(54)}  entries {b(55)}')
    out.append(f'  buffer: format {u16(g, 16):#06x}  width {u16(g, 20)}  stride {u16(g, 18)}  rows {u16(g, 22)}  x {u16(g, 24)}  y {u16(g, 26)}  active {u16(g, 10)} x {u16(g, 56)}  size {u32(g, 32)}')
    out.append(f'  bus {u32(g, 28):#010x}  first CPU address {u32(g, 40):#010x}  access: {G_CLASS.get(b(37) & 15, "?")}  window mode {b(36) & 15}  mode to restore {b(7)}  '
               f'route {("-", "blend", "output")[min(b(36) >> 4, 2)]}  pass CPU {b(37) >> 4}')
    out.append(f'  seed {u32(g, 44):#010x}  blend result {u16(g, 12)}  pending level {b(95)}  halation word {u16(g, 96):#06x}')
    out.append(f'  before the blend: buffer {u32(g, 68):#x} bus {u32(g, 64):#010x}; buffer {u32(g, 76):#x} bus {u32(g, 72):#010x}')
    out.append('  raw +80: ' + bytes(g[80:]).hex())
    if flags & F_GM:
        if st == 6:
            out.append(f'  => the record says the grain pass was writing rows: {u16(g, 14)} of {u16(g, 22)} done (updated once per lock)')
        elif st == 7:
            out.append('  => the grain pass of the last capture had finished')
        elif st in (4, 5):
            out.append('  => inside the grain pass, before the first row')
        elif st in (1, 2, 3):
            out.append('  => a capture had been set up; the grain pass had not started')
    return out


def record(slot, i, w, last=40):
    st = state(slot)
    out = []
    head = {'ok': 'complete, checksum ok', 'damaged': f'complete, but CHECKSUM MISMATCH (stored {u32(slot, O_SUM):#010x}, computed {checksum(slot):#010x}): damaged after the fault',
            'busy': 'INCOMPLETE: the stub started on this CPU and did not finish; fields may be missing'}[st]
    info = u32(slot, O_INFO)
    ver, cpu, flags = info & 255, info >> 8 & 255, info >> 16
    out.append(f'== slot {i}: {head}')
    if st == 'busy' and ver != VERSION:
        out.append('   (the header was not written yet; reading the slot as CPU%d)' % i)
        cpu, flags = i, 0
    elif ver != VERSION:
        out.append(f'   format version {ver}, this tool knows {VERSION}: not decoded')
        return out
    if cpu != i:
        out.append(f'   CPU field {cpu} differs from the slot number')
    nmi, sy = u32(slot, O_NMI), u32(slot, O_SYS)
    cause = bits(nmi, NMI_BITS) + (': ' + bits(sy, SYS_BITS) if nmi & 4 else '')
    out.append(f'cause     {cause}   (NMIINTREG {nmi:#010x}, SYSERRREG {sy:#010x})')
    hls = u32(slot, O_STATE) & 0xffff
    out.append(f'CPU       {cpu}')
    tag = u32(slot, O_BUILD)
    out.append(f'build     tag {tag:#010x}' + ('' if w.version is None else f' = the spec\'s build ({w.version})' if tag == build_tag(w.version) else
                                              f': NOT the spec\'s build ({w.version}); addresses of our code may differ'))
    out.append(f'task      {task_name(cpu, u32(slot, O_TID), hls)}   (TCB {u32(slot, O_TCB):#010x})')
    f = slot[O_FRAMES + 0x40 * min(cpu, 2):][:0x40]
    pc = u32(f, 12)
    out.append(f'PC        {pc:#010x}  {w.describe(pc)}')
    psw = u32(f, 8) & 0xffff
    out.append(f'SP        {u32(f, 4):#010x}   PSW {psw:#06x} ({"".join(c for c, b in zip("ZNCV", (1, 2, 4, 8)) if psw & b) or "-"}, IM {psw >> 8 & 7}, IE {psw >> 11 & 1})   bus monitor word {u32(f, 16):#010x}')
    out.append('registers ' + '  '.join(f'{n} {u32(f, 0x20 + 4 * k):#010x}' for k, n in enumerate(('d0', 'd1', 'd2', 'd3'))))
    out.append('          ' + '  '.join(f'{n} {u32(f, 0x30 + 4 * k):#010x}' for k, n in enumerate(('a0', 'a1', 'a2', 'a3'))))
    for k, n in enumerate(('a0', 'a1', 'a2', 'a3')):
        v = u32(f, 0x30 + 4 * k)
        if IMAGE[0] <= v < IMAGE[1]:
            out.append(f'          {n} -> {w.describe(v)}')
    lt = u32(slot, O_LATER)
    if lt:
        ln = u32(slot, O_L_NMI)
        out.append(f'later     {lt} more NMI entr{"y" if lt == 1 else "ies"} on this CPU before the record was saved; the last: {bits(ln, NMI_BITS)}'
                   + (': ' + bits(u32(slot, O_L_SYS), SYS_BITS) if ln & 4 else '') + f', PC {u32(slot, O_L_PC):#010x} {w.describe(u32(slot, O_L_PC))}')
    out.append(f'flags     {flags:#04x}: ' + (', '.join(n for b, n in FLAGS.items() if flags & b) or 'none'))
    ad = [u32(slot, O_ADDEC + 4 * k) for k in range(4)]
    xc = u32(slot, O_XCODE)
    out.append(f'context   sections loaded {u32(slot, O_SECT):#x}   REC abort word {u32(slot, O_ABORT):#x}   REC working block {u32(slot, O_RECBLK):#010x}   '
               f'window modes {[u32(slot, O_WMODE + 4 * k) for k in range(3)]}')
    out.append(f'          address-decode error: ADDR {ad[0]:#010x}  R DATA {ad[1]:#010x}  W DATA {ad[2]:#010x}  STATUS {ad[3]:#010x}   system-down code {xc:#x}'
               + (f' ({XCODE[xc]})' if xc in XCODE else ''))
    out.append(f'          card table: handle {u32(slot, O_STATE) >> 16:#06x}, P {u32(slot, O_P):#010x}, word at P+1000 {u32(slot, O_GPTR):#010x}; HLS_EVENT task id {hls}')
    for c in range(NCPU):
        if c != cpu:
            g = slot[O_FRAMES + 0x40 * c:][:0x40]
            out.append(f'CPU{c} frame as CPU{cpu} read it (its last interrupt or NMI; may be stale): PC {u32(g, 12):#010x} {w.describe(u32(g, 12))}, SP {u32(g, 4):#010x}, PSW {u32(g, 8) & 0xffff:#06x}')
    if flags & F_STK:
        s = slot[O_STACK:O_STACK + STACK_LEN]
        out.append(f'stack     {STACK_LEN} B from SP; +0 is the NMI stub\'s return slot, +4 the PC. Words that are main-image addresses (return addresses, mostly):')
        n = 0
        for k in range(2, STACK_LEN // 4):
            v = u32(s, 4 * k)
            if IMAGE[0] <= v < IMAGE[1] and n < 24:
                out.append(f'          +{4 * k:#05x}  {v:#010x}  {w.describe(v)}')
                n += 1
        if not n:
            out.append('          none')
    else:
        out.append('stack     not copied (SP unaligned or outside RAM)')
    for name, off, have in (('CPU0', O_RING0, True), (f'CPU{cpu}', O_RINGN, bool(flags & F_RN))):
        if not have:
            continue
        tail, hd, n, ents, over = ring(slot[off:off + RING_LEN], last)
        out.append(f'history   {name} capture ring: {n} entries (tail {tail}, head {hd}){", overflow ring " + str(over) if over else ""}; the last {len(ents)}, oldest first (task letter, stage, command):')
        for k in range(0, len(ents), 4):
            out.append('          ' + '   '.join(f'{c} {s:3d} {cmd:#06x} {(LETTER.get(c, "?") + (" " + STAGE_NOTE[c, s] if (c, s) in STAGE_NOTE else "")):<20}' for c, s, cmd in ents[k:k + 4]).rstrip())
    out.append('grain record (128 B at the word of P+1000):')
    out += grain(slot[O_GRAIN:O_GRAIN + GRAIN_LEN], flags)
    return out


def decode(data, w, last=40):
    out = []
    if len(data) != FILE_LEN:
        out.append(f'size {len(data)} B, expected {FILE_LEN}: reading what is there')
    n = 0
    for i in range(NCPU):
        s = data[i * SLOT:(i + 1) * SLOT]
        if len(s) == SLOT and state(s):
            n += 1
            out += record(s, i, w, last) + ['']
    out.insert(0, f'{len(data)} B, {n} record{"" if n == 1 else "s"}' + ('' if n else ': no crash record in this file'))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file', type=Path)
    ap.add_argument('--spec', type=Path, help='edits.json of the build that was on the camera: names our code exactly')
    ap.add_argument('--atlas', type=Path, default=ROOT / 'docs/atlas.json')
    ap.add_argument('--map', type=Path, default=ROOT / 'docs/CODE_SPACE_MAP.md')
    ap.add_argument('--last', type=int, default=40, help='history-ring entries to print')
    a = ap.parse_args()
    spec = a.spec or next((p for p in (ROOT / 'generated/crash_log/edits.json',) if p.is_file()), None)
    print('\n'.join(decode(a.file.read_bytes(), Where(a.atlas, a.map, spec), a.last)))


if __name__ == '__main__':
    main()
