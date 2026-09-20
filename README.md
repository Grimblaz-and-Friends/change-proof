# change-proof

Change proof is a reusable GitHub workflow for pull requests: it decides from caller-owned path rules whether use was required, verifies the current-head use evidence and every configured connected reviewer, and requires authorized dispositions on those reviewers' top-level inline comments before the proof passes.

## Call the workflow

The caller grants the three read permissions plus one Actions write permission and invokes the workflow for the four event families that can change its evidence. A caller that wants changes here to reach it only by its own pull request pins a full commit SHA instead.

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

jobs:
  change-proof:
    if: >-
      github.event_name != 'issue_comment' ||
      github.event.issue.pull_request
    permissions:
      actions: write
      contents: read
      issues: read
      pull-requests: read
    uses: Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@main
```

On a `pull_request` event, the called workflow derives the pull request number and evaluates its head; draft pull requests exit successfully without evaluation. On the three comment and review event families, it does not run the checker: it finds the latest `pull_request`-family run of the same workflow for that pull request and sends one POST to the Actions re-run endpoint. `actions: write` is the one write the caller grants, and it is needed because a check attached to the pull request head can only be re-evaluated by re-running the run that produced it.

## Caller-owned configuration

The checker reads both files through the GitHub contents API at the pull request's base head and judges the change by that trusted policy; it also reads the head copies so a policy change, including deletion of either file, is reported. When the base does not contain both files, the introducing pull request is evaluated with its head copies so all other findings remain visible, but it fails because it cannot prove itself and the owner must merge it on the connected reviewers' evidence. `.github/change-proof.json` is the same schema-version-1 use-rules object consumed by the tradecraft entrance. This Organizations of Verra example buys a use for its running product surfaces and excludes tests nested under those surfaces:

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

Matching slash-normalizes each changed path, then applies Python's case-sensitive `fnmatch.fnmatchcase`: a path buys use when it matches an `include` and no `exclude` in at least one rule. Before classification, the checker compares the retrieved file-record count with the pull request's `changed_files` count and fails when they differ.

`.tradecraft/work.json` supplies the identities that may produce evidence and the connected reviewers that must run. Replace `your-github-login` with each login authorized to post use notes and dispositions.

```json
{
  "schema_version": 1,
  "product_repositories": [],
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

A nonempty `product_repositories` list marks a repository that hosts practice work; that repository fills the list with the products it serves.

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

- **Pass:** the current-head note agrees with the path decision, every connected reviewer has a credited run, and every owed inline disposition is present.

- **Fail:** the note is missing, stale, malformed, unauthorized, or false; a configured reviewer has no credited run; or an owed inline disposition is missing or unauthorized.

A connected reviewer has run when at least one review, inline review comment, or pull-request comment by its login exists; a pull-request comment saying the review was limited, rate limited, skipped, or still running is a notice of not reviewing and does not count, repeated appearances are allowed because a bought second look does not fail the gate, and a completed summary-only pull-request comment counts and owes no invented inline disposition. This notice classification reads vendor comment text rather than a vendor API and can be wrong in both directions when a vendor changes its wording.

## Boundary and tests

The checker job never checks out caller content, executes caller code, writes to the caller, or sends a method other than GET; it has only `contents: read`, `issues: read` and `pull-requests: read`. The separate rerun job has only `actions: write`, reads Actions run records, and sends its single POST to re-run the selected pull-request-head run. The only caller files the checker reads are the two configuration files above at the base and head revisions; changed paths, comments, reviews, and review comments are GitHub API records.

`proof/check.py` is standard-library-only and has recorded-shape unit tests for both acceptance polarities, trusted policy, renamed paths, authorization, pagination, exact evidence boundaries and the GET-only transport. The proof job runs that module as its sole `run` step without a checkout. A test compares the embedded script with `proof/check.py` byte for byte after line-ending normalization, and workflow tests assert both jobs' exact permissions and event routing, so the tested module and the shipped workflow cannot drift; CI runs the suite on Ubuntu and Windows.
