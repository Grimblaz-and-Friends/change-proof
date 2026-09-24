# change-proof

Change proof is a reusable GitHub workflow for pull requests: it decides from caller-owned path rules whether use was required, verifies the applicable use or no-use evidence and every configured connected reviewer, and requires authorized dispositions on those reviewers' top-level inline comments before the proof passes.

## Call the workflow

The caller grants the three read permissions and invokes the workflow for the four pull request activity types that evaluate a pull request head. A caller that wants changes here to reach it only by its own pull request pins a full commit SHA instead.

```yaml
name: Change proof

on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review]

jobs:
  change-proof:
    name: Change proof
    permissions:
      contents: read
      issues: read
      pull-requests: read
    uses: Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@main
```

The check context GitHub reports for a reusable-workflow call is the caller's job name — or the job id, where the job has no `name:` — followed by the called job's name. The called job is named `Change proof`, so the example above reports `Change proof / Change proof`, and the same caller without its `name:` line reports `change-proof / Change proof` instead. A ruleset that requires one will never see the other.

A caller workflow is checked out from the pull request it judges, so a pull request can edit it. Requiring a caller's context therefore proves nothing a pull request could not arrange for itself. The gate that cannot be arranged is the organization ruleset's workflow rule, which names this repository's `.github/workflows/self-change-proof.yml` at `refs/heads/main` and runs a definition no caller's pull request can rewrite. Keep a caller for what it adds — it is the only one of the two that starts when a pull request is marked ready — and do not make its context a required status check.

On a `pull_request` event, the called workflow derives the pull request number and evaluates its head; draft pull requests are not evaluated and exit non-zero. Mark the pull request ready and re-run the failed check.

A workflow required by a ruleset ignores the filters its own file declares — `branches`, `paths`, `types` and the rest — and starts only on the default activity types of the events that rule supports, which for `pull_request` are `opened`, `reopened` and `synchronize`. Marking a pull request ready therefore starts a caller's run and never the required one. Both consequences are expected rather than faults: a repository with no caller sees no run at all when a pull request is marked ready, and a repository with a caller sees a run that begins at the same moment as the connected reviewers it requires and fails because they have not posted yet. In both cases the required check is re-run once the reviewers have landed.

After a note or disposition lands, re-run the failed check from the pull request's checks tab or from the command line. `gh run rerun <run-id> --failed` works for an ordinary workflow run. It does not work for a run produced by a ruleset-required workflow: that run carries a `workflow_id` that is not an addressable workflow in the repository the run belongs to, and `gh run rerun` resolves the workflow before re-running the run, so the command fails with `HTTP 404`. This holds even in the repository where the required workflow's file lives — there the file's own workflow id and the id its required runs carry are different, and only the first can be fetched. The URL in that error names the **workflow** id rather than the run id, so the message reads as though the run is gone; it is not. Re-run it through the run-level endpoint:

```text
gh api -X POST repos/OWNER/REPO/actions/runs/<run-id>/rerun
```

A workflow's token cannot re-run workflow runs, and this design grants no write permission. A `no-use` note stays pinned to the current head. A `use` note for an earlier head counts only when it says `changed=false`, GitHub's single compare response proves that head is an ancestor of the current head and contains every intervening commit, and every such commit changes no path that the base branch's current-tip policy says buys a use; otherwise the use note must be posted again for the current head. Each intervening commit is classified separately, including both names of a rename, so a bought change still stales the note if a later commit reverts it.

## Caller-owned configuration

The checker resolves the pull request's base ref to the base branch's current tip commit, reports that SHA in a `verified:` line, reads both files there through the GitHub contents API, and judges the change by those trusted copies; it also reads the head copies so a policy change, including deletion of either file, is reported. When the base branch tip does not contain both files, the introducing pull request is evaluated with its head copies so all other findings remain visible, but it fails because it cannot prove itself and the owner must merge it on the connected reviewers' evidence. `.github/change-proof.json` is the same schema-version-1 use-rules object consumed by the tradecraft entrance. The following generic example is for a web product whose source is kept under `src/`. It buys a use for production source and web build surfaces while excluding the product's tests and test-support modules:

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
        "src/test/**",
        "**/*.test.*",
        "**/*.test-*.*"
      ]
    }
  ]
}
```

A caller's exclude list must cover test-support modules kept beside production code, not only test files, because a module named like `Suite.test-helpers.ts` matches no test-file pattern and would buy a use.

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

Pull requests to this repository take the same release proof as its callers. A change here is reported ready for merge only after the change-proof check has run, every configured connected reviewer has run, and every top-level inline reviewer thread has a marker-producer disposition.

When the paths buy use, a `marker_producers` login posts the practice's exact `use` marker for the head the experience session used in a pull-request comment, review, or review comment:

```text
<!-- tradecraft:use:v1 head=SHA status=pass changed=CHANGED staffing_status=STAFFING_STATUS [same_vendor_reason=REASON] -->
```

`CHANGED` is `true` or `false`; `STAFFING_STATUS` is `qualified` or `degraded`; and a degraded run carries the nonempty hyphenated `same_vendor_reason` while a qualified run does not. A note naming the current pull-request head may carry either `CHANGED` value. A note naming an earlier head applies only with `changed=false`. The single, unpaginated GitHub comparison must report `ahead` or `identical`, name the note head as its merge base, and return as many intervening commits as its `ahead_by` value. That candidate is not applicable when the status or merge base does not prove ancestry, when `ahead_by` is missing or differs from the returned commit count, when a returned commit lacks a full revision, or when any returned commit changes a use-bought path. Each returned commit is read through the paginated `repos/{repo}/commits/{sha}?per_page=100` endpoint, and both `filename` and `previous_filename` are classified under the policy read from the base branch's current tip. If reading a candidate's comparison or commit pages fails—including a GET failure, invalid JSON, or a page that omits `files`—that candidate is not applicable and the checker continues to the next older eligible note. If no candidate applies, the check fails with the latest candidate's reason and the remedy to post at the current head. A `no-use` note never carries forward.

For a carried use note, the `verified:` line names its head and every intervening commit read. When an intervening commit buys a use, the stale finding names the note head and the first such commit.

When the paths do not buy use, a marker producer posts the practice's exact `no-use` marker followed in the same comment by its line and reason:

```text
<!-- tradecraft:no-use:v1 head=SHA -->
Use: not required — REASON
```

A current-head `use` marker when the paths do not buy use is a false claim and fails even if other evidence is complete.

Every top-level inline comment from a connected reviewer needs a reply by a marker producer whose first line begins with one of the closed dispositions: `fixed`; `fixed — nothing else found it`; `fixed in #<N>`; `yours — in the release report`; `declined — <why it earns no end>`; `duplicate of <the earlier comment>`; `lapsed — <the rule we do not run>`.

The checker ignores leading whitespace and one balanced Markdown inline wrapper—backticks, asterisks or underscores—before reading a disposition or the `Use: not required` line.

The checker returns exit `0` only when it has evaluated the pull request head's evidence and that evidence satisfies this contract; a result that does not evaluate the evidence is not a pass.

- **Pass:** a current-head no-use note agrees with a no-use decision, or a valid current-head or qualifying ancestor use note agrees with a use decision; every connected reviewer has a credited run; and every owed inline disposition is present.

- **Fail:** the note is missing, stale, malformed, unauthorized, or false; a configured reviewer has no credited run; or an owed inline disposition is missing or unauthorized.

A connected reviewer has run when at least one review, inline review comment, or pull-request comment by its login exists; a pull-request comment saying the review was limited, rate limited, skipped, or still running is a notice of not reviewing and does not count, repeated appearances are allowed because a bought second look does not fail the gate, and a completed summary-only pull-request comment counts and owes no invented inline disposition. This notice classification reads vendor comment text rather than a vendor API and can be wrong in both directions when a vendor changes its wording.

## Boundary and tests

The checker job never checks out caller content, executes caller code, writes to the caller, or sends a method other than GET; it has only `contents: read`, `issues: read` and `pull-requests: read`. The only caller files the checker reads are the two configuration files above at the base and head revisions; changed paths, comments, reviews, and review comments are GitHub API records.

`proof/check.py` is standard-library-only and has recorded-shape unit tests for both acceptance polarities, trusted policy, renamed paths, authorization, pagination, exact evidence boundaries and the GET-only transport. The proof job runs that module as its sole `run` step without a checkout. A test compares the embedded script with `proof/check.py` byte for byte after line-ending normalization, and workflow tests assert the job's exact permissions and pull-request-only routing, so the tested module and the shipped workflow cannot drift; CI runs the suite on Ubuntu and Windows.
