# Mission Control copy

Section 4.4 of the Mission Control spec is the page wording, with one exception. The gallery heading stays "Latest hits, and the checks applied." The spec's gallery heading contains a banned word, so it is not used. That exception is decision D-019, Proposed.

The subtitle, hero, sky, floor, gallery hint, and footer use the spec sentences. The later-panel cards stay on "not started" until a non-demo manifest with experiment id EXP-010 or EXP-020 is in the runs directory. A live card then names that run, its outcome, and any pages_processed, fireball_count, or kp_max integer the manifest recorded.

Measured contrast, WCAG relative luminance, on 2026-10-13: `#eaf0fa` on `#070b14` is 17.19; `#8c9ab3` on `#070b14` is 6.92; `#8c9ab3` on `#0d1320` is 6.53. All are above 4.5. The phone layout uses one column below 620 px and a body minimum width of 320 px. A 360 px browser was not opened in this session.

`feed.json` is a JSON Feed 1.1 of survivor cards. Open Graph tags use the page subtitle. `og:image` is set when a gallery or hero PNG exists.
