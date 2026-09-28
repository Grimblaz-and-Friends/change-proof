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

The world files retain every record and field consumed by the gate for these
documents. The #767 world was recaptured from the public GitHub REST record with
GET only and keeps every member of each consumed collection and every consumed
body verbatim; its field trimming removes only material the gate does not read.
The earlier worlds were selected mechanically from `fixtures20/world-*.json`.
The standalone producer comments are byte-for-byte producer output apart from
the repository's enforced LF line endings.
