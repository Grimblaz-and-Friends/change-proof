# change-proof

Change proof is a reusable GitHub workflow for pull requests: it decides from caller-owned path rules whether use was required, verifies the current-head use evidence and every configured connected reviewer, and requires authorized dispositions on those reviewers' top-level inline comments before the proof passes.

## Call the workflow

The caller grants only the three read permissions and invokes the workflow for the four event families that can change its evidence. Replace `<release-commit-sha>` with a full commit SHA from this repository.

```yaml
name: Change proof

on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review, converted_to_draft]
  issue_comment:
    types: [created, edited, deleted]
  pull_request_review:
    types: [submitted, edited, dismissed]
  pull_request_review_comment:
    types: [created, edited, deleted]

permissions:
  contents: read
  issues: read
  pull-requests: read

jobs:
  change-proof:
    if: >-
      github.event_name != 'issue_comment' ||
      github.event.issue.pull_request
    uses: Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@<release-commit-sha>
```

The called workflow derives the pull request number from `pull_request.number` or `issue.number`. It uses the event's pull-request head SHA when present and resolves the head through a GET otherwise. Draft pull requests exit successfully without evaluation.

## Caller-owned configuration

The workflow reads both files through the GitHub contents API at the head SHA. `.github/change-proof.json` is the same schema-version-1 use-rules object consumed by the tradecraft entrance. This Organizations of Verra example buys a use for its running product surfaces and excludes tests nested under those surfaces:

```json
{
  "schema_version": 1,
  "rules": [
    {
      "name": "runtime-or-user-surface",
      "include": [
        "src/**",
        "public/**",
        "index.html",
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "tailwind.config.js",
        "postcss.config.js"
      ],
      "exclude": [
        "src/tests/**",
        "src/**/tests/**",
        "src/*.test.*",
        "src/**/*.test.*"
      ]
    }
  ]
}
```

Matching slash-normalizes each changed path, then applies Python's case-sensitive `fnmatch.fnmatchcase`: a path buys use when it matches an `include` and no `exclude` in at least one rule.

`.tradecraft/work.json` supplies the identities that may produce evidence and the connected reviewers that must run. Replace `your-github-login` with each login authorized to post use notes and dispositions.

```json
{
  "schema_version": 1,
  "product_repositories": [
    "Grimblaz-and-Friends/Organizations-of-Verra"
  ],
  "connected_reviewers": [
    "greptile-apps[bot]",
    "coderabbitai[bot]",
    "chatgpt-codex-connector[bot]"
  ],
  "marker_producers": [
    "your-github-login"
  ]
}
```

All three lists are required by the shared work-configuration schema, including an empty list where a caller has no entries.

## Evidence contract

When the paths buy use, a `marker_producers` login posts the practice's exact `use` marker for the current head in a pull-request comment, review, or review comment:

```text
<!-- tradecraft:use:v1 head=SHA status=pass changed=CHANGED staffing_status=STAFFING_STATUS [same_vendor_reason=REASON] -->
```

`CHANGED` is `true` or `false`; `STAFFING_STATUS` is `qualified` or `degraded`; and a degraded run carries the nonempty hyphenated `same_vendor_reason` while a qualified run does not.

When the paths do not buy use, a marker producer posts the practice's exact `no-use` marker followed in the same comment by its line and reason:

```text
<!-- tradecraft:no-use:v1 head=SHA -->
Use: not required — REASON
```

A current-head `use` marker when the paths do not buy use is a false claim and fails even if other evidence is complete.

Every top-level inline comment from a connected reviewer needs a reply by a marker producer whose first line begins with one of the closed dispositions: `fixed`; `fixed — nothing else found it`; `fixed in #<N>`; `yours — in the release report`; `declined — <why it earns no end>`; `duplicate of <the earlier comment>`; `lapsed — <the rule we do not run>`.

- **Pass:** the current-head note agrees with the path decision, every connected reviewer has appeared, and every owed inline disposition is present.

- **Fail:** the note is missing, stale, malformed, unauthorized, or false; a configured reviewer has not appeared; or an owed inline disposition is missing or unauthorized.

A connected reviewer has run when at least one review, review comment, or pull-request comment by its login exists. Repeated appearances are allowed: a bought second look does not fail the gate. A reviewer that posts only a summary has run and owes no invented inline disposition.

## Boundary and tests

The reusable workflow never checks out caller content, executes caller code, writes to the caller, or sends a method other than GET. The only caller files it reads are the two configuration files above at the selected head; changed paths, comments, reviews, and review comments are GitHub API records.

`proof/check.py` is standard-library-only and has recorded-shape unit tests for both acceptance polarities, authorization, pagination, and the GET-only transport. The workflow runs that module as its sole `run` step without a checkout. A test compares the embedded script with `proof/check.py` byte for byte after line-ending normalization, so the tested module and the shipped workflow cannot drift; CI runs the suite on Ubuntu and Windows.
