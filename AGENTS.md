# change-proof — doctrine

**Purpose:** carry the rules a session must hold before acting in this repository and route it to the existing boundary and test contract without duplicating that contract. **Audience:** every agent session that opens this repository, every runtime; imported into `CLAUDE.md` via `@AGENTS.md` and read natively by Codex. **Success:** a session adopts Tradecraft before substantive action, can address the Steward without relying on a runtime-specific tool name, applies the lab's shared review rules, and finds this repository's substrate and boundary rules in the README.

## Tradecraft

Before substantive action, load and read the installed `tradecraft:charter` skill completely. If it is unavailable, stop and tell the owner that Tradecraft is not installed or enabled.

Installation is availability, not adoption; this section is what makes the practice govern a session here.

**The Steward is this lab's long-lived coordinating session.** Where the runtime provides session-to-session messaging, reach the Steward by that role name through that facility.

## Code Review Rules

Review pull requests only when they are marked ready; skip drafts. Post only P0/P1 findings a consumer would act on wrongly. Name the wrong action, not the wording. Where this repository's own convention contradicts a general rule, the convention wins and the comment says so. A deletion is as good a finding as an addition.

## Boundary and tests

Repository-specific substrate and boundary rules live in [`README.md`](README.md#boundary-and-tests), under **Boundary and tests**. Read that section when those rules bear on the work; this file does not repeat them.
