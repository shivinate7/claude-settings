# Branch cleanup: the Mac delete list

Owner ask, 2026-11-02 10:41 CST: "Clean up branches" (fb-1041-3). Lane branch-cleanup.

The cloud proxy refuses a ref delete, so a session on the owner's Mac runs this list under the standing grant for acts the cloud refuses (`.claude/CLAUDE.md`, Standing grants).

## What is on the list

- **On main by patch** (113): the tip is an ancestor of main, or `git cherry` prints no `+`, or one synthetic commit of the branch's net change is on main (decision `a-branch-is-redundant-by-patch-not-by-ancestry`, a branch is redundant by patch).
- **Archived first** (23): batch branches whose PR closed without a merge, and lane branches with no open PR and no commit since 2026-10-30. Each tip is on origin under the `archive/` name in its row, checked by sha (rule `shared-trees-archive-then-delete`).

Kept: `main`; branches with open PRs; branches a live lane names (`other-checkout-cd-gap` and its five related branches); `merge-lock/main`, the merge tool's lock; `roadmap`, `c138-roadmap-precommit` and `worktree-agent-a14b2fddf62c05643`, which share no history with main.

Each delete carries a lease on the tip read on 2026-11-02. git skips a branch that moved since, and names it in the output.

## The command

Paste in Terminal on the Mac:

```bash
cd ~/Developer/claude-settings
gh auth switch -u shivinate7
git push origin \
  --force-with-lease=refs/heads/archive/batch-31:99bc35acedc680f66263f0f8ef08d6202e7e4e80 :refs/heads/archive/batch-31 \
  --force-with-lease=refs/heads/archive/batch-34:e44b224088238854de167a4475c57437e4708204 :refs/heads/archive/batch-34 \
  --force-with-lease=refs/heads/archive/batch-37:c0d60ba1e5cd6c7b5b7246928416d8b4fcea9de3 :refs/heads/archive/batch-37 \
  --force-with-lease=refs/heads/archive/batch-37-b:68807aec145b2d2a88dc1a463b6c0cd6a0455cc4 :refs/heads/archive/batch-37-b \
  --force-with-lease=refs/heads/archive/batch-44-r2:0ecf0264433c4ba67e12824db73b05c6ad559ec9 :refs/heads/archive/batch-44-r2 \
  --force-with-lease=refs/heads/archive/batch-59-first-build:6b4200e053a2297faa670b08f821b11ad52798a6 :refs/heads/archive/batch-59-first-build \
  --force-with-lease=refs/heads/archive/batch-60-first-build:47368af80b79d12d31fa9b930898f16b3fa1ac49 :refs/heads/archive/batch-60-first-build \
  --force-with-lease=refs/heads/archive/claude/held-ci-spend:233de80c94c2fd3dfd80d9fb215377b03c62fb01 :refs/heads/archive/claude/held-ci-spend \
  --force-with-lease=refs/heads/archive/merge-lock/c53-probe-base:e66aaa3d461932c28365647753550d3c4280a6af :refs/heads/archive/merge-lock/c53-probe-base \
  --force-with-lease=refs/heads/audit-prose-trees-merge:d24155b58afc54492bb2779aaf82a23ccda7207f :refs/heads/audit-prose-trees-merge \
  --force-with-lease=refs/heads/batch-20:221ca5f88b31222ee0a2dcebd54a4fd32bf913a7 :refs/heads/batch-20 \
  --force-with-lease=refs/heads/batch-22:66071ed30f7b777cc97c25f0d872cef982fde2e6 :refs/heads/batch-22 \
  --force-with-lease=refs/heads/batch-22b:b6936417460416f8fd379fcf252f3d4935b098ee :refs/heads/batch-22b \
  --force-with-lease=refs/heads/batch-37:68807aec145b2d2a88dc1a463b6c0cd6a0455cc4 :refs/heads/batch-37 \
  --force-with-lease=refs/heads/batch-38:41b963a069e09f5fa0f44a350deb13cfd5270202 :refs/heads/batch-38 \
  --force-with-lease=refs/heads/batch-39:49b7034de097b8d5da79fd1db86033a60863307a :refs/heads/batch-39 \
  --force-with-lease=refs/heads/batch-40:92141e754afbcee646b1490ebcd6244b7780def0 :refs/heads/batch-40 \
  --force-with-lease=refs/heads/batch-40-r2:5aea7cc5b70ea3b65010ea03c2bf0f498c46fe87 :refs/heads/batch-40-r2 \
  --force-with-lease=refs/heads/batch-40-r3:73ab3f1bedaa49c276c7b427c8998254d5ce0399 :refs/heads/batch-40-r3 \
  --force-with-lease=refs/heads/batch-41:d05c88334a7fe0ac90c36d7638a84064f42e8229 :refs/heads/batch-41 \
  --force-with-lease=refs/heads/batch-41-r2:b6afa10ef1d1f25dea1e7d08ff04eef37f0d041f :refs/heads/batch-41-r2 \
  --force-with-lease=refs/heads/batch-44:6fa57a034cb1a46bf040c02b4ca95d3fd4781760 :refs/heads/batch-44 \
  --force-with-lease=refs/heads/batch-54:418c0cbae1883d8fbb37decac40b880a44e5bfbe :refs/heads/batch-54 \
  --force-with-lease=refs/heads/batch-61:0eb88169d4bb1b08d274d4a39c270c6138cd09f6 :refs/heads/batch-61 \
  --force-with-lease=refs/heads/batch-63c:22d59757e3bd721f55dbaf82736d953010cd47a7 :refs/heads/batch-63c \
  --force-with-lease=refs/heads/batch-63e:160e1d284c6ceb6512b5d194c5b5f3b7c24d1020 :refs/heads/batch-63e \
  --force-with-lease=refs/heads/batch-63f:99553386ac7129a37a29078b7491d1bc0dba6639 :refs/heads/batch-63f \
  --force-with-lease=refs/heads/batch-64d:441585d963f13c276116b66131f15c143e9212e7 :refs/heads/batch-64d \
  --force-with-lease=refs/heads/batch-oct19e:d44d69c6443de75b2df2ddbfbc7995cb3819a33c :refs/heads/batch-oct19e \
  --force-with-lease=refs/heads/batch-oct27d:ebbd4826a8f2574283b9bea57b96ac760068cddb :refs/heads/batch-oct27d \
  --force-with-lease=refs/heads/batch-oct27j:4fb7210ae4f2388fc4840f8df6dc51a3c60d5a2c :refs/heads/batch-oct27j \
  --force-with-lease=refs/heads/batch-oct27m:73c54cfdd6e110ea54145b2676fbdab8655fb763 :refs/heads/batch-oct27m \
  --force-with-lease=refs/heads/batch-oct27n:93a2252227385c9843e0f60abb763361850f9efc :refs/heads/batch-oct27n \
  --force-with-lease=refs/heads/batch-oct27q:03255e5f594131617c67261a2261721491b29101 :refs/heads/batch-oct27q \
  --force-with-lease=refs/heads/batch-oct27v:27c5cad9aa786abf91f675742644aae535853672 :refs/heads/batch-oct27v \
  --force-with-lease=refs/heads/batch-oct27x:41c821fcceca6f8ed0ba9250e821e89c34376af1 :refs/heads/batch-oct27x \
  --force-with-lease=refs/heads/batch-oct27y:2bba1651651b5ae6c243aecb83a94f6117ebf6a7 :refs/heads/batch-oct27y \
  --force-with-lease=refs/heads/batch-oct27z:c563b73bacd2cb11ebd38f367d7cc7d909f56c93 :refs/heads/batch-oct27z \
  --force-with-lease=refs/heads/batch-oct28b:b2a90e838c60aace8f9d15d3e7520653670d22b2 :refs/heads/batch-oct28b \
  --force-with-lease=refs/heads/batch-runner-merges:e4cef792260335117132f611e5fc500e61aeb411 :refs/heads/batch-runner-merges \
  --force-with-lease=refs/heads/c204-scroll-width-tests:41b02aca4190b8439bc89e5d2773efac59f888a2 :refs/heads/c204-scroll-width-tests \
  --force-with-lease=refs/heads/c204-scroll-width-tests-r2:0580e9b44c736caf67a27c2a659a43ad140696df :refs/heads/c204-scroll-width-tests-r2 \
  --force-with-lease=refs/heads/claude/project-thread-3sv5at:5eb3a8ecd4681b95c9fae5322680abfa4cd6eaa9 :refs/heads/claude/project-thread-3sv5at \
  --force-with-lease=refs/heads/claude/project-thread-ld0jcg:1fb3c0e25a01d39ad67a68244b2319aad1ed8fc5 :refs/heads/claude/project-thread-ld0jcg \
  --force-with-lease=refs/heads/claude/project-thread-rqwx3m:d8030c661160c16547e33411dfe75de5d64f7c72 :refs/heads/claude/project-thread-rqwx3m \
  --force-with-lease=refs/heads/claude/project-thread-x5hnku:0b9925ff4b120af1a5f8560fe65265bafbb3e07b :refs/heads/claude/project-thread-x5hnku \
  --force-with-lease=refs/heads/cloud-main-source:f2a0e074510d64df3bd242012117090d16e53363 :refs/heads/cloud-main-source \
  --force-with-lease=refs/heads/compaction-carry-watch-build:11e675fc12e914c2075e045ba67891d1e462255c :refs/heads/compaction-carry-watch-build \
  --force-with-lease=refs/heads/compaction-carry-watch-docs:2929fe28eabf0a85154f2a636c45b7f85e74f2a0 :refs/heads/compaction-carry-watch-docs \
  --force-with-lease=refs/heads/compaction-carry-watch-tests:cc07eb7bc023623f4ae11b00474adaa082c9c589 :refs/heads/compaction-carry-watch-tests \
  --force-with-lease=refs/heads/design/page-ask-box:dc1b7e62ca612c7da08ab39d363576a492dd7b6d :refs/heads/design/page-ask-box \
  --force-with-lease=refs/heads/feel-fix-records:31dd1e52a4cc4915d21c269f29a1648c74be2a73 :refs/heads/feel-fix-records \
  --force-with-lease=refs/heads/fork-own-page-build:104af4d76721f53e7bf4597568a29312eef6d498 :refs/heads/fork-own-page-build \
  --force-with-lease=refs/heads/fork-own-page-build2:ccc26ea199bc809c9c119331bb2817138316a2ac :refs/heads/fork-own-page-build2 \
  --force-with-lease=refs/heads/fork-own-page-docs2:9a466fb3d5160422e2d524146d53d9c69a6c38d6 :refs/heads/fork-own-page-docs2 \
  --force-with-lease=refs/heads/fork-own-page-records:e85e9c1e3f48e83c40d4040e67869efbe48085f3 :refs/heads/fork-own-page-records \
  --force-with-lease=refs/heads/fork-own-page-tests:d9aacb34127e514ef0d08cbfd9a90816c24d528e :refs/heads/fork-own-page-tests \
  --force-with-lease=refs/heads/fork-own-page-tests2:02bcc0153b8aab03dece75224f21b667ca592610 :refs/heads/fork-own-page-tests2 \
  --force-with-lease=refs/heads/guard-log-cloud-na-tests:6b874ed06dd054cf2356f2a6ef15e7a7fe883dd9 :refs/heads/guard-log-cloud-na-tests \
  --force-with-lease=refs/heads/guard-time-budget:5b256f567d9fc23922687e54a7c0bd7028dfb389 :refs/heads/guard-time-budget \
  --force-with-lease=refs/heads/guard-time-budget-tests:e6f9fd4a77d4c2ebe145de7c79724947832795c7 :refs/heads/guard-time-budget-tests \
  --force-with-lease=refs/heads/handoff-checkpoint-before-compact:5fdd0a9831a134532d3c71059954394278ba00fb :refs/heads/handoff-checkpoint-before-compact \
  --force-with-lease=refs/heads/hcbc-fix2:104848deb06f8911380469e0363bf80f813cecc6 :refs/heads/hcbc-fix2 \
  --force-with-lease=refs/heads/hcbc-tests2:aa04e216d82539de3597eff8f7b4895583997f17 :refs/heads/hcbc-tests2 \
  --force-with-lease=refs/heads/hcct-tests2:c00165abf6b2aff6708bcc5bc54180be50d75a83 :refs/heads/hcct-tests2 \
  --force-with-lease=refs/heads/hcct-tests3:71151f261e97b9b40b45a20f17d053325a72baea :refs/heads/hcct-tests3 \
  --force-with-lease=refs/heads/hook-if-filters:372f3aec565ad3ad561eaae7dbe70f8ce6dede8f :refs/heads/hook-if-filters \
  --force-with-lease=refs/heads/idle-compaction-off-test:4855504321df801302942cbdfbcc46f90da79cbd :refs/heads/idle-compaction-off-test \
  --force-with-lease=refs/heads/inbox-send-debts:90943456b104d7dd9d2f4f3a9aa4d98d979b5e0d :refs/heads/inbox-send-debts \
  --force-with-lease=refs/heads/install-caseg1-flake:240bfa17fac96a6be15c8b51e02ea86c72830685 :refs/heads/install-caseg1-flake \
  --force-with-lease=refs/heads/installer-spine:704a2e8cd747add7187f5f98b02cf2ec29f83537 :refs/heads/installer-spine \
  --force-with-lease=refs/heads/lane/ci-alarm-by-event-rec:ba2e1000753c3524f01350398bd0359398cf02a1 :refs/heads/lane/ci-alarm-by-event-rec \
  --force-with-lease=refs/heads/lane/env-heredoc-debt:8538a52116b487c317cee608af7c8844fced0364 :refs/heads/lane/env-heredoc-debt \
  --force-with-lease=refs/heads/last-answer-page-tests:5c79b80599cac80732fb8fad7fac23abe1d21c5b :refs/heads/last-answer-page-tests \
  --force-with-lease=refs/heads/live-pin-b:d0a2c82ff86c5f87a59d9e970d8539b371195fa5 :refs/heads/live-pin-b \
  --force-with-lease=refs/heads/m981:fc64bb0e085fc69a7ac0da27aec450c43864d8b2 :refs/heads/m981 \
  --force-with-lease=refs/heads/map-skill-jsx-scan:ed1c332228ccb92c86f91e0709a15ba72f972753 :refs/heads/map-skill-jsx-scan \
  --force-with-lease=refs/heads/one-inbox-per-repo-build:b5487b98d6ef51b73442524615f70559af2356c4 :refs/heads/one-inbox-per-repo-build \
  --force-with-lease=refs/heads/one-inbox-per-repo-merge:1ecd7088817d7eef539d12cfd06b98a5f52db960 :refs/heads/one-inbox-per-repo-merge \
  --force-with-lease=refs/heads/one-inbox-per-repo-record:a1fc21b9f8b20bf7519b0ba5cc7edcd602549d43 :refs/heads/one-inbox-per-repo-record \
  --force-with-lease=refs/heads/one-inbox-per-repo-tests:6904f43be235d91ffb4ba918944b5340ad9e9049 :refs/heads/one-inbox-per-repo-tests \
  --force-with-lease=refs/heads/page-shows-last-answer-build:ee95ad20650ab9db6303b2a938f7b4c042283b05 :refs/heads/page-shows-last-answer-build \
  --force-with-lease=refs/heads/page-shows-last-answer-design:2b66f6a303a504525e42301167416a2b22f46dd5 :refs/heads/page-shows-last-answer-design \
  --force-with-lease=refs/heads/page-shows-last-answer-merge36:9dbc5a0b3e047c2b2d2371604aa0d98ddd3f3dad :refs/heads/page-shows-last-answer-merge36 \
  --force-with-lease=refs/heads/page-shows-last-answer-r2-build:97a5be4cac18f5366c0a10eb5e86c268146479d7 :refs/heads/page-shows-last-answer-r2-build \
  --force-with-lease=refs/heads/page-shows-last-answer-r2-tests:1fb47c1826deb4f3066f2ffc52756563db5833f0 :refs/heads/page-shows-last-answer-r2-tests \
  --force-with-lease=refs/heads/page-shows-last-answer-r3-build:c9fffeb27cd4850cb952ee83eabba12cfd0bd082 :refs/heads/page-shows-last-answer-r3-build \
  --force-with-lease=refs/heads/page-shows-last-answer-tests:749f6e889b6a6a20ed699e80894bf53115c66071 :refs/heads/page-shows-last-answer-tests \
  --force-with-lease=refs/heads/question-departs-comment:605c8f45444857285f4e7c82ec0193383611e97a :refs/heads/question-departs-comment \
  --force-with-lease=refs/heads/question-departs-r2-tests:59faae88dd2b0c561b014c330cba95ccf003295a :refs/heads/question-departs-r2-tests \
  --force-with-lease=refs/heads/question-departs-skill:e75f2485136743d92a795a988254389d792711e4 :refs/heads/question-departs-skill \
  --force-with-lease=refs/heads/question-past-rulings:e0857daa3a4c071d2fe74ff4467aca9d270e3e2d :refs/heads/question-past-rulings \
  --force-with-lease=refs/heads/records-stale-docs:4b1b208395b1f4a449cbac9223fc7984a63244ef :refs/heads/records-stale-docs \
  --force-with-lease=refs/heads/rulings-to-records:2ef77c557ce392bc54d40dc1ddc5ca6d5c145e1c :refs/heads/rulings-to-records \
  --force-with-lease=refs/heads/spawn-model-check-gloss:b594d22fe3a170285dc6f5e80d68920809d82453 :refs/heads/spawn-model-check-gloss \
  --force-with-lease=refs/heads/spawn-model-check-layout:ed3d19026dcf06db7966e39ca68aa6d166d023fa :refs/heads/spawn-model-check-layout \
  --force-with-lease=refs/heads/spawn-model-check-m885:f49cb49dbab91b0aa285427168ccc19e30a56723 :refs/heads/spawn-model-check-m885 \
  --force-with-lease=refs/heads/spawn-model-check-r2-build:d9a238f881913e7569a9a2b064eb9d1a17f1e1cc :refs/heads/spawn-model-check-r2-build \
  --force-with-lease=refs/heads/spawn-model-check-r2-tests:ca07c4654b6fed7e0a72aed521cc3fd6db1bb65d :refs/heads/spawn-model-check-r2-tests \
  --force-with-lease=refs/heads/spawn-model-check-r3-mut:439c6b69eeb89aa60bc68fc3030935da0759fd2f :refs/heads/spawn-model-check-r3-mut \
  --force-with-lease=refs/heads/spawn-model-check-ruff:5e1862e1b737a97c20dd494f0ad54537016ec587 :refs/heads/spawn-model-check-ruff \
  --force-with-lease=refs/heads/start-hook-visibility-record:72fece54a959c1a5fba02eaa0bc5b36da6bd3226 :refs/heads/start-hook-visibility-record \
  --force-with-lease=refs/heads/stop-blocks-live-tasks:b8feeb5202e9ec8028767fc6870fb71850117bb8 :refs/heads/stop-blocks-live-tasks \
  --force-with-lease=refs/heads/stricter-guard-fixes:e5e948e4bba51508a5234c3c0b32a5ac78279047 :refs/heads/stricter-guard-fixes \
  --force-with-lease=refs/heads/sweep-fast:9475d0fb62e5075d136270a6a9043e898eb2fe98 :refs/heads/sweep-fast \
  --force-with-lease=refs/heads/test-builder-shell-write:aada878f69474c608a96a7f1a8a962bfde4e0eeb :refs/heads/test-builder-shell-write \
  --force-with-lease=refs/heads/test/widens-card-plain-words-red:5b375c336b535afbd3dd632e76f0ccaedae9af06 :refs/heads/test/widens-card-plain-words-red \
  --force-with-lease=refs/heads/worktree-agent-a159a691f176f3cbc:ac692a617eb6a22ae4c2f520e48cfdace3c45f0f :refs/heads/worktree-agent-a159a691f176f3cbc \
  --force-with-lease=refs/heads/worktree-agent-a1761859b79cf0ecc:58d5ee766277ef446297581981a2a9dc46637412 :refs/heads/worktree-agent-a1761859b79cf0ecc \
  --force-with-lease=refs/heads/worktree-agent-a1d9445139018c3d6:629710cb3fd581d24196e8911ebbd253ba834e63 :refs/heads/worktree-agent-a1d9445139018c3d6 \
  --force-with-lease=refs/heads/worktree-agent-a1e0ff304689d17f2:5f06f58e42d6aa38a34861c741b6f4871cf10e98 :refs/heads/worktree-agent-a1e0ff304689d17f2 \
  --force-with-lease=refs/heads/worktree-agent-a26d12c8f2660d319:80fdfa5e775101208a6dad42fc1d94f2b2cc18f2 :refs/heads/worktree-agent-a26d12c8f2660d319 \
  --force-with-lease=refs/heads/worktree-agent-a45ba43cc7cdb9218:861fb61a9f23b8bb3621d3dee8c246c72dd94fff :refs/heads/worktree-agent-a45ba43cc7cdb9218 \
  --force-with-lease=refs/heads/worktree-agent-a49aa623b56948b4d:0e235b0dc8d7a4c565211774f1dd30ba4262562d :refs/heads/worktree-agent-a49aa623b56948b4d \
  --force-with-lease=refs/heads/worktree-agent-a522d25b3b24d1948:db20d046f18ac180e600f25ef6e0539bfd00e130 :refs/heads/worktree-agent-a522d25b3b24d1948 \
  --force-with-lease=refs/heads/worktree-agent-a60adb0248f5e4d9e:f98c773ddb7bc8b70f2b3767bc3fb66af10a1f2e :refs/heads/worktree-agent-a60adb0248f5e4d9e \
  --force-with-lease=refs/heads/worktree-agent-a6bf3f09c3bb50d07:a995af5a23facbd2b0972a19c5a5fba4dfe8a186 :refs/heads/worktree-agent-a6bf3f09c3bb50d07 \
  --force-with-lease=refs/heads/worktree-agent-a6c226ba70c216e4d:25f2f5d6c1c7c237629d23c7b04adb5cc37f111c :refs/heads/worktree-agent-a6c226ba70c216e4d \
  --force-with-lease=refs/heads/worktree-agent-a7444fec05b76d0f1:cc24c90991fa4086e3fbc0f61e8898305e01cb27 :refs/heads/worktree-agent-a7444fec05b76d0f1 \
  --force-with-lease=refs/heads/worktree-agent-a76c691697e107474:9639c1cedb76974b53d683bc58ba89b1914b5cdb :refs/heads/worktree-agent-a76c691697e107474 \
  --force-with-lease=refs/heads/worktree-agent-a7e59f46f5249f796:17bf0bc632f1777debd0ac8ed456d18886138b0e :refs/heads/worktree-agent-a7e59f46f5249f796 \
  --force-with-lease=refs/heads/worktree-agent-a8f4c5919b255d333:89160c2b75dbaf0b8b72aa789ca82c8f83e77a2d :refs/heads/worktree-agent-a8f4c5919b255d333 \
  --force-with-lease=refs/heads/worktree-agent-a97a4327f2642fb57:9639c1cedb76974b53d683bc58ba89b1914b5cdb :refs/heads/worktree-agent-a97a4327f2642fb57 \
  --force-with-lease=refs/heads/worktree-agent-aa4a5b028e2f334e9:669d9fa970bb2db466c9a2c6c84f26de90e6a1d7 :refs/heads/worktree-agent-aa4a5b028e2f334e9 \
  --force-with-lease=refs/heads/worktree-agent-aad7092ae89f754ec:f8ae9a106271fca36b7caef31122bc54341c64d0 :refs/heads/worktree-agent-aad7092ae89f754ec \
  --force-with-lease=refs/heads/worktree-agent-ab558e0f008b1efb8:111015e69c0e9d0233740aef9da28b84874bdb24 :refs/heads/worktree-agent-ab558e0f008b1efb8 \
  --force-with-lease=refs/heads/worktree-agent-ac92082bef10f6510:a62c19c6af0b1b05d619d7c8e2f774be55fed693 :refs/heads/worktree-agent-ac92082bef10f6510 \
  --force-with-lease=refs/heads/worktree-agent-acadb77f39b699337:9d0e0c12ffd3a54a6d2c856299a54aa07b398fea :refs/heads/worktree-agent-acadb77f39b699337 \
  --force-with-lease=refs/heads/worktree-agent-ad8324f77c75bd5b0:88210682931bb25e176630c2ab92a5f2d473ec2a :refs/heads/worktree-agent-ad8324f77c75bd5b0 \
  --force-with-lease=refs/heads/worktree-agent-ad983c68d8d317518:73e0c0de6618ead769e9c7459c21a13e1926d31b :refs/heads/worktree-agent-ad983c68d8d317518 \
  --force-with-lease=refs/heads/worktree-agent-aecd9abc359e5f9e1:8ffe4d2ab770c42fe39d8ab73f7499b7e4b0f0a5 :refs/heads/worktree-agent-aecd9abc359e5f9e1 \
  --force-with-lease=refs/heads/worktree-agent-aed60b7f6860382f8:c2d7b10b5fd28bfe122b02f8dd1a3adbb328abf4 :refs/heads/worktree-agent-aed60b7f6860382f8 \
  --force-with-lease=refs/heads/worktree-agent-af93a8c734193113a:532435bf6ec4cf986dfa3c0b5ce183b8a8ace022 :refs/heads/worktree-agent-af93a8c734193113a \
  --force-with-lease=refs/heads/worktree-agent-afdb73d2717d16359:e534fb807d71b05eaf8f684df6555da5ef546379 :refs/heads/worktree-agent-afdb73d2717d16359 \
  --force-with-lease=refs/heads/worktree-base-copies-remove:e1b381fae8d0a4f6ce20a13c376478821b54c57d :refs/heads/worktree-base-copies-remove \
  --force-with-lease=refs/heads/wt-reap-delay:879869cd8c41a0a7a23962725a9b07565dfa9d0b :refs/heads/wt-reap-delay
git ls-remote --heads origin | wc -l
```

## The list

| Branch | Why | Tip |
|---|---|---|
| archive/batch-31 | patch | `99bc35ac` |
| archive/batch-34 | patch | `e44b2240` |
| archive/batch-37 | patch | `c0d60ba1` |
| archive/batch-37-b | patch | `68807aec` |
| archive/batch-44-r2 | patch | `0ecf0264` |
| archive/batch-59-first-build | patch | `6b4200e0` |
| archive/batch-60-first-build | patch | `47368af8` |
| archive/claude/held-ci-spend | squash | `233de80c` |
| archive/merge-lock/c53-probe-base | patch | `e66aaa3d` |
| audit-prose-trees-merge | archived:archive/audit-prose-trees-merge | `d24155b5` |
| batch-20 | patch | `221ca5f8` |
| batch-22 | patch | `66071ed3` |
| batch-22b | patch | `b6936417` |
| batch-37 | patch | `68807aec` |
| batch-38 | archived:archive/batch-38-v2 | `41b963a0` |
| batch-39 | archived:archive/batch-39-v2 | `49b7034d` |
| batch-40 | archived:archive/batch-40 | `92141e75` |
| batch-40-r2 | patch | `5aea7cc5` |
| batch-40-r3 | patch | `73ab3f1b` |
| batch-41 | patch | `d05c8833` |
| batch-41-r2 | patch | `b6afa10e` |
| batch-44 | archived:archive/batch-44 | `6fa57a03` |
| batch-54 | patch | `418c0cba` |
| batch-61 | archived:archive/batch-61 | `0eb88169` |
| batch-63c | archived:archive/batch-63c | `22d59757` |
| batch-63e | archived:archive/batch-63e | `160e1d28` |
| batch-63f | patch | `99553386` |
| batch-64d | archived:archive/batch-64d | `441585d9` |
| batch-oct19e | patch | `d44d69c6` |
| batch-oct27d | patch | `ebbd4826` |
| batch-oct27j | archived:archive/batch-oct27j | `4fb7210a` |
| batch-oct27m | patch | `73c54cfd` |
| batch-oct27n | patch | `93a22522` |
| batch-oct27q | patch | `03255e5f` |
| batch-oct27v | patch | `27c5cad9` |
| batch-oct27x | patch | `41c821fc` |
| batch-oct27y | patch | `2bba1651` |
| batch-oct27z | patch | `c563b73b` |
| batch-oct28b | patch | `b2a90e83` |
| batch-runner-merges | patch | `e4cef792` |
| c204-scroll-width-tests | patch | `41b02aca` |
| c204-scroll-width-tests-r2 | ancestor | `0580e9b4` |
| claude/project-thread-3sv5at | patch | `5eb3a8ec` |
| claude/project-thread-ld0jcg | archived:archive/claude/project-thread-ld0jcg | `1fb3c0e2` |
| claude/project-thread-rqwx3m | archived:archive/claude/project-thread-rqwx3m | `d8030c66` |
| claude/project-thread-x5hnku | archived:archive/claude/project-thread-x5hnku | `0b9925ff` |
| cloud-main-source | ancestor | `f2a0e074` |
| compaction-carry-watch-build | ancestor | `11e675fc` |
| compaction-carry-watch-docs | ancestor | `2929fe28` |
| compaction-carry-watch-tests | ancestor | `cc07eb7b` |
| design/page-ask-box | patch | `dc1b7e62` |
| feel-fix-records | ancestor | `31dd1e52` |
| fork-own-page-build | ancestor | `104af4d7` |
| fork-own-page-build2 | ancestor | `ccc26ea1` |
| fork-own-page-docs2 | ancestor | `9a466fb3` |
| fork-own-page-records | ancestor | `e85e9c1e` |
| fork-own-page-tests | ancestor | `d9aacb34` |
| fork-own-page-tests2 | ancestor | `02bcc015` |
| guard-log-cloud-na-tests | patch | `6b874ed0` |
| guard-time-budget | archived:archive/guard-time-budget | `5b256f56` |
| guard-time-budget-tests | archived:archive/guard-time-budget-tests | `e6f9fd4a` |
| handoff-checkpoint-before-compact | ancestor | `5fdd0a98` |
| hcbc-fix2 | ancestor | `104848de` |
| hcbc-tests2 | ancestor | `aa04e216` |
| hcct-tests2 | ancestor | `c00165ab` |
| hcct-tests3 | ancestor | `71151f26` |
| hook-if-filters | archived:archive/hook-if-filters | `372f3aec` |
| idle-compaction-off-test | patch | `48555043` |
| inbox-send-debts | ancestor | `90943456` |
| install-caseg1-flake | patch | `240bfa17` |
| installer-spine | archived:archive/installer-spine | `704a2e8c` |
| lane/ci-alarm-by-event-rec | ancestor | `ba2e1000` |
| lane/env-heredoc-debt | patch | `8538a521` |
| last-answer-page-tests | ancestor | `5c79b805` |
| live-pin-b | archived:archive/live-pin-b | `d0a2c82f` |
| m981 | ancestor | `fc64bb0e` |
| map-skill-jsx-scan | archived:archive/map-skill-jsx-scan | `ed1c3322` |
| one-inbox-per-repo-build | ancestor | `b5487b98` |
| one-inbox-per-repo-merge | ancestor | `1ecd7088` |
| one-inbox-per-repo-record | ancestor | `a1fc21b9` |
| one-inbox-per-repo-tests | ancestor | `6904f43b` |
| page-shows-last-answer-build | ancestor | `ee95ad20` |
| page-shows-last-answer-design | ancestor | `2b66f6a3` |
| page-shows-last-answer-merge36 | ancestor | `9dbc5a0b` |
| page-shows-last-answer-r2-build | ancestor | `97a5be4c` |
| page-shows-last-answer-r2-tests | ancestor | `1fb47c18` |
| page-shows-last-answer-r3-build | ancestor | `c9fffeb2` |
| page-shows-last-answer-tests | ancestor | `749f6e88` |
| question-departs-comment | ancestor | `605c8f45` |
| question-departs-r2-tests | ancestor | `59faae88` |
| question-departs-skill | patch | `e75f2485` |
| question-past-rulings | ancestor | `e0857daa` |
| records-stale-docs | patch | `4b1b2083` |
| rulings-to-records | ancestor | `2ef77c55` |
| spawn-model-check-gloss | ancestor | `b594d22f` |
| spawn-model-check-layout | ancestor | `ed3d1902` |
| spawn-model-check-m885 | ancestor | `f49cb49d` |
| spawn-model-check-r2-build | ancestor | `d9a238f8` |
| spawn-model-check-r2-tests | ancestor | `ca07c465` |
| spawn-model-check-r3-mut | ancestor | `439c6b69` |
| spawn-model-check-ruff | ancestor | `5e1862e1` |
| start-hook-visibility-record | ancestor | `72fece54` |
| stop-blocks-live-tasks | archived:archive/stop-blocks-live-tasks | `b8feeb52` |
| stricter-guard-fixes | patch | `e5e948e4` |
| sweep-fast | archived:archive/sweep-fast | `9475d0fb` |
| test-builder-shell-write | ancestor | `aada878f` |
| test/widens-card-plain-words-red | patch | `5b375c33` |
| worktree-agent-a159a691f176f3cbc | archived:archive/worktree-agent-a159a691f176f3cbc-v2 | `ac692a61` |
| worktree-agent-a1761859b79cf0ecc | ancestor | `58d5ee76` |
| worktree-agent-a1d9445139018c3d6 | patch | `629710cb` |
| worktree-agent-a1e0ff304689d17f2 | ancestor | `5f06f58e` |
| worktree-agent-a26d12c8f2660d319 | ancestor | `80fdfa5e` |
| worktree-agent-a45ba43cc7cdb9218 | ancestor | `861fb61a` |
| worktree-agent-a49aa623b56948b4d | ancestor | `0e235b0d` |
| worktree-agent-a522d25b3b24d1948 | ancestor | `db20d046` |
| worktree-agent-a60adb0248f5e4d9e | ancestor | `f98c773d` |
| worktree-agent-a6bf3f09c3bb50d07 | ancestor | `a995af5a` |
| worktree-agent-a6c226ba70c216e4d | ancestor | `25f2f5d6` |
| worktree-agent-a7444fec05b76d0f1 | ancestor | `cc24c909` |
| worktree-agent-a76c691697e107474 | ancestor | `9639c1ce` |
| worktree-agent-a7e59f46f5249f796 | ancestor | `17bf0bc6` |
| worktree-agent-a8f4c5919b255d333 | ancestor | `89160c2b` |
| worktree-agent-a97a4327f2642fb57 | ancestor | `9639c1ce` |
| worktree-agent-aa4a5b028e2f334e9 | ancestor | `669d9fa9` |
| worktree-agent-aad7092ae89f754ec | patch | `f8ae9a10` |
| worktree-agent-ab558e0f008b1efb8 | ancestor | `111015e6` |
| worktree-agent-ac92082bef10f6510 | patch | `a62c19c6` |
| worktree-agent-acadb77f39b699337 | patch | `9d0e0c12` |
| worktree-agent-ad8324f77c75bd5b0 | patch | `88210682` |
| worktree-agent-ad983c68d8d317518 | ancestor | `73e0c0de` |
| worktree-agent-aecd9abc359e5f9e1 | patch | `8ffe4d2a` |
| worktree-agent-aed60b7f6860382f8 | ancestor | `c2d7b10b` |
| worktree-agent-af93a8c734193113a | ancestor | `532435bf` |
| worktree-agent-afdb73d2717d16359 | ancestor | `e534fb80` |
| worktree-base-copies-remove | patch | `e1b381fa` |
| wt-reap-delay | archived:archive/wt-reap-delay | `879869cd` |
