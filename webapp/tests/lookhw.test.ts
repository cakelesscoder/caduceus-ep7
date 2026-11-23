// v0.34 base curve and colour matrix (docs/LOOK_FORMAT_V4.md): shared fields, BUNDLES.BIN slot bytes +53..+59, share codes.
import { afterEach, describe, expect, it } from 'vitest';
import { FW_LATEST, checkBundlesBin, checkLooksBin, decodeLooksBin, encodeBundlesBin, encodeLooksBin, placeLook, setFirmware, validateLook } from '../src/format';
import { blankLook, parseLook, PACK_SCHEMA, type Pack } from '../src/pack';
import { decodePackCode, encodePackCode } from '../src/sharecode';
import { CURVE_CHROMA, curveLut, lookMatrix } from '../src/lookhw';

const look = () => ({ ...blankLook('colour', 'HW Look'), curve: 'flat' as const, matrix: [32, -32, 16, -8, -24, 40] });

afterEach(() => setFirmware(FW_LATEST));

describe('look_hw fields', () => {
  it('parse keeps them, drops bad ones, old looks stay as they were', () => {
    const l = parseLook(JSON.parse(JSON.stringify(look())));
    expect(l.curve).toBe('flat');
    expect(l.matrix).toEqual([32, -32, 16, -8, -24, 40]);
    const b = parseLook({ ...blankLook(), curve: 'bogus', matrix: [0, 0, 0, 0, 0, 0] });
    expect(b.curve).toBeUndefined();
    expect(b.matrix).toBeUndefined();
    expect(validateLook({ ...look(), matrix: [65, 0, 0, 0, 0, 0] }).some((p) => p.field === 'matrix')).toBe(true);
  });

  it('COLOR slot gets +53 curve, +54..+59 matrix for v0.34; MONO slots and older firmware do not', () => {
    const b = placeLook(look(), 'COLOR1');
    expect(b[53]).toBe(6);
    expect([...b.subarray(54, 60)].map((v) => (v > 127 ? v - 256 : v))).toEqual([32, -32, 16, -8, -24, 40]);
    expect([...placeLook(look(), 'MONO1').subarray(53, 60)]).toEqual([0, 0, 0, 0, 0, 0, 0]);
    setFirmware(32);
    expect([...placeLook(look(), 'COLOR1').subarray(53, 60)]).toEqual([0, 0, 0, 0, 0, 0, 0]);
  });

  it('BUNDLES.BIN checks: v0.34 accepts, older firmware option rejects', () => {
    const pack: Pack = { schema: PACK_SCHEMA, name: 'p', looks: [look()], slots: { COLOR1: 0 } };
    const d = encodeBundlesBin(pack);
    expect(checkBundlesBin(d)).toEqual([]);
    setFirmware(32);
    expect(checkBundlesBin(d).some((m) => m.includes('v0.34'))).toBe(true);
  });

  it('LOOKS.BIN: v4 with the extension for v0.34, v3 byte for byte for older firmware or without the fields', () => {
    const pack: Pack = { schema: PACK_SCHEMA, name: 'p', looks: [look(), blankLook('mono', 'Mono')], slots: {} };
    const plain: Pack = { ...pack, looks: [{ ...blankLook('colour', 'HW Look') }, blankLook('mono', 'Mono')] };
    const v4 = encodeLooksBin(pack), v3 = encodeLooksBin(plain);
    expect([v4[4], v4.length, v3[4], v3.length]).toEqual([4, 64 + 80 * 2, 3, 64 + 64 * 2]);
    expect(checkLooksBin(v4)).toEqual([]);
    expect([...v4.subarray(192, 208)].map((v) => (v > 127 ? v - 256 : v))).toEqual([6, 32, -32, 16, -8, -24, 40, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    expect([...v4.subarray(208)]).toEqual(new Array(16).fill(0));
    const back = decodeLooksBin(v4);
    expect([back.looks[0].curve, back.looks[0].matrix]).toEqual(['flat', [32, -32, 16, -8, -24, 40]]);
    const bad = v4.slice(); bad[200] ^= 1;
    expect(checkLooksBin(bad)).toEqual(['extension crc']);
    setFirmware(32);
    expect(encodeLooksBin(pack)).toEqual(encodeLooksBin(plain));
  });

  it('pk1_ pack links keep the fields', async () => {
    const pack: Pack = { schema: PACK_SCHEMA, name: 'p', looks: [look()], slots: {} };
    const back = await decodePackCode(await encodePackCode(pack));
    expect(back.looks[0].curve).toBe('flat');
    expect(back.looks[0].matrix).toEqual([32, -32, 16, -8, -24, 40]);
  });

  it('preview model: rows sum to 1, standard curve is the identity', () => {
    for (const r of lookMatrix([32, -32, 16, -8, -24, 40])) expect(r.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    const lut = curveLut('standard');
    for (const i of [0, 256, 512, 900, 1024]) expect(lut[i]).toBeCloseTo(i / 1024, 2);
  });

  it('preview model: Flat and Log as measured on the camera (issue #57): highlights down, darks up, less chroma', () => {
    for (const c of ['flat', 'log'] as const) {
      const lut = curveLut(c);
      expect(lut[Math.round(0.92 * 1024)]).toBeLessThan(0.86);   // white patch (L* 91.6) comes down
      expect(lut[Math.round(0.47 * 1024)]).toBeLessThan(0.55);   // N5 stays near mid grey (old model 0.61 / 0.64)
      expect(lut[Math.round(0.2 * 1024)]).toBeGreaterThan(0.24);  // N3.5 is lifted
      expect(CURVE_CHROMA[c]).toBeLessThan(1);
    }
    expect(CURVE_CHROMA.pale).toBeUndefined();
  });
});

describe('named colour mixes (camera Extras "Mix", v0.34b)', () => {
  it('names a matrix that holds a named mix at a strength step, as the camera does', async () => {
    const { NAMED_MIXES, mixRow, namedMix } = await import('../src/pack');
    expect(namedMix(undefined)).toBeNull();
    expect(namedMix([32, -20, 5, 1, 0, 9])).toBeNull();
    for (const x of NAMED_MIXES) {
      expect(namedMix(mixRow(x.m, 10))).toEqual({ name: x.name, pct: 100 });
      expect(namedMix(mixRow(x.m, 6))).toEqual({ name: x.name, pct: 60 });
    }
    expect(mixRow([6, -10, 4, -6, -8, 4], 5)).toEqual([3, -5, 2, -3, -4, 2]);   // half away from zero
    expect(mixRow([6, -10, 4, -6, -8, 4], 1)).toEqual([1, -1, 0, -1, -1, 0]);
  });
});
