# Card files without a half-press (design, not built)

> **Shelved (user, 2026-11-12): looks keep loading on the first half-press.** The brick/boot-path risk was not worth it. The design and the flag-byte proof below are kept for reference; nothing was built.

Goal: BUNDLES, LOOKS, MOVIE and AP load at power-on without a half-press. PLUGIN.BIN still loads only on the first
real half-press, so boot never runs card code. The half-press stays as the fallback. Issue #26.

Traced statically from generated/v032 (not emulated yet). Why we don't hook the card mount: [SPLIT_TONE_G1.md](SPLIT_TONE_G1.md) §3.

## Route: GUI_TASK present posts one synthetic event to HLS_EVENT

- **Send can't block.** `queue_send` 0x600514b6 passes the timeout to the kernel's message-buffer send (0x60036ede).
  A timeout of 0 polls: on a full queue it returns −50 at once and doesn't call the error reporter [V code].
- **Message.** 12 B `{u16 priority 0, event, param}` to the appevent queue id at 0x60040ce8, built as the stock sender
  at 0x60c7a7a4 builds it [V].
- **Event value.** Low half 0x100, with a class byte that is in none of the event tables
  (0x604d6168/6178/6260/6334/6410/6488) and outside 0xF0–0xF7. Both delivery paths (direct receive 0x602c7fb7,
  drain 0x602c8771) then reach hook 0x602c805f with no table side effects [V].
- **Tracker.** `trig_tracker` 0x602c818c reads only a0 and sets d0 first, so a check in front of it can use d0 [V].
- **Half-press during the load.** The load runs in HLS_EVENT, as it does today, and a half-press queues behind it.
  Only a press that lands during the boot load waits, and only for the rest of that load [I].

## Pieces (64 B hole 0x601de740 + 96 B hole 0x60210e90; #32 Sharpness dropped, so this space is free)

| Stub | Where | What |
|---|---|---|
| `au_post` | replaces the call at 0x60d0ed79 (GUI_TASK present) | Posts once, when all of these hold: own flag clear, `ap_boot` byte 0x6203c8bb == 0 (read only), BUNDLES state 0, all 9 sections loaded, HLS_EVENT id valid, a medium reports MOUNT OK. A failed send clears the flag, so the next present retries. Then calls stock |
| `au_hook` | the jump target at 0x602c805f | Synthetic event: skip the tracker, write 0x02000100 into the event slot, continue at 0x605b7407. Real events go to `sd_hook` unchanged |
| `au_end` | ed_trig's tail jump 0x605b73bc | Magic param: jump to the loop head 0x602c7f6d (no stock state touched, no fake half-press). On the first real half-press, if the plugin is still owed, run the plugin step once (`pl_ap`+5 with a2 = P from `ap_P`), then mark it done |
| `au_ap` | re-points ap_post's call at 0x601df730 | During the synthetic event: run `ap_load` only and mark the plugin as owed. Otherwise: `pl_ap`, as in v0.32 |

- **Post exactly once.** That keeps the budget at 5 load attempts per power-on (the auto-load plus `ap_boot`'s 4
  re-arms on half-press). Re-posting would use up the re-arms at boot.
- **Card inserted after boot.** It should work at no extra cost: the present hook keeps running and the mount check
  passes later [I].

## Flag byte (open)

- It must be cleared at boot, written only by GUI_TASK, and readable before P exists. That rules out P, and it rules
  out sharing 0x6203c8bb with `ap_boot`, because two tasks updating one byte can lose a write.
- 0x6203c8ba and 0x6203c8bb are taken in v0.32: the rotation latch and `ap_boot`.
- **Best candidate: the padding at 0x622ab792/3.** It follows a u16 that is only accessed with `movhu` and comes
  before u32s at 0x622ab794/798, the same pattern as the rotation pad. Still to rule out: the extents of the base
  pointers 0x622aa110 and 0x622a9990.
- Other candidates without references (scan of v0.32): 0x62246e00, 0x622930d0, 0x622e0738, 0x6266a24c, 0x626c39b4.
- **Unconfirmed:** whether the screen repaints after the card mounts, and which CPU GUI_TASK runs on. Use the
  uncached alias for the flag. If the screen doesn't repaint, the half-press still loads.

## Tests needed (risk HIGH: boot path)

- No card; a card without EP7MOD; corrupt files.
- An auto-load racing a half-press; power-on with an immediate shot.
- The byte-exact no-op path.
- Auto-load runs exactly once, and the existing loaders are unchanged.
- The plugin still loads once, on the first real half-press, whether that comes before or after the auto-load.
- One package anti-brick check.

## Progress notes (build session)

**1. Flag bytes 0x622ab792/3: proven unused [V, v0.32 image].**
- 0x622a9990: a u32 array, cleared with `memset(0x622a9990, 0, 1920)` at 0x605c2062. It ends at 0x622aa110.
- 0x622aa110: 480 records of 12 B, cleared with a 5760 B bzero at 0x605c2328. It ends at 0x622ab790.
- 0x622ab790: a u16, only `movhu` (stores 0x605c0474 and 0x605c06c3, load 0x605c257b). After it come u32s at 0x622ab794 and
  0x622ab798 (`mov` only), then a u32 array based at 0x622ab79c (indexed upward from its base).
- No abs32 reference touches 0x622ab792/3. The hits at 0x622ab273 and 0xa22ab1dd are mid-instruction false positives inside
  the 5760 B array. The bytes are in .bss (0x621caf00–0x62796888), so they are 0 at boot.
- So 0x622ab792/3 is the padding between a u16 and a u32, the same evidence as the rotation pad.
- Use: **0xa22ab792** = `au_post` flag, written only by GUI_TASK (0 = not posted, 1 = posted).
  **0xa22ab793** = plugin owed, written only by HLS_EVENT (0 = none, 1 = owed, 2 = done; agreed instead of a P word, which
  can be stale across power-ons). Both are accessed through the uncached alias.
- Trace for the stubs: the handler chain is sd_hook → ap_pre → mv_trig → ap_post → ed_trig → 0x602c8064. In `au_ap`
  (ap_post's `call ..,24`), S0 = sp+60, so the param is at (80,sp). At 0x605b73bc, sp = S0. 0x60d125af reads no argument
  registers.
