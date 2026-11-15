# Japanese labels

Goal: when the camera's menu language is 日本語, every label Caduceus writes on the editor's guide line (Saturation / Hue
/ Light pages, the Film page prefix, the Extras Effects and Colour & Light pages including split tone and look_hw_ui's
Curve / Mix / Strength, the AP / Movie "stills only" labels, the Colour Profile page label) shows in Japanese.

Status: **shipped in v0.34a (layer `patches/i18n_ja/`), camera-tested by the owner on 2026-11-16.** The wording
wants a native speaker's review, as issue #46 did for Chinese.

## 1. Language and font [V tables, V content]

- Japanese is **sid 3009 value 0** -> string resource **17** -> font resource **51** (RE_RESOURCES §2.3).
- The check is the one i18n_zh uses, on the loaded string table rather than the setting: string 134 of the table
  `(0x61fc1530)[(0x61fb2818)]` starts **L"バー"** (0x30d0 0x30fc, `バージョン`). No other of the 34 tables has those two
  units at 134; Vietnamese (res 21), which copies 2549 Japanese strings and has a Latin font, has `Firmware` there, so it
  stays English.
- Font res 51: 551 glyphs (kana and kanji, 35 px, pages 0x30, 0x4e–0x9e, 0xff) plus a 133-glyph Latin font (ASCII,
  Latin-1). The renderer falls back per character, so digits, `+ - : / % * .` and Latin film names draw beside kana.

    .venv/bin/python -I tools/zh_glyphs.py --font 51 --strings 17 --check 彩度 色相   # OK / MISSING per argument

## 2. How it works

Same path and rules as i18n_zh (I18N_ZH.md §2, §5): every label is a kind-5 view label with UTF-16 text at view+52, and all
of them pass through the guide part word 0x6025aa98. `ja_gd` takes that word (it held look_hw_ui's `lu_guide`) and runs
the chain first: lu_guide -> i18n_gd -> xp_guide -> ap_gd -> ex_guide -> ed_guide -> stock. look_hw_ui writes English
for any language but Chinese, so its labels go through the one Japanese table too; nothing in look_hw_ui changed.

- Whole entries first (the label equals the English), then tokens left to right at word starts, longest English first,
  ending at end / ` ` / `/` / `:`.
- **Film page:** whole entries, plus tokens marked "Film prefix" at the label start only, so `Film: Velvia*` ->
  `フィルム: Velvia*` and the look name stays as written (i18n_zh leaves the Film page's prefix in English).
- Section-7 gate first, as i18n_zh (section 7 not loaded -> the stock guide part).
- Code space: two sec-5 claims in the dead `sdk api` handlers (CODE_SPACE_MAP "i18n_ja"): code + whole table
  0x607e1b10 (1356 B), token table 0x607ccf72 (1740 B, 18 B left in its run).
- Adding a label = one line in `LABELS` (build.py); the build refuses a character font 51 lacks.

## 3. Glyph substitutions

Missing from font 51, with what is used instead:

| Wanted | Missing | Used | Note |
|---|---|---|---|
| 色相 (Hue) | 相 | 色合い | the camera's own word ("色合いを変える") |
| 明瞭度 (Clarity) | 瞭 | 鮮明度 | |
| 周辺減光補正 (VigFix) | 辺 | 減光補正 | シェーディング補正 (the camera's term) is too wide for the guide line |
| 寒色 (cool) | 寒 | クール | `Cool sep.` -> クール分離 |
| 全て不可 (no All) | 不 | 全色なし | |
| 赤橙 (Or-Red) | 橙 | 赤オレンジ | the camera writes Orange as オレンジ |

Width choices (the guide slot width is not decoded; I18N_ZH "Open"): widest English label about 233 px, widest Chinese
272 px, widest Japanese **284 px** (`2 WB グリーン/マゼンタ`; next `6 ノイズ低減 本体設定` 277 px). To stay near the Chinese
width: split tone uses the camera's 明部 / 暗部 (its "Hi. & Sh." words) instead of ハイライト / シャドウ, Halo is ハロー not
ハレーション, Sharp is シャープ not シャープネス, NR is ノイズ低減 (the camera's 高感度ノイズ低減) not ノイズリダクション, Mix is 配色
(as the Chinese) not ミックス. `Off` stays `Off`, as the camera's own Japanese UI writes it.

## 4. Translations (83 entries; review wanted)

"whole" = the label must equal the English; "token" = replaced inside composed labels (`7 High ` + `Yl-Green` ->
`7 明部色 黄緑`). Film names (Portra 400, Velvia, ...) and look names stay Latin.

| English | 日本語 | Kind |
|---|---|---|
| Stock | 標準 | whole |
| Custom | カスタム | whole |
| Extras: 1-5 only | 詳細設定: 1-5のみ | whole |
| Extras: 1-9 only | 詳細設定: 1-9のみ | whole |
| Extras: 1-10 only | 詳細設定: 1-10のみ | whole |
| Extras: 1-11 only | 詳細設定: 1-11のみ | whole |
| Extras: no All | 詳細設定: 全色なし | whole |
| Effects: 1-7 | 効果: 1-7 | whole |
| Colour: 1-8 | カラー: 1-8 | whole |
| Colour: 1-11 | カラー: 1-11 | whole |
| Split: COLOR 1-4 | 調色: COLOR 1-4 | whole |
| Curve: COLOR 1-4 | 階調: COLOR 1-4 | whole |
| Mix: COLOR 1-4 | 配色: COLOR 1-4 | whole |
| Grain: stills | 粒状: 静止画のみ | whole |
| Glow: stills | グロー: 静止画のみ | whole |
| Art: stills | アート: 静止画のみ | whole |
| Halo: stills | ハロー: 静止画のみ | whole |
| Saturation | 彩度 | token |
| Hue | 色合い | token |
| Light | 明度 | token |
| All | 全色 | token |
| Film | フィルム | token, Film prefix |
| Extras | 詳細設定 | token |
| Grain | 粒状 | token |
| Low | 弱 | token |
| Medium | 中 | token |
| Med | 中 | token |
| Grain High | 粒状 強 | token |
| Halo High | ハロー 強 | token |
| Art | アート | token |
| Star Light | スターライト | token |
| Pin Hole | ピンホール | token |
| Blur | ぼかし | token |
| Glow | グロー | token |
| Clarity | 鮮明度 | token |
| Clarity/Glow | 鮮明度/グロー | token |
| Amber | アンバー | token |
| Amber/Blue | アンバー/ブルー | token |
| Green/Mag. | グリーン/マゼンタ | token |
| WB Blue | WB ブルー | token |
| WB Green | WB グリーン | token |
| WB Amber/Blue | WB アンバー/ブルー | token |
| WB Green/Mag. | WB グリーン/マゼンタ | token |
| Blacks | 黒レベル | token |
| Whites | 白レベル | token |
| NR | ノイズ低減 | token |
| Camera | 本体設定 | token |
| Std | 標準 | token |
| VigFix | 減光補正 | token |
| Sharp | シャープ | token |
| Halo | ハロー | token |
| Shadow | 暗部 | token |
| High | 明部 | token |
| 5 Shadow | 5 暗部色 | token |
| 6 Shadow | 6 暗部強度 | token |
| 7 High | 7 明部色 | token |
| 8 High | 8 明部強度 | token |
| Yellow | 黄 | token |
| Orange | オレンジ | token |
| Or-Red | 赤オレンジ | token |
| Red | 赤 | token |
| Magenta | マゼンタ | token |
| Violet | 紫 | token |
| Blue | 青 | token |
| Bl-Cyan | 青シアン | token |
| Cyan | シアン | token |
| Gr-Cyan | 緑シアン | token |
| Green | 緑 | token |
| Yl-Green | 黄緑 | token |
| Curve | 階調 | token |
| Mix | 配色 | token |
| Strength | 配色強度 | token |
| Standard | 標準 | token |
| Auto | オート | token |
| Pale | ペール | token |
| Curve Light | 階調 ライト | token |
| Pop | ポップ | token |
| Flat | フラット | token |
| From look | ルックのまま | token |
| Warm film | 暖色フィルム | token |
| Cool sep. | クール分離 | token |
| Muted | 穏やか | token |
| Punchy | 鮮やか | token |

Examples (host model `build.translate`, same rules as the camera code): `1 Grain High` -> `1 粒状 強`,
`2 Clarity/Glow 0` -> `2 鮮明度/グロー 0`, `1 WB Amber/Blue` -> `1 WB アンバー/ブルー`, `7 VigFix Camera` -> `7 減光補正 本体設定`,
`5 Shadow Or-Red` -> `5 暗部色 赤オレンジ`, `9 Curve Light` -> `9 階調 ライト`, `10 Mix From look` -> `10 配色 ルックのまま`,
`11 Strength 70%` -> `11 配色強度 70%`, `Film: Portra 400` -> `フィルム: Portra 400`.

Not on this path (stay English, as for Chinese): byte-widened menu rows (`Right Fn`, `INFO Custom`, `8-BIT LOG`,
Firmware `Caduceus`, Lowest S/S), the mono-preset label (`Film[INFO]`), EXIF text.

## 5. Build and checks

    .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out <spec> --version 0.34a ... \
        --extra look_hw_ui=patches/look_hw_ui/build.py --extra movie_quality=... --extra looks_v4=... \
        --extra i18n_ja=patches/i18n_ja/build.py
    .venv/bin/python -I patches/i18n_ja/verify.py <spec without i18n_ja> <spec> [package dir] [--v034 releases/v0.34/edits.json]

verify: Z (chain labels through the real ja_gd, lu_guide and i18n_gd in ja / zh / en, Film page, kind 4, no table),
L (look_hw_ui's own labels through the real lu_guide in ja / zh / en), G (section gate), P (package = stock + edits,
restore = stock, only this layer's bytes differ).

Camera test: set the menu language to 日本語, open the Colour editor on each page (Saturation, Hue, Light, Film, both
Extras pages incl. 9–11) and the SCP Colour Profile page, then a Movie / AP slot; then 简体中文 and English (labels as
before).
