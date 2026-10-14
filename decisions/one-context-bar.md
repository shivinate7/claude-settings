# One context bar, against the auto-compact window

## Ruling

Owner ruling, 2026-10-14. The token-weather forecast band is the one context bar. It measures
the fill against the auto-compact window when auto-compact is on and that window is smaller
than the model window. Otherwise it measures against the model window. The desktop-statusline
mod draws no context bar. All its other parts stay.

Both mods are third-party copies. Each `SOURCE.md` lists our local changes, so a later update
from the source can apply them again.

Kind: process
Home: mods/token-weather/SOURCE.md

## Why

Two mods drew a context bar in the same strip. The band used the model window (1M), so it showed
half the true fill when the owner set the auto-compact window to 500k. The status-line bar was
correct. The owner keeps the band for its chart of recent turns.

## Checks

- `mods/token-weather/token-weather.test.mjs` pins the window rule, the fallback when the
  auto-compact size is missing or 0, and the label.
- The status line has no test. Check it on screen after an install.

