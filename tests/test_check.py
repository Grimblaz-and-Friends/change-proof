from __future__ import annotations

import base64
import io
import json

import pytest

from proof import check


REPO = "Grimblaz-and-Friends/Organizations-of-Verra"
HEAD = "a" * 40
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
    suffix = "\nUse: not required - documentation-only change" if line else ""
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
        return self.responses[endpoint]


def scenario(
    *,
    paths=("src/main.ts",),
    comments=None,
    reviews=None,
    review_comments=None,
    reviewers=(REVIEWER,),
    head=HEAD,
    draft=False,
):
    use_rules = {
        "schema_version": 1,
        "rules": [
            {
                "name": "runtime-or-user-surface",
                "include": ["src/**", "public/**", "index.html", "package.json"],
                "exclude": ["**/tests/**", "**/*.test.ts"],
            }
        ],
    }
    work_config = {
        "schema_version": 1,
        "product_repositories": [REPO],
        "connected_reviewers": list(reviewers),
        "marker_producers": [OWNER],
    }
    pull = f"repos/{REPO}/pulls/17"
    responses = {
        pull: {"number": 17, "draft": draft, "head": {"sha": head}},
        f"repos/{REPO}/contents/.github/change-proof.json?ref={head}": contents(use_rules),
        f"repos/{REPO}/contents/.tradecraft/work.json?ref={head}": contents(work_config),
        f"{pull}/files?per_page=100": [{"filename": path} for path in paths],
        f"repos/{REPO}/issues/17/comments?per_page=100": list(comments or []),
        f"{pull}/reviews?per_page=100": list(reviews or []),
        f"{pull}/comments?per_page=100": list(review_comments or []),
    }
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


def test_authorized_first_line_disposition_passes():
    inline = record(REVIEWER, "finding", id=41, in_reply_to_id=None)
    reply = record(OWNER, "fixed - nothing else found it\nDetails.", id=42, in_reply_to_id=41)
    result, output = execute(
        scenario(comments=[use_note()], review_comments=[inline, reply])
    )

    assert result == 0
    assert "marker-producer disposition" in output


@pytest.mark.parametrize(
    "reply",
    [
        record("stranger", "fixed", id=42, in_reply_to_id=41),
        record(OWNER, "Thanks\nfixed", id=42, in_reply_to_id=41),
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


def test_complete_evidence_passes():
    inline = record(REVIEWER, "finding", id=91, in_reply_to_id=None)
    reply = record(OWNER, "declined - not a product defect", id=92, in_reply_to_id=91)
    transport = complete_scenario(review_comments=[inline, reply])
    result, output = execute(transport)

    assert result == 0
    assert output.count("verified:") == 3


def test_missing_event_head_is_resolved_by_get():
    result, output = execute(complete_scenario(), head="")

    assert result == 0
    assert "change-proof: PASS" in output


def test_draft_pull_request_exits_zero_without_evaluating():
    transport = scenario(draft=True)
    pull = f"repos/{REPO}/pulls/17"
    transport.responses = {pull: transport.responses[pull]}
    result, output = execute(transport)

    assert result == 0
    assert "SKIP" in output
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
