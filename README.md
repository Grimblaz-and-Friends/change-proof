# change-proof

**Purpose:** define and operate the independent release-proof gate used by this repository and its adopters. **Audience:** repository owners, holders, and adopters configuring or interpreting the gate. **Success:** a reader can grant the exact read boundary, supply either compatibility markers or one proof document per head, and distinguish facts the gate verified from producer declarations and diagnostics.

Change proof is a reusable GitHub workflow for pull requests: it requires the pull-request body's `**Path departures:**` paragraph, decides from caller-owned path rules whether use was required unless the owner's verified mechanical lane exempts it, verifies the applicable use or no-use evidence and every configured connected reviewer, and requires authorized dispositions on those reviewers' top-level inline comments before the proof passes.

## Call the workflow

The caller grants the five read permissions and invokes the workflow for the four pull request activity types that evaluate a pull request head. A caller that wants changes here to reach it only by its own pull request pins a full commit SHA instead.

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
      checks: read
      actions: read
    uses: Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@main
```

The check context GitHub reports for a reusable-workflow call is the caller's job name — or the job id, where the job has no `name:` — followed by the called job's name. The called job is named `Change proof`, so the example above reports `Change proof / Change proof`, and the same caller without its `name:` line reports `change-proof / Change proof` instead. A ruleset that requires one will never see the other.

A caller workflow is checked out from the pull request it judges, so a pull request can edit it. Requiring a caller's context therefore proves nothing a pull request could not arrange for itself. The gate that cannot be arranged is the organization ruleset's workflow rule, which names this repository's `.github/workflows/self-change-proof.yml` at `refs/heads/main` and runs a definition no caller's pull request can rewrite. Keep a caller for what it adds — it is the only one of the two that starts when a pull request is marked ready — and do not make its context a required status check.

On a `pull_request` event, the called workflow derives the pull request number and evaluates its head; draft pull requests are not evaluated and exit non-zero. Mark the pull request ready and re-run the failed check.

A workflow required by a ruleset ignores the filters its own file declares — `branches`, `paths`, `types` and the rest — and starts only on the default activity types of the events that rule supports, which for `pull_request` are `opened`, `reopened` and `synchronize`. Marking a pull request ready therefore starts a caller's run and never the required one. Both consequences are expected rather than faults: a repository with no caller sees no run at all when a pull request is marked ready, and a repository with a caller sees a run that begins at the same moment as the connected reviewers it requires and fails because they have not posted yet. In both cases the required check is re-run once the reviewers have landed.

After a note or disposition lands, or after the pull-request body is edited to add the required paragraph, re-run the failed check from the pull request's checks tab or from the command line. `gh run rerun <run-id> --failed` works for an ordinary workflow run. It does not work for a run produced by a ruleset-required workflow: that run carries a `workflow_id` that is not an addressable workflow in the repository the run belongs to, and `gh run rerun` resolves the workflow before re-running the run, so the command fails with `HTTP 404`. This holds even in the repository where the required workflow's file lives — there the file's own workflow id and the id its required runs carry are different, and only the first can be fetched. The URL in that error names the **workflow** id rather than the run id, so the message reads as though the run is gone; it is not. Re-run it through the run-level endpoint:

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

Pull requests to this repository take the same release proof as its callers. A change here is reported ready for merge only after its body has the required path-departures paragraph, the change-proof check has run, every configured connected reviewer has run, and every top-level inline reviewer thread has a marker-producer disposition.

For the compatibility release, the gate selects one of two evidence paths and prints the selected path. One authorized comment framed by a `tradecraft:proof:v1 head=FULL_SHA` envelope followed by exactly one JSON fence selects `proof-v1`; the fenced object is the input and its readable rendering is not. Multiple authorized current-head documents, an invalid selected document, or a document whose envelope cannot be scoped safely fails without falling back to markers. When no authorized current-head document exists, older documents are ignored and the existing marker family selects `legacy-markers`. Unauthorized proof comments supply neither declarations nor authority and cannot suppress otherwise valid evidence.

The document path requires a public, authorized `tradecraft:floor:v1 head=FULL_SHA status=pass` note on the source surface named by the document. The proof document identifies that and its other public sources rather than replacing them. The gate resolves issue comments only through the document's named work issue, resolves pull-request comments, reviews, and inline comments through the evaluated pull request, and constructs every authenticated API endpoint itself. It re-derives the live head, trusted base-tip policy, changed-path classification, floor checks, configured reviewers, and dispositions. A current-head generated no-use record needs no second legacy marker; ancestor relaxation applies only to bought use evidence.

A sourced generated no-use record is the proof-document carrier for the owner-affirmed mechanical lane. Its source must be an issue comment on the document's distinct work issue, authored by a marker producer in the trusted base-tip configuration. The gate first selects the work issue's latest authorized comment containing an exact, attribute-free `tradecraft:affirmed-brief:v1` marker; that record must then contain exactly one lawful `Review risk:` / `Review lane:` pair, and only `ordinary` / `mechanical` exempts use. The gate reads the complete work-comment order at evaluation time, so a later authorized affirmed record supersedes an older source even when the proof has not changed. It never follows the source URL or trusts its claimed author, timestamp, reason, or producer version. The carrier must still be current-head, generated, `not-required`, without intervening commits, and have a nonempty reason. This exception belongs only to `proof-v1`; it does not change the compatibility marker path.

A verified exception names its authority and keeps the path decision visible:

```text
verified: owner-affirmed mechanical lane in OWNER/REPO#N issue-comment #ID exempts use; changed paths would otherwise require use
verified: owner-affirmed mechanical lane in OWNER/REPO#N issue-comment #ID exempts use; changed paths would otherwise not require use
```

Output labels facts and limitations by source. `verified:` names a fact re-derived from GitHub records or trusted policy. `declared:` preserves an authorized producer statement about local dispatch, staffing, model settings, bundles, or policy provenance the gate did not fetch. `producer-diagnostic:` preserves a limitation reported by that producer, while `diagnostic:` is reserved for a limitation the gate derived itself; neither becomes an automatic failure. Embedded line breaks are escaped so producer content cannot manufacture another output line.

Public floor checks are matched by check id, application, exact name, workflow and run identities, head, status, conclusion, and timestamps. Every visible current-head check other than the gate's own identified proof job must be present in the document and completed with `success`, `neutral`, or `skipped`; `neutral` and `skipped` retain those distinct names and are not described as successful executions. Job records establish reruns: a newer run, or a newer attempt of the same run, supersedes an older execution inside one application/workflow/name group, while same-named checks in one run attempt and same-named checks from different workflows stay separate. The running gate's own job and a caller's reusable proof job are excluded only when exactly one job in that run attempt matches the called `Change proof` identity; zero or multiple matches fail with the candidate jobs named, and unrelated caller jobs remain in the floor set. Each excluded proof execution prints an `excluded:` line naming its run and check and whether it was the current gate, an earlier attempt of that gate, or a separate caller invocation.

Every ready pull-request body must have a Markdown paragraph whose first logical line begins at column zero with the exact lead-in `**Path departures:**`. Write that lead-in in the Markdown source, for example in the Write tab, because copying it from the rendered preview drops the `**` markers. The checker verifies only that paragraph's presence; it does not interpret or require any content after the lead-in. A heading, list item, block quote, indented or fenced code, HTML comment, raw HTML block, or mention later in an existing paragraph does not count. For a blank-line-terminated HTML block, a line directly after a tag line such as `</details>` still belongs to the block, so put a blank line before the paragraph. A `---` or `===` line immediately below the paragraph, with no blank line between, makes it a setext heading and therefore does not count.

The condition reports these exact lines:

```text
verified: pull request body has a **Path departures:** paragraph
```

```text
missing: a pull request body paragraph beginning with **Path departures:**
satisfy: add the **Path departures:** paragraph to the pull request body and re-run change-proof
```

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

Every top-level inline comment from a connected reviewer needs a reply by a marker producer whose first non-blank line begins with one of the closed dispositions: `fixed`; `fixed — nothing else found it`; `fixed in #<N>`; `yours — in the release report`; `declined — <why it earns no end>`; `duplicate of <the earlier comment>`; `lapsed — <the rule we do not run>`.

The checker ignores leading blank lines and whitespace and one balanced Markdown inline wrapper—backticks, asterisks or underscores—around the whole line or its opening disposition word. It also ignores one balanced whole-line wrapper when reading the `Use: not required` line.

The checker returns exit `0` only when it has evaluated the pull request head's evidence and that evidence satisfies this contract; a result that does not evaluate the evidence is not a pass.

- **Pass:** the pull-request body has the required paragraph; a current-head generated no-use record or compatibility no-use note agrees with a no-use decision, a valid current-head or qualifying ancestor use note agrees with a use decision, or a proof document's sourced generated no-use carrier has the latest authorized ordinary/mechanical affirmed brief; every connected reviewer has a credited run; and every owed inline disposition is present.

- **Fail:** the pull-request body lacks the required paragraph; the note or mechanical-lane source is missing, stale, malformed, unauthorized, misplaced, or false; a configured reviewer has no credited run; or an owed inline disposition is missing or unauthorized.

A connected reviewer has run when at least one review, inline review comment, or pull-request comment by its login exists; a work-issue comment cannot credit review of the pull request. A pull-request comment saying the review was limited, rate limited, skipped, or still running is a notice of not reviewing and does not count; review bodies and inline comments retain the legacy path's direct credit. Repeated appearances are allowed because a bought second look does not fail the gate, and a completed summary-only pull-request comment counts and owes no invented inline disposition. This notice classification reads vendor comment text rather than a vendor API and can be wrong in both directions when a vendor changes its wording.

## Boundary and tests

The checker job never checks out caller content, executes caller code, writes to the caller, or sends a method other than GET; it has exactly `contents: read`, `issues: read`, `pull-requests: read`, `checks: read`, and `actions: read`. The only caller files it reads are `.github/change-proof.json` and `.tradecraft/work.json` at the pull-request head and resolved base-branch tip. Changed paths, comments, reviews, inline comments, check runs, workflow runs, and run jobs are GitHub API records. The two added scopes let the job re-derive check and workflow identity in private repositories; they add no write authority.

Trusted policy comes from the resolved base-branch tip. The gate also fetches the head copies to report policy changes. A proof document's policy descriptor is verified only when it names either fetched copy at the same repository, path, and revision. A differing digest for either fetched copy remains `declared:` and produces a non-fatal `diagnostic:` naming tradecraft #742; the gate still applies the fetched base-tip policy, so a missing reviewer or false use classification still fails. A descriptor for another producer path or revision is declared as not among the gate's fetched bytes. Missing base policy remains a bootstrap failure.

`proof/check.py` is standard-library-only and has recorded-shape unit tests for both evidence paths, trusted policy, renamed paths, authorization, pagination, source membership, check and workflow identity, declarations, incomplete reads, and the GET-only transport. The pinned proof-v1 schema and interoperability inputs live under `tests/fixtures/proof-v1/` and are not runtime dependencies. The proof job runs the module as its sole `run` step without a checkout. A test compares the embedded script with `proof/check.py` byte for byte after line-ending normalization, and workflow tests assert the exact five permissions in the reusable job, required self caller, and parsed README example, so the tested module and shipped workflow cannot drift; CI runs the suite on Ubuntu and Windows.
