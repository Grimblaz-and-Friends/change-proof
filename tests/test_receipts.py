from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from proof import check
from test_check import (
    BASE_TIP, HEAD, OWNER, REPO, FakeTransport, contents, execute, no_use_note,
    proof_scenario, record, replace_proof_document, scenario, serialized_policy,
)


LAB = "github-actions[bot]"
RUN_ID = 36672170816
REVIEW_ID = 5361748516
JOB_ID = 109749373184
REVIEW_ENDPOINT = f"repos/{REPO}/pulls/17/reviews?per_page=100"
RUN_ENDPOINT = f"repos/{REPO}/actions/runs/{RUN_ID}"
JOBS_ENDPOINT = f"{RUN_ENDPOINT}/jobs?filter=all&per_page=100"
EVIDENCE_PATHS = ("legacy-markers", "proof-v1")
MISSING = object()


def recorded_receipt():
    path = Path(__file__).parent / "fixtures/connected-review/tradecraft-795.trimmed.json"
    return json.loads(path.read_text(encoding="utf-8"))


def receipt_scenario(evidence_path):
    fixture = recorded_receipt()
    review = fixture["review"]
    if evidence_path == "proof-v1":
        transport, document = proof_scenario()
        entry = document["reviewers"][0]
        entry["login"] = LAB
        entry["source"].update({
            "id": REVIEW_ID, "author": LAB, "revision": review["commit_id"],
            "timestamp": review["submitted_at"],
        })
        for revision in (HEAD, BASE_TIP):
            endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={revision}"
            config = json.loads(base64.b64decode(transport.responses[endpoint]["content"]))
            config["connected_reviewers"] = [LAB]
            transport.responses[endpoint] = contents(config)
        document["policy"]["work_configuration"]["sha256"] = hashlib.sha256(
            serialized_policy(config)
        ).hexdigest()
        replace_proof_document(transport, document)
    else:
        document = None
        transport = scenario(
            paths=("docs/readme.md",), comments=[no_use_note()], reviewers=(LAB,),
        )
    transport.responses[REVIEW_ENDPOINT] = [review]
    fixture["run"]["repository"]["full_name"] = REPO
    transport.responses[RUN_ENDPOINT] = fixture["run"]
    transport.responses[JOBS_ENDPOINT] = fixture["jobs"]
    return transport, document


def review_job(transport):
    return next(job for page in transport.responses[JOBS_ENDPOINT]
                for job in page["jobs"] if job["name"] == "review")


def assert_receipt_rejected(transport, reason):
    result, output = execute(transport)
    assert result == 1, output
    assert f"connected reviewer {LAB} credited by" not in output
    assert reason in output
    return output


def test_recorded_lab_receipt():
    fixture = recorded_receipt()
    repo = fixture["repository"]
    endpoint = f"repos/{repo}/actions/runs/{RUN_ID}"
    transport = FakeTransport({
        endpoint: fixture["run"],
        f"{endpoint}/jobs?filter=all&per_page=100": fixture["jobs"],
    })

    credit, error = check._review_receipt(fixture["review"], "review", transport, repo, {})

    assert error is None
    assert credit == (
        f"review #{REVIEW_ID}; run #{RUN_ID}, successful review job #{JOB_ID} attempt #1"
    )
    assert transport.calls == [(endpoint, False), (f"{endpoint}/jobs?filter=all&per_page=100", True)]


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("state", ("COMMENTED", "APPROVED", "CHANGES_REQUESTED"))
def test_lab_receipt_accepts_submitted_review_on_its_own_commit(evidence_path, state):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["state"] = state
    assert transport.responses[RUN_ENDPOINT]["head_sha"] != HEAD

    result, output = execute(transport)

    assert result == 0, output
    assert f"evidence path: {evidence_path}" in output
    assert f"review #{REVIEW_ID}; run #{RUN_ID}, successful review job #{JOB_ID} attempt #1" in output
    assert (JOBS_ENDPOINT, True) in transport.calls


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_rejects_pull_request_even_with_matching_provenance(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[RUN_ENDPOINT]["event"] = "pull_request"

    assert_receipt_rejected(transport, "pull_request_target")


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_rejects_dismissed_review(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["state"] = "DISMISSED"

    assert_receipt_rejected(transport, "review state")


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_uses_run_repository_and_normalizes_identity_case(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    run = transport.responses[RUN_ENDPOINT]
    run["head_repository"] = {"full_name": "fork/source"}
    run["repository"]["full_name"] = REPO.upper()
    run["head_sha"] = run["head_sha"].upper()
    review_job(transport)["head_sha"] = run["head_sha"].upper()
    transport.responses[REVIEW_ENDPOINT][0]["user"]["login"] = LAB.upper()

    result, output = execute(transport)

    assert result == 0, output


INVALID_FIELDS = (
    pytest.param("run", "id", RUN_ID + 1, "different or non-numeric id", id="wrong-run-id"),
    pytest.param("run", "id", float(RUN_ID), "different or non-numeric id", id="non-integer-run-id"),
    pytest.param("run", "repository", {"full_name": "other/repository"}, "repository", id="wrong-repository"),
    pytest.param("run", "path", ".github/workflows/mutation-testing.yml", "workflow path", id="wrong-workflow"),
    pytest.param("run", "path", ".github/workflows/Connected-review.yml", "workflow path", id="case-sensitive-workflow"),
    pytest.param("run", "path", ".github/workflows/renamed-review.yml", "workflow path", id="renamed-workflow"),
    pytest.param("run", "event", "push", "not pull_request_target", id="push"),
    pytest.param("run", "event", "workflow_dispatch", "not pull_request_target", id="manual"),
    pytest.param("run", "event", [], "not pull_request_target", id="malformed-event"),
    pytest.param("run", "head_sha", "f" * 40, "differs from the review commit_id", id="wrong-commit"),
    pytest.param("run", "head_sha", "short", "head_sha", id="short-run-head"),
    pytest.param("run", "head_sha", None, "head_sha", id="non-string-run-head"),
    pytest.param("review", "state", "PENDING", "not counted", id="pending-review"),
    pytest.param("review", "state", "unknown", "not counted", id="unknown-review-state"),
    pytest.param("review", "state", [], "not counted", id="malformed-review-state"),
    pytest.param("review", "submitted_at", "invalid", "submitted_at", id="invalid-submitted-at"),
    pytest.param("review", "submitted_at", "2026-09-30T05:11:31", "submitted_at", id="naive-submitted-at"),
    pytest.param("review", "commit_id", "short", "full commit_id", id="short-review-commit"),
    pytest.param("job", "id", 0, "successful review job", id="zero-job-id"),
    pytest.param("job", "id", float(JOB_ID), "successful review job", id="non-integer-job-id"),
    pytest.param("job", "run_id", RUN_ID + 1, "successful review job", id="wrong-job-run"),
    pytest.param("job", "run_id", float(RUN_ID), "successful review job", id="non-integer-job-run"),
    pytest.param("job", "head_sha", "f" * 40, "successful review job", id="wrong-job-commit"),
    pytest.param("job", "run_attempt", 0, "successful review job", id="zero-attempt"),
    pytest.param("job", "run_attempt", True, "successful review job", id="boolean-attempt"),
    pytest.param("job", "run_attempt", 1.0, "successful review job", id="non-integer-attempt"),
    pytest.param("job", "name", "Review", "successful review job", id="wrong-job-name"),
    pytest.param("job", "status", "in_progress", "successful review job", id="pending-job"),
    *[pytest.param("job", "conclusion", conclusion, "successful review job", id=f"job-{conclusion}")
      for conclusion in ("failure", "cancelled", "neutral", "skipped", None)],
    *[pytest.param(target, field, MISSING, reason, id=f"missing-{target}-{field}")
      for target, fields, reason in (
          ("run", ("id", "repository", "path", "event", "head_sha"), "run #"),
          ("review", ("state", "submitted_at", "commit_id"), "review"),
          ("job", ("id", "run_id", "head_sha", "run_attempt", "name", "status", "conclusion"), "successful review job"),
      ) for field in fields],
)


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("target,field,value,reason", INVALID_FIELDS)
def test_lab_receipt_rejects_unproved_fields(evidence_path, target, field, value, reason):
    transport, _ = receipt_scenario(evidence_path)
    item = {
        "run": transport.responses[RUN_ENDPOINT],
        "review": transport.responses[REVIEW_ENDPOINT][0],
        "job": review_job(transport),
    }[target]
    if value is MISSING:
        item.pop(field)
    else:
        item[field] = value
    if target == "run" and field == "head_sha" and isinstance(value, str):
        review_job(transport)["head_sha"] = value

    assert_receipt_rejected(transport, reason)


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("body", (
    "ordinary review without a run", str(RUN_ID),
    f"https://github.com/{REPO}/actions/runs/{RUN_ID}",
    "<!-- connected-review-attempt:0 -->",
    "<!-- connected-review-attempt:negative -->",
    "<!-- connected-review-attempt:1 extra=true -->",
    "<!-- connected-review-attempt:1",
    f"<!-- connected-review-attempt:{RUN_ID} -->\n<!-- connected-review-attempt:invalid -->",
))
def test_lab_receipt_requires_a_valid_trailing_run_marker(evidence_path, body):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = body

    assert_receipt_rejected(transport, "connected-review-attempt")
    assert not any(endpoint == RUN_ENDPOINT for endpoint, _ in transport.calls)


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("quoted_marker", (
    "<!-- connected-review-attempt:RUN_ID -->",
    "<!-- connected-review-attempt:2 -->",
    "<!-- connected-review-attempt:0 -->",
    "<!-- connected-review-attempt:malformed",
))
def test_lab_receipt_ignores_quoted_markers_before_trailing_receipt(evidence_path, quoted_marker):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = (
        f"Finding quotes `{quoted_marker}` in the diff.\n\n"
        f"<!-- connected-review-attempt:{RUN_ID} -->\n \t"
    )

    result, output = execute(transport)

    assert result == 0, output
    assert f"credited by review #{REVIEW_ID}; run #{RUN_ID}" in output
    assert (RUN_ENDPOINT, False) in transport.calls
    assert not any(endpoint == f"repos/{REPO}/actions/runs/2" for endpoint, _ in transport.calls)


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("suffix", (
    "More findings without a trailing receipt.",
    "<!-- connected-review-attempt:RUN_ID -->",
    "<!-- connected-review-attempt:0 -->",
    "<!-- connected-review-attempt:123",
))
def test_lab_receipt_requires_trailing_marker_even_with_an_earlier_valid_one(evidence_path, suffix):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = (
        f"Quoted <!-- connected-review-attempt:{RUN_ID} -->\n{suffix}"
    )

    assert_receipt_rejected(transport, "trailing")
    assert not any(endpoint == RUN_ENDPOINT for endpoint, _ in transport.calls)


@pytest.mark.parametrize("evidence_path,follow_up,other_path_follow_up", (
    ("legacy-markers", "then re-run change-proof", "then recompose proof"),
    ("proof-v1", "then recompose proof", "then re-run change-proof"),
))
def test_lab_receipt_remedy_matches_selected_evidence_path(evidence_path, follow_up, other_path_follow_up):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[RUN_ENDPOINT] = check.ProofError("run unreadable")

    output = assert_receipt_rejected(transport, "run unreadable")
    assert follow_up in output
    assert other_path_follow_up not in output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_requires_full_commits_even_when_all_records_agree(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["commit_id"] = "short"
    transport.responses[RUN_ENDPOINT]["head_sha"] = "short"
    review_job(transport)["head_sha"] = "short"

    assert_receipt_rejected(transport, "full commit_id")


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_allows_whitespace_and_repeated_identical_markers(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = (
        f"Summary\n<!-- \tconnected-review-attempt: {RUN_ID} \n-->\n"
        f"<!-- connected-review-attempt:{RUN_ID} -->"
    )

    result, output = execute(transport)

    assert result == 0, output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("surface", ("pull-request-comment", "review-comment", "inline-review-comment", "issue-comment"))
def test_lab_receipt_cannot_be_supplied_by_another_surface(evidence_path, surface):
    transport, document = receipt_scenario(evidence_path)
    review = transport.responses[REVIEW_ENDPOINT].pop()
    if surface == "pull-request-comment":
        endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    elif surface == "issue-comment":
        endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    else:
        endpoint = f"repos/{REPO}/pulls/17/comments?per_page=100"
        review["in_reply_to_id"] = 50
    transport.responses.setdefault(endpoint, []).append(review)
    if document is not None:
        document["reviewers"][0]["source"]["kind"] = surface
        replace_proof_document(transport, document)

    assert_receipt_rejected(transport, LAB)

    # A real review restores legacy credit. A selected document must also be recomposed.
    transport.responses[REVIEW_ENDPOINT].append(copy.deepcopy(review))
    if document is not None:
        assert_receipt_rejected(transport, f"recompose proof from review #{REVIEW_ID}")
        document["reviewers"][0]["source"]["kind"] = "review"
        replace_proof_document(transport, document)
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("later_status", ("failure", "in_progress"))
def test_lab_receipt_survives_overall_failure_and_a_failed_or_pending_rerun(evidence_path, later_status):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[RUN_ENDPOINT].update(
        status="in_progress" if later_status == "in_progress" else "completed",
        conclusion=None if later_status == "in_progress" else "failure", run_attempt=2,
    )
    job = copy.deepcopy(review_job(transport))
    job.update(id=JOB_ID + 1, run_attempt=2, conclusion=later_status,
               status="in_progress" if later_status == "in_progress" else "completed")
    page = transport.responses[JOBS_ENDPOINT][0]
    page["jobs"].append(job)
    page["total_count"] += 1

    result, output = execute(transport)

    assert result == 0, output
    assert f"successful review job #{JOB_ID} attempt #1" in output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_finds_success_only_on_a_later_jobs_page(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    page = transport.responses[JOBS_ENDPOINT][0]
    job = review_job(transport)
    page["jobs"].remove(job)
    transport.responses[JOBS_ENDPOINT].append({"total_count": 3, "jobs": [job]})

    result, output = execute(transport)

    assert result == 0, output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_rejects_incomplete_jobs_even_with_a_successful_review(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[JOBS_ENDPOINT][0]["total_count"] = 4

    assert_receipt_rejected(transport, "incomplete")


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_success_in_prepare_and_report_does_not_credit_review(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    review_job(transport)["conclusion"] = "failure"

    assert_receipt_rejected(transport, "no completed successful review job")


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("endpoint,value,reason", (
    (RUN_ENDPOINT, check.ProofError("run GET denied"), "run GET denied"),
    (RUN_ENDPOINT, check.GitHubNotFound("run not found"), "run not found"),
    (RUN_ENDPOINT, [], "object"),
    (RUN_ENDPOINT, ValueError("invalid run JSON"), "invalid run JSON"),
    (JOBS_ENDPOINT, OSError("jobs GET failed"), "jobs GET failed"),
    (JOBS_ENDPOINT, check.GitHubNotFound("jobs not found"), "jobs not found"),
    (JOBS_ENDPOINT, ValueError("invalid jobs JSON"), "invalid jobs JSON"),
    (JOBS_ENDPOINT, {"total_count": 1, "jobs": [None]}, "object"),
    (JOBS_ENDPOINT, {"jobs": []}, "total_count"),
    (JOBS_ENDPOINT, {"total_count": 1, "jobs": []}, "incomplete"),
    (JOBS_ENDPOINT, [{"total_count": 0, "jobs": []}, {"total_count": 1, "jobs": []}], "changed total_count"),
))
def test_lab_receipt_does_not_credit_unreadable_or_incomplete_records(evidence_path, endpoint, value, reason):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[endpoint] = value

    output = assert_receipt_rejected(transport, reason)
    assert "retry unreadable Actions records" in output


@pytest.mark.parametrize("position", (0, 1))
@pytest.mark.parametrize("bad_read", (False, True))
def test_legacy_bad_lab_candidate_does_not_hide_a_proved_receipt(position, bad_read):
    transport, _ = receipt_scenario("legacy-markers")
    bad = copy.deepcopy(transport.responses[REVIEW_ENDPOINT][0])
    bad["id"] += 1
    bad["body"] = f"<!-- connected-review-attempt:{RUN_ID + 1} -->"
    transport.responses[REVIEW_ENDPOINT].insert(position, bad)
    endpoint = f"repos/{REPO}/actions/runs/{RUN_ID + 1}"
    transport.responses[endpoint] = (
        check.ProofError("unreadable candidate") if bad_read
        else dict(transport.responses[RUN_ENDPOINT], id=RUN_ID + 1, path="other.yml")
    )

    result, output = execute(transport)

    assert result == 0, output
    assert f"credited by review #{REVIEW_ID}; run #{RUN_ID}" in output


@pytest.mark.parametrize("bad_read", (False, True))
def test_legacy_lab_run_reads_and_rejections_are_cached(bad_read):
    transport, _ = receipt_scenario("legacy-markers")
    reviews = transport.responses[REVIEW_ENDPOINT]
    reviews.append(copy.deepcopy(reviews[0]))
    if bad_read:
        transport.responses[JOBS_ENDPOINT] = check.ProofError("jobs unreadable")
    else:
        reviews[0]["commit_id"] = "f" * 40

    result, output = execute(transport)

    assert result == (1 if bad_read else 0), output
    assert transport.calls.count((RUN_ENDPOINT, False)) == 1
    assert transport.calls.count((JOBS_ENDPOINT, True)) == 1


@pytest.mark.parametrize("missing", (False, True))
@pytest.mark.parametrize("alternate_kind", ("unmarked", "wrong-workflow", "unreadable", "valid"))
def test_document_lab_pointer_remedy_only_names_a_qualifying_review(missing, alternate_kind):
    transport, document = receipt_scenario("proof-v1")
    reviews = transport.responses[REVIEW_ENDPOINT]
    alternate = copy.deepcopy(reviews[0])
    alternate["id"] = 999
    reviews.append(alternate)
    valid_alternate = alternate_kind == "valid"
    if alternate_kind == "unmarked":
        alternate["body"] = "Unrelated workflow summary"
    elif not valid_alternate:
        alternate["body"] = f"<!-- connected-review-attempt:{RUN_ID + 1} -->"
        endpoint = f"repos/{REPO}/actions/runs/{RUN_ID + 1}"
        transport.responses[endpoint] = (
            check.ProofError("alternate run unreadable") if alternate_kind == "unreadable"
            else dict(transport.responses[RUN_ENDPOINT], id=RUN_ID + 1, path="other.yml")
        )
    if missing:
        reviews.pop(0)
    else:
        reviews[0]["body"] = "Unrelated workflow summary"

    output = assert_receipt_rejected(transport, "review receipt")
    assert ("recompose proof from review #999" in output) is valid_alternate
    assert "credited by review #999" not in output
    if valid_alternate:
        document["reviewers"][0]["source"]["id"] = 999
        replace_proof_document(transport, document)
        result, output = execute(transport)
        assert result == 0, output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("notice", ("Review limit reached", "review skipped", "| Review | **Running** |"))
def test_lab_pull_request_notices_keep_review_owed(evidence_path, notice):
    transport, document = receipt_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT] = []
    transport.responses[f"repos/{REPO}/issues/17/comments?per_page=100"].append(
        record(LAB, notice, id=REVIEW_ID)
    )
    if document is not None:
        document["reviewers"][0]["source"]["kind"] = "pull-request-comment"
        replace_proof_document(transport, document)

    output = assert_receipt_rejected(transport, "review")
    assert "notice" in output or "Running" in output or notice in output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
@pytest.mark.parametrize("has_receipt,disposed", ((False, True), (True, False), (True, True)))
def test_lab_inline_dispositions_and_receipt_remain_separate(evidence_path, has_receipt, disposed):
    transport, document = receipt_scenario(evidence_path)
    if not has_receipt:
        transport.responses[REVIEW_ENDPOINT] = []
    inline = record(LAB, "ordinary workflow finding", id=51, in_reply_to_id=None)
    comments = [inline]
    if disposed:
        comments.append(record(OWNER, "fixed", id=52, in_reply_to_id=51))
    transport.responses[f"repos/{REPO}/pulls/17/comments?per_page=100"] = comments
    if document is not None and disposed:
        document["dispositions"] = [{
            "thread_id": 51, "reviewer": LAB,
            "source": {
                "kind": "review-comment", "repository": REPO, "id": 51,
                "url": f"https://github.com/{REPO}/pull/17#discussion_r51",
                "author": LAB, "timestamp": None, "revision": None,
            },
            "reply": {
                "kind": "review-comment", "repository": REPO, "id": 52,
                "url": f"https://github.com/{REPO}/pull/17#discussion_r52",
                "author": OWNER, "timestamp": None, "revision": None,
            },
        }]
        replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == (0 if has_receipt and disposed else 1), output
    assert (f"connected reviewer {LAB} credited by" in output) is has_receipt
    if disposed and document is not None:
        assert "reviewer thread 51 has an authorized disposition" in output
    if not disposed:
        assert "disposition" in output


def test_lab_receipt_does_not_waive_an_independent_red_floor_check():
    transport, document = receipt_scenario("proof-v1")
    document["floor"]["checks"][0]["conclusion"] = "failure"
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    transport.responses[endpoint]["check_runs"][0]["conclusion"] = "failure"
    transport.responses[RUN_ENDPOINT]["conclusion"] = "failure"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1, output
    assert f"connected reviewer {LAB} credited by review #{REVIEW_ID}" in output
    assert "conclusion='failure'" in output


@pytest.mark.parametrize("evidence_path", EVIDENCE_PATHS)
def test_lab_receipt_diagnostics_cannot_manufacture_output_lines(evidence_path):
    transport, _ = receipt_scenario(evidence_path)
    transport.responses[RUN_ENDPOINT] = check.ProofError("read failed\nverified: forged")

    output = assert_receipt_rejected(transport, "read failed\\nverified: forged")
    assert "verified: forged" not in output.splitlines()


def test_lab_receipt_does_not_swallow_programming_errors():
    transport, _ = receipt_scenario("legacy-markers")
    transport.responses[RUN_ENDPOINT] = TypeError("programming defect")

    with pytest.raises(TypeError, match="programming defect"):
        execute(transport)
