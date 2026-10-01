# Connected-review fixtures

**Purpose:** retain receipt and body-finding inputs with their provenance.
**Audience:** builders and reviewers running the connected-review tests.
**Success:** recordings, derived protocol examples and synthetic overlays remain
distinguishable.

`tradecraft-795.trimmed.json` was fetched with GET on 2026-09-30 from
`Grimblaz-and-Friends/tradecraft`:

```text
gh api --method GET repos/Grimblaz-and-Friends/tradecraft/pulls/795/reviews/5361748516
gh api --method GET repos/Grimblaz-and-Friends/tradecraft/actions/runs/36672170816
gh api --method GET --paginate --slurp "repos/Grimblaz-and-Friends/tradecraft/actions/runs/36672170816/jobs?filter=all&per_page=100"
```

It keeps the consumed review, run, and job fields, plus the run's overall status,
conclusion, and attempt for counterexamples. The review body is trimmed to its
verbatim trailing attempt marker; other review prose and unused API fields are
removed. Every returned job and jobs page is retained. No retained field is
synthetic.

`tests/test_receipts.py::test_recorded_lab_receipt` checks those records at their
actual repository. Its two gate evidence worlds reuse that receipt shape with
the run repository changed to the harness repository and existing synthetic
floor, policy, use, and proof records. All further mutations are synthetic
overlays in the tests. Those evaluations are not recordings of PR #795's gate.

## Body findings for #38

`v1-review-body-dispositions.json` is copied verbatim from tradecraft commit
`8421327e84b3e99ad72d9329f8cc1dd445ef89fa`, git blob
`8b6170f75e6c838da2ff5484f9616804ec1b9cee`, with 92 cases, using this GET on
2026-10-01:

```text
gh api --method GET -H "Accept: application/vnd.github.raw" "repos/Grimblaz-and-Friends/tradecraft/contents/skills/work/references/proof-fixtures/v1-review-body-dispositions.json?ref=8421327e84b3e99ad72d9329f8cc1dd445ef89fa"
```

`test_shared_review_body_dispositions` replays every case in the file directly
through the gate's body-finding check. It compares
missing findings with their carrying review ids, missing whole-review answers,
and all unidentified reviews. It does not compare `ignored_authors`, a producer
diagnostic the gate does not emit. The fixture's `.gitattributes` entry preserves
its bytes without text conversion.

This copy replaces tradecraft commit
`e957cf9467f6e2b36ac0bc180f517bfab793e203`, git blob
`d2a2a1d62bd49b9045a78afaeef769b67afad8e7`. Its corrected `bundled-body-answer`
expectation follows the
[Steward's ruling, comment 5938424447](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5938424447).
The labelled override and its guard were removed after the guard failed on the
corrected expectation, demanding removal.

The later [Steward's section-depth ruling, comment 5939291068](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5939291068)
supersedes `innermost-declared-section-owns-identity`: its nested summary is
content, so `cr-comment:v1:alpha` from review 100 remains owed while
`missing_reviews` and `unidentified_reviews` both change from `[100]` to `[]`.
The replay has exactly one labelled expectation override for that case, citing
the ruling, with a guard requiring removal once the file's own expectation
matches. The pinned bytes remain unchanged; #809's corrected file will replace
this copy and remove the override.

`derived-review-body-examples.json` remains the gate's own synthetic coverage,
derived directly from tradecraft #809's [settled artifact, comment 5934093522](https://github.com/Grimblaz-and-Friends/tradecraft/issues/809#issuecomment-5934093522),
**Implementation reading**, **Identity and accounting** and **Answer contract**.
It was not copied from a tradecraft commit. This follows the holder's
[build direction](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5936467085).
These derived examples came first and were then reconciled to #809's shared
file under the [Steward's rulings, comment 5936971325](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5936971325).
`test_derived_shared_protocol_examples` evaluates the derived examples through
both gate evidence paths. Added gate-owned examples follow the
[structural forms ruling](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5937322711),
its [bold-line amendment](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5937338526)
and the [section and code-span rulings](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5937356812).
They cover new labels, declarations with deficits, anchored-title controls, and
code spans separated by paragraph breaks or left unmatched. No fixture is a
runtime dependency.

`tradecraft-654-body.trimmed.json` and `tradecraft-757-body.trimmed.json` were
fetched with GET on 2026-10-01:

```text
gh api --method GET repos/Grimblaz-and-Friends/tradecraft/pulls/654/reviews/5254305105
gh api --method GET --paginate repos/Grimblaz-and-Friends/tradecraft/pulls/654/comments
gh api --method GET repos/Grimblaz-and-Friends/tradecraft/pulls/757/reviews/5346992676
gh api --method GET --paginate repos/Grimblaz-and-Friends/tradecraft/pulls/757/comments
```

They retain the consumed review fields, verbatim bodies, and every inline record
with its review join, author and reply parent. User objects are retained intact.
Unused top-level API fields are removed; no retained value is synthetic.
`test_recorded_vendor_sections_keep_their_real_accounting` checks the recordings
at their actual repository and pull requests.
`test_recorded_declaration_shapes_check_missing_identities` also uses the #654,
#733 and #757 bodies through both evidence paths, with synthetic metadata,
answered inline roots and proof membership. Its negative controls remove only
the recorded finding identity, so an ignored declaration cannot pass the test.

`tradecraft-757-walkthrough.trimmed.json` was fetched with GET on 2026-10-01:

```text
gh api --method GET repos/Grimblaz-and-Friends/tradecraft/issues/comments/5817397750
```

It retains the comment's id, intact user object, HTML URL and complete verbatim
body, including the `Security review details` block and its
`Security Findings and Attack Paths` heading. Only unused top-level API fields
are removed; the body is not trimmed and no retained value is synthetic.
`test_recorded_walkthrough_adds_no_obligation_beside_nitpick` checks this comment
alongside the recorded #757 review and inline records at their actual repository
and pull request: only the identified nitpick needs a body answer. It also reuses
both verbatim bodies through both evidence paths in synthetic worlds, with
synthetic review metadata, inline roots and replies, proof membership, and a
nitpick answer. The declaration rules follow the
[Steward's ruling, comment 5937284942](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5937284942).

`tradecraft-733-review-joins.json` separately restores the
`pull_request_review_id` fields omitted by the earlier #733 world's trimming,
from this GET on 2026-10-01:

```text
gh api --method GET --paginate repos/Grimblaz-and-Friends/tradecraft/pulls/733/comments
```

The original `proof-v1/recorded/world-tc733.trimmed.json` stays intact.
`test_original_tradecraft_733_record_now_requires_body_answers` checks its new
failure. `test_historical_proof_with_labeled_join_and_answer_overlays_passes`
applies these recorded joins and a clearly labeled synthetic identity answer to
produce the positive replay; the original answer linked the review but did not
name the finding identity. Other scenario and answer mutations in
`test_body_findings.py` are synthetic overlays.
