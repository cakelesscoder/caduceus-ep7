# New atlas entries from docs/FILM_DOWN_CRASH.md (issue #48 investigation, v0.32a). Same structure as atlas_data.py:
# E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: mono_profile_view 0x60e26ab0, guide_label 0x60decbfc, profile_view_parts 0x61fc27d0, GUI_TASK 0x60dd5067.
SRC = 'docs/FILM_DOWN_CRASH.md'
u = 'ui'

E(0x60e27289, 'profile_view_color_page', 'func', u, 'V', 'Profile view page 1 writer for COLOR; frame [d2,d3,a2,a3],44; (8,sp) = view, d2 = view+4',
  'Guide label at view+186 when (404,view) == 1, else view+260. Skips the label when 0x60e231e0 and 0x60e230e0 both answer non-zero; '
  'ALL (0x61fc3800 / 0x61fc3804) -> id 2756 else 2755, written at 0x60e2757d (scp_name hook from v0.32). Then call 0x60e27950,[d2,d3,a2,a3],40 '
  'and, on 1, view+4+330..332 = 2, 1, 1. Only branch into the hooked bytes 0x60e2757d..88 is the bra at 0x60e27567 (to 0x60e2757d)', SRC)
E(0x60decbfc, 'guide_label_fake_view', 'note', u, 'V', 'view+128 (= (12,sp)+88) == 1: facade path',
  'With a zeroed view and +128 = 1 the stock part reads only the facade (GetValue 111, the sector-id table 0x61fc27e8.. '
  '(12 u32 per COLOR mode at 0x61fc27e8 / 2818 / 2848 / 2878), GetDefault) and globals; it writes view+43, +44..+51 (label kind/id/style) '
  'and view+118..+132. Emulated on the v0.32a image through the whole layer chain (i18n_gd .. ed_guide): no view pointer is read', SRC)
