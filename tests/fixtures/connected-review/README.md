# Recorded connected-review receipt

**Purpose:** retain GitHub's receipt provenance for change-proof #35's positive
case. **Audience:** builders and reviewers running the receipt tests. **Success:**
the real record and each synthetic counterexample remain distinguishable.

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
