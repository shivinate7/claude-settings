# A routed receiver that ends with no done report is silent

**What.** A page answer routed to another session closes its item at once and keeps `lane` and `lastAnswer`. If the receiver dies with no done report, no check names it. `stalled_items` and `wait_lines` skip closed rows. A dead lane's unconfirmed act now looks answered and filed, and the owner never sees it. Claude hits this in normal work, since each busy-lane relay takes this path.

**Where.** `stalled_items` in `skills/roadmap/build.py` and `wait_lines` in `skills/waiting-page/stale_pages.py`: both skip an item with `status` `closed`.

**Decision.** relayed-grant-read-from-page (a relayed act counts only from the owner's saved answer; its gaps hold the routed-answer behaviour). Ruling own-748-b-rule-4 (owner 13:20 CST Nov 13, page item 748 b: a closed routed answer keeps a counted grant route), step answered-leaves-page.

**Retire.** A routed closed item whose receiver has ended with no done report shows as a stalled row on its home step. The roadmap build exits 1 on it until the session confirms or re-routes the act. A case in `skills/roadmap/test_build.py` shows it: a closed item with `lane`, `home` and `lastAnswer`, and no live session or open pull for the lane.
