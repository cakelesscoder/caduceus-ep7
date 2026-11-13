"""E-M1 Mark II: "65:24" / "21:9" labels for the Super Control Panel aspect tile (v0.4c11).

The SCP tile draws widget record 0x611771d8 (6 parts: bitmaps 5871..5866 = 4:3, 3:2, 3:4, 1:1, 16:9, 17:9), 106x31,
fmt 14, colour key 7. The text is cut out of a filled box: index 22 = box, 23 / 24 = anti-aliasing, 0 = transparent
(the text and the margins). Box: cols 26..79 for one-digit labels, 20..85 for 17:9 / 16:9; rows 2..28.
  21:9  = '2' (3:2) + '1' (1:1) + ':' '9' (16:9), 16:9 spacing.
  65:24 = '6' ':' (16:9) + '2' (3:2) + '4' (3:4) + a '5' rendered from DejaVu Sans Condensed Bold at the stock digit band
          and the width of the stock '6', quantised to the label's own levels.
The box is rebuilt at the needed width from the 17:9 box (edge columns kept, fill column repeated), text centred.
"""
import numpy as np

IDS = {'4:3': 5871, '3:2': 5870, '3:4': 5869, '1:1': 5868, '16:9': 5867, '17:9': 5866}
BOX, AA_HI, AA_LO, HOLE = 22, 24, 23, 0          # 24 '@' = mostly box, 23 '+' = mostly hole
COVER = {BOX: 0.0, AA_HI: 1 / 3, AA_LO: 2 / 3, HOLE: 1.0}
ROW0, ROW1 = 3, 28                               # text rows lie inside the box rows 3..27


def glyphs(a):
    """Column segments of the cut-out text inside the box (rows 3..27)."""
    cols = np.nonzero((a != 0).any(0))[0]
    lo, hi = int(cols[0]), int(cols[-1])
    inner = a[ROW0:ROW1, lo + 1:hi]
    txt = (inner != BOX).any(0)
    # the box's own left/right AA columns are not text: keep only runs not touching the box edge
    segs, k = [], 0
    while k < len(txt):
        if txt[k]:
            s = k
            while k < len(txt) and txt[k]:
                k += 1
            segs.append((lo + 1 + s, lo + 1 + k))
        else:
            k += 1
    segs = [s for s in segs if s[0] > lo + 2 and s[1] < hi - 1]
    return lo, hi, segs


def render5(height_rows, width):
    from PIL import Image, ImageDraw, ImageFont
    SS = 8
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf', size=int(height_rows * SS / 0.729))
    l, t, r, b = f.getbbox('5')
    im = Image.new('L', (r - l + 4 * SS, b - t + 4 * SS), 0)
    ImageDraw.Draw(im).text((2 * SS - l, 2 * SS - t), '5', font=f, fill=255)
    im = im.crop(im.getbbox()).resize((width * SS, height_rows * SS), Image.LANCZOS).resize((width, height_rows), Image.BOX)
    return np.asarray(im, float) / 255


def quant(c):
    """coverage of 'hole' -> index"""
    out = np.full(c.shape, BOX, np.uint8)
    out[c > 1 / 6] = AA_HI
    out[c > 1 / 2] = AA_LO
    out[c > 5 / 6] = HOLE
    return out


def compose(o, bitmap, which):
    src = {k: bitmap(o, i).astype(np.uint8) for k, i in IDS.items()}
    lo169, hi169, g169 = glyphs(src['16:9'])         # 1 6 : 9
    _, _, g32 = glyphs(src['3:2'])                     # 3 : 2
    _, _, g34 = glyphs(src['3:4'])                     # 3 : 4
    _, _, g11 = glyphs(src['1:1'])                     # 1 : 1
    assert len(g169) == 4 and len(g32) == 3 and len(g34) == 3 and len(g11) == 3, (g169, g32, g34, g11)
    col = lambda k, s: src[k][ROW0:ROW1, s[0]:s[1]]
    gap_dd = g169[1][0] - g169[0][1]                   # digit-digit
    gap_dc = g169[2][0] - g169[1][1]                   # digit-colon
    gap_cd = g169[3][0] - g169[2][1]                   # colon-digit
    six, colon, nine = col('16:9', g169[1]), col('16:9', g169[2]), col('16:9', g169[3])
    two, four, one = col('3:2', g32[2]), col('3:4', g34[2]), col('1:1', g11[0])
    if which == '219':
        parts = [two, one, colon, nine]
        gaps = [gap_dd, gap_dc, gap_cd]
    else:
        ink = (six != BOX)
        rows = np.nonzero(ink.any(1))[0]
        r0, r1 = int(rows[0]), int(rows[-1]) + 1
        c5 = render5(r1 - r0, six.shape[1])
        five = np.full(six.shape, BOX, np.uint8)
        five[r0:r1] = quant(c5)
        parts = [six, five, colon, two, four]
        gaps = [gap_dd, gap_dc, gap_cd, gap_dd]
    text_w = sum(p.shape[1] for p in parts) + sum(gaps)
    ref = src['17:9']
    rlo, rhi, rg = glyphs(ref)
    margin_l = rg[0][0] - rlo                          # box edge -> first glyph
    margin_r = rhi - rg[-1][1] + 1
    box_w = margin_l + text_w + margin_r
    W, H = ref.shape[1], ref.shape[0]
    assert box_w <= W - 4, (which, box_w)
    x0 = (W - box_w) // 2
    out = np.zeros((H, W), np.uint8)
    edge = 4
    out[:, x0:x0 + edge] = ref[:, rlo:rlo + edge]
    out[:, x0 + box_w - edge:x0 + box_w] = ref[:, rhi + 1 - edge:rhi + 1]
    fill = ref[:, rlo + edge]                          # a pure-box column of 17:9
    assert set(fill[ROW0:ROW1].tolist()) == {BOX}, fill
    for x in range(x0 + edge, x0 + box_w - edge):
        out[:, x] = fill
    x = x0 + margin_l
    for k, p in enumerate(parts):
        out[ROW0:ROW1, x:x + p.shape[1]] = p
        x += p.shape[1] + (gaps[k] if k < len(gaps) else 0)
    return out
