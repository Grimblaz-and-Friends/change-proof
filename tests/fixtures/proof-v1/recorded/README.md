# Recorded proof-v1 fixtures

These files are field-trimmed copies of the real GitHub REST recordings and exact
producer comments supplied for change-proof #20's repair round:

- `world-tc733.trimmed.json` and the two `tradecraft-733*.comment.md` files come
  from tradecraft pull request #733 and work issue #725.
- `world-verra476.trimmed.json` and the two `verra-476*.comment.md` files come
  from Organizations-of-Verra pull request #476 and work issue #471.

The world files retain every record and field consumed by the gate for these
documents. They were selected mechanically from `fixtures20/world-*.json`; the
comments are byte-for-byte producer output apart from the repository's enforced
LF line endings.
