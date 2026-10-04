from __future__ import annotations

import copy
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path

import pytest

from proof import check
from test_check import FakeTransport, contents, record


FIXTURES = Path(__file__).parent / "fixtures" / "proof-v1"
WORLD = json.loads((FIXTURES / "v1-ci-floor.json").read_text(encoding="utf-8"))
CASES = WORLD["cases"]
REPO = WORLD["repository"]


def fixture_transport(case):
    head, base = case["head"], case["base_tip"]
    config = {"schema_version": 1, "product_repositories": [],
              "marker_producers": ["holder"], "connected_reviewers": []}
    pull = f"repos/{REPO}/pulls/19"
    responses = {
        pull: {"number": 19, "draft": False, "head": {"sha": head},
               "base": {"ref": "main", "sha": "c" * 40}, "changed_files": 1,
               "body": "**Path departures:** Expected path ran."},
        f"repos/{REPO}/git/ref/heads/main": {"object": {"sha": base}},
        f"{pull}/files?per_page=100": [{"filename": "docs/readme.md"}],
        f"{pull}/reviews?per_page=100": [],
        f"{pull}/comments?per_page=100": [],
        f"repos/{REPO}/issues/12/comments?per_page=100": [],
        f"repos/{REPO}/actions/runs?head_sha={head}&per_page=100": case["workflow_runs"],
        f"repos/{REPO}/commits/{head}/check-runs?filter=all&per_page=100": case["check_runs"],
    }
    for revision, policy in ((head, case["head_policy"]), (base, case["base_policy"])):
        responses[f"repos/{REPO}/contents/.tradecraft/work.json?ref={revision}"] = contents(config)
        responses[f"repos/{REPO}/contents/.github/change-proof.json?ref={revision}"] = (
            check.ProofError(policy["error"]) if "error" in policy else
            check.GitHubNotFound("confirmed absent base policy") if policy.get("absent") else
            contents(policy["content"])
        )
    for run in case["runs"]:
        responses[f"repos/{REPO}/actions/runs/{run['id']}"] = (
            check.ProofError(run["error"]) if "error" in run else run["record"]
        )
    for jobs in case["jobs"]:
        responses[f"repos/{REPO}/actions/runs/{jobs['run_id']}/jobs?filter=all&per_page=100"] = (
            check.ProofError(jobs["error"]) if "error" in jobs else jobs["pages"]
        )
    document = json.loads((FIXTURES / "v1-valid.json").read_text(encoding="utf-8"))
    document["reviewers"] = []
    patch = copy.deepcopy(case["document_patch"])
    floor_policy = patch.pop("policy_floor", "omitted")
    document.update(patch)
    for name, path, value in (
        ("work_configuration", ".tradecraft/work.json", config),
        ("use_rules", ".github/change-proof.json", case["base_policy"].get("content", {})),
    ):
        document["policy"][name] = {"repository": REPO, "path": path, "revision": base,
            "sha256": hashlib.sha256((json.dumps(value) + "\n").encode()).hexdigest()}
    if floor_policy != "omitted":
        document["policy"]["floor"] = floor_policy
    comments = [record("holder", f"<!-- tradecraft:proof:v1 head={head} -->\n\n"
        f"```json\n{json.dumps(document)}\n```", id=501)]
    mode = case.get("proof_mode")
    if mode == "missing":
        comments = []
    elif mode == "unauthorized":
        comments[0]["user"]["login"] = "stranger"
    elif mode == "older":
        comments[0]["body"] = comments[0]["body"].replace(head, "c" * 40)
    elif mode == "invalid":
        comments[0]["body"] = comments[0]["body"].replace('"schema_version": 1', '"schema_version": 2')
    elif mode == "unscoped":
        comments[0]["body"] = comments[0]["body"].replace(f" head={head}", "")
    if case["builder_source"] is not None:
        comments.append(record("holder", f"<!-- tradecraft:floor:v1 head={head} status=pass -->", id=31))
    if mode in {"missing", "unauthorized", "older", "invalid"}:
        comments.extend([
            record("holder", f"<!-- tradecraft:floor:v1 head={head} status=pass -->", id=32),
            record("holder", f"<!-- tradecraft:no-use:v1 head={head} -->\nUse: not required - docs", id=33),
        ])
    responses[f"repos/{REPO}/issues/19/comments?per_page=100"] = comments
    return FakeTransport(copy.deepcopy(responses)), document


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_ci_floor_normalized_obligation(case):
    transport, _ = fixture_transport(case)
    policy = case["base_policy"]
    if "error" in policy:
        with pytest.raises(check.ProofError, match="policy read failed"):
            check._optional_json_file_record(transport, REPO, ".github/change-proof.json", case["base_tip"])
        return
    if policy.get("absent"):
        assert check._optional_json_file_record(transport, REPO, ".github/change-proof.json", case["base_tip"]) is None
        return
    try:
        declaration = check.load_floor_policy(policy["content"])
    except check.ProofError:
        assert case["expected"]["outcome"] == "unverifiable"
        return
    if not declaration["jobs"]:
        assert case["expected"]["outcome"] == "builder"
        return
    result = check._declared_floor_checks(
        transport, REPO, case["head"], declaration,
        case.get("current_run_id"), case.get("current_run_attempt"),
        datetime.fromisoformat(case["observed_at"]),
    )
    assert result.outcome == case["expected"]["outcome"], result.findings
    assert [item["id"] for item in result.checks] == case["expected"]["check_ids"]
    expected = case["expected"]["executions"]
    if expected is not None:
        assert len(result.executions) == len(expected)
        assert [{field: execution.get(field) for field in expectation}
                for execution, expectation in zip(result.executions, expected)] == expected
    for check_id in case["expected"].get("excluded_check_ids", []):
        assert any(f"check #{check_id} " in exclusion for exclusion in result.excluded)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_ci_floor_complete_document_gate(case):
    transport, _ = fixture_transport(case)
    output = io.StringIO()
    environ = {"GITHUB_TOKEN": "test", "GITHUB_REPOSITORY": REPO, "PULL_REQUEST_NUMBER": "19"}
    if "current_run_id" in case:
        environ["GITHUB_RUN_ID"] = str(case["current_run_id"])
        environ["GITHUB_RUN_ATTEMPT"] = str(case["current_run_attempt"])
    result = check.run(
        environ,
        transport=transport, output=output, observed_at=datetime.fromisoformat(case["observed_at"]),
    )
    assert result == (0 if case["expected"]["gate_pass"] else 1), output.getvalue()
    if case["expected"]["gate_pass"]:
        assert f"floor authority: {REPO} .github/change-proof.json at base tip {case['base_tip']}" in output.getvalue()
        if case["expected"]["outcome"] == "ci-met":
            assert "floor satisfied by declared CI; no builder floor was needed" in output.getvalue()
            for execution in case["expected"]["executions"] or []:
                assert f"event={execution['event']} run=#{execution['run_id']}" in output.getvalue()
        else:
            assert "builder floor supplied by an authorized public attestation" in output.getvalue()
    if case["expected"]["outcome"] in {"blocked", "pending", "stalled"}:
        assert f"declared floor {case['expected']['outcome']}" in output.getvalue()
    if case.get("proof_mode") in {"missing", "unauthorized", "older"}:
        assert "run proof" in output.getvalue()
    if case["base_policy"].get("absent"):
        assert "floor satisfied by declared CI" not in output.getvalue()


@pytest.mark.parametrize("workflow", (
    "/.github/workflows/ci.yml", "C:/.github/workflows/ci.yml", ".github\\workflows\\ci.yml",
    ".github/workflows/../ci.yml", ".github/workflows/./ci.yml", ".github/workflows//ci.yml",
    ".github/workflows/*.yml", ".github/workflows/c?.yml", ".github/workflows/[ci].yml",
    ".github/workflows/ci.yml@main", ".github/workflows/ci.txt", ".github/workflows/ci\n.yml",
))
def test_floor_policy_refuses_nonliteral_workflow_paths(workflow):
    with pytest.raises(check.ProofError, match="workflow"):
        check.load_floor_policy({"floor": {"jobs": [{"workflow": workflow, "job": "Tests"}]}})


@pytest.mark.parametrize("floor", (
    None, [], {}, {"jobs": [], "unknown": True}, {"jobs": True},
    {"jobs": [{}]}, {"jobs": [{"workflow": ".github/workflows/ci.yml", "job": " "}]},
    {"jobs": [{"workflow": ".github/workflows/ci.yml", "job": "Test\x7f"}]},
    {"jobs": [], "stall_after_seconds": True}, {"jobs": [], "stall_after_seconds": 0},
    {"jobs": [], "stall_after_seconds": 1.5},
    {"jobs": [{"workflow": ".github/workflows/ci.yml", "job": "Tests"}] * 2},
))
def test_malformed_floor_is_never_an_empty_declaration(floor):
    with pytest.raises(check.ProofError):
        check.load_floor_policy({"floor": floor})


def test_floor_schema_extension_is_optional_and_independently_pinned():
    schema = json.loads((FIXTURES / "proof-v1.schema.json").read_text(encoding="utf-8"))
    policy_schema = schema["properties"]["policy"]
    assert policy_schema["required"] == ["work_configuration", "use_rules"]
    assert policy_schema["properties"]["floor"] == {
        "oneOf": [{"$ref": "#/$defs/policy_source"}, {"type": "null"}]
    }
    for case in CASES:
        _, document = fixture_transport(case)
        check.validate_proof_document(document)
    document["policy"]["floor"] = {"untrusted": True}
    with pytest.raises(check.ProofError):
        check.validate_proof_document(document)


@pytest.mark.parametrize("surface", ("missing", "unauthorized", "wrong-kind", "stale", "wrong-issue"))
def test_declared_fallback_keeps_lawful_builder_source_contract(surface):
    case = next(case for case in CASES if case["name"] == "skipped-with-builder")
    transport, document = fixture_transport(case)
    comments = transport.responses[f"repos/{REPO}/issues/19/comments?per_page=100"]
    if surface == "missing":
        comments.pop()
    elif surface == "unauthorized":
        comments[-1]["user"]["login"] = "stranger"
    elif surface == "stale":
        comments[-1]["body"] = "<!-- tradecraft:floor:v1 head=" + "c" * 40 + " status=pass -->"
    else:
        document["floor"]["source"]["kind"] = "review" if surface == "wrong-kind" else "issue-comment"
        comments[0]["body"] = f"<!-- tradecraft:proof:v1 head={case['head']} -->\n```json\n{json.dumps(document)}\n```"
    output = io.StringIO()
    assert check.run({"GITHUB_TOKEN": "test", "GITHUB_REPOSITORY": REPO, "PULL_REQUEST_NUMBER": "19"},
        transport=transport, output=output) == 1
    assert "authorized valid floor source" in output.getvalue()


@pytest.mark.parametrize("moved", ("base-tip", "base-ref", "head"))
def test_declared_completion_is_invalidated_by_live_identity_movement(moved):
    case = CASES[0]
    transport, _ = fixture_transport(case)
    target = f"repos/{REPO}/git/ref/heads/main" if moved == "base-tip" else f"repos/{REPO}/pulls/19"

    class MovingTransport(FakeTransport):
        def __init__(self, responses):
            super().__init__(responses)
            self.reads = 0

        def get(self, endpoint, *, paginate=False):
            value = copy.deepcopy(super().get(endpoint, paginate=paginate))
            if endpoint == target:
                self.reads += 1
                if self.reads > 1:
                    if moved == "base-tip":
                        value["object"]["sha"] = "d" * 40
                    elif moved == "head":
                        value["head"]["sha"] = "d" * 40
                    else:
                        value["base"]["ref"] = "release"
            return value

    output = io.StringIO()
    assert check.run({"GITHUB_TOKEN": "test", "GITHUB_REPOSITORY": REPO, "PULL_REQUEST_NUMBER": "19"},
        transport=MovingTransport(transport.responses), output=output) == 1
    assert "through evaluation" in output.getvalue()


@pytest.mark.parametrize("conclusion", (
    "failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"
))
def test_each_terminal_red_blocks_even_a_lawful_builder_marker(conclusion):
    case = copy.deepcopy(next(case for case in CASES if case["name"] == "declared-matrix-failure"))
    case["jobs"][0]["pages"][0]["jobs"][1]["conclusion"] = conclusion
    case["check_runs"][0]["check_runs"][1]["conclusion"] = conclusion
    case["document_patch"]["floor"]["checks"][1]["conclusion"] = conclusion
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("field,value", (
    ("run_id", 99), ("head_sha", "d" * 40), ("run_attempt", True),
    ("run_attempt", 2), ("id", None), ("run_url", "https://evil.example/runs/91"),
    ("status", ["completed"]), ("conclusion", {"result": "success"}),
))
def test_contradictory_job_records_are_unverifiable(field, value):
    case = copy.deepcopy(CASES[0])
    case["jobs"][0]["pages"][0]["jobs"][0][field] = value
    transport, _ = fixture_transport(case)
    result = check._declared_floor_checks(transport, REPO, case["head"],
        check.load_floor_policy(case["base_policy"]["content"]), None, None,
        datetime.fromisoformat(case["observed_at"]))
    assert result.outcome == "unverifiable"
    assert result.findings


def test_selected_proof_gate_execution_cannot_supply_floor_without_a_reusable_reference():
    case = next(case for case in CASES if case["name"] == "gate-cannot-declare-itself")
    transport, _ = fixture_transport(case)
    transport.responses[f"repos/{REPO}/actions/runs/91"]["referenced_workflows"] = []
    result = check._declared_floor_checks(transport, REPO, case["head"],
        check.load_floor_policy(case["base_policy"]["content"]), 91, 1,
        datetime.fromisoformat(case["observed_at"]))
    assert result.outcome == "fallback"
    assert result.checks == []
    assert "cannot establish its own declared floor" in result.excluded[0]


def test_same_named_unexpanded_matrix_key_does_not_declare_expanded_jobs():
    case = copy.deepcopy(CASES[0])
    case["base_policy"]["content"]["floor"]["jobs"] = [
        {"workflow": ".github/workflows/ci.yml", "job": "lint-and-test"}
    ]
    transport, _ = fixture_transport(case)
    result = check._declared_floor_checks(transport, REPO, case["head"],
        check.load_floor_policy(case["base_policy"]["content"]), None, None,
        datetime.fromisoformat(case["observed_at"]))
    assert result.outcome == "fallback"
    assert result.checks == []


@pytest.mark.parametrize("conclusion", (
    "failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"
))
def test_repair_empty_terminal_red_run_blocks_builder_attestation(conclusion):
    case = copy.deepcopy(next(case for case in CASES
        if case["name"] == "repair-terminal-red-run-without-declared-jobs"))
    case["workflow_runs"][0]["workflow_runs"][0]["conclusion"] = conclusion
    case["runs"][0]["record"]["conclusion"] = conclusion
    for execution in case["expected"]["executions"]:
        execution["conclusion"] = conclusion
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("conclusion", ("success", "skipped", "neutral"))
def test_repair_empty_nonexecuted_run_keeps_builder_fallback(conclusion):
    case = copy.deepcopy(next(case for case in CASES
        if case["name"] == "repair-successful-run-with-omitted-jobs-keeps-fallback"))
    case["workflow_runs"][0]["workflow_runs"][0]["conclusion"] = conclusion
    case["runs"][0]["record"]["conclusion"] = conclusion
    for execution in case["expected"]["executions"]:
        execution["conclusion"] = conclusion
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("url", (None, "https://reports.example/test", "https://github.com/owner/repo/runs/83"))
@pytest.mark.parametrize("same_name", (False, True))
def test_repair_api_created_actions_check_requires_declared_name_for_uncertainty(url, same_name):
    name = "repair-same-name-api-actions-check-is-unverifiable" if same_name else "repair-unrelated-api-actions-check-is-excluded"
    case = copy.deepcopy(next(case for case in CASES if case["name"] == name))
    case["check_runs"][0]["check_runs"][-1]["details_url"] = url
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("age", (3599, 3600, 3601))
def test_repair_current_gate_pending_job_uses_attempt_clock_at_boundary(age):
    case = copy.deepcopy(next(case for case in CASES
        if case["name"] == "repair-current-gate-keeps-rerun-test-pending"))
    case["observed_at"] = (datetime.fromisoformat("2026-10-03T12:04:00+00:00")
        + timedelta(seconds=age)).isoformat()
    state = "pending" if age < 3600 else "stalled"
    case["expected"]["outcome"] = state
    case["expected"]["executions"][0].update(state=state, age_seconds=age)
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


def test_repair_rerun_without_attempt_clock_is_unverifiable():
    case = copy.deepcopy(next(case for case in CASES
        if case["name"] == "repair-unfinished-rerun-uses-attempt-start"))
    run = case["runs"][0]["record"]
    run.pop("run_started_at")
    for job in case["jobs"][0]["pages"][0]["jobs"]:
        if job["run_attempt"] == 2:
            job["started_at"] = None
    case["expected"].update(outcome="unverifiable", executions=None)
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("proof_jobs", (0, 2))
def test_repair_current_gate_retention_requires_unambiguous_gate_identity(proof_jobs):
    case = copy.deepcopy(next(case for case in CASES
        if case["name"] == "repair-current-gate-retains-earlier-tests"))
    jobs = case["jobs"][0]["pages"][0]["jobs"]
    proof = jobs.pop()
    jobs.extend(copy.deepcopy(proof) for _ in range(proof_jobs))
    case["expected"].update(outcome="unverifiable", check_ids=[], executions=None, gate_pass=False)
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)


@pytest.mark.parametrize("event", (None, "", "push", "pull_request\n"))
def test_repair_selected_run_requires_consistent_event_identity(event):
    case = copy.deepcopy(CASES[0])
    case["runs"][0]["record"]["event"] = event
    case["expected"].update(outcome="unverifiable", check_ids=[], executions=None, gate_pass=False)
    test_shared_ci_floor_normalized_obligation(case)
    test_shared_ci_floor_complete_document_gate(case)
