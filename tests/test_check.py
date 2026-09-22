from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

import pytest

from proof import check


REPO = "Grimblaz-and-Friends/Organizations-of-Verra"
HEAD = "a" * 40
BASE = "b" * 40
BASE_TIP = "c" * 40
AMBIGUOUS_TAG_TIP = "d" * 40
BASE_REF = "main"
OWNER = "proof-owner"
REVIEWER = "review-bot[bot]"

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


def use_note(head=HEAD, author=OWNER):
    body = (
        f"<!-- tradecraft:use:v1 head={head} status=pass changed=false "
        "staffing_status=qualified -->\n\nUse session completed."
    )
    return record(author, body)


def no_use_note(head=HEAD, author=OWNER, *, line=True):
    if line is True:
        line = "Use: not required - documentation-only change"
    suffix = f"\n{line}" if isinstance(line, str) else ""
    return record(author, f"<!-- tradecraft:no-use:v1 head={head} -->{suffix}")


def contents(value):
    encoded = base64.b64encode((json.dumps(value) + "\n").encode()).decode()
    return {"encoding": "base64", "content": encoded}


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
    responses = {
        pull: {
            "number": 17,
            "draft": draft,
            "head": {"sha": head},
            "base": {"sha": base, "ref": base_ref},
            "changed_files": len(file_records) if changed_files is None else changed_files,
        },
        f"repos/{REPO}/git/ref/heads/{base_ref}": {"object": {"sha": base_tip}},
        f"repos/{REPO}/commits/{base_ref}": {"sha": AMBIGUOUS_TAG_TIP},
        f"{pull}/files?per_page=100": file_records,
        f"repos/{REPO}/issues/17/comments?per_page=100": list(comments or []),
        f"{pull}/reviews?per_page=100": list(reviews or []),
        f"{pull}/comments?per_page=100": list(review_comments or []),
    }
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


def test_stale_use_note_fails_current_head_check():
    transport = complete_scenario(comments=[use_note("b" * 40)])
    result, output = execute(transport)

    assert result == 1
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
    assert output.count("verified:") == 4
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
