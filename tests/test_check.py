from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import time
from pathlib import Path

import pytest

from proof import check


REPO = "Grimblaz-and-Friends/Organizations-of-Verra"
HEAD = "a" * 40
BASE = "b" * 40
BASE_TIP = "c" * 40
AMBIGUOUS_TAG_TIP = "d" * 40
ANCESTOR = "1" * 40
OLDER_ANCESTOR = "2" * 40
COMMIT_ONE = "3" * 40
COMMIT_TWO = "4" * 40
BASE_REF = "main"
OWNER = "proof-owner"
REVIEWER = "review-bot[bot]"
VALID_BODY = "**Path departures:** Expected path ran without a departure."
ABSENT_BODY = object()

# Grimblaz-and-Friends/Organizations-of-Verra#455, issue comment 5750507875.
CODERABBIT_RATE_LIMIT_NOTICE = """\
<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->

> [!WARNING]
> ## Review limit reached
>
> **Next included review available in 59 minutes.**
"""

# Grimblaz-and-Friends/change-proof#1, issue comment 5750390080.
CODERABBIT_SUMMARY_ONLY_NOTICE = """\
**Grimblaz-and-Friends is on CodeRabbit Free, which includes PR summaries. Ask your admin to upgrade for code reviews.**
"""

# The mutable Codex summary on both specified pull requests uses this status table.
# The GET-visible completed form is quoted here from change-proof#1, issue comment
# 5750586451; the use session observed the same row while its status read `Running`.
CODEX_COMPLETED_SUMMARY = """\
<!-- codex-pull-request-review-summary -->

## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | ✅ **Completed** | `45db1e8` | Draft marked ready |

Codex reacts with 👀 while any review is running.
"""
CODEX_RUNNING_NOTICE = """\
<!-- codex-pull-request-review-summary -->

## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | **Running** | `45db1e8` | Draft marked ready |
"""


def record(login, body="", **values):
    return {"user": {"login": login}, "body": body, **values}


def use_note(head=HEAD, author=OWNER, *, changed=False, **values):
    body = (
        f"<!-- tradecraft:use:v1 head={head} status=pass changed={str(changed).lower()} "
        "staffing_status=qualified -->\n\nUse session completed."
    )
    return record(author, body, **values)


def no_use_note(head=HEAD, author=OWNER, *, line=True):
    if line is True:
        line = "Use: not required - documentation-only change"
    suffix = f"\n{line}" if isinstance(line, str) else ""
    return record(author, f"<!-- tradecraft:no-use:v1 head={head} -->{suffix}")


def contents(value):
    encoded = base64.b64encode((json.dumps(value) + "\n").encode()).decode()
    return {"encoding": "base64", "content": encoded}


def comparison(ancestor, commits, *, status="ahead", merge_base=None, ahead_by=None):
    return {
        "status": status,
        "merge_base_commit": {"sha": ancestor if merge_base is None else merge_base},
        "ahead_by": len(commits) if ahead_by is None else ahead_by,
        "commits": [{"sha": revision} for revision in commits],
    }


def compare_endpoint(ancestor, head=HEAD):
    return f"repos/{REPO}/compare/{ancestor}...{head}"


def commit_endpoint(revision):
    return f"repos/{REPO}/commits/{revision}?per_page=100"


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, endpoint, *, paginate=False):
        self.calls.append((endpoint, paginate))
        if endpoint not in self.responses:
            raise AssertionError(f"unexpected GET {endpoint}")
        value = self.responses[endpoint]
        if isinstance(value, Exception):
            raise value
        return value


def scenario(
    *,
    paths=("src/main.ts",),
    comments=None,
    reviews=None,
    review_comments=None,
    reviewers=(REVIEWER,),
    head=HEAD,
    base=BASE,
    base_tip=BASE_TIP,
    base_ref=BASE_REF,
    draft=False,
    files=None,
    changed_files=None,
    head_rules=None,
    head_config=None,
    head_missing=(),
    base_rules=None,
    base_config=None,
    base_policy=True,
    base_missing=(),
    body=VALID_BODY,
):
    default_rules = {
        "schema_version": 1,
        "rules": [
            {
                "name": "runtime-or-user-surface",
                "include": ["src/**", "public/**", "index.html", "package.json"],
                "exclude": ["**/tests/**", "**/*.test.ts"],
            }
        ],
    }
    default_config = {
        "schema_version": 1,
        "product_repositories": [REPO],
        "connected_reviewers": list(reviewers),
        "marker_producers": [OWNER],
    }
    head_rules = default_rules if head_rules is None else head_rules
    head_config = default_config if head_config is None else head_config
    base_rules = default_rules if base_rules is None else base_rules
    base_config = default_config if base_config is None else base_config
    file_records = list(files) if files is not None else [{"filename": path} for path in paths]
    pull = f"repos/{REPO}/pulls/17"
    pull_response = {
        "number": 17,
        "draft": draft,
        "head": {"sha": head},
        "base": {"sha": base, "ref": base_ref},
        "changed_files": len(file_records) if changed_files is None else changed_files,
    }
    if body is not ABSENT_BODY:
        pull_response["body"] = body
    responses = {
        pull: pull_response,
        f"repos/{REPO}/git/ref/heads/{base_ref}": {"object": {"sha": base_tip}},
        f"repos/{REPO}/commits/{base_ref}": {"sha": AMBIGUOUS_TAG_TIP},
        f"{pull}/files?per_page=100": file_records,
        f"repos/{REPO}/issues/17/comments?per_page=100": list(comments or []),
        f"{pull}/reviews?per_page=100": list(reviews or []),
        f"{pull}/comments?per_page=100": list(review_comments or []),
    }
    for revision in (COMMIT_ONE, COMMIT_TWO):
        responses[compare_endpoint(revision, base_tip)] = comparison(
            revision, [], status="diverged", merge_base=BASE
        )
    head_missing = set(head_missing)
    base_missing = set(base_missing)
    if not base_policy:
        base_missing.update((".github/change-proof.json", ".tradecraft/work.json"))
    for path, value in (
        (".github/change-proof.json", head_rules),
        (".tradecraft/work.json", head_config),
    ):
        endpoint = f"repos/{REPO}/contents/{path}?ref={head}"
        responses[endpoint] = (
            check.GitHubNotFound(f"missing {path}")
            if path in head_missing
            else contents(value)
        )
    for path, value in (
        (".github/change-proof.json", base_rules),
        (".tradecraft/work.json", base_config),
    ):
        endpoint = f"repos/{REPO}/contents/{path}?ref={base_tip}"
        responses[endpoint] = (
            check.GitHubNotFound(f"missing {path}")
            if path in base_missing
            else contents(value)
        )
    return FakeTransport(responses)


def environment(*, head=HEAD):
    return {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": REPO,
        "PULL_REQUEST_NUMBER": "17",
        "PULL_REQUEST_HEAD_SHA": head,
        "GITHUB_API_URL": "https://api.github.com",
    }


def execute(transport, *, head=HEAD):
    output = io.StringIO()
    result = check.run(environment(head=head), transport=transport, output=output)
    return result, output.getvalue()


def complete_scenario(**overrides):
    values = {
        "comments": [use_note()],
        "reviews": [record(REVIEWER, "review summary")],
    }
    values.update(overrides)
    return scenario(**values)


def serialized_policy(value):
    return (json.dumps(value) + "\n").encode()


def proof_scenario(*, document_patch=None, proof_author=OWNER, extra_comments=()):
    transport = scenario(
        paths=("docs/readme.md",),
        comments=[],
        reviews=[record(REVIEWER, "completed review", id=41, commit_id=HEAD)],
    )
    rules_endpoint = f"repos/{REPO}/contents/.github/change-proof.json?ref={BASE_TIP}"
    config_endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={BASE_TIP}"
    rules = json.loads(base64.b64decode(transport.responses[rules_endpoint]["content"]))
    config = json.loads(base64.b64decode(transport.responses[config_endpoint]["content"]))
    document = {
        "schema_version": 1,
        "identity": {
            "work": f"{REPO}#12",
            "repository": REPO,
            "issue": 12,
            "pull_request": 17,
            "head": HEAD,
            "producer_version": "0.156.0",
        },
        "policy": {
            "work_configuration": {
                "repository": REPO,
                "path": ".tradecraft/work.json",
                "revision": BASE_TIP,
                "sha256": hashlib.sha256(serialized_policy(config)).hexdigest(),
            },
            "use_rules": {
                "repository": REPO,
                "path": ".github/change-proof.json",
                "revision": BASE_TIP,
                "sha256": hashlib.sha256(serialized_policy(rules)).hexdigest(),
            },
        },
        "floor": {
            "head": HEAD,
            "source": {
                "kind": "issue-comment",
                "repository": REPO,
                "id": 31,
                "url": f"https://github.com/{REPO}/issues/12#issuecomment-31",
                "author": OWNER,
                "timestamp": "2026-09-23T12:06:00Z",
                "revision": HEAD,
            },
            "checks": [{
                "id": 81,
                "name": "Tests",
                "app_id": 15368,
                "app_slug": "github-actions",
                "workflow_id": 71,
                "run_id": 91,
                "url": f"https://github.com/{REPO}/actions/runs/91",
                "head": HEAD,
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-09-23T12:00:00Z",
                "completed_at": "2026-09-23T12:05:00Z",
            }],
        },
        "use": {
            "required": False,
            "classification": "not-required",
            "evidence_head": HEAD,
            "applicability": "generated",
            "source": None,
            "intervening_commits": [],
            "reason": "no changed path matches a use-bought rule",
        },
        "reviewers": [{
            "login": REVIEWER,
            "result": "present",
            "source": {
                "kind": "review",
                "repository": REPO,
                "id": 41,
                "url": f"https://github.com/{REPO}/pull/17#pullrequestreview-41",
                "author": REVIEWER,
                "timestamp": "2026-09-23T12:07:00Z",
                "revision": HEAD,
            },
            "notices": [],
        }],
        "dispositions": [],
        "declarations": [{
            "stage": "floor",
            "status": "unverifiable",
            "reason": "no matching successful dispatch bundle",
            "dispatch_id": None,
            "completed_at": None,
            "revision": None,
            "requested_vendor": None,
            "requested_model": None,
            "requested_effort": None,
            "requested_classification": None,
            "actual_vendor": None,
            "actual_model": None,
            "actual_effort": None,
            "fallback_reason": None,
            "staffing_status": None,
            "same_vendor_reason": None,
        }],
        "diagnostics": [],
    }
    if document_patch:
        document.update(copy.deepcopy(document_patch))
    proof_body = (
        f"<!-- tradecraft:proof:v1 head={HEAD} -->\n\n"
        f"```json\n{json.dumps(document, indent=2, sort_keys=True)}\n```\n\n"
        "Readable rendering is not gate input."
    )
    pull = f"repos/{REPO}/pulls/17"
    proof_comment = record(proof_author, proof_body, id=501)
    transport.responses[f"repos/{REPO}/issues/17/comments?per_page=100"] = [
        proof_comment,
        *extra_comments,
    ]
    transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"] = [
        record(
            OWNER,
            f"<!-- tradecraft:floor:v1 head={HEAD} status=pass -->",
            id=31,
        )
    ]
    transport.responses[f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"] = {
        "total_count": 1,
        "check_runs": [{
            "id": 81,
            "name": "Tests",
            "app": {"id": 15368, "slug": "github-actions"},
            "details_url": f"https://github.com/{REPO}/actions/runs/91/job/811",
            "head_sha": HEAD,
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-09-23T12:00:00Z",
            "completed_at": "2026-09-23T12:05:00Z",
        }],
    }
    transport.responses[f"repos/{REPO}/actions/runs/91"] = {
        "id": 91,
        "head_sha": HEAD,
        "workflow_id": 71,
        "html_url": f"https://github.com/{REPO}/actions/runs/91",
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/91/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Tests",
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/81",
            "run_attempt": 1,
        }],
    }
    return transport, document


def replace_proof_document(transport, document, *, envelope_head=HEAD, author=OWNER):
    body = (
        f"<!-- tradecraft:proof:v1 head={envelope_head} -->\n\n"
        f"```json\n{json.dumps(document, indent=2, sort_keys=True)}\n```"
    )
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[endpoint][0] = record(author, body, id=501)


def affirmed_brief_record(
    *,
    id=32,
    author=OWNER,
    marker="<!-- tradecraft:affirmed-brief:v1 -->",
    pair="Review risk: ordinary\nReview lane: mechanical",
    **values,
):
    body = f"{marker}\n\nAffirmed brief body.\n\n{pair}"
    return record(author, body, id=id, **values)


def mechanical_proof_scenario(*, bought=False, brief=None):
    transport, document = proof_scenario()
    if bought:
        transport.responses[f"repos/{REPO}/pulls/17/files?per_page=100"] = [
            {"filename": "src/main.ts"}
        ]
    source = {
        "kind": "issue-comment",
        "repository": REPO,
        "id": 32,
        "url": f"https://github.com/{REPO}/issues/12#issuecomment-32",
        "author": OWNER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": None,
    }
    document["use"] = {
        "required": False,
        "classification": "not-required",
        "evidence_head": HEAD,
        "applicability": "generated",
        "source": source,
        "intervening_commits": [],
        "reason": (
            "the owner-affirmed mechanical lane exempts use even when changed paths "
            "match the schema-version-1 use policy"
        ),
    }
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(brief or affirmed_brief_record())
    replace_proof_document(transport, document)
    return transport, document


def shared_fixture_scenario(case):
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1"
    document = json.loads((fixture_root / "v1-valid.json").read_text(encoding="utf-8"))
    document.update(copy.deepcopy(case["document_patch"]))
    repo = "example/product"
    head = "a" * 40
    base_tip = "b" * 40
    pull = f"repos/{repo}/pulls/19"
    rules = {
        "schema_version": 1,
        "rules": [{"name": "runtime", "include": ["src/**"], "exclude": []}],
    }
    config = {
        "schema_version": 1,
        "product_repositories": [],
        "connected_reviewers": ["reviewer[bot]"],
        "marker_producers": ["holder"],
    }
    proof_body = (
        f"<!-- tradecraft:proof:v1 head={head} -->\n\n"
        f"```json\n{json.dumps(document, indent=2, sort_keys=True)}\n```"
    )
    comments = [
        record(
            "holder",
            f"<!-- tradecraft:floor:v1 head={head} status=pass -->",
            id=31,
        ),
        record("holder", proof_body, id=501),
    ]
    review_body = (
        "Review limit reached"
        if case["name"] == "non-review-notice"
        else "completed review"
    )
    review_comments = []
    if case["name"] in {"omitted-thread", "unauthorized-disposition"}:
        review_comments.append(
            record("reviewer[bot]", "finding", id=51, in_reply_to_id=None)
        )
    if case["name"] == "unauthorized-disposition":
        review_comments.append(
            record("stranger", "fixed - claimed", id=52, in_reply_to_id=51)
        )
    responses = {
        pull: {
            "number": 19,
            "draft": False,
            "body": VALID_BODY,
            "head": {"sha": head},
            "base": {"sha": base_tip, "ref": "main"},
            "changed_files": 1,
        },
        f"repos/{repo}/git/ref/heads/main": {"object": {"sha": base_tip}},
        f"repos/{repo}/contents/.github/change-proof.json?ref={head}": contents(rules),
        f"repos/{repo}/contents/.tradecraft/work.json?ref={head}": contents(config),
        f"repos/{repo}/contents/.github/change-proof.json?ref={base_tip}": contents(rules),
        f"repos/{repo}/contents/.tradecraft/work.json?ref={base_tip}": contents(config),
        f"{pull}/files?per_page=100": [{"filename": "docs/readme.md"}],
        f"repos/{repo}/issues/19/comments?per_page=100": comments,
        f"repos/{repo}/issues/12/comments?per_page=100": [],
        f"{pull}/reviews?per_page=100": [
            record("reviewer[bot]", review_body, id=41)
        ],
        f"{pull}/comments?per_page=100": review_comments,
        f"repos/{repo}/commits/{head}/check-runs?filter=all&per_page=100": {
            "total_count": 1,
            "check_runs": [{
                "id": 81,
                "name": "Tests",
                "app": {"id": 15368, "slug": "github-actions"},
                "details_url": f"https://github.com/{repo}/actions/runs/91",
                "head_sha": head,
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-09-23T12:00:00Z",
                "completed_at": "2026-09-23T12:05:00Z",
            }],
        },
        f"repos/{repo}/actions/runs/91": {
            "id": 91,
            "head_sha": head,
            "workflow_id": 71,
            "html_url": f"https://github.com/{repo}/actions/runs/91",
            "repository": {"full_name": repo},
            "referenced_workflows": [],
        },
        f"repos/{repo}/actions/runs/91/jobs?filter=all&per_page=100": {
            "total_count": 1,
            "jobs": [{
                "name": "Tests",
                "check_run_url": f"https://api.github.com/repos/{repo}/check-runs/81",
                "run_attempt": 1,
            }],
        },
    }
    environ = {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": repo,
        "PULL_REQUEST_NUMBER": "19",
        "PULL_REQUEST_HEAD_SHA": head,
        "GITHUB_API_URL": "https://api.github.com",
    }
    return FakeTransport(responses), environ


def recorded_scenario(world_name, comment_name, *, add_path_departures=False):
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1" / "recorded"
    world = json.loads((fixture_root / world_name).read_text(encoding="utf-8"))
    responses = copy.deepcopy(world["responses"])
    comment = (fixture_root / comment_name).read_text(encoding="utf-8")
    endpoint = (
        f"repos/{world['repository']}/issues/{world['pull_request']}/comments?per_page=100"
    )
    proof_comment = world.get("proof_comment", {})
    proof_id = proof_comment.get("id", 9_000_000_001)
    proof_author = proof_comment.get("author", "Grimblaz")
    proof_values = {
        key: value
        for key, value in proof_comment.items()
        if key not in {"author", "id", "index"}
    }
    responses[endpoint] = [
        item for item in responses[endpoint] if item.get("id") != proof_id
    ]
    proof_index = proof_comment.get("index", 0)
    responses[endpoint].insert(
        proof_index,
        record(proof_author, comment, id=proof_id, **proof_values),
    )
    if add_path_departures:
        pull_endpoint = f"repos/{world['repository']}/pulls/{world['pull_request']}"
        responses[pull_endpoint]["body"] = VALID_BODY
    environ = {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": world["repository"],
        "PULL_REQUEST_NUMBER": str(world["pull_request"]),
        "PULL_REQUEST_HEAD_SHA": world["head"],
        "GITHUB_API_URL": "https://api.github.com",
    }
    environ.update({key: str(value) for key, value in world.get("environment", {}).items()})
    return FakeTransport(responses), environ


def line_ending(body, separator):
    return separator.join(body.splitlines())


def test_shared_proof_fixture_and_semantic_cases_keep_their_structural_roles():
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1"
    schema = json.loads((fixture_root / "proof-v1.schema.json").read_text(encoding="utf-8"))
    valid = json.loads((fixture_root / "v1-valid.json").read_text(encoding="utf-8"))
    cases = json.loads(
        (fixture_root / "v1-negative-cases.json").read_text(encoding="utf-8")
    )

    assert schema["$id"].endswith("proof-v1.schema.json")
    assert schema["properties"]["schema_version"]["const"] == 1
    assert check.validate_proof_document(valid) is valid
    for case in cases:
        candidate = copy.deepcopy(valid)
        candidate.update(case["document_patch"])
        if case["name"] == "producer-verification-field":
            with pytest.raises(check.ProofError, match="unexpected verified"):
                check.validate_proof_document(candidate)
        else:
            assert check.validate_proof_document(candidate) is candidate


@pytest.mark.parametrize(
    ("case_name", "expected", "passes"),
    (
        ("wrong-head", "proof identity head", False),
        ("substituted-floor-check", "public floor check #999", False),
        ("omitted-configured-reviewer", "missing: reviewer[bot]", False),
        # A review object remains a legacy receipt regardless of its body. The
        # pull-request-comment notice case is covered separately below.
        ("non-review-notice", "credited by review #41", True),
        ("omitted-thread", "missing: 51", False),
        ("unauthorized-disposition", "reviewer thread 51", False),
        ("producer-verification-field", "unexpected verified", False),
        ("declaration-rendered-as-verified", "actual_model=gpt-6-sol", True),
    ),
)
def test_every_shared_negative_case_runs_through_the_wire_with_live_facts(
    case_name, expected, passes
):
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1"
    cases = json.loads(
        (fixture_root / "v1-negative-cases.json").read_text(encoding="utf-8")
    )
    case = next(item for item in cases if item["name"] == case_name)
    transport, environ = shared_fixture_scenario(case)
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)
    rendered = output.getvalue()

    assert result == (0 if passes else 1)
    assert "evidence path: proof-v1" in rendered
    assert expected in rendered
    if case_name == "declaration-rendered-as-verified":
        assert "declared: stage=use" in rendered
        assert "verified: stage=use" not in rendered


@pytest.mark.parametrize(
    "comment_name",
    ("tradecraft-733.comment.md", "tradecraft-733-no-bundle.comment.md"),
)
def test_original_tradecraft_733_record_now_requires_body_answers(comment_name):
    transport, environ = recorded_scenario("world-tc733.trimmed.json", comment_name)
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)

    assert result == 1
    rendered = output.getvalue()
    assert "body finding cr-comment:v1:7d3d3fcdd8d9891aeabf8880" in rendered
    # Original trimming omitted the review join; labeled overlays supply the positive replay.
    assert "actionable comments declares 3, accounted 0" in rendered
    assert "evidence path: proof-v1" in rendered
    assert "floor source pull-request-comment #5804738722" in rendered
    assert "floor check #107431978288 ask-declaration" in rendered
    assert "floor check #107426496559 ask-declaration" not in rendered
    assert "producer-diagnostic: invalid-marker-claim:" in rendered
    assert not any(
        line.startswith("diagnostic: invalid-marker-claim:")
        for line in rendered.splitlines()
    )


def test_exact_verra_composer_comment_passes_with_case_folded_source_authors():
    transport, environ = recorded_scenario(
        "world-verra476.trimmed.json",
        "verra-476.comment.md",
        add_path_departures=True,
    )
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)

    assert result == 0
    assert "evidence path: proof-v1" in output.getvalue()
    assert "floor source pull-request-comment #5787215547" in output.getvalue()


def test_exact_mechanical_producer_comment_passes_against_recorded_github_facts():
    transport, environ = recorded_scenario(
        "world-tc767.trimmed.json", "tradecraft-767.comment.md"
    )
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)
    rendered = output.getvalue()

    assert result == 0
    assert (
        "verified: owner-affirmed mechanical lane in "
        "Grimblaz-and-Friends/tradecraft#759 issue-comment #5851221027 exempts use; "
        "changed paths would otherwise not require use"
    ) in rendered
    assert "missing: a current-head generated no-use record matching trusted policy" not in rendered
    proof_endpoint = "repos/Grimblaz-and-Friends/tradecraft/issues/767/comments?per_page=100"
    assert sum(
        item.get("id") == 5852491047 for item in transport.responses[proof_endpoint]
    ) == 1
    assert (
        "excluded: current gate's earlier attempt run #36292658635 attempt #1 "
        "check #108545582382"
    ) in rendered
    assert (
        "excluded: current gate execution run #36292658635 check #108549502051"
    ) in rendered


def test_tc767_world_keeps_the_get_record_and_labels_historical_reconstructions():
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1" / "recorded"
    world = json.loads(
        (fixture_root / "world-tc767.trimmed.json").read_text(encoding="utf-8")
    )
    responses = world["responses"]
    repo = "Grimblaz-and-Friends/tradecraft"
    head = "4f12aa5efa0ae765cebd213f89eec7da754c3d6a"

    assert "GET only" in world["provenance"]
    assert world["reconstructions"] == [
        {
            "field": "environment",
            "value": "gate run 36292658635 attempt 5",
            "basis": "attempt-5 job log for job 108549502051",
        },
        {
            "field": f"responses['repos/{repo}/git/ref/heads/main'].object.sha",
            "value": "6789582047cf306607573ecaff25ba1a4eda379d",
            "basis": "base tip printed by the attempt-5 gate job",
        },
        {
            "field": f"responses['repos/{repo}/pulls/767'].state",
            "value": "open",
            "basis": (
                "pull request #767 and work issue #759 were open during attempt 5; "
                "their later closed states are not attributed to that run"
            ),
        },
    ]

    checks = responses[f"repos/{repo}/commits/{head}/check-runs?filter=all&per_page=100"]
    assert checks["total_count"] == len(checks["check_runs"]) == 21
    assert [item["id"] for item in checks["check_runs"]] == [
        108549502051,
        108548930259,
        108548930241,
        108548930130,
        108548610111,
        108548116684,
        108548116656,
        108548116503,
        108547697600,
        108547460071,
        108547460040,
        108547459913,
        108547334634,
        108547254666,
        108545707219,
        108545707172,
        108545707111,
        108545582382,
        108545580625,
        108545580623,
        108545580487,
    ]

    body_hashes = {
        item["id"]: hashlib.sha256(item["body"].encode()).hexdigest()
        for route in (
            f"repos/{repo}/issues/759/comments?per_page=100",
            f"repos/{repo}/issues/767/comments?per_page=100",
        )
        for item in responses[route]
    }
    assert body_hashes == {
        5849372099: "187be9a59e5fe5062c19be00eacdb1c38fce251c6f508e23e3139b624207dfe1",
        5851221027: "017b7e474849bc5565b3cba8073249c476d2f3e65839ef947e2dc64b6b8d8843",
        5852421302: "b55bc44f35ed454a93a55880c80721f63d0cf712cc23d8f8c7338f7dbacd131d",
        5852424198: "72cbc923686328b5aa78c14f9cd92994a4f6dad898d8d7def1cb1435fcc23ac4",
        5852487982: "4d3edbfefb54e9c23ed45080e6cd2e24c4b1ca22133592b06f4d62a4c872f607",
        5852491047: "f60d4780b110786bb01a28fc8067b840eca010fd5d06b9b163a935cbba26304c",
        5852495163: "57253387675f94d4fbf9955f849487a4cb3fe880f957e589962ff4500e123d9b",
        5852502444: "b93506ddd4e52631088f9af9ff2a72538e21c9513980672e944ab6928932d4a9",
    }
    pull_body = responses[f"repos/{repo}/pulls/767"]["body"]
    assert hashlib.sha256(pull_body.encode()).hexdigest() == (
        "4ecd8eeb24408d2bde59a0fa815dc835989c67c98b7d0cfb56856af1141a695e"
    )

    action_runs = [
        route
        for route in responses
        if "/actions/runs/" in route and "/jobs?" not in route
    ]
    assert len(action_runs) == 6
    for route, value in responses.items():
        if "/actions/runs/" in route and "/jobs?" in route:
            assert value["total_count"] == len(value["jobs"])


def test_recorded_mechanical_producer_comment_is_the_exact_prechange_falsifier():
    fixture_root = Path(__file__).parent / "fixtures" / "proof-v1" / "recorded"
    body = (fixture_root / "tradecraft-767.comment.md").read_text(encoding="utf-8")
    candidate = check._proof_candidates(
        [record("Grimblaz", body, id=5852491047)], frozenset({"grimblaz"})
    )[0]
    assert candidate.error is None
    use = candidate.document["use"]

    assert use["required"] is False
    assert use["classification"] == "not-required"
    assert use["evidence_head"] == "4f12aa5efa0ae765cebd213f89eec7da754c3d6a"
    assert use["applicability"] == "generated"
    assert use["intervening_commits"] == []
    assert use["reason"]
    assert use["source"] is not None

    transport, environ = recorded_scenario(
        "world-tc767.trimmed.json", "tradecraft-767.comment.md"
    )
    output = io.StringIO()
    result = check.run(environ, transport=transport, output=output)

    assert result == 0
    actual_lines = output.getvalue().splitlines()
    lane_line = (
        "verified: owner-affirmed mechanical lane in "
        "Grimblaz-and-Friends/tradecraft#759 issue-comment #5851221027 exempts use; "
        "changed paths would otherwise not require use"
    )
    assert actual_lines.count(lane_line) == 1

    # This is attempt 5's output from job 108549502051, whose reusable checker
    # was pinned to cb5b746. Compare every line unaffected by this change and
    # assert that the old checker had exactly the generated no-use failure.
    expected_lines = (
        fixture_root / "tradecraft-767.attempt-5.output.txt"
    ).read_text(encoding="utf-8").splitlines()
    prechange_lines = [
        "change-proof: FAIL" if index == 0 else line
        for index, line in enumerate(actual_lines)
        if line != lane_line
    ]
    prechange_lines.extend(expected_lines[-2:])

    assert prechange_lines == expected_lines
    assert [line for line in expected_lines if line.startswith("missing:")] == [
        "missing: a current-head generated no-use record matching trusted policy"
    ]
    assert [line for line in expected_lines if line.startswith("satisfy:")] == [
        "satisfy: recompose proof under the base-tip use rules with a nonempty "
        "generated reason"
    ]


def test_recorded_mechanical_producer_comment_passes_a_synthetic_bought_path_overlay():
    transport, environ = recorded_scenario(
        "world-tc767.trimmed.json", "tradecraft-767.comment.md"
    )
    files_endpoint = "repos/Grimblaz-and-Friends/tradecraft/pulls/767/files?per_page=100"
    assert transport.responses[files_endpoint] == [{"filename": ".tradecraft/work.json"}]
    transport.responses[files_endpoint][0]["filename"] = "lib/work.py"
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)

    assert result == 0
    assert (
        "verified: owner-affirmed mechanical lane in "
        "Grimblaz-and-Friends/tradecraft#759 issue-comment #5851221027 exempts use; "
        "changed paths would otherwise require use"
    ) in output.getvalue()


def test_recorded_current_gate_attempts_are_distinct_from_a_caller_run():
    transport, environ = recorded_scenario(
        "world-verra476.trimmed.json",
        "verra-476.comment.md",
        add_path_departures=True,
    )
    environ.update({
        "GITHUB_RUN_ID": "35804256431",
        "GITHUB_RUN_ATTEMPT": "2",
    })
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)
    rendered = output.getvalue()

    assert result == 0
    assert (
        "excluded: current gate execution run #35804256431 check #107031065299 "
        "is not floor evidence because a gate cannot prove itself"
    ) in rendered
    assert (
        "excluded: current gate's earlier attempt run #35804256431 attempt #1 "
        "check #107001377611 is not floor evidence because the current gate is attempt #2"
    ) in rendered
    assert "caller proof execution run #35804256431" not in rendered
    assert (
        "excluded: caller proof execution run #35804256441 check #107001378116 "
        "is not floor evidence because it invokes the reusable change-proof job"
    ) in rendered


def test_recorded_crlf_policy_digests_are_declared_and_nonfatal():
    transport, environ = recorded_scenario(
        "world-verra476.trimmed.json",
        "verra-476-crlf.comment.md",
        add_path_departures=True,
    )
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)
    rendered = output.getvalue()

    assert result == 0
    assert rendered.count("diagnostic: policy digest mismatch") == 2
    assert "tradecraft #742" in rendered
    assert "missing:" not in rendered


@pytest.mark.parametrize(
    ("bought", "path_result"),
    ((False, "not require"), (True, "require")),
)
def test_owner_affirmed_mechanical_lane_exempts_both_path_classifications(
    bought, path_result
):
    transport, _document = mechanical_proof_scenario(bought=bought)

    result, output = execute(transport)

    assert result == 0
    assert (
        f"verified: owner-affirmed mechanical lane in {REPO}#12 issue-comment #32 "
        f"exempts use; changed paths would otherwise {path_result} use"
    ) in output
    assert "trusted policy classifies the changed paths as no-use" not in output


@pytest.mark.parametrize("bought", (False, True))
@pytest.mark.parametrize("kind", ("pull-request-comment", "review", "review-comment"))
def test_mechanical_lane_source_must_use_the_work_issue_surface(bought, kind):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["use"]["source"]["kind"] = kind
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"wrong surface {kind}; expected issue-comment" in output
    assert "verified: owner-affirmed mechanical lane" not in output


@pytest.mark.parametrize("bought", (False, True))
def test_mechanical_lane_source_must_name_the_evaluated_repository(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["use"]["source"]["repository"] = "example/other"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"affirmed-brief source in {REPO}" in output
    assert "repository example/other" in output


@pytest.mark.parametrize("bought", (False, True))
def test_mechanical_lane_source_must_be_on_the_named_work_issue(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["use"]["source"]["id"] = 99
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"issue-comment source #99 on {REPO}#12" in output
    assert "not on its claimed surface" in output


@pytest.mark.parametrize("bought", (False, True))
def test_mechanical_lane_source_rejects_a_forged_claimed_author(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["use"]["source"]["author"] = "stranger"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "author differs from the public record" in output


@pytest.mark.parametrize("bought", (False, True))
def test_mechanical_lane_source_requires_a_base_tip_marker_producer(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint][-1]["user"]["login"] = "head-only-producer"
    document["use"]["source"]["author"] = "head-only-producer"
    head_config_endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={HEAD}"
    head_config = json.loads(base64.b64decode(transport.responses[head_config_endpoint]["content"]))
    head_config["marker_producers"].append("head-only-producer")
    transport.responses[head_config_endpoint] = contents(head_config)
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "head-only-producer is not a configured marker producer" in output


@pytest.mark.parametrize(
    "marker",
    (
        "<!-- tradecraft:affirmed-brief:v1 extra=true -->",
        "<!-- tradecraft:affirmed-brief:v1 bare-garbage -->",
    ),
)
def test_mechanical_lane_source_requires_an_attribute_free_affirmed_marker(marker):
    transport, _document = mechanical_proof_scenario(
        brief=affirmed_brief_record(marker=marker)
    )

    result, output = execute(transport)

    assert result == 1
    assert "exact attribute-free tradecraft:affirmed-brief:v1 marker" in output


@pytest.mark.parametrize("bought", (False, True))
def test_forged_issue_comment_identity_on_the_pull_request_is_rejected(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    pull_endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[pull_endpoint].append(
        affirmed_brief_record(id=99)
    )
    document["use"]["source"]["id"] = 99
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"issue-comment source #99 on {REPO}#12" in output
    assert "not on its claimed surface" in output


@pytest.mark.parametrize("bought", (False, True))
def test_work_issue_equal_to_pull_request_is_a_named_surface_collision(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["identity"]["issue"] = 17
    document["identity"]["work"] = f"{REPO}#17"
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    pull_endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    proof_comment = transport.responses[pull_endpoint][0]
    transport.responses[pull_endpoint] = [
        proof_comment,
        *copy.deepcopy(transport.responses[work_endpoint]),
    ]
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment source #32 is misplaced on the pull-request surface" in output
    assert "name the actual work issue" in output


@pytest.mark.parametrize("bought", (False, True))
def test_wrong_source_kind_is_named_before_a_pull_request_surface_collision(bought):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["identity"]["issue"] = 17
    document["identity"]["work"] = f"{REPO}#17"
    document["use"]["source"]["kind"] = "review"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "wrong surface review; expected issue-comment" in output
    assert "issue-comment source #32 is misplaced" not in output


@pytest.mark.parametrize(
    ("bought", "remedy"),
    (
        (
            True,
            "run the use owed by affirmed-brief issue-comment #33, then recompose "
            "proof from that use record",
        ),
        (
            False,
            "recompose proof as an ordinary policy-based no-use record with no source",
        ),
    ),
)
def test_later_connected_brief_supersedes_the_mechanical_source(bought, remedy):
    transport, _document = mechanical_proof_scenario(bought=bought)
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(
        affirmed_brief_record(id=33, pair="Review risk: ordinary\nReview lane: connected")
    )

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment #32 is superseded by issue-comment #33" in output
    assert remedy in output
    assert "verified: owner-affirmed mechanical lane" not in output


@pytest.mark.parametrize("bought", (False, True))
@pytest.mark.parametrize(
    ("pair", "detail"),
    (
        ("Review lane: mechanical", "recognized Review risk lines=0"),
        (
            "Review risk: ordinary\nReview risk: ordinary\nReview lane: mechanical",
            "recognized Review risk lines=2",
        ),
        (
            "Review risk: ordinary\nReview lane: substantial-panel",
            "unlawful review pair ordinary / substantial-panel",
        ),
    ),
)
def test_later_broken_pair_supersedes_the_mechanical_source(bought, pair, detail):
    transport, _document = mechanical_proof_scenario(bought=bought)
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(affirmed_brief_record(id=33, pair=pair))

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment #32 is superseded by issue-comment #33" in output
    assert f"latest review pair is invalid: {detail}" in output
    assert "do not choose an older source" in output
    assert "verified: owner-affirmed mechanical lane" not in output


def test_later_mechanical_brief_requires_recomposition_and_then_passes():
    transport, document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(affirmed_brief_record(id=33))

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment #32 is superseded by issue-comment #33" in output

    document["use"]["source"]["id"] = 33
    document["use"]["source"]["url"] = (
        f"https://github.com/{REPO}/issues/12#issuecomment-33"
    )
    replace_proof_document(transport, document)
    result, output = execute(transport)

    assert result == 0
    assert "issue-comment #33 exempts use" in output


def artifact_form_copy(pair="Review risk: ordinary\nReview lane: mechanical"):
    return record(
        OWNER,
        "<!-- tradecraft:artifact:v1 status=draft -->\n\n"
        "Purpose: preserve the settled artifact.\n\n"
        "<!-- tradecraft:affirmed-brief:v1 -->\n\n"
        "Copied affirmed brief.\n\n"
        f"{pair}",
        id=33,
    )


def test_artifact_form_copy_supersedes_the_original_pointer():
    transport, document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(artifact_form_copy())

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment #32 is superseded by issue-comment #33" in output

    document["use"]["source"]["id"] = 33
    document["use"]["source"]["url"] = (
        f"https://github.com/{REPO}/issues/12#issuecomment-33"
    )
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 0
    assert "issue-comment #33 exempts use" in output


@pytest.mark.parametrize(
    ("pair", "expected"),
    (
        (
            "Review risk: ordinary\nReview risk: ordinary\nReview lane: mechanical",
            "recognized Review risk lines=2",
        ),
        ("Review risk: ordinary\nReview lane: connected", "found ordinary / connected"),
    ),
)
def test_artifact_form_copy_rejects_an_invalid_or_connected_pair(pair, expected):
    transport, document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(artifact_form_copy(pair))
    document["use"]["source"]["id"] = 33
    document["use"]["source"]["url"] = (
        f"https://github.com/{REPO}/issues/12#issuecomment-33"
    )
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert expected in output
    assert "verified: owner-affirmed mechanical lane" not in output


@pytest.mark.parametrize("bought", (False, True))
def test_later_unauthorized_affirmed_comment_does_not_supersede_authority(bought):
    transport, _document = mechanical_proof_scenario(bought=bought)
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(
        affirmed_brief_record(id=33, author="stranger")
    )

    result, output = execute(transport)

    assert result == 0
    assert "issue-comment #32 exempts use" in output


@pytest.mark.parametrize(
    "body",
    (
        "<!-- tradecraft:note:v1 draft\n"
        "<!-- tradecraft:affirmed-brief:v1 -->\n"
        "Review risk: ordinary\nReview lane: connected\n",
        "<!-- tradecraft:artifact:v1 status=settled\n"
        "<!-- tradecraft:affirmed-brief:v1 -->\n"
        "Review risk: ordinary\nReview lane: connected\n",
        "<!-- tradecraft:affirmed-brief:v1 garbage\n"
        "<!-- tradecraft:affirmed-brief:v1 -->\n"
        "Review risk: ordinary\nReview lane: connected\n",
    ),
)
def test_nested_affirmed_token_swallowed_by_an_earlier_marker_is_not_a_record(body):
    assert check._has_exact_affirmed_brief(body) is False
    transport, _document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].append(record(OWNER, body, id=33))

    result, output = execute(transport)

    assert result == 0
    assert "issue-comment #32 exempts use" in output


def test_mixed_case_affirmed_marker_is_accepted():
    transport, _document = mechanical_proof_scenario(
        brief=affirmed_brief_record(
            marker="<!-- TrAdEcRaFt:AfFiRmEd-BrIeF:v1 -->"
        )
    )

    result, output = execute(transport)

    assert result == 0
    assert "issue-comment #32 exempts use" in output


def test_github_comment_order_not_updated_at_selects_the_latest_brief():
    transport, _document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint][-1]["updated_at"] = "2026-09-23T13:00:00Z"
    transport.responses[work_endpoint].append(affirmed_brief_record(
        id=33,
        pair="Review risk: ordinary\nReview lane: connected",
        updated_at="2026-09-22T13:00:00Z",
    ))

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment #32 is superseded by issue-comment #33" in output


@pytest.mark.parametrize(
    ("pair", "passes", "expected"),
    (
        ("ReViEw RiSk:\tOrDiNaRy  \r\nReViEw LaNe: MeChAnIcAl\r\n", True, None),
        ("Review lane: mechanical", False, "recognized Review risk lines=0"),
        ("Review risk: ordinary", False, "recognized Review lane lines=0"),
        (
            "Review risk: ordinary\nReview risk: ordinary\nReview lane: mechanical",
            False,
            "recognized Review risk lines=2",
        ),
        (
            "Review risk: ordinary\nReview lane: mechanical\nReview lane: connected",
            False,
            "recognized Review lane lines=2",
        ),
        ("Review risk: unknown\nReview lane: mechanical", False, "recognized Review risk lines=0"),
        (
            "Review risk: ordinary\nReview lane: substantial-panel",
            False,
            "unlawful review pair ordinary / substantial-panel",
        ),
        (
            "Review risk: ordinary\nReview lane: connected",
            False,
            "found ordinary / connected",
        ),
        (
            "Review risk: elevated\nReview lane: routine-panel",
            False,
            "found elevated / routine-panel",
        ),
        (
            "Review risk: critical\nReview lane: substantial-panel",
            False,
            "found critical / substantial-panel",
        ),
    ),
)
def test_mechanical_lane_requires_one_lawful_ordinary_mechanical_pair(
    pair, passes, expected
):
    transport, _document = mechanical_proof_scenario(
        brief=affirmed_brief_record(pair=pair)
    )

    result, output = execute(transport)

    assert result == (0 if passes else 1)
    if expected is not None:
        assert expected in output
        assert "verified: owner-affirmed mechanical lane" not in output


@pytest.mark.parametrize("bought", (False, True))
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("required", True),
        ("classification", "required"),
        ("evidence_head", "d" * 40),
        ("intervening_commits", [{"sha": "d" * 40, "paths": ["docs/readme.md"]}]),
        ("reason", ""),
        ("applicability", "current-head"),
    ),
)
def test_mechanical_lane_does_not_relax_generated_carrier_shape(bought, field, value):
    transport, document = mechanical_proof_scenario(bought=bought)
    document["use"][field] = value
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "verified: owner-affirmed mechanical lane" not in output


def test_lane_sounding_reason_without_source_does_not_exempt_bought_paths():
    transport, document = mechanical_proof_scenario(bought=True)
    document["use"]["source"] = None
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "proof use classification matching trusted policy: required" in output
    assert "verified: owner-affirmed mechanical lane" not in output


def test_irrelevant_mechanical_brief_does_not_override_current_head_use():
    transport, document = proof_scenario()
    transport.responses[f"repos/{REPO}/pulls/17/files?per_page=100"] = [
        {"filename": "src/main.ts"}
    ]
    source = {
        "kind": "issue-comment",
        "repository": REPO,
        "id": 32,
        "url": f"https://github.com/{REPO}/issues/12#issuecomment-32",
        "author": OWNER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": HEAD,
    }
    document["use"] = {
        "required": True,
        "classification": "required",
        "evidence_head": HEAD,
        "applicability": "current-head",
        "source": source,
        "intervening_commits": [],
        "reason": "current-head use completed",
    }
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint].extend((
        use_note(id=32),
        affirmed_brief_record(id=33),
    ))
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 0
    assert "trusted policy requires use and the public use source is current-head" in output
    assert "verified: owner-affirmed mechanical lane" not in output


def test_mechanical_brief_does_not_change_the_marker_only_path():
    transport = scenario(
        paths=("src/main.ts",),
        comments=[affirmed_brief_record()],
        reviews=[record(REVIEWER, "completed review")],
    )

    result, output = execute(transport)

    assert result == 1
    assert "evidence path: legacy-markers" in output
    assert "authorized, valid use marker" in output
    assert "verified: owner-affirmed mechanical lane" not in output


def test_valid_mechanical_lane_does_not_clear_missing_path_departures():
    transport, _document = mechanical_proof_scenario()
    transport.responses[f"repos/{REPO}/pulls/17"]["body"] = ""

    result, output = execute(transport)

    assert result == 1
    assert "Path departures" in output
    assert "verified: owner-affirmed mechanical lane" in output


def test_valid_mechanical_lane_does_not_clear_a_failed_floor_check():
    transport, document = mechanical_proof_scenario()
    document["floor"]["checks"][0]["conclusion"] = "failure"
    check_endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    transport.responses[check_endpoint]["check_runs"][0]["conclusion"] = "failure"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "completed acceptable result for floor check #81" in output
    assert "verified: owner-affirmed mechanical lane" in output


def test_valid_mechanical_lane_does_not_clear_a_missing_reviewer():
    transport, document = mechanical_proof_scenario()
    document["reviewers"] = []
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "exactly one proof entry for every trusted configured reviewer" in output
    assert "verified: owner-affirmed mechanical lane" in output


def test_mechanical_lane_cannot_pass_when_work_comments_are_unreadable():
    transport, _document = mechanical_proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[work_endpoint] = check.ProofError("recording unavailable")

    result, output = execute(transport)

    assert result == 1
    assert "readable work-issue comments for issue 12: recording unavailable" in output
    assert "verified: owner-affirmed mechanical lane" not in output


def test_complete_proof_document_passes_and_keeps_local_records_declared():
    transport, _document = proof_scenario()

    result, output = execute(transport)

    assert result == 0
    assert "evidence path: proof-v1" in output
    assert "selected proof-v1 comment #501" in output
    assert "declared: stage=floor status=unverifiable" in output
    assert "verified: stage=floor" not in output
    assert "no matching successful dispatch bundle" in output


def test_selected_document_with_substituted_floor_check_is_rejected_semantically():
    transport, document = proof_scenario()
    substituted = copy.deepcopy(document["floor"])
    substituted["checks"][0]["id"] = 999
    transport, _document = proof_scenario(document_patch={"floor": substituted})

    result, output = execute(transport)

    assert result == 1
    assert "evidence path: proof-v1" in output
    assert "public floor check #999" in output
    assert "omitted check id(s): 81" in output


def test_invalid_selected_document_does_not_fall_back_to_complete_legacy_markers():
    transport, _document = proof_scenario(
        document_patch={"schema_version": 2},
        extra_comments=(no_use_note(),),
    )

    result, output = execute(transport)

    assert result == 1
    assert "evidence path: proof-v1" in output
    assert "schema_version must be integer 1" in output
    assert "authorized current-head no-use note" not in output


def test_older_document_leaves_the_legacy_compatibility_path_available():
    transport, document = proof_scenario()
    old_head = "9" * 40
    document["identity"]["head"] = old_head
    old_body = (
        f"<!-- tradecraft:proof:v1 head={old_head} -->\n\n"
        f"```json\n{json.dumps(document, indent=2)}\n```"
    )
    transport.responses[f"repos/{REPO}/issues/17/comments?per_page=100"] = [
        record(OWNER, old_body, id=502),
        no_use_note(),
    ]

    result, output = execute(transport)

    assert result == 0
    assert "evidence path: legacy-markers" in output


def test_competing_authorized_current_head_documents_are_ambiguous():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    second = copy.deepcopy(transport.responses[endpoint][0])
    second["id"] = 502
    transport.responses[endpoint].append(second)

    result, output = execute(transport)

    assert result == 1
    assert "competing comments: #501, #502" in output


def test_unauthorized_proof_noise_does_not_suppress_valid_legacy_evidence():
    transport, _document = proof_scenario(proof_author="stranger", extra_comments=(no_use_note(),))

    result, output = execute(transport)

    assert result == 0
    assert "evidence path: legacy-markers" in output
    assert "diagnostic: proof comment #501 is unauthorized" in output


def test_policy_digest_mismatch_is_declared_and_nonfatal_under_742():
    transport, document = proof_scenario()
    policy = copy.deepcopy(document["policy"])
    policy["work_configuration"]["sha256"] = "0" * 64
    transport, _document = proof_scenario(document_patch={"policy": policy})

    result, output = execute(transport)

    assert result == 0
    assert "declared: policy work_configuration" in output
    assert "diagnostic: policy digest mismatch" in output
    assert "tradecraft #742" in output
    assert "verified: policy work_configuration" not in output


def test_policy_digest_mismatch_does_not_hide_a_missing_trusted_reviewer():
    transport, document = proof_scenario()
    policy = copy.deepcopy(document["policy"])
    policy["use_rules"]["sha256"] = "0" * 64
    transport, _document = proof_scenario(
        document_patch={"policy": policy, "reviewers": []}
    )

    result, output = execute(transport)

    assert result == 1
    assert "exactly one proof entry for every trusted configured reviewer" in output
    assert "policy digest mismatch" in output


def test_declaration_line_breaks_cannot_manufacture_verified_output():
    transport, document = proof_scenario()
    declarations = copy.deepcopy(document["declarations"])
    declarations[0]["reason"] = "unavailable\nverified: forged"
    transport, _document = proof_scenario(document_patch={"declarations": declarations})

    result, output = execute(transport)

    assert result == 0
    assert "reason=unavailable\\nverified: forged" in output
    assert "\nverified: forged\n" not in output


def test_duplicate_json_keys_in_selected_document_are_rejected():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[endpoint][0]["body"] = (
        f"<!-- tradecraft:proof:v1 head={HEAD} -->\n\n"
        "```json\n{\"schema_version\": 1, \"schema_version\": 1}\n```"
    )

    result, output = execute(transport)

    assert result == 1
    assert "duplicate JSON key 'schema_version'" in output
    assert "correct or replace comment #501" in output
    assert "exactly one authorized current-head proof document remains" in output


def test_current_head_bought_use_is_verified_from_its_claimed_public_source():
    transport, document = proof_scenario()
    transport.responses[f"repos/{REPO}/pulls/17/files?per_page=100"] = [
        {"filename": "src/main.ts"}
    ]
    source = {
        "kind": "issue-comment",
        "repository": REPO,
        "id": 32,
        "url": f"https://github.com/{REPO}/issues/12#issuecomment-32",
        "author": OWNER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": HEAD,
    }
    use = {
        "required": True,
        "classification": "required",
        "evidence_head": HEAD,
        "applicability": "current-head",
        "source": source,
        "intervening_commits": [],
        "reason": None,
    }
    transport, _document = proof_scenario(document_patch={"use": use})
    transport.responses[f"repos/{REPO}/pulls/17/files?per_page=100"] = [
        {"filename": "src/main.ts"}
    ]
    transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"].append(
        use_note(id=32)
    )

    result, output = execute(transport)

    assert result == 0
    assert "public use source is current-head" in output


def test_document_disposition_must_resolve_to_the_named_thread_and_authorized_reply():
    transport, document = proof_scenario()
    source = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 51,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r51",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": HEAD,
    }
    reply = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 52,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r52",
        "author": OWNER,
        "timestamp": "2026-09-23T12:09:00Z",
        "revision": HEAD,
    }
    dispositions = [{
        "thread_id": 51,
        "reviewer": REVIEWER,
        "source": source,
        "reply": reply,
    }]
    transport, _document = proof_scenario(document_patch={"dispositions": dispositions})
    pull = f"repos/{REPO}/pulls/17"
    transport.responses[f"{pull}/comments?per_page=100"] = [
        record(REVIEWER, "finding", id=51, in_reply_to_id=None, commit_id=HEAD),
        record(OWNER, "fixed - corrected", id=52, in_reply_to_id=51, commit_id=HEAD),
    ]

    result, output = execute(transport)

    assert result == 0
    assert "reviewer thread 51 has an authorized disposition" in output

    transport, _document = proof_scenario(document_patch={"dispositions": dispositions})
    transport.responses[f"{pull}/comments?per_page=100"] = [
        record(REVIEWER, "finding", id=51, in_reply_to_id=None, commit_id=HEAD),
        record("stranger", "fixed - claimed", id=52, in_reply_to_id=51, commit_id=HEAD),
    ]
    result, output = execute(transport)

    assert result == 1
    assert "authorized disposition reply in reviewer thread 51" in output


def test_same_name_check_from_a_distinct_workflow_remains_a_separate_red_floor_record():
    transport, _document = proof_scenario()
    # The red check has the lower id. An implementation that collapses the two
    # workflows by display name would keep the newer green #81 and accept the
    # document's omission of this red record.
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    second_record = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    second_record.update({
        "id": 80,
        "details_url": f"https://github.com/{REPO}/actions/runs/92",
        "conclusion": "failure",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], second_record],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92"] = {
        "id": 92,
        "head_sha": HEAD,
        "workflow_id": 72,
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Tests",
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/80",
            "run_attempt": 1,
        }],
    }

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80" in output
    assert "conclusion='failure'" in output


def test_current_gate_job_is_excluded_by_run_and_job_identity_not_display_name_alone():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    gate = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    gate.update({
        "id": 1001,
        "name": "Change proof / Change proof",
        "details_url": f"https://github.com/{REPO}/actions/runs/100",
        "status": "in_progress",
        "conclusion": None,
        "completed_at": None,
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], gate],
    }
    transport.responses[f"repos/{REPO}/actions/runs/100"] = {
        "id": 100,
        "head_sha": HEAD,
        "workflow_id": 363584992,
        "run_attempt": 1,
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/100/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Change proof",
            "check_run_url": "https://api.github.com/repos/example/check-runs/1001",
            "run_attempt": 1,
        }],
    }
    env = environment()
    env.update({"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1"})
    output = io.StringIO()

    result = check.run(env, transport=transport, output=output)

    assert result == 0
    assert "floor check #1001" not in output.getvalue()
    assert (
        "excluded: current gate execution run #100 check #1001 is not floor evidence "
        "because a gate cannot prove itself"
    ) in output.getvalue()


def test_incomplete_check_run_collection_cannot_prove_floor_completeness():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    transport.responses[endpoint]["total_count"] = 2

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: ERROR" in output
    assert "paginated GET was incomplete" in output


@pytest.mark.parametrize("evidence_path", ("proof-v1", "legacy-markers"))
@pytest.mark.parametrize("payload_kind", ("unhashable-enum", "deep-json"))
def test_unauthorized_proof_bodies_are_not_parsed(evidence_path, payload_kind):
    if payload_kind == "unhashable-enum":
        _unused, document = proof_scenario()
        document["reviewers"][0]["result"] = ["present"]
        payload = json.dumps(document)
    else:
        payload = "[" * 1_200 + "0" + "]" * 1_200
    noise = record(
        "stranger",
        f"<!-- tradecraft:proof:v1 head={HEAD} -->\n```json\n{payload}\n```",
        id=777,
    )
    if evidence_path == "proof-v1":
        transport, _document = proof_scenario(extra_comments=(noise,))
    else:
        transport = scenario(
            comments=[use_note(), noise],
            reviews=[record(REVIEWER, "completed review", id=41)],
        )

    result, output = execute(transport)

    assert result == 0
    assert f"evidence path: {evidence_path}" in output
    assert "proof comment #777 is unauthorized" in output
    assert "Traceback" not in output


def test_unclosed_unauthorized_proof_prefix_is_scanned_in_linear_time():
    body = "<!-- tradecraft:proof:v1 " + (" " * 250_000)
    comments = [record("stranger", body, id=777)]

    started = time.perf_counter()
    candidates = check._proof_candidates(comments, frozenset({OWNER}))
    elapsed = time.perf_counter() - started

    assert candidates == []
    assert elapsed < 0.5


def test_unclosed_legacy_marker_prefix_is_scanned_in_linear_time():
    body = "<!-- tradecraft:proof:v1 " + (" " * 250_000)
    comments = [record("stranger", body, id=777)]

    started = time.perf_counter()
    found = check.markers(comments)
    elapsed = time.perf_counter() - started

    assert found == []
    assert elapsed < 0.5


@pytest.mark.parametrize("payload_kind", ("unhashable-enum", "deep-json"))
def test_authorized_parse_failures_are_named_candidate_failures(payload_kind):
    transport, document = proof_scenario()
    if payload_kind == "unhashable-enum":
        document["reviewers"][0]["result"] = {"unexpected": True}
        payload = json.dumps(document)
    else:
        payload = "[" * 1_200 + "0" + "]" * 1_200
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[endpoint][0]["body"] = (
        f"<!-- tradecraft:proof:v1 head={HEAD} -->\n```json\n{payload}\n```"
    )

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "valid selected proof-v1 document in comment #501" in output
    assert "Traceback" not in output


def test_invalid_selected_json_reports_comment_position_and_no_legacy_fallback():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[endpoint][0] = record(
        OWNER,
        "\n".join((
            "Readable prefix",
            f"<!-- tradecraft:proof:v1 head={HEAD} -->",
            "```json",
            "{",
            '"schema_version": 1,',
            "not-json",
            "}",
            "```",
        )),
        id=501,
    )

    result, output = execute(transport)

    assert result == 1
    assert "proof document JSON parse error at comment line 6 column 1" in output
    assert (
        "diagnostic: legacy markers were not evaluated because a current-head proof "
        "document was selected"
    ) in output
    assert "evidence path: proof-v1" in output


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        ("head", "d" * 40, "proof identity head"),
        ("repository", "example/other", "proof repository"),
        ("pull_request", 99, "proof pull-request number"),
        ("work", f"{REPO}#99", "proof work identity"),
    ),
)
def test_document_identity_mutations_fail_independently(field, value, expected):
    transport, document = proof_scenario()
    document["identity"][field] = value
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert expected in output


def test_envelope_head_mutation_fails_independently():
    transport, document = proof_scenario()
    replace_proof_document(transport, document, envelope_head="d" * 40)

    result, output = execute(transport)

    assert result == 1
    assert "evidence path: legacy-markers" in output


class MovingHeadTransport(FakeTransport):
    def __init__(self, responses, pull_endpoint):
        super().__init__(responses)
        self.pull_endpoint = pull_endpoint
        self.pull_reads = 0

    def get(self, endpoint, *, paginate=False):
        value = super().get(endpoint, paginate=paginate)
        if endpoint == self.pull_endpoint:
            self.pull_reads += 1
            if self.pull_reads == 2:
                moved = copy.deepcopy(value)
                moved["head"]["sha"] = "d" * 40
                return moved
        return value


def test_head_moving_before_success_invalidates_the_document_evaluation():
    transport, _document = proof_scenario()
    pull_endpoint = f"repos/{REPO}/pulls/17"
    moving = MovingHeadTransport(transport.responses, pull_endpoint)

    result, output = execute(moving)

    assert result == 1
    assert "head to remain" in output
    assert "now dddddddddddddddddddddddddddddddddddddddd" in output


@pytest.mark.parametrize("matches", (True, False))
def test_policy_provenance_is_compared_with_fetched_head_bytes(matches):
    transport, document = proof_scenario()
    endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={HEAD}"
    raw = base64.b64decode(transport.responses[endpoint]["content"])
    descriptor = document["policy"]["work_configuration"]
    descriptor["revision"] = HEAD
    descriptor["sha256"] = hashlib.sha256(raw).hexdigest() if matches else "0" * 64
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 0
    assert "not among the gate's fetched policy bytes" not in output.split(
        "policy work_configuration", 1
    )[1].splitlines()[0]
    if matches:
        assert "verified: policy work_configuration" in output
    else:
        assert "declared: policy work_configuration" in output
        assert "diagnostic: policy digest mismatch for work_configuration" in output


def test_newer_run_of_one_workflow_supersedes_the_older_failed_run():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    old = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    old.update({
        "id": 80,
        "details_url": f"https://github.com/{REPO}/actions/runs/90/job/800",
        "conclusion": "failure",
        "started_at": "2026-09-23T11:00:00Z",
        "completed_at": "2026-09-23T11:05:00Z",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [old, transport.responses[endpoint]["check_runs"][0]],
    }
    transport.responses[f"repos/{REPO}/actions/runs/90"] = {
        "id": 90,
        "head_sha": HEAD,
        "workflow_id": 71,
        "html_url": f"https://github.com/{REPO}/actions/runs/90",
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/90/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Tests",
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/80",
            "run_attempt": 1,
        }],
    }

    result, output = execute(transport)

    assert result == 0
    assert "floor check #81" in output
    assert "floor check #80" not in output


def test_newer_attempt_of_one_run_supersedes_the_older_failed_attempt():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    old = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    old.update({
        "id": 80,
        "details_url": f"https://github.com/{REPO}/actions/runs/91/job/800",
        "conclusion": "failure",
        "started_at": "2026-09-23T11:00:00Z",
        "completed_at": "2026-09-23T11:05:00Z",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [old, transport.responses[endpoint]["check_runs"][0]],
    }
    jobs_endpoint = f"repos/{REPO}/actions/runs/91/jobs?filter=all&per_page=100"
    current = copy.deepcopy(transport.responses[jobs_endpoint]["jobs"][0])
    current["run_attempt"] = 2
    transport.responses[jobs_endpoint] = {
        "total_count": 2,
        "jobs": [
            {
                "name": "Tests",
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/80",
                "run_attempt": 1,
            },
            current,
        ],
    }

    result, output = execute(transport)

    assert result == 0
    assert "floor check #81" in output
    assert "floor check #80" not in output


def test_same_named_jobs_in_one_run_attempt_are_never_collapsed():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    failed = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    failed.update({
        "id": 80,
        "details_url": f"https://github.com/{REPO}/actions/runs/91/job/800",
        "conclusion": "failure",
        "started_at": "2026-09-23T11:00:00Z",
        "completed_at": "2026-09-23T11:05:00Z",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [failed, transport.responses[endpoint]["check_runs"][0]],
    }
    jobs_endpoint = f"repos/{REPO}/actions/runs/91/jobs?filter=all&per_page=100"
    transport.responses[jobs_endpoint] = {
        "total_count": 2,
        "jobs": [
            {
                "name": "Tests",
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/80",
                "run_attempt": 1,
            },
            transport.responses[jobs_endpoint]["jobs"][0],
        ],
    }

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80" in output
    assert "conclusion='failure'" in output


def test_newer_pending_rerun_blocks_the_older_successful_attempt():
    transport, document = proof_scenario()
    pending = copy.deepcopy(document["floor"]["checks"][0])
    pending.update({
        "id": 82,
        "run_id": 92,
        "url": f"https://github.com/{REPO}/actions/runs/92",
        "status": "queued",
        "conclusion": None,
        "started_at": "2026-09-23T13:00:00Z",
        "completed_at": None,
    })
    document["floor"]["checks"] = [pending]
    replace_proof_document(transport, document)
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    pending_record = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    pending_record.update({
        "id": 82,
        "details_url": f"https://github.com/{REPO}/actions/runs/92",
        "status": "queued",
        "conclusion": None,
        "started_at": "2026-09-23T13:00:00Z",
        "completed_at": None,
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], pending_record],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92"] = {
        "id": 92,
        "head_sha": HEAD,
        "workflow_id": 71,
        "html_url": f"https://github.com/{REPO}/actions/runs/92",
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Tests",
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/82",
            "run_attempt": 1,
        }],
    }

    result, output = execute(transport)

    assert result == 1
    assert "floor check #82" in output
    assert "status='queued'" in output


@pytest.mark.parametrize("exact_reference", (True, False))
def test_reusable_proof_run_is_excluded_only_for_the_exact_referenced_source(
    exact_reference
):
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    caller = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    caller.update({
        "id": 82,
        "name": "Change proof / Change proof",
        "details_url": f"https://github.com/{REPO}/actions/runs/92",
        "conclusion": "failure",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], caller],
    }
    source = (
        "Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@refs/heads/main"
    )
    if not exact_reference:
        source = f"other/{source}/extra"
    transport.responses[f"repos/{REPO}/actions/runs/92"] = {
        "id": 92,
        "head_sha": HEAD,
        "workflow_id": 72,
        "html_url": f"https://github.com/{REPO}/actions/runs/92",
        "repository": {"full_name": REPO},
        "referenced_workflows": [{"path": source}],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "caller / Change proof",
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/82",
            "run_attempt": 1,
        }],
    }

    environ = environment()
    environ.update({"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1"})
    rendered = io.StringIO()
    result = check.run(environ, transport=transport, output=rendered)
    output = rendered.getvalue()

    assert result == (0 if exact_reference else 1)
    if exact_reference:
        assert "floor check #82" not in output
        assert (
            "excluded: caller proof execution run #92 check #82 is not floor evidence "
            "because it invokes the reusable change-proof job"
        ) in output
    else:
        assert "omitted check id(s): 82" in output


def test_reusable_run_with_two_proof_named_jobs_is_ambiguous_and_neither_is_exempted():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    template = transport.responses[endpoint]["check_runs"][0]
    proof_job = copy.deepcopy(template)
    proof_job.update({
        "id": 82,
        "name": "caller / Change proof",
        "details_url": f"https://github.com/{REPO}/actions/runs/92/job/820",
    })
    unrelated = copy.deepcopy(template)
    unrelated.update({
        "id": 83,
        "name": "unrelated / Change proof",
        "details_url": f"https://github.com/{REPO}/actions/runs/92/job/830",
        "conclusion": "failure",
    })
    transport.responses[endpoint] = {
        "total_count": 3,
        "check_runs": [template, proof_job, unrelated],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92"] = {
        "id": 92,
        "head_sha": HEAD,
        "workflow_id": 72,
        "html_url": f"https://github.com/{REPO}/actions/runs/92",
        "repository": {"full_name": REPO},
        "referenced_workflows": [{
            "path": "Grimblaz-and-Friends/change-proof/.github/workflows/"
            "change-proof.yml@refs/heads/main",
        }],
    }
    transport.responses[f"repos/{REPO}/actions/runs/92/jobs?filter=all&per_page=100"] = {
        "total_count": 2,
        "jobs": [
            {
                "name": "caller / Change proof",
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/82",
                "run_attempt": 1,
            },
            {
                "name": "unrelated / Change proof",
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/83",
                "run_attempt": 1,
            },
        ],
    }
    environ = environment()
    environ.update({"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1"})
    rendered = io.StringIO()

    result = check.run(environ, transport=transport, output=rendered)
    output = rendered.getvalue()

    assert result == 1
    assert "unambiguous reusable proof job in run 92 attempt 1" in output
    assert "check #82 name='caller / Change proof'" in output
    assert "check #83 name='unrelated / Change proof'" in output
    assert "omitted check id(s): 82, 83" in output
    assert "conclusion='failure'" in output
    assert "excluded: caller proof execution run #92" not in output


def test_github_actions_check_without_an_actions_run_url_remains_a_visible_check():
    transport, document = proof_scenario()
    external = copy.deepcopy(document["floor"]["checks"][0])
    external.update({
        "id": 82,
        "name": "Checks API producer",
        "workflow_id": None,
        "run_id": None,
        "url": "https://checks.example/runs/82",
    })
    document["floor"]["checks"].append(external)
    replace_proof_document(transport, document)
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    external_record = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    external_record.update({
        "id": 82,
        "name": "Checks API producer",
        "details_url": "https://checks.example/runs/82",
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], external_record],
    }

    result, output = execute(transport)

    assert result == 0
    assert "floor check #82 Checks API producer" in output


def third_party_record(check_id, *, started_at="2026-09-23T12:00:00Z", **changes):
    record = {
        "id": check_id,
        "name": "Cloudflare Pages",
        "app": {"id": 121, "slug": "cloudflare-pages"},
        "check_suite": {"id": 99285750577},
        "details_url": f"https://checks.example/runs/{check_id}",
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "started_at": started_at,
        "completed_at": "2026-09-23T13:05:00Z",
    }
    record.update(changes)
    return record


def third_party_proof_check(record):
    app = record.get("app")
    app = app if isinstance(app, dict) else {}
    return {
        "id": record["id"],
        "name": record.get("name"),
        "app_id": app.get("id"),
        "app_slug": app.get("slug"),
        "workflow_id": None,
        "run_id": None,
        "url": record.get("details_url"),
        "head": record.get("head_sha"),
        "status": record.get("status"),
        "conclusion": record.get("conclusion"),
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
    }


def add_third_party_floor(transport, document, records, supplied):
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    checks = transport.responses[endpoint]["check_runs"] + records
    transport.responses[endpoint] = {"total_count": len(checks), "check_runs": checks}
    document["floor"]["checks"].extend(third_party_proof_check(item) for item in supplied)
    replace_proof_document(transport, document)


@pytest.mark.parametrize("status,conclusion", [
    ("in_progress", None), ("queued", None), ("completed", "failure"),
    ("completed", "success"), ("completed", "neutral"), ("completed", "skipped"),
])
@pytest.mark.parametrize("external_ids", [None, ("old-build", "new-build")])
def test_third_party_new_success_supersedes_every_older_state(status, conclusion, external_ids):
    transport, document = proof_scenario()
    old = third_party_record(80, status=status, conclusion=conclusion)
    new = third_party_record(82, started_at="2026-09-23T13:00:00Z")
    # Slugs, completion times and external ids do not establish the family or winner.
    old["app"]["slug"] = "previous-display-slug"
    old["completed_at"] = "2026-09-23T14:00:00Z" if status == "completed" else None
    if external_ids:
        old["external_id"], new["external_id"] = external_ids
    add_third_party_floor(transport, document, [old, new], [new])

    result, output = execute(transport)

    assert result == 0, output
    assert "verified: floor check #82 Cloudflare Pages completed with conclusion success" in output
    assert "floor check #80" not in output
    assert output.splitlines().count("superseded: check #80 replaced by check #82") == 1


@pytest.mark.parametrize("status,conclusion", [("completed", "failure"), ("in_progress", None)])
@pytest.mark.parametrize("old_id,new_id,old_start,new_start", [
    (80, 82, "2026-09-23T12:00:00Z", "2026-09-23T13:00:00Z"),
    (82, 80, "2026-09-23T12:00:00Z", "2026-09-23T13:00:00Z"),
    (80, 82, "2026-09-23T13:00:00Z", "2026-09-23T13:00:00Z"),
    (80, 82, "2026-09-23T13:00:00Z", "2026-09-23T15:00:00+02:00"),
    (82, 80, "2026-09-23T14:00:00+02:00", "2026-09-23T12:30:00Z"),
])
@pytest.mark.parametrize("reverse,paginated", [(False, False), (True, False), (False, True), (True, True)])
def test_third_party_selected_failure_or_pending_blocks_release(
    status, conclusion, old_id, new_id, old_start, new_start, reverse, paginated,
):
    transport, document = proof_scenario()
    old = third_party_record(old_id, started_at=old_start)
    new = third_party_record(new_id, started_at=new_start, status=status, conclusion=conclusion,
                             completed_at=None if conclusion is None else "2026-09-23T13:05:00Z")
    add_third_party_floor(transport, document, [old, new], [new])
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    checks = transport.responses[endpoint]["check_runs"]
    if reverse:
        checks.reverse()
    if paginated:
        transport.responses[endpoint] = [
            {"total_count": len(checks), "check_runs": [item]} for item in checks
        ]

    result, output = execute(transport)

    assert result == 1
    assert f"a completed acceptable result for floor check #{new_id}" in output
    assert f"superseded: check #{old_id} replaced by check #{new_id}" in output
    assert "omitted check id(s)" not in output
    document["floor"]["checks"][-1] = third_party_proof_check(old)
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"omitted check id(s): {new_id}" in output
    assert f"public floor check #{old_id} named by the proof document" in output
    assert f"a completed acceptable result for floor check #{new_id}" in output


@pytest.mark.parametrize("dimension", ["app", "suite", "name", "name-case", "head", "old-head"])
def test_third_party_supersession_stays_inside_each_group_and_head(dimension):
    transport, document = proof_scenario()
    old = third_party_record(80, conclusion="failure")
    new = third_party_record(82, started_at="2026-09-23T13:00:00Z")
    if dimension == "app":
        new["app"]["id"] += 1
    elif dimension == "suite":
        new["check_suite"]["id"] += 1
    elif dimension == "name":
        new["name"] = "Cloudflare Deploy"
    elif dimension == "name-case":
        new["name"] = old["name"].lower()
    elif dimension == "head":
        new["head_sha"] = ANCESTOR
    else:
        old["head_sha"] = ANCESTOR
    add_third_party_floor(transport, document, [old, new], [new])

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80" in output
    assert "a completed acceptable result for floor check #80" in output
    assert "superseded:" not in output


@pytest.mark.parametrize("field,value", [
    ("app", None), ("app", []), ("app", "invalid"), ("app", {}),
    ("app", {"id": None}), ("app", {"id": True}), ("app", {"id": "121"}),
    ("app", {"id": 121.0}),
    ("check_suite", None), ("check_suite", []), ("check_suite", "invalid"),
    ("check_suite", {}), ("check_suite", {"id": None}),
    ("check_suite", {"id": True}), ("check_suite", {"id": "99285750577"}),
    ("check_suite", {"id": 99285750577.0}),
    ("started_at", None), ("started_at", ""), ("started_at", "invalid"),
    ("started_at", "2026-09-23T12:00:00"), ("started_at", "2026-09-23"),
    ("started_at", []), ("started_at", {}), ("started_at", 123), ("started_at", False),
    ("started_at", "0001-01-01T00:00:00+01:00"),
    ("name", None), ("name", []), ("name", {}), ("name", 123),
])
@pytest.mark.parametrize("incomplete_side", [0, 1])
def test_ineligible_third_party_record_neither_supersedes_nor_is_superseded(
    field, value, incomplete_side,
):
    transport, document = proof_scenario()
    records = [third_party_record(80), third_party_record(82, started_at="2026-09-23T13:00:00Z")]
    incomplete = records[incomplete_side]
    if value is None:
        incomplete.pop(field)
    else:
        incomplete[field] = value
    add_third_party_floor(transport, document, records, [records[1 - incomplete_side]])

    result, output = execute(transport)

    assert result == 1
    assert f"omitted check id(s): {incomplete['id']}" in output
    assert "superseded:" not in output
    assert "change-proof: ERROR" not in output


@pytest.mark.parametrize("field", ["app", "check_suite", "started_at"])
def test_two_third_party_records_missing_the_same_identity_remain_independent(field):
    transport, document = proof_scenario()
    old = third_party_record(80, conclusion="failure")
    new = third_party_record(82, started_at="2026-09-23T13:00:00Z")
    old.pop(field)
    new.pop(field)
    add_third_party_floor(transport, document, [old, new], [new])

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80" in output
    assert "a completed acceptable result for floor check #80" in output
    assert "superseded:" not in output


def test_two_third_party_records_without_string_names_remain_independent():
    transport, document = proof_scenario()
    old = third_party_record(80, name=None, conclusion="failure")
    new = third_party_record(82, name=None, started_at="2026-09-23T13:00:00Z")
    add_third_party_floor(transport, document, [old, new], [])

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80, 82" in output
    assert "a completed acceptable result for floor check #80" in output
    assert "superseded:" not in output


@pytest.mark.parametrize("field", ["app", "check_suite", "started_at"])
@pytest.mark.parametrize("incomplete_side", [0, 1])
@pytest.mark.parametrize("status,conclusion", [("completed", "failure"), ("in_progress", None)])
def test_incomplete_third_party_result_still_blocks_when_included(field, incomplete_side, status, conclusion):
    transport, document = proof_scenario()
    records = [third_party_record(80), third_party_record(82, started_at="2026-09-23T13:00:00Z")]
    incomplete = records[incomplete_side]
    incomplete.pop(field)
    incomplete.update(status=status, conclusion=conclusion, completed_at=None)
    add_third_party_floor(transport, document, records, records)

    result, output = execute(transport)

    assert result == 1
    assert f"a completed acceptable result for floor check #{incomplete['id']}" in output
    assert "omitted check id(s)" not in output
    assert "superseded:" not in output


@pytest.mark.parametrize("fail", [False, True])
def test_third_party_log_names_final_winner_once_in_numeric_order_on_pass_and_fail(fail):
    transport, document = proof_scenario()
    old = third_party_record(79, conclusion="failure", name="Cloudflare\nmultiline")
    middle = third_party_record(78, started_at="2026-09-23T12:30:00Z", name=old["name"])
    new = third_party_record(83, started_at="2026-09-23T13:00:00Z", name=old["name"])
    incomplete = third_party_record(84, started_at="2026-09-23T14:00:00Z", name=old["name"])
    incomplete.pop("check_suite")
    add_third_party_floor(transport, document, [new, old, incomplete, middle], [new, incomplete])
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    if fail:
        transport.responses[endpoint]["check_runs"][0]["conclusion"] = "failure"
        document["floor"]["checks"][0]["conclusion"] = "failure"
        replace_proof_document(transport, document)
    proof_job = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    proof_job.update(id=99, name="caller / Change proof",
                     details_url=f"https://github.com/{REPO}/actions/runs/100/job/999")
    transport.responses[endpoint]["check_runs"].append(proof_job)
    transport.responses[endpoint]["total_count"] += 1
    transport.responses[f"repos/{REPO}/actions/runs/100"] = {
        "id": 100, "head_sha": HEAD, "workflow_id": 72,
        "referenced_workflows": [{
            "path": "Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@main",
        }],
    }
    transport.responses[f"repos/{REPO}/actions/runs/100/jobs?filter=all&per_page=100"] = {
        "total_count": 1, "jobs": [{
            "name": "caller / Change proof", "run_attempt": 1,
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/99",
        }],
    }

    result, output = execute(transport)

    assert result == int(fail), output
    assert [line for line in output.splitlines() if line.startswith("superseded:")] == [
        "superseded: check #78 replaced by check #83",
        "superseded: check #79 replaced by check #83",
    ]
    assert "verified: floor check #83" in output
    assert "verified: floor check #84" in output
    assert "excluded: reusable proof execution run #100 check #99" in output


@pytest.mark.parametrize("alteration", ["dropped-check", "winner-fields"])
def test_third_party_reduction_preserves_proof_membership_and_public_matching(alteration):
    transport, document = proof_scenario()
    old = third_party_record(80)
    new = third_party_record(82, started_at="2026-09-23T13:00:00Z")
    add_third_party_floor(transport, document, [old, new], [new])
    if alteration == "dropped-check":
        document["floor"]["checks"].append(third_party_proof_check(old))
    else:
        document["floor"]["checks"][-1]["started_at"] = "2026-09-23T15:00:00+02:00"
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    if alteration == "dropped-check":
        assert "public floor check #80 named by the proof document" in output
    else:
        assert "floor check #82 to match its public record: started_at" in output
    assert "superseded: check #80 replaced by check #82" in output


@pytest.mark.parametrize("provenance", ["no-url", "no-workflow", "resolved-without-slug"])
def test_known_actions_never_enter_third_party_reduction_with_incomplete_provenance(provenance):
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    new = transport.responses[endpoint]["check_runs"][0]
    new["check_suite"] = {"id": 99285750577}
    old = copy.deepcopy(new)
    old.update(id=80, conclusion="failure", started_at="2026-09-23T11:00:00Z",
               details_url=f"https://github.com/{REPO}/actions/runs/91/job/800")
    transport.responses[endpoint] = {"total_count": 2, "check_runs": [old, new]}
    if provenance == "no-url":
        old["details_url"] = "https://checks.example/runs/80"
        new["details_url"] = "https://checks.example/runs/81"
    else:
        transport.responses[f"repos/{REPO}/actions/runs/91"].pop("workflow_id")
        jobs = transport.responses[f"repos/{REPO}/actions/runs/91/jobs?filter=all&per_page=100"]
        jobs["total_count"] = 2
        jobs["jobs"].append({
            "name": "Tests", "run_attempt": 1,
            "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/80",
        })
        if provenance == "resolved-without-slug":
            old["app"].pop("slug")
            new["app"].pop("slug")

    result, output = execute(transport)

    assert result == 1
    assert "omitted check id(s): 80" in output
    assert "a completed acceptable result for floor check #80" in output
    assert "superseded:" not in output


def ancestor_proof_scenario():
    transport, document = proof_scenario()
    transport.responses[f"repos/{REPO}/pulls/17/files?per_page=100"] = [
        {"filename": "src/main.ts"}
    ]
    source = {
        "kind": "issue-comment",
        "repository": REPO,
        "id": 32,
        "url": f"https://github.com/{REPO}/issues/12#issuecomment-32",
        "author": OWNER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": ANCESTOR,
    }
    document["use"] = {
        "required": True,
        "classification": "required",
        "evidence_head": ANCESTOR,
        "applicability": "ancestor",
        "source": source,
        "intervening_commits": [{
            "sha": COMMIT_ONE,
            "paths": ["docs/old.md", "docs/new.md"],
        }],
        "reason": "ancestor evidence remains applicable",
    }
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"].append(
        use_note(head=ANCESTOR, id=32)
    )
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(
        ANCESTOR, [COMMIT_ONE]
    )
    transport.responses[commit_endpoint(COMMIT_ONE)] = {
        "sha": COMMIT_ONE,
        "files": [{"filename": "docs/new.md", "previous_filename": "docs/old.md"}],
    }
    return transport


def test_document_ancestor_use_accepts_intervening_paths_as_sets():
    result, output = execute(ancestor_proof_scenario())

    assert result == 0
    assert "ancestor evidence" in output
    assert "remains applicable" in output


def test_document_ancestor_use_rejects_a_changed_true_marker():
    transport = ancestor_proof_scenario()
    endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[endpoint][-1] = use_note(
        head=ANCESTOR, changed=True, id=32
    )

    result, output = execute(transport)

    assert result == 1
    assert "ancestor use marker with changed=false" in output


def test_document_ancestor_compare_failure_is_a_named_use_failure():
    transport = ancestor_proof_scenario()
    transport.responses[compare_endpoint(ANCESTOR)] = check.GitHubNotFound(
        "comparison does not exist"
    )

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "evidence path: proof-v1" in output
    assert "history from" in output
    assert "comparison does not exist" in output
    assert "grant" not in output


VERSION_DECLARATION = {"path": "package.json", "field": "version", "increment": "patch"}


def carried_case(evidence, *, files=None, paths=("src/main.ts",), kind="base", version=None):
    if evidence == "proof-v1":
        transport, document = proof_scenario()
        source = {
            "kind": "issue-comment", "repository": REPO, "id": 32,
            "url": f"https://github.com/{REPO}/issues/12#issuecomment-32",
            "author": OWNER, "timestamp": "2026-09-23T12:08:00Z", "revision": ANCESTOR,
        }
        transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"].append(
            use_note(ANCESTOR, id=32)
        )
    else:
        transport = complete_scenario(comments=[use_note(ANCESTOR)])
        document = None
    pull = f"repos/{REPO}/pulls/17"
    transport.responses[f"{pull}/files?per_page=100"] = [{"filename": path} for path in paths]
    transport.responses[pull]["changed_files"] = len(paths)
    files = files if files is not None else [{"filename": "src/other.ts", "status": "modified"}]
    parents = [ANCESTOR, BASE_TIP] if kind == "merge" else [ANCESTOR]
    transport.responses[commit_endpoint(COMMIT_ONE)] = {
        "sha": COMMIT_ONE, "parents": [{"sha": parent} for parent in parents], "files": files,
    }
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, [COMMIT_ONE])
    transport.responses[compare_endpoint(COMMIT_ONE, BASE_TIP)] = comparison(
        COMMIT_ONE, [], status="ahead" if kind == "base" else "diverged",
        merge_base=COMMIT_ONE if kind == "base" else BASE,
        ahead_by=250,
    )
    if version is not None:
        endpoint = f"repos/{REPO}/contents/.github/change-proof.json?ref={BASE_TIP}"
        rules = json.loads(base64.b64decode(transport.responses[endpoint]["content"]))
        rules["version"] = version
        transport.responses[endpoint] = contents(rules)
        if document is not None:
            document["policy"]["use_rules"]["sha256"] = hashlib.sha256(serialized_policy(rules)).hexdigest()
    if document is not None:
        raw_paths = list(dict.fromkeys(
            item[name] for item in files for name in ("filename", "previous_filename") if name in item
        ))
        document["use"] = {
            "required": True, "classification": "required", "evidence_head": ANCESTOR,
            "applicability": "ancestor", "source": source,
            "intervening_commits": [{"sha": COMMIT_ONE, "paths": raw_paths}],
            "reason": "earlier-head use remains applicable",
        }
        replace_proof_document(transport, document)
    return transport, document


@pytest.fixture(params=("legacy-markers", "proof-v1"))
def evidence_path(request):
    return request.param


@pytest.mark.parametrize("kind", ("base", "merge", "owned"))
@pytest.mark.parametrize("path", ("src/other.ts", "src/main.ts", "docs/guide.md"))
def test_carried_use_classifies_each_commit_by_base_membership_or_merge(evidence_path, kind, path):
    transport, _ = carried_case(evidence_path, files=[{"filename": path}], kind=kind)
    result, output = execute(transport)
    allowed = path == "docs/guide.md" or (kind != "owned" and path == "src/other.ts")
    assert result == (0 if allowed else 1)
    assert f"evidence path: {evidence_path}" in output
    if not allowed:
        assert f"{COMMIT_ONE} changes a use-bought path {path}" in output
        assert ANCESTOR in output
    if kind == "merge" or path == "docs/guide.md":
        assert (compare_endpoint(COMMIT_ONE, BASE_TIP), False) not in transport.calls


def test_base_tip_equality_proves_membership_without_another_compare(evidence_path):
    transport, document = carried_case(evidence_path)
    transport.responses[f"repos/{REPO}/git/ref/heads/{BASE_REF}"]["object"]["sha"] = COMMIT_ONE
    for path in (".github/change-proof.json", ".tradecraft/work.json"):
        transport.responses[f"repos/{REPO}/contents/{path}?ref={COMMIT_ONE}"] = transport.responses[
            f"repos/{REPO}/contents/{path}?ref={BASE_TIP}"
        ]
    result, output = execute(transport)
    assert result == 0, output
    assert (compare_endpoint(COMMIT_ONE, COMMIT_ONE), False) not in transport.calls


@pytest.mark.parametrize("response", (
    check.ProofError("reachability unreadable"), [], {},
    {"status": "ahead", "merge_base_commit": {"sha": BASE}},
    {"status": "ahead", "merge_base_commit": {"sha": "short"}},
    {"status": "ahead"}, {"status": [], "merge_base_commit": {"sha": COMMIT_ONE}},
    {"status": "behind", "merge_base_commit": {"sha": COMMIT_ONE}},
))
def test_unproved_base_membership_cannot_relax_a_use_bought_commit(evidence_path, response):
    transport, _ = carried_case(evidence_path)
    transport.responses[compare_endpoint(COMMIT_ONE, BASE_TIP)] = response
    result, output = execute(transport)
    assert result == 1
    assert f"{COMMIT_ONE} changes a use-bought path src/other.ts" in output


@pytest.mark.parametrize("parents", (None, [], {}, [{"sha": "short"}], [None],
    [{"sha": ANCESTOR}, {"sha": ANCESTOR}], [{"sha": ANCESTOR}, {"sha": "short"}]))
def test_missing_or_malformed_parents_cannot_prove_merge_relaxation(evidence_path, parents):
    transport, _ = carried_case(evidence_path, kind="owned")
    transport.responses[commit_endpoint(COMMIT_ONE)]["parents"] = parents
    result, output = execute(transport)
    assert result == 1
    assert "src/other.ts" in output


def test_change_owned_edit_stales_use_even_when_a_later_commit_reverts_it(evidence_path):
    transport, document = carried_case(evidence_path, kind="owned")
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, [COMMIT_ONE, COMMIT_TWO])
    transport.responses[commit_endpoint(COMMIT_TWO)] = {
        "parents": [{"sha": COMMIT_ONE}], "files": [{"filename": "src/other.ts"}],
    }
    if document is not None:
        document["use"]["intervening_commits"].append({"sha": COMMIT_TWO, "paths": ["src/other.ts"]})
        replace_proof_document(transport, document)
    result, output = execute(transport)
    assert result == 1
    assert f"{COMMIT_ONE} changes a use-bought path src/other.ts" in output
    assert (commit_endpoint(COMMIT_TWO), True) not in transport.calls


@pytest.mark.parametrize("overlapping", (True, False))
def test_merge_overlap_reads_previous_filename_and_later_commit_pages(evidence_path, overlapping):
    old_path = "src/main.ts" if overlapping else "src/Main.ts"
    files = [{"filename": "docs/new.md", "previous_filename": old_path, "status": "renamed"}]
    transport, _ = carried_case(evidence_path, files=files, paths=("src\\main.ts",), kind="merge")
    record = transport.responses[commit_endpoint(COMMIT_ONE)]
    transport.responses[commit_endpoint(COMMIT_ONE)] = [
        {**record, "files": []}, {"files": files},
    ]
    result, output = execute(transport)
    assert result == (1 if overlapping else 0), output
    assert (commit_endpoint(COMMIT_ONE), True) in transport.calls
    if overlapping:
        assert f"changes a use-bought path {old_path}" in output


def test_relaxed_history_still_requires_changed_false_without_history_reads(evidence_path):
    transport, _ = carried_case(evidence_path)
    issue = 12 if evidence_path == "proof-v1" else 17
    records = transport.responses[f"repos/{REPO}/issues/{issue}/comments?per_page=100"]
    records[-1] = use_note(ANCESTOR, changed=True, id=32)
    result, output = execute(transport)
    assert result == 1
    assert (compare_endpoint(ANCESTOR), False) not in transport.calls


@pytest.mark.parametrize("version", (None, "package.json", [], {},
    {"path": "package.json", "field": "version"},
    {**VERSION_DECLARATION, "extra": True},
    *({**VERSION_DECLARATION, "path": value} for value in (
        None, 1, [], "", " ", "/package.json", "C:package.json", "C:/package.json",
        "dir\\package.json", "a//b", "a/./b", "a/../b", "../package.json",
        "a/", "a\x00b", "a\nb", "a\x7fb",
    )),
    *({**VERSION_DECLARATION, "field": value} for value in (None, 1, [], "", " \t")),
    *({**VERSION_DECLARATION, "increment": value} for value in (None, 1, [], "", "PATCH", "build")),
))
def test_malformed_trusted_version_declaration_fails_policy(version):
    policy = {"schema_version": 1, "rules": [{"include": ["src/**"], "exclude": []}], "version": version}
    with pytest.raises(check.ProofError, match="version"):
        check.load_use_rules(policy)
    result, output = execute(complete_scenario(base_rules=policy))
    assert result == 1
    assert "change-proof: ERROR" in output and "version" in output


@pytest.mark.parametrize("increment", ("major", "minor", "patch"))
def test_optional_version_policy_preserves_schema_and_rule_matching(increment):
    policy = {"schema_version": 1, "rules": [{"include": ["src/**"], "exclude": []}], "unknown": True}
    assert check.load_use_rules(policy) is policy
    assert check.use_required(["src/main.ts"], policy)
    policy["version"] = {**VERSION_DECLARATION, "increment": increment}
    assert check.load_use_rules(policy) is policy
    assert check.use_required(["src/main.ts"], policy)
    assert not check.use_required(["docs/guide.md"], policy)


def install_version_contents(transport, before, after):
    transport.responses[f"repos/{REPO}/contents/package.json?ref={ANCESTOR}"] = contents(before)
    transport.responses[f"repos/{REPO}/contents/package.json?ref={COMMIT_ONE}"] = contents(after)


@pytest.mark.parametrize("kind", ("base", "merge", "owned"))
@pytest.mark.parametrize("before,after,qualifies", (
    ({"version": "1", "name": "app"}, {"version": "2", "name": "app"}, True),
    ({"name": "app"}, {"name": "app", "version": "2"}, True),
    ({"version": "1", "name": "app"}, {"name": "app"}, True),
    ({"version": "1", "name": "app"}, {"version": "2", "name": "other"}, False),
    ({"version": "1", "nested": {"version": "1"}}, {"version": "2", "nested": {"version": "2"}}, False),
    ({"version": "1", "items": [1, 2]}, {"version": "2", "items": [2, 1]}, False),
    ({"version": "1", "nested": [True]}, {"version": "2", "nested": [1]}, False),
    ({"version": "1", "nested": {"v": 1}}, {"version": "2", "nested": {"v": True}}, False),
    ({"version": "1", "value": 1}, {"value": 1.0, "version": "2"}, True),
))
def test_version_exemption_removes_only_the_declared_top_level_key(evidence_path, kind, before, after, qualifies):
    transport, _ = carried_case(evidence_path, kind=kind, paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    install_version_contents(transport, before, after)
    result, output = execute(transport)
    assert result == (0 if qualifies and kind != "owned" else 1), output
    extra_reads = [endpoint for endpoint, _ in transport.calls if "/contents/package.json?ref=" in endpoint]
    if kind == "owned":
        assert extra_reads == []
    else:
        assert extra_reads == [f"repos/{REPO}/contents/package.json?ref={COMMIT_ONE}",
            f"repos/{REPO}/contents/package.json?ref={ANCESTOR}"]


def test_version_only_commit_does_not_exempt_another_overlapping_file(evidence_path):
    transport, _ = carried_case(evidence_path, paths=("package.json", "src/main.ts"),
        files=[{"filename": "package.json", "status": "modified"}, {"filename": "src/main.ts"}],
        version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    result, output = execute(transport)
    assert result == 1
    assert f"{COMMIT_ONE} changes a use-bought path src/main.ts" in output


@pytest.mark.parametrize("head_version", (VERSION_DECLARATION,
    {**VERSION_DECLARATION, "path": "head-only.json"}, {"malformed": True}))
@pytest.mark.parametrize("trusted_version", (True, False))
def test_head_version_declaration_has_no_authority(evidence_path, head_version, trusted_version):
    transport, _ = carried_case(evidence_path, paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}],
        version=VERSION_DECLARATION if trusted_version else None)
    endpoint = f"repos/{REPO}/contents/.github/change-proof.json?ref={HEAD}"
    policy = json.loads(base64.b64decode(transport.responses[endpoint]["content"]))
    policy["version"] = head_version
    transport.responses[endpoint] = contents(policy)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    result, output = execute(transport)
    assert result == (0 if trusted_version else 1), output
    assert not any("/contents/head-only.json" in endpoint for endpoint, _ in transport.calls)
    if not trusted_version:
        assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


def test_bootstrap_policy_failure_grants_no_head_version_exemption(evidence_path):
    transport, _ = carried_case(evidence_path, paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    endpoint = f"repos/{REPO}/contents/.github/change-proof.json"
    transport.responses[f"{endpoint}?ref={HEAD}"] = transport.responses[f"{endpoint}?ref={BASE_TIP}"]
    transport.responses[f"{endpoint}?ref={BASE_TIP}"] = check.GitHubNotFound("no trusted policy")
    result, output = execute(transport)
    assert result == 1
    assert "trusted policy on the pull request base branch tip" in output
    assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


@pytest.mark.parametrize("file", (
    {"filename": "package.json", "status": "added"},
    {"filename": "package.json", "status": "removed"},
    {"filename": "package.json"},
    {"filename": "package.json", "previous_filename": "old.json", "status": "renamed"},
    {"filename": "package.json", "status": "renamed"},
    {"filename": "package.json", "previous_filename": "old.json", "status": "modified"},
    {"filename": "other.json", "previous_filename": "package.json", "status": "renamed"},
))
def test_missing_deleted_or_renamed_version_file_cannot_be_exempted(evidence_path, file):
    transport, _ = carried_case(evidence_path, paths=("package.json",), files=[file], version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    result, output = execute(transport)
    assert result == 1
    assert "use-bought path package.json" in output
    assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


@pytest.mark.parametrize("parents", (None, [], [{"sha": "short"}]))
def test_version_exemption_requires_a_valid_first_parent(evidence_path, parents):
    transport, _ = carried_case(evidence_path, paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    transport.responses[commit_endpoint(COMMIT_ONE)]["parents"] = parents
    result, output = execute(transport)
    assert result == 1
    assert "use-bought path package.json" in output
    assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


def test_duplicate_version_file_records_cannot_prove_an_ordinary_modification(evidence_path):
    file = {"filename": "package.json", "status": "modified"}
    transport, _ = carried_case(evidence_path, paths=("package.json",), files=[file, file],
        version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    result, output = execute(transport)
    assert result == 1
    assert "use-bought path package.json" in output
    assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


def raw_contents(value):
    return {"encoding": "base64", "content": base64.b64encode(value).decode()}


@pytest.mark.parametrize("response", (
    check.GitHubNotFound("missing version file"), check.ProofError("contents unreadable"),
    {"encoding": "utf8", "content": "{}"}, {"encoding": "base64", "content": "%%%"},
    contents([]), contents(None), contents("text"), raw_contents(b"not JSON"), raw_contents(b"\xff"),
    raw_contents(b'{"version":"2","name":1,"name":2}'),
    raw_contents(b'{"version":"2","nested":{"v":1,"v":2}}'),
    raw_contents(b'{"version":"1","version":"2"}'),
    raw_contents(b'{"version":"2","v":NaN}'), raw_contents(b'{"version":"2","v":Infinity}'),
    raw_contents(b'{"version":NaN}'), raw_contents(b'{"version":-Infinity}'),
    raw_contents(b'{"version":1e9999999999999999999999999999}'),
))
@pytest.mark.parametrize("revision", (ANCESTOR, COMMIT_ONE))
def test_unreadable_or_ambiguous_version_contents_cannot_grant_exemption(evidence_path, response, revision):
    transport, _ = carried_case(evidence_path, paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    transport.responses[f"repos/{REPO}/contents/package.json?ref={revision}"] = response
    result, output = execute(transport)
    assert result == 1
    assert f"{COMMIT_ONE} changes a use-bought path package.json" in output


def test_version_reads_use_first_parent_and_ignore_response_urls(evidence_path):
    transport, _ = carried_case(evidence_path, kind="merge", paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1", "name": "app"}, {"version": "2", "name": "app"})
    current = transport.responses[f"repos/{REPO}/contents/package.json?ref={COMMIT_ONE}"]
    current.update({"download_url": "https://attacker.example/file", "url": "https://attacker.example/api"})
    current["content"] = "\n".join(current["content"][i:i+16] for i in range(0, len(current["content"]), 16))
    transport.responses[f"repos/{REPO}/contents/package.json?ref={BASE_TIP}"] = contents({"name": "other"})
    result, output = execute(transport)
    assert result == 0, output
    assert not any("attacker.example" in endpoint or endpoint == f"repos/{REPO}/contents/package.json?ref={BASE_TIP}"
        for endpoint, _ in transport.calls)


def test_version_path_outside_overlap_needs_no_contents_reads(evidence_path):
    transport, _ = carried_case(evidence_path,
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    result, output = execute(transport)
    assert result == 0, output
    assert not any("/contents/package.json" in endpoint for endpoint, _ in transport.calls)


def test_declared_path_is_encoded_and_needs_no_json_suffix(evidence_path):
    path = "meta/release #1"
    declaration = {"path": path, "field": "release.version", "increment": "minor"}
    transport, _ = carried_case(evidence_path, paths=("src/main.ts", path),
        files=[{"filename": path, "status": "modified"}], version=declaration)
    policy_endpoint = f"repos/{REPO}/contents/.github/change-proof.json?ref={BASE_TIP}"
    policy = json.loads(base64.b64decode(transport.responses[policy_endpoint]["content"]))
    policy["rules"][0]["include"].append(path)
    transport.responses[policy_endpoint] = contents(policy)
    for revision, value in ((ANCESTOR, "1"), (COMMIT_ONE, "2")):
        transport.responses[f"repos/{REPO}/contents/meta/release%20%231?ref={revision}"] = contents(
            {"release.version": value, "other": {"version": "same"}}
        )
    result, output = execute(transport)
    assert result == 0, output
    assert (f"repos/{REPO}/contents/meta/release%20%231?ref={ANCESTOR}", False) in transport.calls


@pytest.mark.parametrize("mutation", ("omit-path", "classification"))
def test_relaxed_proof_keeps_the_original_intervening_record_contract(mutation):
    transport, document = carried_case("proof-v1", paths=("package.json",),
        files=[{"filename": "package.json", "status": "modified"}], version=VERSION_DECLARATION)
    install_version_contents(transport, {"version": "1"}, {"version": "2"})
    result, output = execute(transport)
    assert result == 0, output
    assert document["use"]["intervening_commits"] == [{"sha": COMMIT_ONE, "paths": ["package.json"]}]
    if mutation == "omit-path":
        document["use"]["intervening_commits"][0]["paths"] = []
    else:
        document["use"]["intervening_commits"][0]["classification"] = "base"
    replace_proof_document(transport, document)
    result, output = execute(transport)
    assert result == 1


def test_empty_commit_page_list_cannot_carry_use(evidence_path):
    transport, _ = carried_case(evidence_path)
    transport.responses[commit_endpoint(COMMIT_ONE)] = []
    result, output = execute(transport)
    assert result == 1
    assert "omitted files" in output


def test_missing_work_issue_is_a_named_source_failure_not_a_gate_error():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[endpoint] = check.GitHubNotFound("issue 12 does not exist")

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "evidence path: proof-v1" in output
    assert "readable work-issue comments for issue 12" in output
    assert "correct the named issue" in output


def test_document_review_body_is_credited_exactly_like_the_legacy_path():
    transport, _document = proof_scenario()
    transport.responses[f"repos/{REPO}/pulls/17/reviews?per_page=100"][0][
        "body"
    ] = "Review limit reached"

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review #41" in output


def test_document_pull_request_notice_is_not_a_completed_receipt():
    transport, document = proof_scenario()
    document["reviewers"][0]["source"] = {
        "kind": "pull-request-comment",
        "repository": REPO,
        "id": 42,
        "url": f"https://github.com/{REPO}/pull/17#issuecomment-42",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:07:00Z",
        "revision": HEAD,
    }
    replace_proof_document(transport, document)
    endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[endpoint].append(
        record(REVIEWER, "Review limit reached", id=42)
    )

    result, output = execute(transport)

    assert result == 1
    assert f"completed public review receipt for {REVIEWER}" in output
    assert "Review limit reached" in output


def test_document_work_issue_comment_cannot_credit_a_pull_request_review():
    transport, document = proof_scenario()
    document["reviewers"][0]["source"] = {
        "kind": "issue-comment",
        "repository": REPO,
        "id": 42,
        "url": f"https://github.com/{REPO}/issues/12#issuecomment-42",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:07:00Z",
        "revision": HEAD,
    }
    replace_proof_document(transport, document)
    endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    transport.responses[endpoint].append(
        record(REVIEWER, "completed review", id=42)
    )

    result, output = execute(transport)

    assert result == 1
    assert f"review receipt for {REVIEWER}" in output
    assert "source kind issue-comment" in output
    assert "cannot credit a pull-request review" in output


def test_document_inline_comment_text_that_says_running_still_counts_as_a_receipt():
    transport, document = proof_scenario()
    document["reviewers"][0]["source"] = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 41,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r41",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:07:00Z",
        "revision": HEAD,
    }
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/pulls/17/comments?per_page=100"] = [
        record(REVIEWER, "The service is running normally.", id=41, in_reply_to_id=50)
    ]

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review-comment #41" in output


def test_document_inline_notice_text_is_credited_exactly_like_the_legacy_path():
    transport, document = proof_scenario()
    document["reviewers"][0]["source"] = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 41,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r41",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:07:00Z",
        "revision": HEAD,
    }
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/pulls/17/comments?per_page=100"] = [
        record(REVIEWER, "Review limit reached", id=41, in_reply_to_id=50)
    ]

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review-comment #41" in output


def test_document_reports_named_missing_duplicate_and_extra_reviewers():
    transport, document = proof_scenario()
    duplicate = copy.deepcopy(document["reviewers"][0])
    extra = copy.deepcopy(document["reviewers"][0])
    extra["login"] = "extra-reviewer[bot]"
    document["reviewers"] = [duplicate, duplicate, extra]
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"duplicated: {REVIEWER}" in output
    assert "extra: extra-reviewer[bot]" in output


def test_document_reports_named_missing_duplicate_and_extra_threads():
    transport, document = proof_scenario()
    source = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 51,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r51",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": HEAD,
    }
    entry = {
        "thread_id": 52,
        "reviewer": REVIEWER,
        "source": {**source, "id": 52},
        "reply": None,
    }
    document["dispositions"] = [entry, copy.deepcopy(entry)]
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/pulls/17/comments?per_page=100"] = [
        record(REVIEWER, "finding", id=51, in_reply_to_id=None)
    ]

    result, output = execute(transport)

    assert result == 1
    assert "missing: 51" in output
    assert "duplicated: 52" in output
    assert "extra: 52" in output


def test_document_wrong_thread_reply_is_rejected_by_membership():
    transport, document = proof_scenario()
    source = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 51,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r51",
        "author": REVIEWER,
        "timestamp": "2026-09-23T12:08:00Z",
        "revision": HEAD,
    }
    reply = {
        "kind": "review-comment",
        "repository": REPO,
        "id": 52,
        "url": f"https://github.com/{REPO}/pull/17#discussion_r52",
        "author": OWNER,
        "timestamp": "2026-09-23T12:09:00Z",
        "revision": HEAD,
    }
    document["dispositions"] = [{
        "thread_id": 51,
        "reviewer": REVIEWER,
        "source": source,
        "reply": reply,
    }]
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/pulls/17/comments?per_page=100"] = [
        record(REVIEWER, "finding", id=51, in_reply_to_id=None),
        record(OWNER, "fixed - elsewhere", id=52, in_reply_to_id=99),
    ]

    result, output = execute(transport)

    assert result == 1
    assert "authorized disposition reply in reviewer thread 51" in output


@pytest.mark.parametrize("summary_body", ("", "summary only", CODEX_COMPLETED_SUMMARY))
def test_document_accepts_repeated_and_summary_only_reviews(summary_body):
    transport, _document = proof_scenario()
    reviews_endpoint = f"repos/{REPO}/pulls/17/reviews?per_page=100"
    transport.responses[reviews_endpoint][0]["body"] = summary_body
    transport.responses[reviews_endpoint].append(
        record(REVIEWER, "a second completed review", id=42, commit_id=HEAD)
    )

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review #41" in output


def test_reviewer_notice_labels_are_free_text_in_the_wire_contract():
    transport, document = proof_scenario()
    document["reviewers"][0]["notices"] = ["producer-specific explanatory label"]
    replace_proof_document(transport, document)

    result, _output = execute(transport)

    assert result == 0


@pytest.mark.parametrize("label", (ABSENT_BODY, None, "review-ready"))
def test_reviewer_label_does_not_change_document_acceptance(label):
    transport, _document = proof_scenario()
    for revision in (HEAD, BASE_TIP):
        endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={revision}"
        config = json.loads(base64.b64decode(transport.responses[endpoint]["content"]))
        if label is not ABSENT_BODY:
            config["reviewer_label"] = label
        transport.responses[endpoint] = contents(config)

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER}" in output


def test_source_id_on_another_comment_collection_is_not_on_the_claimed_surface():
    transport, _document = proof_scenario()
    work_endpoint = f"repos/{REPO}/issues/12/comments?per_page=100"
    floor_record = transport.responses[work_endpoint].pop()
    pr_endpoint = f"repos/{REPO}/issues/17/comments?per_page=100"
    transport.responses[pr_endpoint].append(floor_record)

    result, output = execute(transport)

    assert result == 1
    assert "issue-comment source 31 is not on its claimed surface" in output


def test_stale_floor_source_pointer_recomposes_instead_of_posting_a_duplicate():
    transport, document = proof_scenario()
    document["floor"]["source"]["id"] = 999
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "document pointer is stale" in output
    assert "matching issue-comment #31 already exists" in output
    assert "recompose proof from issue-comment #31" in output
    assert "post the exact successful floor marker" not in output


def test_stale_reviewer_source_pointer_recomposes_instead_of_buying_another_review():
    transport, document = proof_scenario()
    document["reviewers"][0]["source"]["id"] = 999
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert "document pointer is stale; matching review #41 already exists" in output
    assert "recompose proof from review #41" in output
    assert f"asking {REVIEWER} to review again" in output


def test_missing_floor_source_record_still_tells_the_holder_to_post_it():
    transport, document = proof_scenario()
    document["floor"]["source"]["id"] = 999
    replace_proof_document(transport, document)
    transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"] = []

    result, output = execute(transport)

    assert result == 1
    assert "floor record is missing" in output
    assert "post the exact successful floor marker" in output


@pytest.mark.parametrize(
    "separator",
    ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"),
)
def test_every_python_line_separator_is_escaped_in_failure_output(separator):
    transport, document = proof_scenario()
    document["floor"]["source"]["repository"] = (
        f"{REPO}{separator}verified: forged"
    )
    replace_proof_document(transport, document)

    result, output = execute(transport)

    assert result == 1
    assert f"{separator}verified: forged" not in output
    assert not any(line == "verified: forged" for line in output.splitlines())


def test_legacy_running_word_outside_the_status_cell_is_not_a_notice():
    body = "| Subject | Status |\n| --- | --- |\n| running service | completed |"
    transport = scenario(
        comments=[use_note(), record(REVIEWER, body, id=42)],
    )

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by pull-request comment #42" in output


def test_failed_floor_source_never_prints_verified_public_attestation():
    transport, document = proof_scenario()
    document["floor"]["checks"] = []
    replace_proof_document(transport, document)
    checks_endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    transport.responses[checks_endpoint] = {"total_count": 0, "check_runs": []}
    transport.responses[f"repos/{REPO}/issues/12/comments?per_page=100"] = []

    result, output = execute(transport)

    assert result == 1
    assert "authorized floor attestation remains public" not in output


def test_current_gate_exemption_uses_the_associated_jobs_attempt():
    transport, _document = proof_scenario()
    endpoint = f"repos/{REPO}/commits/{HEAD}/check-runs?filter=all&per_page=100"
    gate = copy.deepcopy(transport.responses[endpoint]["check_runs"][0])
    gate.update({
        "id": 1001,
        "name": "Change proof / Change proof",
        "details_url": f"https://github.com/{REPO}/actions/runs/100",
        "status": "in_progress",
        "conclusion": None,
        "completed_at": None,
    })
    transport.responses[endpoint] = {
        "total_count": 2,
        "check_runs": [transport.responses[endpoint]["check_runs"][0], gate],
    }
    transport.responses[f"repos/{REPO}/actions/runs/100"] = {
        "id": 100,
        "head_sha": HEAD,
        "workflow_id": 363584992,
        "run_attempt": 1,
        "repository": {"full_name": REPO},
        "referenced_workflows": [],
    }
    transport.responses[f"repos/{REPO}/actions/runs/100/jobs?filter=all&per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "Change proof",
            "check_run_url": "https://api.github.com/repos/example/check-runs/1001",
            "run_attempt": 2,
        }],
    }
    environ = environment()
    environ.update({"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1"})
    output = io.StringIO()

    result = check.run(environ, transport=transport, output=output)

    assert result == 1
    assert "omitted check id(s): 1001" in output.getvalue()


POSITIVE_PATH_DEPARTURES_BODIES = (
    "**Path departures:** Expected path ran without a departure.",
    "Context for the change.\n\n**Path departures:**",
    "## Release record\n**Path departures:** Expected path ran without a departure.",
    "> ## Release record\n**Path departures:** Expected path ran without a departure.",
    "**Path departures:** Expected path ran\nwithout a departure.",
    "**Path departures:** Expected path ran\n- release detail",
    "---\n**Path departures:** Expected path ran without a departure.",
    "Release record\n---\n**Path departures:** Expected path ran without a departure.",
    "~~~markdown\nquoted convention\n~~~\n"
    "**Path departures:** Expected path ran without a departure.",
    "<!-- quoted convention -->\n**Path departures:** Expected path ran without a departure.",
    "<pre>\nquoted convention\n</pre>\n"
    "**Path departures:** Expected path ran without a departure.",
    "<?instruction?>\n**Path departures:** Expected path ran without a departure.",
    "<!DOCTYPE html>\n**Path departures:** Expected path ran without a departure.",
    "<![CDATA[quoted convention]]>\n"
    "**Path departures:** Expected path ran without a departure.",
    "<div>\nquoted convention\n\n"
    "**Path departures:** Expected path ran without a departure.",
    "Context\n<div>\n\n**Path departures:** Expected path ran without a departure.",
    "<custom-tag>\nquoted convention\n\n"
    "**Path departures:** Expected path ran without a departure.",
    "Context <!--\n\n**Path departures:** None.\n-->",
)


NEGATIVE_PATH_DEPARTURES_BODIES = (
    "## **Path departures:**",
    "**Path departure:** None.",
    "This comment mentions **Path departures:** but records no paragraph.",
    "This comment mentions the convention on its next source line:\n"
    "**Path departures:** but records no separate paragraph.",
    "> **Path departures:** None.",
    "- Earlier prose in a list item\n**Path departures:** is a lazy continuation.",
    "    **Path departures:** None.",
    "```markdown\n**Path departures:** None.\n```",
    "````markdown\n**Path departures:** None.\n```\n**Path departures:** Still fenced.\n````",
    "~~~markdown\n**Path departures:** None.\n~~~",
    "<!--\n**Path departures:** None.\n-->",
    "<pre>\n\n**Path departures:** None.\n</pre>",
    "<?instruction\n\n**Path departures:** None.\n?>",
    "<!DECLARATION\n\n**Path departures:** None.\n>",
    "<![CDATA[\n\n**Path departures:** None.\n]]>",
    "<div>\n**Path departures:** None.\n\n",
    "<custom-tag>\n**Path departures:** None.\n\n",
    "Context\n<custom-tag>\n**Path departures:** is still the same paragraph.",
    "Context <!--\n**Path departures:** is still the same paragraph.\n-->",
    "**Path departures:** None.\n---",
    "**Path departures:** None stated\nfor this change.\n===",
)


@pytest.mark.parametrize("separator", ("\n", "\r\n", "\r"), ids=("lf", "crlf", "cr"))
@pytest.mark.parametrize("body", POSITIVE_PATH_DEPARTURES_BODIES)
def test_path_departures_paragraph_shapes_pass_for_all_line_endings(body, separator):
    result, output = execute(complete_scenario(body=line_ending(body, separator)))

    assert result == 0
    assert output.count(
        "verified: pull request body has a **Path departures:** paragraph\n"
    ) == 1
    assert "missing: a pull request body paragraph" not in output


@pytest.mark.parametrize("separator", ("\n", "\r\n", "\r"), ids=("lf", "crlf", "cr"))
@pytest.mark.parametrize("body", NEGATIVE_PATH_DEPARTURES_BODIES)
def test_nonparagraph_path_departures_shapes_fail_for_all_line_endings(body, separator):
    result, output = execute(complete_scenario(body=line_ending(body, separator)))

    assert result == 1
    assert "verified: pull request body has a **Path departures:** paragraph" not in output
    assert output.count(
        "missing: a pull request body paragraph beginning with **Path departures:**\n"
    ) == 1
    assert output.count(
        "satisfy: add the **Path departures:** paragraph to the pull request body and re-run "
        "change-proof\n"
    ) == 1


@pytest.mark.parametrize(
    "body",
    (ABSENT_BODY, None, "", 17),
    ids=("absent", "null", "empty", "non-string"),
)
def test_missing_path_departures_body_fails_with_exact_repair(body):
    result, output = execute(complete_scenario(body=body))

    assert result == 1
    assert output.count(
        "missing: a pull request body paragraph beginning with **Path departures:**\n"
    ) == 1
    assert output.count(
        "satisfy: add the **Path departures:** paragraph to the pull request body and re-run "
        "change-proof\n"
    ) == 1


def test_missing_body_remains_visible_when_policy_preflight_also_fails():
    result, output = execute(complete_scenario(body=None, base_policy=False))

    assert result == 1
    assert "missing: a pull request body paragraph beginning with **Path departures:**\n" in output
    assert "missing: trusted policy on the pull request base branch tip" in output


def test_readme_use_rules_classify_documented_paths():
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    sections = re.findall(
        r"^## Caller-owned configuration\n(.*?)(?=^## |\Z)",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert len(sections) == 1
    json_blocks = re.findall(
        r"^```json\n(.*?)^```$",
        sections[0],
        flags=re.MULTILINE | re.DOTALL,
    )
    documents = [json.loads(block) for block in json_blocks]
    examples = [
        document
        for document in documents
        if isinstance(document, dict) and "rules" in document
    ]

    assert len(examples) == 1
    rules = examples[0]
    expected = {
        "src/application.ts": True,
        "src/Suite.test.ts": False,
        "src/Suite.test-helpers.ts": False,
        "src/Suite.test-fixtures.ts": False,
        "src/Suite.test-utils.ts": False,
        "src/test/factories.ts": False,
        "docs/guide.md": False,
    }

    for path, required in expected.items():
        assert check.use_required([path], rules) is required


def test_bought_use_fails_without_current_head_used_note():
    result, output = execute(scenario(reviews=[record(REVIEWER, "summary")]))

    assert result == 1
    assert "authorized, valid use marker for the current head" in output
    assert "satisfy:" in output


def test_bought_use_passes_with_current_head_used_note():
    result, output = execute(complete_scenario())

    assert result == 0
    assert "change-proof: PASS" in output
    assert "current-head use marker is valid" in output


def test_policy_is_loaded_from_base_branch_reference_tip():
    transport = complete_scenario()
    policy_paths = (".github/change-proof.json", ".tradecraft/work.json")
    for path in policy_paths:
        transport.responses[f"repos/{REPO}/contents/{path}?ref={BASE}"] = (
            check.GitHubNotFound(f"missing {path}")
        )

    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output
    assert f"verified: base branch {BASE_REF} tip resolved to commit {BASE_TIP}" in output
    assert (f"repos/{REPO}/git/ref/heads/{BASE_REF}", False) in transport.calls
    assert (f"repos/{REPO}/commits/{BASE_REF}", False) not in transport.calls
    assert all(
        (f"repos/{REPO}/contents/{path}?ref={BASE_TIP}", False) in transport.calls
        for path in policy_paths
    )
    assert all(
        (f"repos/{REPO}/contents/{path}?ref={BASE}", False) not in transport.calls
        for path in policy_paths
    )


def test_missing_base_branch_reference_fails_when_old_commit_lookup_would_pass():
    transport = complete_scenario()
    base_ref_endpoint = f"repos/{REPO}/git/ref/heads/{BASE_REF}"
    transport.responses[base_ref_endpoint] = check.GitHubNotFound("missing branch reference")

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: ERROR" in output
    assert f"base branch reference refs/heads/{BASE_REF} does not exist" in output
    assert (base_ref_endpoint, False) in transport.calls
    assert (f"repos/{REPO}/commits/{BASE_REF}", False) not in transport.calls


def test_head_that_weakens_policy_is_judged_by_base_and_fails():
    weakened_rules = {
        "schema_version": 1,
        "rules": [{"name": "weakened", "include": ["docs/**"], "exclude": []}],
    }
    weakened_config = {
        "schema_version": 1,
        "product_repositories": [],
        "connected_reviewers": [],
        "marker_producers": ["attacker"],
    }
    transport = scenario(
        comments=[no_use_note(author="attacker")],
        head_rules=weakened_rules,
        head_config=weakened_config,
    )
    result, output = execute(transport)

    assert result == 1
    assert "verified: pull request changes policy and was judged by the base branch tip policy" in output
    assert "authorized, valid use marker for the current head" in output
    assert f"connected reviewer run(s): {REVIEWER}" in output


def test_head_policy_identical_to_base_passes():
    result, output = execute(complete_scenario())

    assert result == 0
    assert "change-proof: PASS" in output
    assert "pull request changes policy" not in output


def test_base_branch_tip_without_policy_is_bootstrap_failure_with_other_verifications():
    result, output = execute(complete_scenario(base_policy=False))

    assert result == 1
    assert "trusted policy on the pull request base branch tip" in output
    assert ".github/change-proof.json, .tradecraft/work.json" in output
    assert "this pull request cannot prove itself" in output
    assert "the owner merges it on the connected reviewers' evidence" in output
    assert f"verified: base branch {BASE_REF} tip resolved to commit {BASE_TIP}" in output
    assert "verified: changed paths buy a use" in output
    assert f"verified: connected reviewer {REVIEWER} credited by review" in output


def test_policy_deleted_on_head_is_judged_by_complete_base():
    transport = complete_scenario(head_missing=(".tradecraft/work.json",))
    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output
    assert "verified: pull request changes policy and was judged by the base branch tip policy" in output


def test_policy_absent_on_base_and_head_is_bootstrap_failure():
    missing = ".tradecraft/work.json"
    transport = complete_scenario(head_missing=(missing,), base_missing=(missing,))
    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "change-proof: ERROR" not in output
    assert f"trusted policy on the pull request base branch tip; absent: {missing}" in output
    assert "this pull request cannot prove itself" in output


def test_docs_only_fails_on_false_used_claim():
    result, output = execute(complete_scenario(paths=("docs/guide.md",)))

    assert result == 1
    assert "current-head use marker is a false claim" in output


def test_docs_only_passes_with_verified_no_use_line():
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note()],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == 0
    assert "current-head no-use note has its line" in output


def test_no_use_marker_without_required_line_fails():
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note(line=False)],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == 1
    assert "'Use: not required' line" in output


@pytest.mark.parametrize(
    "line",
    [
        "Use: not required - documentation-only change",
        "Use: not required — documentation-only change",
    ],
)
def test_no_use_line_accepts_hyphen_or_em_dash_with_reason(line):
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note(line=line)],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == 0
    assert "current-head no-use note has its line" in output


@pytest.mark.parametrize(
    ("line", "passes"),
    [
        ("  `Use: not required — documentation-only change`", True),
        ("*Use: not required — documentation-only change*", True),
        ("**Use: not required — documentation-only change**", True),
        ("_Use: not required — documentation-only change_", True),
        ("__Use: not required — documentation-only change__", True),
        ("`Use: not required — documentation-only change", False),
        ("*Use: not required — documentation-only change", False),
        ("_Use: not required — documentation-only change", False),
        ("*Use: not required — documentation-only change_", False),
        ("**Use: not required — documentation-only change*", False),
    ],
)
def test_no_use_line_requires_balanced_markdown_wrapper(line, passes):
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note(line=line)],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == (0 if passes else 1)
    expected = (
        "current-head no-use note has its line"
        if passes
        else "'Use: not required' line"
    )
    assert expected in output


@pytest.mark.parametrize(
    "line",
    [
        "Use: not required",
        "Use: not requiredness - documentation-only change",
        "Use: not required -",
        "Use: not required —   ",
        "Note: `Use: not required — documentation-only change`",
    ],
)
def test_no_use_line_requires_separator_and_nonempty_reason(line):
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note(line=line)],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == 1
    assert "'Use: not required' line" in output


def test_non_ancestor_use_note_fails_current_head_check():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(
        ANCESTOR, [], status="diverged", merge_base=BASE
    )
    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "change-proof: ERROR" not in output
    assert f"use evidence head {ANCESTOR} is not an ancestor of current head {HEAD}" in output
    assert "for the current head" in output
    assert transport.calls.count((compare_endpoint(ANCESTOR), False)) == 1


def test_changed_false_ancestor_note_carries_across_use_free_commits():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(
        ANCESTOR, [COMMIT_ONE, COMMIT_TWO]
    )
    transport.responses[commit_endpoint(COMMIT_ONE)] = {"files": [{"filename": "docs/one.md"}]}
    transport.responses[commit_endpoint(COMMIT_TWO)] = [
        {"files": [{"filename": "docs/two.md"}]},
        {"files": [{"filename": "tests/test_check.py"}]},
    ]

    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output
    assert (
        "verified: changed paths buy a use and authorized use marker at "
        f"{ANCESTOR} remains valid after intervening commits: {COMMIT_ONE}, {COMMIT_TWO}"
    ) in output
    assert transport.calls.count((compare_endpoint(ANCESTOR), False)) == 1
    assert (commit_endpoint(COMMIT_ONE), True) in transport.calls
    assert (commit_endpoint(COMMIT_TWO), True) in transport.calls


def test_current_head_changed_true_use_note_still_passes():
    result, output = execute(complete_scenario(comments=[use_note(changed=True)]))

    assert result == 0
    assert "current-head use marker is valid" in output


def test_earlier_changed_true_use_note_does_not_carry():
    transport = complete_scenario(comments=[use_note(ANCESTOR, changed=True)])

    result, output = execute(transport)

    assert result == 1
    assert "authorized, valid use marker for the current head" in output
    assert not any(endpoint == compare_endpoint(ANCESTOR) for endpoint, _paginate in transport.calls)


def test_incomplete_single_compare_response_is_stale_without_pagination():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(
        ANCESTOR, [COMMIT_ONE], ahead_by=2
    )

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "change-proof: ERROR" not in output
    assert f"complete intervening history from {ANCESTOR} is unavailable" in output
    assert transport.calls.count((compare_endpoint(ANCESTOR), False)) == 1


def test_intervening_commit_without_full_revision_is_stale():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, ["short"])

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert f"intervening commit from {ANCESTOR} has no full revision" in output
    assert not any(endpoint.startswith(f"repos/{REPO}/commits/short") for endpoint, _ in transport.calls)


def test_paginated_commit_pages_and_previous_filename_can_stale_ancestor_note():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, [COMMIT_ONE])
    transport.responses[commit_endpoint(COMMIT_ONE)] = [
        {"files": [{"filename": "docs/moved.ts"}]},
        {
            "files": [
                {
                    "filename": "docs/renamed.ts",
                    "previous_filename": "src/renamed.ts",
                }
            ]
        },
    ]

    result, output = execute(transport)

    assert result == 1
    assert (
        f"use evidence at {ANCESTOR} is stale because intervening commit {COMMIT_ONE} "
        "changes a use-bought path"
    ) in output
    assert (commit_endpoint(COMMIT_ONE), True) in transport.calls


def test_use_bought_commit_stales_note_even_when_later_commit_reverts_it():
    transport = complete_scenario(comments=[use_note(ANCESTOR)])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(
        ANCESTOR, [COMMIT_ONE, COMMIT_TWO]
    )
    transport.responses[commit_endpoint(COMMIT_ONE)] = {"files": [{"filename": "src/main.ts"}]}
    transport.responses[commit_endpoint(COMMIT_TWO)] = {"files": [{"filename": "docs/revert.md"}]}

    result, output = execute(transport)

    assert result == 1
    assert ANCESTOR in output
    assert COMMIT_ONE in output
    assert (commit_endpoint(COMMIT_TWO), True) not in transport.calls


@pytest.mark.parametrize(
    ("failure", "newest_compare", "newest_commit"),
    [
        ("compare GET failed", check.ProofError("compare GET failed"), None),
        (
            "commit GET failed",
            comparison(ANCESTOR, [COMMIT_ONE]),
            check.ProofError("commit GET failed"),
        ),
        ("invalid candidate JSON", ValueError("invalid candidate JSON"), None),
        (
            "omitted files",
            comparison(ANCESTOR, [COMMIT_ONE]),
            [{"sha": COMMIT_ONE}],
        ),
    ],
)
def test_candidate_history_failure_continues_to_older_clean_note(
    failure, newest_compare, newest_commit
):
    newer = use_note(ANCESTOR, created_at="2026-09-24T12:00:00Z", id=20)
    older = use_note(OLDER_ANCESTOR, created_at="2026-09-23T12:00:00Z", id=10)
    transport = complete_scenario(comments=[older, newer])
    transport.responses[compare_endpoint(ANCESTOR)] = newest_compare
    if newest_commit is not None:
        transport.responses[commit_endpoint(COMMIT_ONE)] = newest_commit
    transport.responses[compare_endpoint(OLDER_ANCESTOR)] = comparison(
        OLDER_ANCESTOR, [COMMIT_TWO]
    )
    transport.responses[commit_endpoint(COMMIT_TWO)] = {
        "files": [{"filename": "docs/older.md"}]
    }

    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output
    assert OLDER_ANCESTOR in output
    assert COMMIT_TWO in output
    assert ANCESTOR not in output
    assert transport.calls.index((compare_endpoint(ANCESTOR), False)) < transport.calls.index(
        (compare_endpoint(OLDER_ANCESTOR), False)
    )


def test_all_rejected_candidates_fail_with_newest_reason_and_current_head_remedy():
    newer = use_note(ANCESTOR, created_at="2026-09-24T12:00:00Z", id=20)
    older = use_note(OLDER_ANCESTOR, created_at="2026-09-23T12:00:00Z", id=10)
    transport = complete_scenario(comments=[older, newer])
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, [COMMIT_ONE])
    transport.responses[commit_endpoint(COMMIT_ONE)] = [{"sha": COMMIT_ONE}]
    transport.responses[compare_endpoint(OLDER_ANCESTOR)] = comparison(
        OLDER_ANCESTOR, [COMMIT_TWO]
    )
    transport.responses[commit_endpoint(COMMIT_TWO)] = {"files": [{"filename": "src/main.ts"}]}

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: FAIL" in output
    assert "change-proof: ERROR" not in output
    assert f"history unavailable from {ANCESTOR}" in output
    assert f"intervening commit {COMMIT_TWO} changes a use-bought path" not in output
    assert "post the completed use note with the exact tradecraft:use:v1 form at this head" in output


def test_intervening_paths_are_classified_by_base_tip_policy():
    weakened_head_rules = {
        "schema_version": 1,
        "rules": [{"name": "weakened", "include": ["docs/**"], "exclude": []}],
    }
    transport = complete_scenario(
        comments=[use_note(ANCESTOR)], head_rules=weakened_head_rules
    )
    transport.responses[compare_endpoint(ANCESTOR)] = comparison(ANCESTOR, [COMMIT_ONE])
    transport.responses[commit_endpoint(COMMIT_ONE)] = {"files": [{"filename": "src/new.ts"}]}

    result, output = execute(transport)

    assert result == 1
    assert f"intervening commit {COMMIT_ONE} changes a use-bought path" in output
    assert "pull request changes policy and was judged by the base branch tip policy" in output


def test_older_no_use_note_remains_insufficient():
    transport = scenario(
        paths=("docs/guide.md",),
        comments=[no_use_note(ANCESTOR)],
        reviews=[record(REVIEWER, "summary")],
    )

    result, output = execute(transport)

    assert result == 1
    assert "no-use marker" in output
    assert "for the current head" in output


def test_unauthorized_use_note_does_not_supply_evidence():
    transport = complete_scenario(comments=[use_note(author="stranger")])
    result, output = execute(transport)

    assert result == 1
    assert "authorized, valid use marker" in output


def test_rename_out_of_included_path_buys_a_use():
    transport = complete_scenario(
        files=[
            {
                "filename": "docs/main.ts",
                "previous_filename": "src/main.ts",
                "status": "renamed",
            }
        ]
    )
    result, output = execute(transport)

    assert result == 0
    assert "changed paths buy a use" in output


def test_changed_file_count_matching_pull_response_passes():
    transport = complete_scenario(paths=("src/main.ts", "docs/guide.md"))
    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output


def test_truncated_changed_file_list_fails_without_classification():
    files = [{"filename": f"docs/generated-{index}.md"} for index in range(3000)]
    transport = scenario(
        files=files,
        changed_files=3001,
        comments=[no_use_note()],
        reviews=[record(REVIEWER, "summary")],
    )
    result, output = execute(transport)

    assert result == 1
    assert "pull reports 3001, retrieved 3000" in output
    assert "the change cannot be classified" in output
    assert "changed paths do not buy a use" not in output


def test_missing_connected_reviewer_run_fails():
    result, output = execute(scenario(comments=[use_note()]))

    assert result == 1
    assert f"connected reviewer run(s): {REVIEWER}" in output


def test_repeated_connected_reviewer_runs_pass():
    transport = complete_scenario(
        reviews=[record(REVIEWER, "first"), record(REVIEWER, "bought second look")]
    )
    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review" in output


def test_rate_limit_notice_alone_fails_naming_notice():
    reviewer = "coderabbitai[bot]"
    transport = scenario(
        comments=[use_note(), record(reviewer, CODERABBIT_RATE_LIMIT_NOTICE, id=5750507875)],
        reviewers=(reviewer,),
    )
    result, output = execute(transport)

    assert result == 1
    assert "'Review limit reached' do not count" in output
    assert "a review is still owed" in output


def test_summary_only_plan_notice_does_not_count_as_a_review():
    reviewer = "coderabbitai[bot]"
    transport = scenario(
        comments=[use_note(), record(reviewer, CODERABBIT_SUMMARY_ONLY_NOTICE, id=5750390080)],
        reviewers=(reviewer,),
    )
    result, output = execute(transport)

    assert result == 1
    assert "'Ask your admin to upgrade for code reviews' do not count" in output
    assert "a review is still owed" in output


def test_completed_summary_comment_counts_as_reviewer_run():
    reviewer = "chatgpt-codex-connector[bot]"
    transport = scenario(
        comments=[use_note(), record(reviewer, CODEX_COMPLETED_SUMMARY, id=5750586451)],
        reviewers=(reviewer,),
    )
    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {reviewer} credited by pull-request comment #5750586451" in output


def test_running_notice_alone_fails():
    reviewer = "chatgpt-codex-connector[bot]"
    transport = scenario(
        comments=[use_note(), record(reviewer, CODEX_RUNNING_NOTICE, id=5750586451)],
        reviewers=(reviewer,),
    )
    result, output = execute(transport)

    assert result == 1
    assert "'Running' do not count" in output
    assert "a review is still owed" in output


@pytest.mark.parametrize(
    ("body", "notice"),
    [
        ("THE REVIEW WAS LIMITED", "review limited"),
        ("REVIEW SKIPPED", "review skipped"),
    ],
)
def test_notice_phrasings_match_case_insensitively(body, notice):
    transport = scenario(
        comments=[use_note(), record(REVIEWER, body)],
    )
    result, output = execute(transport)

    assert result == 1
    assert f"'{notice}' do not count" in output
    assert "a review is still owed" in output


def test_review_endpoint_record_counts_as_reviewer_run():
    transport = scenario(
        comments=[use_note()],
        reviews=[record(REVIEWER, "review summary", id=5260887954)],
    )
    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review #5260887954" in output


def test_legacy_review_endpoint_body_does_not_change_reviewer_credit():
    transport = scenario(
        comments=[use_note()],
        reviews=[record(REVIEWER, "Review limit reached", id=41)],
    )

    result, output = execute(transport)

    assert result == 0
    assert f"connected reviewer {REVIEWER} credited by review #41" in output


def test_undispositioned_top_level_inline_comment_fails():
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline])
    )

    assert result == 1
    assert "top-level inline comment(s): 41" in output


@pytest.mark.parametrize(
    "disposition",
    [
        "fixed",
        "fixed - addressed",
        "fixed — addressed",
    ],
)
def test_authorized_first_line_disposition_passes(disposition):
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    reply = record(OWNER, f"{disposition}\nDetails.", id=42, in_reply_to_id=41)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == 0
    assert "marker-producer disposition" in output


@pytest.mark.parametrize(
    ("disposition", "passes"),
    [
        ("`fixed`", True),
        ("`fixed — nothing else found it`", True),
        ("  `yours — in the release report`", True),
        ("*fixed*", True),
        ("**fixed**", True),
        ("_fixed_", True),
        ("__fixed__", True),
        ("`fixed", False),
        ("**fixed", False),
        ("_fixed", False),
        ("*fixed_", False),
        ("**fixed*", False),
    ],
)
def test_disposition_requires_balanced_markdown_wrapper(disposition, passes):
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    reply = record(OWNER, f"{disposition}\nDetails.", id=42, in_reply_to_id=41)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == (0 if passes else 1)
    expected = (
        "marker-producer disposition"
        if passes
        else "top-level inline comment(s): 41"
    )
    assert expected in output


@pytest.mark.parametrize(
    ("disposition", "passes"),
    [
        ("**fixed** - addressed", True),
        ("__declined__ - not a defect", True),
        ("*yours* - in the release report", True),
        ("`duplicate` of the earlier comment", True),
        ("**fixing** this", False),
        ("*fixed*ness", False),
        ("**fixed in** #12", False),
        ("_sustained_ - fixed", False),
    ],
)
def test_disposition_reads_formatted_opening_word(disposition, passes):
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    reply = record(OWNER, disposition, id=42, in_reply_to_id=41)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == (0 if passes else 1)
    expected = (
        "marker-producer disposition"
        if passes
        else "top-level inline comment(s): 41"
    )
    assert expected in output


@pytest.mark.parametrize(
    ("body", "passes"),
    [
        ("\n\nFixed\nDetails.", True),
        ("\n\nThanks\nFixed", False),
    ],
)
def test_disposition_reads_first_non_blank_line(body, passes):
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    reply = record(OWNER, body, id=42, in_reply_to_id=41)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == (0 if passes else 1)
    expected = (
        "marker-producer disposition"
        if passes
        else "top-level inline comment(s): 41"
    )
    assert expected in output


@pytest.mark.parametrize(
    "reply",
    [
        record("stranger", "fixed", id=42, in_reply_to_id=41),
        record(OWNER, "Thanks\nfixed", id=42, in_reply_to_id=41),
        record(OWNER, "Thanks, fixed", id=42, in_reply_to_id=41),
        record(OWNER, "fixedness", id=42, in_reply_to_id=41),
    ],
)
def test_reply_must_be_from_producer_and_start_with_disposition(reply):
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == 1
    assert "top-level inline comment(s): 41" in output


def test_summary_only_reviewer_run_owes_no_disposition():
    reviewer = "chatgpt-codex-connector[bot]"
    transport = scenario(
        comments=[use_note(), record(reviewer, CODEX_COMPLETED_SUMMARY)],
        reviewers=(reviewer,),
    )
    result, output = execute(transport)

    assert result == 0
    assert "every top-level inline reviewer comment" in output


def test_ready_pull_request_with_complete_evidence_passes():
    inline = record(REVIEWER, "finding", id=91, in_reply_to_id=None)
    reply = record(OWNER, "declined - not a product defect", id=92, in_reply_to_id=91)
    transport = complete_scenario(draft=False, review_comments=[inline, reply])
    result, output = execute(transport)

    assert result == 0
    assert "change-proof: PASS" in output
    assert output.count("verified:") == 5
    assert output.count(
        "verified: pull request body has a **Path departures:** paragraph\n"
    ) == 1
    pull = f"repos/{REPO}/pulls/17"
    evidence_calls = {
        (f"{pull}/files?per_page=100", True),
        (f"repos/{REPO}/issues/17/comments?per_page=100", True),
        (f"{pull}/reviews?per_page=100", True),
        (f"{pull}/comments?per_page=100", True),
    }
    assert evidence_calls <= set(transport.calls)


def test_missing_event_head_is_resolved_by_get():
    result, output = execute(complete_scenario(), head="")

    assert result == 0
    assert "change-proof: PASS" in output


def test_draft_pull_request_exits_nonzero_without_evaluating():
    transport = scenario(draft=True)
    pull = f"repos/{REPO}/pulls/17"
    transport.responses = {pull: transport.responses[pull]}
    result, output = execute(transport)

    assert result == 1
    assert output == (
        "change-proof: SKIP: pull request #17 is draft; evidence is not evaluated\n"
        "satisfy: mark pull request #17 ready and re-run change-proof\n"
    )
    assert transport.calls == [(pull, False)]


@pytest.mark.parametrize(
    "endpoint",
    [
        f"repos/{REPO}/pulls/17",
        f"repos/{REPO}/git/ref/heads/{BASE_REF}",
        f"repos/{REPO}/contents/.github/change-proof.json?ref={HEAD}",
        f"repos/{REPO}/contents/.tradecraft/work.json?ref={BASE_TIP}",
        f"repos/{REPO}/pulls/17/files?per_page=100",
        f"repos/{REPO}/issues/17/comments?per_page=100",
        f"repos/{REPO}/pulls/17/reviews?per_page=100",
        f"repos/{REPO}/pulls/17/comments?per_page=100",
    ],
)
def test_primary_input_failures_remain_whole_check_errors(endpoint):
    transport = complete_scenario()
    transport.responses[endpoint] = check.ProofError("primary input unavailable")

    result, output = execute(transport)

    assert result == 1
    assert "change-proof: ERROR" in output
    assert "primary input unavailable" in output


class Response:
    def __init__(self, value, headers=None):
        self.value = value
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self):
        return json.dumps(self.value).encode()


class OpenerSpy:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.responses.pop(0)


def test_transport_rejects_non_get_before_sending():
    opener = OpenerSpy()
    transport = check.GitHubTransport("token", opener=opener)

    with pytest.raises(check.ProofError, match="permits GET only"):
        transport.request("POST", "repos/example/project/issues")

    assert opener.calls == []


def test_transport_follows_link_header_pagination():
    next_url = "https://api.github.com/repos/example/project/items?page=2"
    opener = OpenerSpy([
        Response([{"id": 1}], {"Link": f'<{next_url}>; rel="next"'}),
        Response([{"id": 2}]),
    ])
    transport = check.GitHubTransport("token", opener=opener)

    value = transport.get("repos/example/project/items?per_page=1", paginate=True)

    assert value == [{"id": 1}, {"id": 2}]
    assert [call[0].get_method() for call in opener.calls] == ["GET", "GET"]
    assert opener.calls[1][0].full_url == next_url


def test_transport_preserves_paginated_object_pages_in_order():
    next_url = "https://api.github.com/repos/example/project/commits/abc?page=2"
    opener = OpenerSpy([
        Response({"sha": "abc", "files": [{"filename": "docs/one.md"}]}, {
            "Link": f'<{next_url}>; rel="next"'
        }),
        Response({"sha": "abc", "files": [{"filename": "docs/two.md"}]}),
    ])
    transport = check.GitHubTransport("token", opener=opener)

    value = transport.get("repos/example/project/commits/abc?per_page=1", paginate=True)

    assert value == [
        {"sha": "abc", "files": [{"filename": "docs/one.md"}]},
        {"sha": "abc", "files": [{"filename": "docs/two.md"}]},
    ]
    assert [call[0].get_method() for call in opener.calls] == ["GET", "GET"]
    assert opener.calls[1][0].full_url == next_url
