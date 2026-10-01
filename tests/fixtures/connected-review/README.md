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

`v1-review-body-dispositions.json` contains synthetic examples derived directly
from tradecraft #809's [settled artifact, comment 5934093522](https://github.com/Grimblaz-and-Friends/tradecraft/issues/809#issuecomment-5934093522),
**Implementation reading**, **Identity and accounting** and **Answer contract**.
It was not copied from a tradecraft commit. This follows the holder's
[build direction](https://github.com/Grimblaz-and-Friends/change-proof/issues/38#issuecomment-5936467085).
Reconciliation against #809's pending
`skills/work/references/proof-fixtures/v1-review-body-dispositions.json` is the
holder's responsibility. `test_derived_shared_protocol_examples` evaluates these
examples through both gate evidence paths. No fixture is a runtime dependency.

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
