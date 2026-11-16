# One Control Panel for every Caduceus body

Caduceus started from one idea: **one look format, one set of share codes and one Control Panel for every camera.**
A look made on an E-P7 should open on an OM-3, an OM-5 or any later port, and a code posted in a forum should work
for everyone who reads it. Each body that builds its own look editor, pack format or code splits the community:
looks stop moving between cameras, and the same editor, preview and encoder get written again for each body.

This page explains how the panel in this repo is laid out, and how a port adds its camera to it.
The rules for ports are in [`AGENTS.md`](../AGENTS.md). The formats are in
[`webapp/README.md`](../webapp/README.md) (pack file, share codes) and [`LOOK_FORMAT_V4.md`](LOOK_FORMAT_V4.md)
(E-P7 card record).

Live panel: <https://cakelesscoder.github.io/caduceus-ep7/>

## The model in one picture

```
            shared (one copy, here)                         per camera (one entry + one module each)
 ┌───────────────────────────────────────────────┐      ┌─────────────────────────────────────────────┐
 │ Look / Pack     src/pack.ts                    │      │ Profile   src/cameras.ts   (what to offer)  │
 │ Share codes     src/sharecode.ts  (1…8, pk1_)  │ ───▶ │ Export    src/targets/<cam>.ts (card files) │
 │ Editor UI       src/main.ts                    │      │ Import    same module (card file → Look)    │
 │ Preview         src/preview.ts, tone.ts        │      │ Vendored  src/<cam>.ts (port's own encoder, │
 │ Library         src/data/library.json          │      │           copied unchanged, source line)    │
 └───────────────────────────────────────────────┘      └─────────────────────────────────────────────┘
```

The **look is the shared truth**. A camera never changes what a field means. It only changes:

1. which controls the editor shows, and their ranges (the profile), and
2. how a look becomes that camera's card files, and back (the export target).

If your body can do less than the look holds (a smaller hue range, no mono), the export clamps or leaves it out and
says so. The look keeps the wider value until the user moves that control, so it still exports in full to a body
that can use it.

## Files

| Path | Shared or per camera | What it does |
|---|---|---|
| `src/pack.ts` | Shared | The `Look` and `Pack` types (`caduceus-pack/1`), the value names, parsing and defaults. **New look fields start here, by issue or PR.** |
| `src/sharecode.ts` | Shared | Look codes (versions `1`–`8`) and pack links (`pk1_`). Old codes decode forever; a new layout gets a new version symbol. |
| `src/format.ts` | E-P7 | E-P7 `LOOKS.BIN` / `BUNDLES.BIN` encoders and checks (byte-exact with `tools/`). |
| `src/cameras.ts` | Per camera | One `CameraProfile` per body: ranges (`hl`, `sat`, `wb`) and flags (`mono`, `tints`, `halo`, `lookHw`, …). The editor reads only these. |
| `src/targets/types.ts` | Shared | The `Target` interface: `id`, `label`, `status`, `note`, `supports(look)`, `export(pack)`. |
| `src/targets/index.ts` | Shared | The list of targets in the camera selector. Add yours here. |
| `src/targets/ep7.ts` | Per camera | E-P7 export. The smallest example. |
| `src/targets/om3.ts` | Per camera | OM-3 export and import: glue between the shared look and the vendored OM-3 code. The full example. |
| `src/targets/recipe.ts` | Generic | A Markdown recipe card per look, for any camera. |
| `src/om3.ts`, `src/om3names.ts`, `src/om3films.ts` | Vendored | Copied unchanged from `androidfanman/caduceus-om3`, with a source line at the top, so they can be resynced. |
| `src/main.ts` | Shared | The editor and dialogs. Camera differences should come from `cam()` flags, not `CAM === '<id>'` checks (the few OM-3 checks left are debt, not a pattern). |
| `src/preview.ts`, `src/tone.ts` | Shared | Approximate preview. A camera can pass a translated look to it (see `om3PreviewLook` in `main.ts`). |
| `tests/` | Both | Shared tests (encoder, share codes) and per-target tests (`om3-target.test.ts`, `targets.test.ts`). |

## Adding a camera

A port sends one PR touching only these places. No firmware, patches or build tools come into this repo: those stay
in the port's own repo.

1. **Profile.** Add your id to `Cam` and an entry to `CAMERAS` in `src/cameras.ts`. If your body needs a control the
   flags can't express, add a flag (with the E-P7 and OM-3 values) rather than a `CAM === '<id>'` check.
2. **Vendored encoder (optional).** If your repo already has a TypeScript encoder for your card file, copy it to
   `src/<cam>.ts` **unchanged**, with a first line naming the source repo, file and version. Resyncing then means
   copying the file again.
3. **Export target.** Write `src/targets/<cam>.ts` implementing `Target`:
   - `export(pack)` returns your card files (`{ name: 'YOURDIR/LOOKS.BIN', data }`). Clamp to your ranges here.
   - `supports(look)` returns `true` or a short reason the look can't go to your body.
   - Report what was clamped or left out (see `Placed.changed` / `dropped` in `targets/om3.ts`), so users know.
   - If your card file can be read back, add an import that turns it into shared `Look`s.
   - `note` names the firmware version the files are for. Add a firmware picker if your format changed between
     versions (`OM3_FWS` in `targets/om3.ts`).
4. **List it** in `src/targets/index.ts`. Use `status: 'soon'` with a `doc` link until a camera has run the files.
5. **Tests.** At least: the export of the built-in library doesn't throw, the files match your firmware's own
   tool byte for byte on a few looks, and a look round-trips through your import if you have one.
6. **Credit.** Add your project to `NOTICE` and to [`BODIES.md`](BODIES.md).

Run `cd webapp && npm ci && npm test && npm run build` before opening the PR.

## New features that need new look fields

Ports will add features the shared look can't describe yet: a new film setting, a tone control, an effect. That's
expected, and it's how the format should grow. The aim is that every new field is added **once, here**, so it
means the same thing on every body and older panels and firmware ignore it safely.

### 1. Propose it here first

Open an issue on caduceus-ep7 titled `Look field: <name>` with:

- **What it does on the camera**, in plain words, and on which firmware version.
- **Values**: type, range and step (for example, an integer from −7 to 7, or a list of names), and the **neutral
  value** that means "no change". The neutral value is what old looks and other bodies read it as.
- **Body-specific or general.** Could another body do it, even roughly? Say so if you know.
- **Where it should travel**: pack links only, or look codes too (see 3).

Keep the setting in your target's own data until it's agreed (step 5). Small, obvious fields can go straight in as
a PR that follows the rules below. The issue is for anything whose meaning could be argued about.

### 2. Name and define it in `src/pack.ts`

- Use a **plain, camera-neutral name** for what the setting does (`tone.blacks`, `split`, `curve`), not the menu
  label of one body. If two bodies have the same idea at different ranges, it's **one field** with the wider range;
  each target clamps.
- Make it **optional**, with neutral = missing. A look without the field must behave exactly as before.
- Never change the meaning or range of an existing field. If the meaning changes, add a new field and translate
  the old one in the parser (as `grainFromName` does for the old grain names).
- Group related values into one object (`tone: {…}`, `split: {…}`) rather than many top-level keys.
- **Look settings and profile settings are different things.** Grain, NR and Sharp are the user's own settings for
  each profile, not part of a look (`ProfileSettings` in `pack.ts`). If your feature is a camera setting the user
  picks, not part of the look's character, it belongs there. Don't let a look overwrite it.

### 3. Decide how it travels

| Carrier | How to add a field | Older apps |
|---|---|---|
| Pack file / `pk1_` link | Optional JSON key on the look or pack | Ignore it. **Note:** `parseLook` drops unknown keys today, so a pack opened and saved in an older app loses the field. |
| Look code | Needs a new version symbol in `sharecode.ts` | Show "made by a newer app" |

**Look codes are almost out of version symbols:** `1`–`8` are in use and only `9` is left. So:

- New fields go into **pack links only** by default. That needs no code change beyond `pack.ts`.
- Only fields that matter for a look's character on most bodies should be in look codes. Don't add a symbol per
  field. Symbol `9` is reserved for one **extensible** layout (the v8 fields plus a list of tagged extension
  fields, where each tag is a field id with its own radix). After that, new fields add a tag, not a version. That
  design gets its own issue before anyone uses `9`.
- Old codes must keep decoding with the same meaning, forever. Add a test that pins an old code.

### 4. Wire it through the panel

- **Editor**: add a `CameraProfile` flag (`src/cameras.ts`), set to `false` for bodies that can't do it, and show
  the control only when `cam().<flag>` is true. Don't use `CAM === '<id>'`.
- **Every target** decides what to do with the field: write it, clamp it, or leave it out and **say so** in the
  export report (`changed` / `dropped`). Leaving it out on a body that lacks it is normal. Failing silently isn't.
- **Preview**: approximate it if you can. If not, say "not shown in the preview" next to the control.
- **Recipe card** (`targets/recipe.ts`): list it in plain words, so bodies without it can still follow the recipe.
- **Library** (`bundles/library_v3.json`): only add values once a camera has run the field.

### 5. Until it's agreed: keep it in your target

A setting that only your firmware understands can live in your target's own data (the vendored bank in
`src/<cam>.ts`, as `targets/om3.ts` does for OM-3-only settings), shown only on your profile. It must **not**
reach a pack file or share code under a made-up name. A field that only one panel understands is exactly how
codes stop working everywhere. Once it's agreed, move it into `pack.ts` and translate in your target.

### 6. Tests for a new field

- A look without the field parses, exports and codes exactly as before (byte-identical card files).
- The field round-trips through the pack file and `pk1_` (and the look code, if it's in one).
- Each target either writes it (byte-exact against the port's own tool) or reports it as left out.
- Old share codes in `tests/sharecode.test.ts` still decode to the same looks.

## What a port shouldn't do

- Ship its own look editor, pack format or share-code scheme. A local preview or debug page in your repo is fine;
  the page users make and share looks with should be this one.
- Reuse a field with a different meaning ("hue +1 means something else on my body"). Translate in the export target.
- Change `sharecode.ts` or `pack.ts` in its own fork and keep the change there. Send it here so every body gets it.
- Add look fields under made-up names in pack files or codes before they're agreed (see "New features that need
  new look fields").

## Links from your repo

Point your README's "make looks" link at the live panel, and tell users to pick your body in the camera selector.
Firmware, install guide, releases and bug reports stay in
your repo; the panel's About dialog and [`BODIES.md`](BODIES.md) send people there.

## Review and hosting

Open the PR here and mention @cakelesscoder. The maintainer can't test your body, so review covers the shared
format and the panel, not your firmware: the export is trusted to match your firmware's own tools, which your tests
show. Once merged, the export is hosted at the live panel and credited in `NOTICE`.
