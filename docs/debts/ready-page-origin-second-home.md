# Ready-page origin read is a second home for the origin read

- **What.** `ready_page_read` tells "the checkout's own repo" from "another repo" with its own github.com-only origin pattern. A checkout's origin may be the cloud proxy form (`http://local_proxy@127.0.0.1:PORT/git/OWNER/NAME`), a GHE host or a mirror. If it marks its own repo's pull request ready, it is taken as another repo. It then clones github.com over https. The clone may fail or time out, and the ready mark is refused unknown. Unmeasured in a proxy-origin session.
- **Where.** `READY_PAGE_ORIGIN` and `ready_page_read` in `hooks/guard_merge.py`. `origin_slug` in `hooks/git_reads.py` already reads the proxy form.
- **Decision.** `records-index-at-merge` (only the merge tool rebuilds the records page, before the branch goes ready); `building-one-home-per-capability`.
- **Retire.** Read the origin with `origin_slug`, and add a case with a proxy-form origin that marks its own repo's pull request ready and passes. `hooks/test_guard.py`
