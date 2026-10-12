# Mission Control detail pages

`xenia live render` writes one page per cadence and one page per hit, plus `sitemap.xml`.

A cadence page is `site/cadences/<cadence_id>/index.html`. It shows the target, coordinates, frequency window, on-source seconds, the manifest command, any six-panel plot URL stored on a hit, and every hit with its verdict and the count of checks recorded. The five check names match the verdict function: `not_in_off`, `not_known_transmitter`, `drift_sane`, `session_census_clear`, and `review`. The manifest stores that count. It does not store a separate pass bit for each check, so the page does not invent one.

A hit page is `site/hits/<hit_id>.html`. It links back to the cadence page and the run manifest, and it repeats the command.

Sky-map dots are links inside the inline SVG. Each dot opens that cadence page. Gallery thumbnails open the hit page. The manifest link stays on the card. The same CSS tokens as the index are used. The pages do not require JavaScript.

`docs/experiments.md` is generated from every manifest under `runs/` by `xenia docs experiments`. `make experiments-check` fails when the file is stale, and `make docs` runs that check before the site build.

A 360 px browser was not opened in this session. The command block wraps, and the page shell stays within the viewport width used by the index.
