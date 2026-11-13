# New atlas entries from docs/PLUGINS.md §9 (resident plugin key hook, E-P7 1.1 stock main + v0.32 keyhook layer). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
p = 'ui'
SRC = 'docs/PLUGINS.md §9'

# ---- stock: the CA key path around the hook ----
E(0x60ce011a, 'ca_key_generic_kmap_call', 'site', p, 'V', 'call 0x60cc9a05,[d2],4 (7 B)', 'First call after the 6-word record copy. Fixed registers there: a0 = sp+28, a1 = a2+24, d0 = (24,sp), d1 = 0; a3 = CA module, a2 = event record. No branch into +1..+7. v0.32 keyhook: jmp kh + 2 nop', SRC)
E(0x60cc9a05, 'ca_event_map', 'func', p, 'V', 'call entry [d2],4; reads the caller\'s (4,sp) = event -> d0', 'Pure: reads only the stack and image tables; ends retf (MDR). Result goes to btn_dispatch', SRC)
E(0x60ceb5b6, 'ca_select_mode', 'func', p, 'V', 'call entry [d2,d3,a2,a3],68; d0 action, a0 CA module, a1 event record', 'Class-1 action handler (stock popup + dials), CANEXEC 0x60cce3dc inside; entered from ca_key_generic for class 1. Action 50 = SELECT_MODE_MULTI_ASPECT', SRC)
E(0x60cf30b5, 'ca_handler_calls', 'site', p, 'V', 'calls (a2): a0 = (CA+164), a1 = event record', 'The handler return value is ignored (the matcher returns a3 = matched)', SRC)
E(0x60ce05ab, 'ca_key_release', 'func', p, 'V', 'calls entry, frame 48', 'One of the Fn release (0x0100002f) handlers; release never reaches ca_key_generic 0x60ce0108', SRC)
E(0x60a9a918, 'sdk_subcmd_api_word', 'data', p, 'V', '{name*, fn} word: "api" -> 0x607b4b25', 'v0.32 keyhook: -> kh_ret0. Also 0x60a9a920 starttimer (0x607dab9f), 0x60a9a928 stoptimer (0x607dac2e)', SRC)

# ---- v0.32 keyhook layer (our code, sec 5, claim 0x607b6420-0x607b8420) ----
E(0x607b6430, 'kh_ret0', 'func', p, 'V', 'clr d0; rets', 'sdk sub-command stub (entered by calls (a1) at 0x607adda1)', SRC)
E(0x607b6433, 'kh', 'func', p, 'V', 'jmp target from 0x60ce011a, on ca_key_generic\'s frame', 'kh_chk -> 1: ret [d2,a2,a3],40; else rebuild registers, call 0x60cc9a05, jmp 0x60ce0121', SRC)
E(0x607b6454, 'kh_chk', 'func', p, 'V', 'call entry [d2,d3,a2,a3],24 -> d0 1 handled', 'ap_P, P+852 EP7K, hook word B+24 inside B\'s cached code bytes -> calls hook(d0 event, d1 B, a0 CA, a1 record)', SRC)
E(0x607b6497, 'ka_sel', 'func', p, 'V', 'calls entry: d0 action 41..67, a0 CA, a1 record', 'movm [d2,d3,a2,a3] + add -52 -> jmp 0x60ceb5b6; other d0 -> -1', SRC)
E(0x607b64ad, 'ka_get', 'func', p, 'V', 'calls entry: d0 key, d1 index -> d0', 'prop_get 0x6005e971 with a0 = 0 and its 4 B slot', SRC)
E(0x607b64c0, 'kh_api', 'table', p, 'V', 'u16 1, u16 6, fw_text, prop_get, text_set, ka_sel, ka_get, features (bit 0 key hook)', 'Plugin API v1.1; pl_chk passes it to init (mov at 0x601e1ace)', SRC)

# ---- docs/PLUGINS.md §12 (Fn cycle v4: stage mark + exit-and-replay) ----
SRC12 = 'docs/PLUGINS.md §12'
E(0x60ce2d84, 'ca_multi_function_press', 'func', p, 'V', 'class-2 action 18 EVF_FN (Multi Function) handler', 'Request 174, CA state 0x590d (Fn held). The popup opens on the release', SRC12)
E(0x60ce2da0, 'ca_multi_function_release', 'func', p, 'V', 'state 0x590d handler for Fn release 0x0100002f', 'Sub-function action = 0x60cc8929 (sid 437 -> table 0x60f38d8c: 6 -> 49 colour/mono profile, 3 -> 50 aspect); 49 -> call 0x60ceb5b6 -> state 0x5800', SRC12)
E(0x60f38d8c, 'multi_function_actions', 'table', p, 'V', '9 x {u32 sub-function, u32 action}', '1->48, 3->50, 5->42, 6->49, 2->23, 8->43, 7->44, 9->88, 10->30', SRC12)
E(0x60f4d230, 'select_action_state', 'table', p, 'V', '25 x {u32 action, u32 CA state}', 'Read by 0x60ceb5b6; 49 and 50 -> 0x5800', SRC12)
E(0x60cebd3d, 'sel_fn_same_mode_close', 'site', p, 'V', '0x60cebc89 jump-table case 18', 'Multi Function key in its own popup: request 158, ddc = key, no dd8 (close, no replay)', SRC12)
E(0x60cebce9, 'sel_other_key_exit', 'site', p, 'V', '0x60cebc89 jump-table case 26', '0x60cd2330(key), request 158, ddc = key, dd8 = key when its function != the open mode: exit and replay', SRC12)
E(0x60ceb952, 'sel_exit', 'func', p, 'V', 'select state exit', 'Reads and clears 0x61fb0dd8; Fn (in list 0x60f39e08, a press) -> 0x60cebd8b -> 0x60cebdeb: record+176 = key, +184 = 1 (re-posted key event)', SRC12)
E(0x61fb0dd8, 'sel_replay_key', 'data', p, 'V', 'u32 key to replay after the select state exits (+4 0x61fb0ddc last key)', 'Written by the select-state key handlers and keyhook ka_rep', SRC12)
E(0x6203bcb2, 'kh_fn_stage', 'data', p, 'V', 'u8 Fn stage byte (.bss pad)', 'bits 0-1 site + 1, bits 2-3 plugin decision (0 not called, 1 stock, 2 handled), bits 4-7 Fn presses mod 16; diag readout K', SRC12)
