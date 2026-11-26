# Recorded proof-v1 fixtures

These files are field-trimmed copies of the real GitHub REST recordings and exact
producer comments supplied for change-proof #20's repair round and #21's mechanical
lane replay:

- `world-tc733.trimmed.json` and the two `tradecraft-733*.comment.md` files come
  from tradecraft pull request #733 and work issue #725.
- `world-verra476.trimmed.json` and the two `verra-476*.comment.md` files come
  from Organizations-of-Verra pull request #476 and work issue #471.
- `world-tc767.trimmed.json` and `tradecraft-767.comment.md` come from tradecraft
  pull request #767 and work issue #759. The exact producer comment is
  `5852491047`, updated `2026-09-27T04:21:14Z`, from Tradecraft `0.156.0` at
  head `4f12aa5efa0ae765cebd213f89eec7da754c3d6a`; it names affirmed source
  `5851221027`. `tradecraft-767.attempt-5.output.txt` is the gate output copied
  line for line from job `108549502051`, whose reusable checker was
  `cb5b746f92457dc6075099db0f9d2d3c24341fdf`. The replay pins historical base tip
  `6789582047cf306607573ecaff25ba1a4eda379d`, gate run `36292658635` attempt
  `5`, and the then-open pull request. The world file labels each historical
  reconstruction separately, including the open states of pull request #767
  and work issue #759.
- `world-tc1030.trimmed.json` and `tradecraft-1030.comment.md` come from
  tradecraft pull request #1030 and work issue #1014, the builder-route proof the
  gate at `966476916407b843e294dcb8ee2aae064c19ee73` refused. The exact producer
  comment is `7173428037`, created and never edited at `2026-11-25T20:16:30Z`, from
  Tradecraft `0.220.0` at head `3f8f243f5d9ad63b4d58f2fc1585cce823aa5eac`; its use
  source is the builder's use report `7173191455`, created and never edited at
  `2026-11-25T20:06:04Z`. The world was captured on 2026-11-26 by running that gate
  GET-only against the live pull request, and holds exactly the 20 endpoints it
  read. Base tip `6f19efc3ea3599d3815d5c889df3f2079b9f7ae1` and the pull request's
  open state were current at capture, so the world lists no reconstruction. The
  SHA-256 of the proof comment body is
  `fa9dc08a9ffe6f00d8ae63b8ad4602956ff45d1a81b0a8736322552c04439765` and of the
  report body is `a68b7d3b233f0d381b11432f5a19513fb9849ed0a4984dfa4075988c3c904189`;
  a test pins both. No gate output is committed.

The world files retain every record and field consumed by the gate for these
documents. The #767 world was recaptured from the public GitHub REST record with
GET only and keeps every member of each consumed collection and every consumed
body verbatim; its field trimming removes only material the gate does not read.
The earlier worlds were selected mechanically from `fixtures20/world-*.json`.
The standalone producer comments are byte-for-byte producer output apart from
the repository's enforced LF line endings.
