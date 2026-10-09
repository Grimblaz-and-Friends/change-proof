# change-proof

**Purpose:** define and operate the independent release-proof gate used by this repository and its adopters. **Audience:** repository owners, holders, and adopters configuring or interpreting the gate. **Success:** a reader can grant the exact read boundary, supply one authorized proof document per head, declare the CI jobs that stop a merge, and distinguish facts the gate verified from producer declarations and diagnostics.

Change proof is a reusable GitHub workflow for pull requests: it requires the pull-request body's `**Path departures:**` paragraph, decides from caller-owned path rules whether use was required unless the owner's verified mechanical lane exempts it, verifies the applicable use or no-use evidence and every configured connected reviewer, and requires authorized dispositions on their inline threads, identified body findings and unidentified reviews before the proof passes.

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

A workflow's token cannot re-run workflow runs, and this design grants no write permission. The proof's generated no-use decision stays pinned to the current head. A `use` note for an earlier head counts only with `changed=false` and complete, proved ancestry. Base-reachable non-merge commits and proved imported paths in catch-up merges stale that use only on use-buying paths the pull request also changes, with an exemption for a proved change confined to the trusted policy's declared version field. Every other intervening use-buying path, including a merge's own edit, still stales use. Each commit is judged separately, including both names of a rename, so a later revert cannot erase an earlier refusing edit. The evidence contract below specifies the reads and failure behavior.

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

The same policy may add an optional top-level `version` object; `schema_version` stays 1. For example, add this member to the use-rules object:

```json
{
  "version": {
    "path": "package.json",
    "field": "version",
    "increment": "patch"
  }
}
```

`version` must carry exactly `path`, `field` and `increment`. The path is a nonempty repository-relative POSIX file path: absolute or drive-prefixed paths, backslashes, control characters and empty, `.` or `..` components are invalid. The field is a nonblank literal top-level JSON key, not an instruction to traverse a dotted path or JSON pointer. The increment must be `major`, `minor` or `patch`; the gate validates it but applies no increment and imposes no semantic-version format. The file must contain a JSON object for an exemption, though its name need not end in `.json`. A malformed trusted declaration fails the policy. An absent declaration grants no version exemption. Only the base-tip declaration has authority; an added, changed or malformed head declaration cannot grant one, including during the existing bootstrap failure. This repository has no version file and declares none.

The policy may also add optional `floor`, naming every CI job whose red must stop a merge:

```json
{
  "floor": {
    "jobs": [
      {"workflow": ".github/workflows/ci.yml", "job": "lint-and-test (ubuntu-latest)"},
      {"workflow": ".github/workflows/ci.yml", "job": "lint-and-test (windows-latest)"},
      {"workflow": ".github/workflows/ask-declaration.yml", "job": "ask-declaration"}
    ],
    "stall_after_seconds": 3600
  }
}
```

`floor` carries required `jobs` and optional `stall_after_seconds`, with no other members. Each job entry carries exactly `workflow` and `job`; duplicate pairs are invalid. Workflow paths must be repository-relative literal files under `.github/workflows/`, ending in `.yml` or `.yaml`. Absolute paths, drive prefixes, backslashes, controls, empty or dot components, globs and `@ref` suffixes are invalid. Job names are case-sensitive nonblank text without controls, as exposed by Actions and its check run; each matrix expansion is a separate entry. The stall bound is a positive integer excluding booleans, defaulting to 3600 seconds. An absent floor or `jobs: []` retains the builder floor. A malformed trusted declaration fails; a read error never becomes absence. This gate half adds no declaration to its own repository.

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

Pull requests to this repository take the same release proof as its callers. A change here is reported ready for merge only after its body has the required path-departures paragraph, the change-proof check has run, every configured connected reviewer has run, and every owed reviewer thread, body finding and unidentified review has a marker-producer disposition.

The gate evaluates only `proof-v1`: one authorized pull-request comment framed by a `tradecraft:proof:v1 head=FULL_SHA` envelope followed by exactly one JSON fence. The fenced object is the input; its readable rendering is not. A missing authorized current-head document fails with `run proof` as the remedy. Older documents remain historical evidence. Multiple current documents, invalid selected documents, and unsafely scoped authorized envelopes fail. Unauthorized comments supply neither evidence nor authority. Standalone markers cannot replace the document.

The gate derives the floor from `.github/change-proof.json` at the resolved base-branch tip B and public executions at the live head H. Adding, editing or deleting the declaration at H does not change that pull request's obligation. Its output names B, the declaration path, digest, and declared job count. A moved base tip or head invalidates completion.

A declared floor passes without a builder marker when every declared job's selected execution completed with `success`. The proof records `floor.head: H`, `floor.source: null`, and every selected declared check. The gate enumerates current-head workflow runs and check runs with complete pagination, reads candidate runs by numeric identity, matches the exact top-level workflow path (removing an API ref suffix), then reads jobs with `filter=all` and complete pagination. Job names match exactly, including expanded matrix names; `check_run_url` associates each job with its check. Workflow display names, IDs, reusable-workflow references, and third-party checks cannot substitute for that provenance.

The greatest run ID for each declared workflow path and triggering event selects its newest execution. Every event that ran that workflow at H must satisfy each declared job: a newer green push cannot hide a red pull-request run. The output records the event for each selected execution. Within each run, the job's greatest attempt governs; a completed partial rerun may retain another job's earlier success in that same run. When the current gate runs in that workflow, its unfinished attempt also retains completed declared jobs from earlier attempts; the gate itself never supplies floor evidence. A newer completed run that omits a job cannot borrow an older run. A queued run without jobs, or another unfinished newer attempt whose inventory cannot establish whether a job is being rerun, stays pending. Same-named jobs in one selected attempt remain separate and must all succeed.

An absent workflow, a job omitted by a completed successful/skipped/neutral run, or a job concluding `skipped` or `neutral` takes the builder fallback. The document then names an authorized current-head `tradecraft:floor:v1 head=FULL_SHA status=pass` source and every visible selected declared check. Missing/nonexecuted jobs are printed as diagnostics. Declared `failure`, `cancelled`, `timed_out`, `action_required`, `startup_failure`, or `stale` conclusions block, including when the selected run concludes red before creating the declared job; a builder marker cannot override them. Unfinished jobs fail as pending within the bound and stalled at or beyond it. The clock uses the job/check start, otherwise that attempt's start, against the observation time. Run creation can time an initial queued attempt; it cannot time a later rerun. Invalid clocks, unknown completed conclusions, contradictory identities, incomplete pages, or unavailable relevant provenance fail as unverifiable. Blocking and unverifiable facts precede pending work, which precedes fallback.

Undeclared checks neither satisfy nor block a declared floor, including during fallback. Runs with top-level paths outside `.github/workflows/`, including GitHub-managed dynamic workflows, are excluded before repository workflow-path validation or job reads. An Actions-app check without a parseable run identity is also excluded when its name differs from every declared job; a matching or unavailable name leaves its provenance unverifiable. Excluded checks are recorded in the output.

With no declared jobs, the builder-source floor and retained non-gate public checks keep their existing contract below. The gate resolves issue-comment sources only through the document's named work issue, and pull-request comments, reviews, and inline comments only through the evaluated pull request. It constructs authenticated endpoints from identities and never follows proof-supplied URLs. A builder marker attests to execution; the gate verifies its lawful public source and current head, rather than certifying local execution from its prose.

The optional `policy.floor` descriptor uses the existing policy-source shape: `repository`, `path`, `revision`, and `sha256` of the raw base-tip policy blob; a confirmed absent blob is represented by `null`. Existing v1 documents without it remain structurally valid. The gate derives authority from its own base read in every case. Descriptor disagreements remain provenance diagnostics under the existing policy contract below.

The proof's `use` object is the sole no-use carrier, retaining its current head, classification, applicability and reason, plus its mechanical-lane source where applicable. The separate no-use marker supplies no release evidence. Ancestor relaxation applies only to bought use evidence.

A sourced generated no-use record is the proof-document carrier for the owner-affirmed mechanical lane. Its source must be an issue comment on the document's distinct work issue, authored by a marker producer in the trusted base-tip configuration. The gate first selects the work issue's latest authorized comment containing an exact, attribute-free `tradecraft:affirmed-brief:v1` marker; that record must then contain exactly one lawful `Review risk:` / `Review lane:` pair, and only `ordinary` / `mechanical` exempts use. The gate reads the complete work-comment order at evaluation time, so a later authorized affirmed record supersedes an older source even when the proof has not changed. It never follows the source URL or trusts its claimed author, timestamp, reason, or producer version. The carrier must still be current-head, generated, `not-required`, without intervening commits, and have a nonempty reason.

A verified exception names its authority and keeps the path decision visible:

```text
verified: owner-affirmed mechanical lane in OWNER/REPO#N issue-comment #ID exempts use; changed paths would otherwise require use
verified: owner-affirmed mechanical lane in OWNER/REPO#N issue-comment #ID exempts use; changed paths would otherwise not require use
```

Output labels facts and limitations by source. `verified:` names a fact re-derived from GitHub records or trusted policy. `declared:` preserves an authorized producer statement about local dispatch, staffing, model settings, bundles, or policy provenance the gate did not fetch. `producer-diagnostic:` preserves a limitation reported by that producer, while `diagnostic:` is reserved for a limitation the gate derived itself; neither becomes an automatic failure. Embedded line breaks are escaped so producer content cannot manufacture another output line.

In an undeclared repository, public floor checks are matched by check id, application, exact name, workflow and run identities, head, status, conclusion, and timestamps. Every retained current-head check must be present in the document and completed with `success`, `neutral`, or `skipped`; `neutral` and `skipped` retain those distinct names and are not described as successful executions. For Actions checks, job records establish reruns: a newer run, or a newer attempt of the same run, supersedes an older execution inside one application/workflow/name group, while same-named checks in one run attempt and same-named checks from different workflows stay separate. Outside Actions, checks from the same app, in the same check suite, under the same exact name are reduced to the run with the latest start time, with the higher check id breaking a tie. A check without an app id, check-suite id or usable start time stays in the floor and neither supersedes nor is superseded by another check. Each third-party check removed this way prints a `superseded:` line naming its check id and the retained replacement's check id. The running gate's own job and a caller's reusable proof job are excluded only when exactly one job in that run attempt matches the called `Change proof` identity; zero or multiple matches fail with the candidate jobs named, and unrelated caller jobs remain in the floor set. Each excluded proof execution prints an `excluded:` line naming its run and check and whether it was the current gate, an earlier attempt of that gate, or a separate caller invocation.

Every ready pull-request body must have a Markdown paragraph whose first logical line begins at column zero with the exact lead-in `**Path departures:**`. Write that lead-in in the Markdown source, for example in the Write tab, because copying it from the rendered preview drops the `**` markers. The checker verifies only that paragraph's presence; it does not interpret or require any content after the lead-in. A green result therefore describes the body as it stood when the gate ran, and certifies only that the paragraph was present then; the release report is where its content is read. A heading, list item, block quote, indented or fenced code, HTML comment, raw HTML block, or mention later in an existing paragraph does not count. For a blank-line-terminated HTML block, a line directly after a tag line such as `</details>` still belongs to the block, so put a blank line before the paragraph. A `---` or `===` line immediately below the paragraph, with no blank line between, makes it a setext heading and therefore does not count.

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

`CHANGED` is `true` or `false`; `STAFFING_STATUS` is `qualified` or `degraded`; and a degraded run carries the nonempty hyphenated `same_vendor_reason` while a qualified run does not. A note naming the current pull-request head may carry either `CHANGED` value. A note naming an earlier head applies only with `changed=false`. The single, unpaginated GitHub comparison must report `ahead` or `identical`, name the note head as its merge base, and return as many intervening commits as its `ahead_by` value. A status or merge base that does not prove ancestry, a missing or mismatched `ahead_by`, or a commit without a full revision refuses the candidate. Each returned commit is read through the paginated `repos/{repo}/commits/{sha}?per_page=100` endpoint, and both `filename` and `previous_filename` are classified under the trusted base-tip policy.

A non-merge commit reachable from the fixed, resolved base tip is judged by overlap: it refuses only when a use-buying path is also in the complete current pull-request changed-path list. Equality with the base tip establishes reachability directly; otherwise a `COMMIT...BASE_TIP` comparison must report `ahead` or `identical` with that commit as its merge base. Missing or malformed parents or membership reads grant no relaxation. Every other non-merge commit refuses on any use-buying path, even one absent from the final pull-request diff.

A merge's paths relative to its first parent are split, including when the merge itself is reachable from the base tip. A path receives overlap treatment only when another valid parent is reachable from that tip and its side changed the path since the parents' merge base. The gate obtains that merge base through `FIRST...OTHER`, then reads the net changed paths through `MERGE_BASE...OTHER`. A merge base equal to `OTHER` contributes no paths, because that side is already contained in the first parent. For multiple other parents, provenance from any eligible side suffices. Both names of renames participate, with slash normalization and case-sensitive equality. Every remaining merge path is the merge's own edit and refuses on any use-buying path, including a restoration to base content that removes the path from the pull-request diff.

Parent comparisons and side-file records supply positive provenance. Missing, malformed, failed or capped records grant no relaxation for an unproved path; a side edit reverted before its parent tip contributes no net change. The comparison commit-list lengths are not history-completeness tests; the original evidence-head-to-current-head comparison owns that check. All endpoints are constructed in the evaluated repository. Commit records, base reachability, parent comparisons and version comparisons are cached across ancestor candidates within one evaluation; no cache outlives it.

Overlap uses the net pull-request diff. The affirmed residual remains: when both sides changed a path and the merge resolves it to base-tip content, that imported path drops out of the diff and the use carries. The gate does not substitute historical overlap for that rule.

In the overlap branch alone, an ordinary modification of the declared version file is exempt when contents GETs at that commit and its first parent both yield unambiguous JSON objects equal after removing only the declared top-level key. Formatting and object-key order do not matter; array order, nested keys and other values do, including booleans versus numbers. Adding, changing or removing the declared key may qualify. Missing, renamed, deleted, unreadable or non-JSON files, duplicate keys, invalid numeric constants and missing first parents grant no exemption. The contents comparison reads no file mode; eligibility depends on GitHub reporting an ordinary modification. Another overlapping imported use-buying file or any merge-owned use-buying path in the same commit still refuses. A separate change-owned version bump or a merge-owned version edit retains the ordinary rule. A catch-up's version resolution qualifies only inside the merge and only when an eligible other parent's side changed the declared file; its contents comparison still uses the first parent.

Failed ancestry or commit-file reads—including a GET failure, invalid JSON, or a page that omits `files`—fail the document's selected use source. Proof-v1 intervening records remain exactly `{sha, paths}`, retaining all fetched paths, including an exempted version path; the gate derives classification itself.

For carried use, the `verified:` output names its evidence head and explains each intervening commit: it changes no use-buying path, its imported use-buying paths do not overlap the pull-request diff, or it qualifies for the version-only exemption. A commit can carry for both non-overlap and version exemption. A stale finding names the evidence head, the first refusing commit and every refusing path in that commit; it stops before later commits.

When the paths do not buy use, the document records a current-head generated `not-required` use decision with a nonempty reason. A sourced generated decision is checked against the mechanical-lane contract above. A false use classification fails even if other evidence is complete.

Every top-level inline comment from a connected reviewer needs a reply by a marker producer whose first non-blank line begins with one of the closed dispositions: `fixed`; `fixed — nothing else found it`; `fixed in #<N>`; `yours — in the release report`; `declined — <why it earns no end>`; `duplicate of <the earlier comment>`; `lapsed — <the rule we do not run>`.

The checker ignores leading blank lines and whitespace and one balanced Markdown inline wrapper—backticks, asterisks or underscores—around the whole line or its opening disposition word.

Findings outside inline threads are checked directly from GitHub, without new proof-document fields. Only submitted reviews create body-finding or unidentified-review obligations. Conversation comments are read only as answers; their identities and declarations create no obligations. For configured CodeRabbit and lab reviewers, genuine `<!-- cr-comment:v1:IDENTITY -->` and `<!-- tradecraft-review-finding:v1:RUN_ID:ORDINAL -->` markup identifies a finding, including CodeRabbit's blockquoted form. Code examples identify nothing. An inline code span cannot cross a blank line, including a blockquoted blank line; an unmatched backtick masks nothing. Fenced code blocks retain their existing handling. Every identified category counts, including nitpicks; repeated identities count once within their reviewer and pull request. Findings from earlier heads stay owed. A body identity needs no second answer only when that reviewer's identical identity appears on an inline root with an authorized disposition reply.

Declarations are accounted for within their own review: inline roots join by `pull_request_review_id` and reviewer. CodeRabbit's `Actionable comments posted: N` line is checked against inline roots. Its sections are declared by a `<summary>` title or a line wholly consisting of one bold span, optionally blockquoted. After stripping one leading emoji or symbol run, the whole trimmed title must be `<label> comments (N)`, where the label is one or more words and `N` is digits; each section is checked against its distinct body identities. This includes Outside diff range, Nitpick, Duplicate and future labels of that shape. No title containing `Findings` declares a CodeRabbit section. For every other configured reviewer, a findings heading's title starts with `Findings`, as in `Findings`, `Findings (N)` or `Findings: N`; merely containing that word declares nothing. Aggregate totals, including the lab's `N validated finding(s).`, are checked against inline findings plus body identities, counting exact restatements once.

A declared section ends at the next section declaration of either shape at its own level, a `---` divider at its own `<details>` depth, or, for a summary declaration, its matching `</details>`, whichever comes first. Matching counts nesting, so an inner finding's closing tag does not end its containing section. Blockquote prefixes do not change depth. Within a declared section, a candidate summary or bold declaration inside its content is content. CodeRabbit's entries are the section's direct `<details>` children; lists and headings declare entries only at the section's own depth. Nested finding prose, bullets, analysis-chain dividers and titles declare neither sections nor entries. Identities credit their containing section; later sections cannot fill an earlier deficit. Another reviewer's counted findings section may use inline roots only when its own content is empty or exactly `None.`, `No findings.` or `No findings were found.`. Other nonempty content needs an identity for each entry; prose only prevents completeness and never creates a finding identity.

Summaries, walkthroughs, Codex opening notes and identity-free fix prompts create no additional obligation. Incomplete, duplicated, malformed or inconsistent declarations make a review **unidentified**, which requires its own answer alongside any identified findings. A whole-review answer clears that obligation while the review remains classified as unidentified.

A body answer is one pull-request conversation comment by a marker producer, opening on its first nonblank line with an **unformatted** existing disposition. Repository owner and name comparisons in answer links and inline-exemption URLs are case-insensitive. Its finding identity comes only from the canonical `[identity](source-review-link)` pair, whose label is the full identity and whose linked review carries it, for example:

```text
declined — unnecessary; [cr-comment:v1:IDENTITY](https://github.com/OWNER/REPO/pull/N#pullrequestreview-REVIEW_ID)
```

Use the lab identity in the same form. An unidentified review receives a separate answer:

```text
fixed — addressed the unaccounted findings; [unidentified review](https://github.com/OWNER/REPO/pull/N#pullrequestreview-REVIEW_ID)
```

Each answer targets one finding or one unidentified review. A link is a target only when it names a review on this pull request carrying an owed body identity or classified as unidentified. Every other link is evidence, including every `#issuecomment` link and reviews with no obligation. Identity text elsewhere, including prose, evidence-link labels, code spans and linked comments, is evidence and never a second answer identity. The `yours` opening retains the literal phrase `yours — in the release report`; put any release-report link after that phrase.

An answer linking two or more distinct obligation-source reviews answers nothing; repeated links to the same review count once. Multiple canonical finding pairs also cannot group different findings into one answer. An unauthorized author or an identity without its canonical pair answers no finding. A whole-review answer must link its unidentified review. An identity answer does not also answer its unidentified review. Conversation answers replace neither inline replies nor reviewer receipts; proof-v1 still requires its existing inline disposition entries. The gate's `missing:` and `satisfy:` lines name the source, identity or unmet declaration and the required comment.

The checker returns exit `0` only when it has evaluated the pull request head's evidence and that evidence satisfies this contract; a result that does not evaluate the evidence is not a pass.

- **Pass:** the pull-request body has the required paragraph; the applicable declared CI or authorized builder floor passes; a current-head generated no-use record agrees with a no-use decision, a valid current-head or qualifying ancestor use note agrees with a use decision, or a proof document's sourced generated no-use carrier has the latest authorized ordinary/mechanical affirmed brief; every connected reviewer has a credited run; and every owed inline, body-finding and whole-review disposition is present.

- **Fail:** the pull-request body lacks the required paragraph; the note or mechanical-lane source is missing, stale, malformed, unauthorized, misplaced, or false; a configured reviewer has no credited run; or an owed inline, body-finding or whole-review disposition is missing or unauthorized.

A connected reviewer has run when at least one review, inline review comment, or pull-request comment by its login exists, with the shared workflow login `github-actions[bot]` subject to the provenance rule below; a work-issue comment cannot credit review of the pull request. A pull-request comment saying the review was limited, rate limited, skipped, or still running is a notice of not reviewing and does not count. For other logins, review bodies and inline comments retain direct credit, repeated appearances are allowed, and a completed summary-only pull-request comment counts and owes no invented inline disposition. This notice classification reads vendor comment text rather than a vendor API and can be wrong in both directions when a vendor changes its wording.

`github-actions[bot]` is shared by workflows, so its receipt must be a submitted pull-request review in state `COMMENTED`, `APPROVED` or `CHANGES_REQUESTED`, with a timestamp, a full `commit_id`, and an exact `<!-- connected-review-attempt:RUN_ID -->` marker on the body's last non-blank line. `RUN_ID` must be a positive decimal id without leading zeros; the untrimmed line must contain only that marker, with exactly the spaces shown. Blank lines (including whitespace-only lines) after it are ignored, as is all earlier text, including quoted markers, for run identification. GitHub's run record must identify the same repository, the exact fixed path `.github/workflows/connected-review.yml`, a `pull_request_target` event, and the review's commit. Renaming that file stops receipt credit. The gate reads jobs from every attempt, with full pagination, and requires a completed successful job named `review`, either directly or after nonempty caller names separated by ` / `, belonging to that run and commit. An earlier successful attempt still counts after a later failed or running attempt; the run's overall result does not determine receipt credit. The comparison is to the review's commit, which may precede the current head. Other workflows' posts, summary comments, and inline comments cannot supply this receipt; their owed inline dispositions and independent floor failures still apply. A proof document must name the qualifying review itself. Unreadable or incomplete provenance leaves review owed; when another qualifying review exists, recompose the document from that review.

## Boundary and tests

The checker job never checks out caller content, executes caller code, writes to the caller, or sends a method other than GET; it has exactly `contents: read`, `issues: read`, `pull-requests: read`, `checks: read`, and `actions: read`. It reads `.github/change-proof.json` and `.tradecraft/work.json` at the pull-request head and resolved base-branch tip. When the trusted base-tip policy declares a version file, ancestor-use verification may also read that one file at an intervening commit and its first parent to determine whether only the declared top-level field changed. Changed paths, commit parents, comparisons, comments, reviews, inline comments, check runs, workflow runs, and run jobs are GitHub API records. The two added scopes let the job re-derive check and workflow identity in private repositories; they add no write authority.

Trusted policy comes from the resolved base-branch tip. The gate also fetches the head copies to report policy changes. A proof document's policy descriptor is verified only when it names either fetched copy at the same repository, path, and revision. A differing digest for either fetched copy remains `declared:` and produces a non-fatal `diagnostic:` naming tradecraft #742; the gate still applies the fetched base-tip policy, so a missing reviewer or false use classification still fails. A descriptor for another producer path or revision is declared as not among the gate's fetched bytes. Missing base policy remains a bootstrap failure.

`proof/check.py` is standard-library-only and has recorded-shape unit tests for the proof-document path, trusted policy, renamed paths, authorization, pagination, source membership, check and workflow identity, declarations, incomplete reads, and the GET-only transport. The pinned proof-v1 schema and interoperability inputs live under `tests/fixtures/proof-v1/` and are not runtime dependencies. The proof job runs the module as its sole `run` step without a checkout. A test compares the embedded script with `proof/check.py` byte for byte after line-ending normalization, and workflow tests assert the exact five permissions in the reusable job, required self caller, and parsed README example, so the tested module and shipped workflow cannot drift; CI runs the suite on Ubuntu and Windows.
