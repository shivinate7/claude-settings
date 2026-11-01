# A design picture is checked when the item is written

## The ruling

An item write whose picture the page would refuse, or would draw as a thin strip, is refused at write, with the page's own sentence. The owner never sees it (decision `questions-go-to-owner`, skill `waiting-page`, "Add a design").

- Guard rule `page-item-design` (`hooks/guard.py`, `page_design_hit`) judges an `ArtifactData` write of this repo's waiting page. It judges a `set` or `update` of an open item whose data carries `designs`, or an option with `design` (`question_form.design_writes`, the one home of "carries a picture"). A write with no picture never starts node.
- It runs `skills/waiting-page/check_designs.mjs --page <file> --item <json>` once per such write, through `_run_check_designs`, the one seam that starts node.
  - The checker loads the published page in headless Chromium with a stub database that holds only the item. It then asks the page's own code: `pictureProblem(item)` for the sentence, and the drawn height of each option card picture (`.opic .dfitwrap`, at 390 px wide) against the page's own `MIN_PIC`. No rule of the page is copied.
  - A missing mockup slug passes: the page warns in its frame, so the floor does not read it.
  - It prints `{"problem": string|null}` and exits 0 pass, 1 miss, 3 unknown. It caps itself at 20 s; the guard caps the run at 45 s, under the 60 s hook timeout.
- The file it loads is the one the last allowed publish recorded. `page_stale_hit` writes the absolute path of an allowed current publish to `<git common dir>/waiting-page-published` (`stale_pages.write_published`, beside `write_stamp`, both through `write_record`). A refused publish leaves the record.
- Miss: it denies. The reason is the page's sentence, then the fix: republish the design, then write the item again. It names no forbidden target.
- Unknown (no node, no Playwright or Chromium, no record, the recorded file gone, a run past its cap): it allows and logs one `noted` line under `page-item-design`. The rule fails open.
- Incident class: named incidents (rule `building-guard-needs-incident`), Nov 1 2026.
  - Waiting-page item 51 reached the owner with "The picture of option A shows nothing the focus names". Only the render caught it.
  - Home's item 43 drew each option picture as a strip a few px high: a wide multi-screen mockup scaled to card width. The page had no floor check at write.
  - Landed 2026-11-01.
- Cost:
  - Per gated item write: one node start and one Chromium start, 0.75 s wall measured here (1 sample; the lane brief measured about 2.4 s, 1 sample). One temp file, removed at once.
  - Per waiting-page publish allowed: one small file write.
  - A write with no picture, a read, and any other call: no cost beyond the `ArtifactData` read the guard already does.
  - No timer, no long-lived process, no new log beyond the one `noted` line on unknown.
- Known limit: an `update` is judged on the fields it carries. An update with `designs` but no `options` runs only what `pictureProblem` checks on that. A pair check or a floor on an option the update leaves out is not run.
- Known limit: the record holds the last allowed publish from this clone, not the live page. A publish from another machine, or by hand, moves the page without moving the record.
- Known limit: the floor is measured at 390 px wide, one viewport. A picture that is a strip at another width is not seen.
- Known limit: an unknown allows, so a machine with no Chromium never gets the check. CI runs the cases.

Kind: process
Home: rule:questions-go-to-owner
