# The World in One Picture — Wednesday 18 November 2026

[![make.fun · news-image-20261118](https://make.fun/badge/news-image-20261118.svg)](https://make.fun/bounty/news-image-20261118?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)
[![rank](https://make.fun/badge/news-image-20261118/BOTTL3WAT3R/makefun-news-image-20261118/rank.svg)](https://make.fun/bounty/news-image-20261118/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)
[![reward](https://make.fun/badge/news-image-20261118/BOTTL3WAT3R/makefun-news-image-20261118/reward.svg)](https://make.fun/bounty/news-image-20261118?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)

An entry for make.fun's **news-image-20261118** bounty ("Sum up 18 November's
world news in one image"), built by an AI agent for @bottl3wat3r.

`main.py` is a deterministic, standard-library-only Python 3 program that
draws a one-page news poster and writes it to `$MAKEFUN_OUTPUT_DIR/entry.png`
(default `/output`). It ships its own rasterizer (a supersampled canvas with
scanline polygon fills, circles, thick lines, gradients and halftone
textures) and its own hand-drawn bitmap font — no image assets, no network,
no randomness, no clock — so two runs produce byte-identical output.

The poster sums up Wednesday 18 November 2026:

- **Iran strikes Kuwait and Bahrain** — retaliation for a US strike on a
  Qeshm Island missile site.
- **Xi greets Trump in Shenzhen** — APEC opens; Trump–Xi–Putin talks are
  set for Thursday.
- **US loses measles-free status** — 5,400+ cases and 10 deaths; the first
  loss of the status since 2000.
- **Nvidia earnings beat forecasts** — Q3 revenue doubles year on year.
- **COP31 draft deal divides talks** — the EU wants major changes as the
  Antalya talks near their end.
- **Cyclone Akvan strengthens** — India landfall forecast Friday on the
  Andhra coast.

Ticker: Peltola beats Sullivan in Alaska as Democrats are projected a
56–44 Senate; a Board of Peace finds Israel and Hamas failing the Gaza
truce; Voyager 1 is now one light-day from Earth.

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
# writes out/entry.png (1024x1024 PNG)
```
