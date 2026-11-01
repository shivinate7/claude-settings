# A design picture is checked when the item is written

## The ruling

An item write whose picture the page would refuse, or would draw as a thin strip, is refused at write, with the page's own sentence. The owner never sees it (decision `questions-go-to-owner`, skill `waiting-page`, "Add a design").

- Guard rule `page-item-design` (`hooks/guard.py`, `page_design_hit`) judges an `ArtifactData` write of this repo's waiting page. It judges a `set`, or an `update` that carries both `options` and `designs`, when its data carries a picture: a `designs` list, or an option with `design` (`question_form.design_writes`, the one home of "carries a picture"). A write with no picture never starts node.
- It runs `skills/waiting-page/check_designs.mjs --page <file> --item <json>` once per judged item, through `_run_check_designs`, the one seam that starts node.
  - The checker loads the published page in headless Chromium at 390 px wide, with a stub database that holds only the item. It then asks the page's own code. `pictureProblem(item)` gives the sentence. The page's `MIN_PIC` gives the floor.
  - It measures every option card picture, ranked cards too: the `.opic .dfitwrap` of the card that holds the option's input, read with `getBoundingClientRect`.
  - The floor: a picture is a miss when the page drew it under `MIN_PIC` high and scaled it below 1. `MIN_PIC` in `page.html` is the page's width floor for a picture it shrinks. The checker reuses it as a height floor for shrunk pictures only. A small focus at natural size passes, because the page never shrank it. This is the item 43 shape.
  - A design the page does not hold passes: the page warns in its frame, so the floor does not read it.
  - An option with a design but no card on the page, or no picture box in its card, is unknown, never a pass.
  - It prints `{"problem": string|null}` and exits 0 pass, 1 miss, 3 unknown. It caps itself at 20 s.
- Batch budget: the pictured items of one call share one deadline, `PAGE_ITEM_DESIGN_BATCH_SECONDS` (45 s, under the 60 s hook timeout). One run is capped at 25 s and never outlasts what is left of the deadline. When the budget is spent, the rest of the items are allowed with one `noted` line.
- The file it loads is the one the last allowed publish stamped. `page_stale_hit` writes the absolute path of an allowed current publish to `<git common dir>/waiting-page-published` (`stale_pages.write_published`, beside `write_stamp`, both through `write_common_file`). A refused publish leaves the stamp.
- Miss: it denies. The reason is the page's sentence, then the fix: republish the design, then write the item again. It names no forbidden target.
- Unknown (no node, no Playwright or Chromium, no stamp, the stamped file gone, a run past its cap): it allows and logs one `noted` line under `page-item-design`. The rule fails open.
- Incident class: named incidents (rule `building-guard-needs-incident`), Nov 1 2026.
  - Waiting-page item 51 reached the owner with "The picture of option A shows nothing the focus names". Only the render caught it.
  - Home's item 43 drew each option picture as a strip a few px high: a wide multi-screen design scaled to card width. The page had no floor check at write.
  - Landed 2026-11-01.
- Cost:
  - Per judged item: one node start and one Chromium start, 0.75 s wall measured here (1 sample; the lane brief measured about 2.4 s, 1 sample). One temp file, removed at once.
  - Per call: at most 45 s of those runs, by the batch budget. A call of N pictured items starts N runs while the budget lasts.
  - Per waiting-page publish allowed: one small file write.
  - A write with no picture, a read, and any other call: no cost beyond the `ArtifactData` read the guard already does.
  - No timer, no long-lived process, no new log beyond the `noted` lines named above.
- Known limit, partial update: an `update` with only one of `options` and `designs` is allowed, with one `noted` line that says partial. The checker needs both, so it is not called.
- Known limit: the stamp holds the last allowed publish from this clone, not the live page. A publish from another machine, or by hand, moves the page without moving the stamp.
- Known limit: the floor is measured at 390 px wide, one viewport. A picture that is a strip at another width is not seen.
- Known limit: an unknown allows, so a machine with no Chromium never gets the check. CI runs the cases.

Kind: process
Home: rule:questions-go-to-owner
