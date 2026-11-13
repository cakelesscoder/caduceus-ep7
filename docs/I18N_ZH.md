# Simplified Chinese labels (issue #46)

Goal: when the camera's menu language is Simplified Chinese, Caduceus's own labels (editor pages, Extras sector guide
labels, the Colour Profile page label from #41) show in Chinese. Traditional Chinese is out of scope for now.

Status: **feasible; layer `patches/i18n_zh/` built and emulator-checked on a v0.32 (plugins=False) spec. Not
camera-tested.** Translations want a native speaker's review (marked `?` below).

## 1. Language setting and stock string lookup [V code]

- The menu language is **sid 3009** (key 0x85e1, MODE bank, RAM byte 0x62509d7c, 34 option values). Value **5 =
  Simplified Chinese**, 6 = Traditional, 1 = English.
- Loader `gui_load_language` 0x60eac6f2 reads it (facade +8, id 0xbc1 = 3009), then maps the value through two tables:
  0x611f0c5c `{u32 lang, u16 string res}` (5 -> 2, 6 -> 3, 1 -> 8) and 0x611f0d7c `{u32 lang, u16 1, u16 font res}`
  (font = string res + 34: 5 -> **36**). It loads font, strings and a third resource through facade +0x34 and stores the
  string resource's two header words in 0x61fc1530 (string pointer table) and 0x61fc15bc (text-style records).
- Stock lookup: `osd_string_get` 0x60d10bf2(id) = `(*(0x61fc1530 + 4*bank))[id]`, bank = byte 0x61fb2818
  (0x60d10c09). Only one language is loaded at a time; a string id draws in whatever language is loaded.
- Text styles (`gc_set_font` 0x60d0fce0) come from the per-language record table, so the font follows the language.

## 2. How our labels are drawn [V code]

- Every editor-side label we write is a **view label** `{u16 kind, -, u16 id, u16 style, u16 text[33]}` at view+44,
  kind 5, with the text **already UTF-16** at view+52 (our code widens ASCII byte by byte as it writes). The drawer
  renders the UTF-16 units through the language's font, exactly as it renders stock kind-4 strings.
- All of them pass through one place: the Colour view's **guide part word 0x6025aa98** (flash init word). Chain in
  v0.32: `xp_guide` (extras_pages) -> `ap_gd` -> `ex_guide` -> `ed_guide` -> stock 0x60decbfc. The Colour Profile page
  (#41, `sn_gd`) calls the same word on a fake view and copies the 74-B label, so it inherits whatever the chain does.
- So CJK needs no new draw path: put UTF-16 Chinese in view+52 and the stock renderer draws it, if the font has the glyph.
- Not on this path (stay English): menu rows built from kind-5 `char*` lists through the byte widener 0x60df2618
  (`Right Fn`, `INFO Custom`, `8-BIT LOG`, Firmware `Caduceus`, Lowest S/S), the mono-preset guide label (mono_presets
  writes the Profile view's MONO page label itself: `Film[INFO]`), and EXIF text.

## 3. Glyph coverage [V structural]

`tools/zh_glyphs.py` decodes font resource 36. A font resource holds fonts as a two-level code-point map:
`dir u32[256]` (high byte -> page pointer, 0 = none), `page {u16 w, u16 h, u32 glyph}[256]` (low byte; glyph = mode-9
stream, 0 = none). The dir pointers sit in the 32 B before the font header. Res 36 has:

| Dir | Glyphs | Height | Pages |
|---|---:|---:|---|
| +0x54580 | 636 | 37 px | 0x30 (、。), 0x4e..0x9e (CJK), 0xff |
| +0x54980 | 133 | 40 px | 0x00 (ASCII, Latin-1), 0xff (full-width) |

763 characters in all, 668 beyond ASCII. Every glyph record's w/h equals its stream header. The CJK set is a subset of
the characters in Chinese string table 2 (799 non-ASCII), which is shared with other bodies; the 168 without a glyph are
text this body never draws. Stock strings mix both fonts (string 2749 `色彩配置文件 1`), so the renderer falls back per
character and ASCII digits, `+`, `-`, `/`, `:` keep working beside CJK.

Missing glyphs that ruled out common terms: 展 (扩展), 附 (附加), 额 (额外), 晕 (光晕), 厂 (原厂), 琥珀, 渗.

    .venv/bin/python -I tools/zh_glyphs.py                 # dirs + full character list
    .venv/bin/python -I tools/zh_glyphs.py --check 颗粒 光晕  # OK / MISSING per argument

## 4. Translations

All Chinese below passes `--check`. "Whole" = the label must equal the English exactly; otherwise it's a token replaced
inside composed labels (`5 Shadow ` + `Yellow` -> `5 阴影 黄`). `?` = wants native review.

| English | 中文 | glyphs OK | Note |
|---|---|---|---|
| Saturation | 饱和度 | yes | |
| Saturation - All | 饱和度 - 全部 | yes | token All |
| Hue | 色相 | yes | |
| Light | 亮度 | yes | |
| Film | 胶片 | yes | not shown in v0.32 (Film page shows the look name) |
| Stock (whole) | 标准 | yes | empty Film slot; 原厂 has no 厂 ? |
| Custom (whole) | 自定义 | yes | |
| Extras | 效果 | yes | 附加 / 额外 / 扩展 have no glyph; same word as Effects ? |
| Extras: 1-N only (whole, N = 5, 9, 10, 11) | 效果: 仅 1-N | yes | |
| Extras: no All (whole) | 效果: 全部不可用 | yes | ? |
| Effects: 1-7 (whole) | 效果: 1-7 | yes | |
| Colour: 1-8 (whole) | 色彩: 1-8 | yes | |
| Split: COLOR 1-4 (whole) | 分离色调: COLOR 1-4 | yes | may be wide ? |
| Grain / Glow / Art / Halo: stills (whole) | 颗粒 / 柔光 / 艺术 / 光环: 仅照片 | yes | AP / movie slot |
| Grain | 颗粒 | yes | |
| Off / Low / Medium, Med / High | 关 / 低 / 中 / 高 | yes | `Grain High`, `Halo High` are phrases so `High` alone can mean highlights |
| Art | 艺术 | yes | |
| Star Light / Pin Hole / Blur | 星光 / 针孔 / 模糊 | yes | |
| Glow | 柔光 | yes | 光晕 has no 晕; 辉 missing ? |
| Clarity | 清晰度 | yes | |
| Clarity/Glow | 清晰/柔光 | yes | |
| WB | 白平衡 | yes | |
| Amber / Blue, Amber/Blue | 黄 / 蓝, 黄/蓝 | yes | 琥珀 missing ? |
| Green / Magenta, Green/Mag. | 绿 / 品红, 绿/品红 | yes | |
| Blacks | 暗部 | yes | ? (LR: 黑色色阶) |
| Whites | 亮部 | yes | ? (LR: 白色色阶); 高光 is taken by the split-tone Highlight fields |
| NR | 降噪 | yes | |
| Camera (NR / VigFix / Sharp default) | 默认 | yes | "the camera's own setting" |
| Std | 标准 | yes | |
| VigFix | 暗角校正 | yes | |
| Sharp | 锐化 | yes | |
| Halo | 光环 | yes | ? 光晕 has no glyph |
| Shadow (split tone) | 阴影 | yes | |
| High (split tone highlight) | 高光 | yes | |
| Yellow / Orange / Or-Red / Red | 黄 / 橙 / 橙红 / 红 | yes | |
| Magenta / Violet / Blue / Bl-Cyan | 品红 / 紫 / 蓝 / 蓝青 | yes | |
| Cyan / Gr-Cyan / Green / Yl-Green | 青 / 绿青 / 绿 / 黄绿 | yes | |

Look names stay as the user wrote them: on the Film page only whole entries apply. Mono preset names (Pan F 50, Acros,
...) and `Sepia Print` / `Selenium` / `Cyanotype` are on the mono path (§2) and stay English; 硒 and 晒 have no glyph.

Examples (host model `build.translate`, same rules as the camera code): `1 Grain High` -> `1 颗粒 高`,
`2 Clarity/Glow 0` -> `2 清晰/柔光 0`, `4 WB Green/Mag.` -> `4 白平衡 绿/品红`, `8 VigFix Camera` -> `8 暗角校正 默认`,
`7 High Yl-Green` -> `7 高光 黄绿`, `11 Halo Med` -> `11 光环 中`.

## 5. The layer (`patches/i18n_zh/`)

- `i18n_gd` takes the guide part word 0x6025aa98 and runs the chain it held first. Then, only if the label is kind 5
  **and** the loaded string 134 starts `固件` (0x56fa 0x4ef6, read the way 0x60d10bf2 does, null-checked), it rewrites
  view+52: whole entries first; else (not on the Film page) tokens left to right, at a word start (label start or after
  ` ` / `/`) and ending at end / ` ` / `/` / `:`, longest English first. Result <= 32 units, rest of the 33 zeroed.
  Otherwise the label is byte-for-byte what the chain wrote.
- **Data-driven:** `LABELS` in `build.py` is keyed by the English text. The build sorts it, packs
  `{u16 elen, u16 zlen, u16 flags, en[], zh[]}` records (1650 B for 60 entries), and refuses any Chinese character the
  font lacks. Adding a label = one dict line.
- Claim 0x607d4200..0x607d5000 (code 0x607d4210, 2112 B incl. the table; 16 B guards) in the dead `sdk api` handlers
  (sec 5, CODE_SPACE_SURVEY §2), past extras_pages' 0x607c9420..0x607c9c20. It is the largest run of that range with
  no abs32 / rel hit into it at all (0x607d41f9..0x607d50dd), so nothing needs pinning; reference scan as extras_pages
  (KH.scan). 0x607cb000.. was tried first and has hits. Requires the three `sdk` sub-command words already cut (extras_pages does it).
- Stores: own stack frame and the view's label text only. No absolute stores, no mul/div/setlb, no fb-prefixed forms.
- Checks (`verify.py`): Z, 17 emulator cases (Chinese tokens / whole / Film page; English table, kind 4 and a null
  table pointer leave the label untouched; d0 and d2/d3/a2/a3/sp kept); P, package decode == emulated image, restore
  == stock, only the claim and the guide word differ from the base.

### Integration

Built and checked against a scratchpad copy of v0.32 (plugins=False): the guide word chain it wrapped is xp_guide
0x607c97f8. In `patches/v032/build.py`, after extras_pages (and before or after lv_grid / fw_version; it touches neither):

    if extras:
        spec = _load('extras_pages', ...).apply(spec, version)
        spec = _load('i18n_zh', ROOT / 'patches/i18n_zh/build.py').apply(spec, version)

- It must come after every layer that re-points 0x6025aa98 (it wraps whatever holds the word at apply time and refuses
  stock). The plugins=True build has no extras_pages; i18n_zh then needs keyhook's sub-command cut first and its claim
  is outside keyhook's / the overlay's.
- If extras_pages adds new label text, add it to `LABELS` (the build fails on a missing glyph, not on a missing key).
- Camera test: set the menu language to 简体中文, open the Colour editor on each page and the SCP Colour Profile page;
  then back to English (labels must be exactly as before).

## Open

- Label widths: CJK glyphs are wider (about 30 px vs 15-20 for ASCII); the guide slot width isn't decoded. Longest:
  `分离色调: COLOR 1-4`.
- Menu rows on the byte-widener path and the mono guide label (§2) are not translated; a second hook would be needed
  (0x60df2618 for `char*` lists, mono_presets' own writer).
