# 3D browser dummy

A learning copy of the Cockpit page in three.js. It is not a product. Owner rulings: page item 130
pick a (browser 3D: three.js and glTF) and item 277 pick a (2026-11-06 12:43 CST: a separate test copy at a new
artifact URL; the live Cockpit is never touched).

- Published at https://claude.ai/artifact/Hf8FFxqMsfw9ds6Pni7Vdd, from `page.html`.
- `page.html`: one file. three.js 0.186.0 from cdnjs, its OrbitControls from jsdelivr. Static data, no runtime capabilities.
- `sample-data.json`: 20 items and 24 roadmap steps, trimmed from the roadmap branch's `waiting/` export.
- `check.mjs`: the Playwright check at 390 and 1440 width, light and dark, forced colours, the lost state and no WebGL.
  Run `verdict node docs/plans/3d-browser-dummy/check.mjs`.
- Design: `docs/design/3d-browser-dummy.html` and its notes. Open owner questions: page items 291 (layout),
  292 (phone panel) and 293 (differences from the Cockpit). The page uses the default pick for each.
