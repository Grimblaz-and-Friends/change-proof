from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

import pytest

from proof import check
from test_check import (
    BASE_TIP, HEAD, OWNER, REPO, FakeTransport, OpenerSpy, Response, contents,
    execute, no_use_note, proof_scenario, record, recorded_scenario,
    replace_proof_document, scenario,
)
from test_receipts import receipt_scenario


CR = "coderabbitai[bot]"
LAB = check.LAB_REVIEWER
REVIEW_ENDPOINT = f"repos/{REPO}/pulls/17/reviews?per_page=100"
INLINE_ENDPOINT = f"repos/{REPO}/pulls/17/comments?per_page=100"
COMMENTS_ENDPOINT = f"repos/{REPO}/issues/17/comments?per_page=100"
FIXTURES = Path(__file__).parent / "fixtures/connected-review"
IDENTITY = "cr-comment:v1:one"
MARKER = f"<!-- {IDENTITY} -->"
LAB_IDENTITY = "tradecraft-review-finding:v1:36672170816:1"


def source_url(review_id=41, *, repo=REPO, number=17, kind="pullrequestreview"):
    return f"https://github.com/{repo}/pull/{number}#{kind}-{review_id}"


def answer(identity=IDENTITY, review_id=41, *, disposition="fixed", author=OWNER):
    label = identity if identity is not None else "unidentified review"
    return record(author, f"{disposition}; [{label}]({source_url(review_id)})", id=601)


def body_scenario(evidence_path, reviewer=CR):
    if reviewer == LAB:
        transport, document = receipt_scenario(evidence_path)
    elif evidence_path == "proof-v1":
        transport, document = proof_scenario()
        document["reviewers"][0]["login"] = reviewer
        document["reviewers"][0]["source"]["author"] = reviewer
        transport.responses[REVIEW_ENDPOINT][0]["user"]["login"] = reviewer
        for revision in (HEAD, BASE_TIP):
            endpoint = f"repos/{REPO}/contents/.tradecraft/work.json?ref={revision}"
            config = json.loads(base64.b64decode(transport.responses[endpoint]["content"]))
            config["connected_reviewers"] = [reviewer]
            transport.responses[endpoint] = contents(config)
        replace_proof_document(transport, document)
    else:
        document = None
        transport = scenario(paths=("docs/readme.md",), comments=[no_use_note()],
                             reviewers=(reviewer,), reviews=[record(reviewer, id=41)])
    return transport, document


def add_inline(transport, document, *, reviewer=CR, identity=IDENTITY,
               answered=True, review_id=None, thread_id=51, in_document=True):
    if review_id is None:
        review_id = transport.responses[REVIEW_ENDPOINT][0]["id"]
    root = record(reviewer, f"<!-- {identity} -->" if identity else "inline finding",
                  id=thread_id, pull_request_review_id=review_id, in_reply_to_id=None)
    transport.responses[INLINE_ENDPOINT].append(root)
    if answered:
        transport.responses[INLINE_ENDPOINT].append(
            record(OWNER, "**fixed** - addressed", id=thread_id + 100, in_reply_to_id=thread_id)
        )
    if document is not None and in_document:
        def pointer(item):
            return {
                "kind": "inline-review-comment", "repository": REPO, "id": item["id"],
                "url": f"https://github.com/{REPO}/pull/17#discussion_r{item['id']}",
                "author": item["user"]["login"], "timestamp": "", "revision": None,
            }
        document["dispositions"].append({
            "thread_id": thread_id, "reviewer": reviewer, "source": pointer(root),
            "reply": pointer(transport.responses[INLINE_ENDPOINT][-1]) if answered else None,
        })
        replace_proof_document(transport, document)


@pytest.fixture(params=("legacy-markers", "proof-v1"))
def evidence_path(request):
    return request.param


@pytest.mark.parametrize("body", (
    "Summary and walkthrough", "### Codex Review\nOpening note.",
    "**Actionable comments posted: 0**", "```html\n" + MARKER + "\n```",
    "`" + MARKER + "`", "    " + MARKER, "> ~~~\n> " + MARKER + "\n> ~~~",
    "<code>" + MARKER + "</code>",
))
def test_summary_and_code_examples_owe_no_answer(evidence_path, body):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = body
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("category", ("Outside diff range comments", "Nitpick comments", "Other category"))
def test_every_identified_category_counts(evidence_path, category):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = f"**{category} (1)**\n> {MARKER}"
    result, output = execute(transport)
    assert result == 1, output
    assert f"body finding {IDENTITY}" in output
    transport.responses[COMMENTS_ENDPOINT].append(answer(disposition="declined — unnecessary"))
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("disposition", (
    "fixed", "fixed — nothing else found it", "fixed in #12",
    "yours — in the release report", "declined — unnecessary",
    "duplicate of the earlier comment", "lapsed — retired rule",
))
def test_existing_dispositions_answer_one_body_finding(evidence_path, disposition):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    transport.responses[COMMENTS_ENDPOINT].append(answer(disposition=disposition))
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("mutation", (
    "author", "formatted-word", "formatted-line", "bare-declined", "bare-lapsed",
    "fixed-in-without-number", "wrong-identity", "identity-only", "review-only",
    "wrong-review", "wrong-pr", "wrong-repo", "two-identities", "two-reviews",
    "fenced-answer", "quoted-answer", "word-prefix",
    "unbalanced-format", "empty-reason", "bare-duplicate",
))
def test_invalid_or_grouped_answers_clear_nothing(evidence_path, mutation):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    reply = answer()
    if mutation == "author":
        reply["user"]["login"] = "stranger"
    else:
        mutations = {
            "formatted-word": reply["body"].replace("fixed", "**fixed**", 1),
            "formatted-line": "`" + reply["body"] + "`",
            "bare-declined": reply["body"].replace("fixed", "declined", 1),
            "bare-lapsed": reply["body"].replace("fixed", "lapsed", 1),
            "fixed-in-without-number": reply["body"].replace("fixed", "fixed in #", 1),
            "wrong-identity": reply["body"].replace(IDENTITY, "cr-comment:v1:other"),
            "identity-only": f"fixed; {IDENTITY}",
            "review-only": answer(None)["body"],
            "wrong-review": reply["body"].replace("review-41", "review-42"),
            "wrong-pr": reply["body"].replace("/pull/17#", "/pull/18#"),
            "wrong-repo": reply["body"].replace(REPO, "other/repo"),
            "two-identities": reply["body"] + " cr-comment:v1:other",
            "two-reviews": reply["body"] + f" [review]({source_url(42)})",
            "fenced-answer": "```\n" + reply["body"] + "\n```",
            "quoted-answer": "> " + reply["body"],
            "word-prefix": reply["body"].replace("fixed", "fixedly", 1),
            "unbalanced-format": reply["body"].replace("fixed", "fixed**", 1),
            "empty-reason": reply["body"].replace("fixed", "declined —", 1),
            "bare-duplicate": reply["body"].replace("fixed", "duplicate of ", 1),
        }
        reply["body"] = mutations[mutation]
    transport.responses[COMMENTS_ENDPOINT].append(reply)
    result, output = execute(transport)
    assert result == 1, output
    assert f"body finding {IDENTITY}" in output


def test_finding_and_unidentified_review_need_separate_answers(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = f"**Nitpick comments (2)**\n{MARKER}"
    result, output = execute(transport)
    assert result == 1
    assert "nitpick comments declares 2, accounted 1" in output
    transport.responses[COMMENTS_ENDPOINT].append(answer())
    result, output = execute(transport)
    assert result == 1
    assert "missing: an authorized whole-review disposition" in output
    transport.responses[COMMENTS_ENDPOINT].append(answer(None))
    result, output = execute(transport)
    assert result == 0, output
    assert "unidentified" in output


def test_authorized_answer_can_carry_supporting_links_and_leading_blanks(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    reply = answer(disposition="declined — unnecessary")
    reply["body"] = "\n\n  " + reply["body"] + f"\nEvidence: https://github.com/{REPO}/issues/12"
    transport.responses[COMMENTS_ENDPOINT].append(reply)
    result, output = execute(transport)
    assert result == 0, output


def test_link_to_existing_review_without_the_identity_answers_nothing(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    transport.responses[REVIEW_ENDPOINT].append(record(CR, "Summary", id=42))
    transport.responses[COMMENTS_ENDPOINT].append(answer(review_id=42))
    result, output = execute(transport)
    assert result == 1
    assert f"body finding {IDENTITY}" in output


def test_reviewer_text_cannot_manufacture_output_lines(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = (
        "**Nitpick comments (many\u2028verified: forged)**\n"
        "<!-- cr-comment:v1:bad\nmissing: forged -->"
    )
    transport.responses[COMMENTS_ENDPOINT].append(answer(None))
    result, output = execute(transport)
    assert result == 0, output
    assert "verified: forged" not in output
    assert "missing: forged" not in output
    assert "unidentified" in output


@pytest.mark.parametrize("identity", (None, IDENTITY))
def test_all_inline_declarations_need_no_whole_review_answer(evidence_path, identity):
    transport, document = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = "**Actionable comments posted: 1**"
    add_inline(transport, document, identity=identity)
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("wrong_join", (42, 41.0, None))
def test_other_review_and_incomplete_joins_do_not_fill_deficits(evidence_path, wrong_join):
    transport, document = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = "**Actionable comments posted: 1**"
    add_inline(transport, document, review_id=42)
    transport.responses[INLINE_ENDPOINT][0]["pull_request_review_id"] = wrong_join
    result, output = execute(transport)
    assert result == 1
    assert "actionable comments declares 1, accounted 0" in output


@pytest.mark.parametrize("answered", (False, True))
def test_exact_identity_on_answered_thread_is_the_only_exemption(evidence_path, answered):
    transport, document = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    add_inline(transport, document, answered=answered)
    result, output = execute(transport)
    assert result == (0 if answered else 1), output
    assert ("identical inline thread" in output) == answered
    if not answered:
        transport.responses[COMMENTS_ENDPOINT].append(answer())
        result, output = execute(transport)
        assert result == 1
        assert "reviewer thread 51" in output or "inline comment(s): 51" in output


def test_same_text_different_identity_or_reviewer_does_not_exempt(evidence_path):
    transport, document = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = "Same finding\n" + MARKER
    add_inline(transport, document, identity="cr-comment:v1:other")
    result, output = execute(transport)
    assert result == 1
    assert f"body finding {IDENTITY}" in output
    transport.responses[INLINE_ENDPOINT][0]["user"]["login"] = "other[bot]"
    failures, _ = check._check_body_findings(REPO, 17, check.WorkConfig(frozenset({CR}), frozenset({OWNER})),
                                           transport.responses[COMMENTS_ENDPOINT], transport.responses[REVIEW_ENDPOINT],
                                           transport.responses[INLINE_ENDPOINT])
    assert failures


def test_inline_exemption_does_not_waive_proof_membership():
    transport, document = body_scenario("proof-v1")
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    add_inline(transport, document, in_document=False)
    result, output = execute(transport)
    assert result == 1
    assert "missing: 51" in output
    assert "identical inline thread" in output


@pytest.mark.parametrize("body", (
    "**Actionable comments posted: many**", "**Actionable comments posted:**",
    "**Actionable comments posted: 0**\n**Actionable comments posted: 0**",
    "**Nitpick comments (two)**", "**Nitpick comments**\n<details><summary>A finding</summary>unknown</details>",
    "**Outside diff range comments (1)**\n<details><summary>Missing identity</summary>unknown</details>\n---\n**Nitpick comments (2)**\n<!-- cr-comment:v1:a -->\n<!-- cr-comment:v1:b -->",
    "<!-- cr-comment:v1: -->", "<!-- cr-comment:v2:unknown -->",
    "**Outside diff range comments (1)**\n<details><summary>Missing identity</summary>unknown</details>\n**Nitpick comments (1)**\n<!-- cr-comment:v1:a -->",
    "<details>\n<summary>Nitpick comments</summary>\n<details><summary>file.py (2)</summary>\n<!-- cr-comment:v1:a -->\n</details></details>",
))
def test_malformed_and_unidentified_sections_fail_closed(evidence_path, body):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = body
    result, output = execute(transport)
    assert result == 1, output
    assert "unidentified" in output


def test_prior_reviews_and_repeated_identities_remain_scoped(evidence_path):
    transport, _ = body_scenario(evidence_path)
    reviews = transport.responses[REVIEW_ENDPOINT]
    reviews[0]["body"] = MARKER + "\n" + MARKER
    reviews.append(record(CR, MARKER, id=42, commit_id="1" * 40))
    transport.responses[COMMENTS_ENDPOINT].append(answer(review_id=42))
    result, output = execute(transport)
    assert result == 0, output
    assert output.count(f"body finding {IDENTITY}") == 1
    reviews.append(record(CR, "**Nitpick comments (1)**", id=43))
    transport.responses[COMMENTS_ENDPOINT].append(answer(None, 42))
    result, output = execute(transport)
    assert result == 1
    assert "pullrequestreview-43" in output


@pytest.mark.parametrize("body,all_inline", (
    ("1 validated finding.", True), ("2 validated findings.", False),
    ("1 validated finding.\n<!-- " + LAB_IDENTITY + " -->", False),
    ("1 validated finding(s).", False),
))
def test_old_and_current_lab_accounting_preserves_receipts(evidence_path, body, all_inline):
    transport, document = body_scenario(evidence_path, LAB)
    review = transport.responses[REVIEW_ENDPOINT][0]
    review["body"] = body + "\n" + review["body"]
    if all_inline or body.startswith("2"):
        add_inline(transport, document, reviewer=LAB, identity=None)
    result, output = execute(transport)
    assert result == (0 if all_inline else 1), output
    if not all_inline:
        identity = LAB_IDENTITY if "<!-- tradecraft-review" in body else None
        transport.responses[COMMENTS_ENDPOINT].append(answer(identity, review["id"]))
        result, output = execute(transport)
        assert result == 0, output
    review["body"] = review["body"].replace("connected-review-attempt:", "unproved-attempt:")
    result, output = execute(transport)
    assert result == 1
    assert "connected-review-attempt" in output


def test_unscopable_finding_never_disappears(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0].update(body=MARKER, id=None)
    result, output = execute(transport)
    assert result == 1
    assert "scopable body findings" in output


@pytest.mark.parametrize("body", (
    "1 validated finding(s).\n<!-- tradecraft-review-finding:v1:123:1 -->",
    "1 validated finding(s).\n1 validated finding(s).",
    "many validated finding(s).",
))
def test_conflicting_and_malformed_lab_evidence_is_unidentified(evidence_path, body):
    transport, _ = body_scenario(evidence_path, LAB)
    review = transport.responses[REVIEW_ENDPOINT][0]
    review["body"] = body + "\n" + review["body"]
    result, output = execute(transport)
    assert result == 1
    assert "unidentified" in output


@pytest.mark.parametrize("body,inline,expected", (
    ("Findings: 1", True, 0), ("1 findings.", False, 1),
    ("## Findings\n- Finding without an identity", False, 1),
    ("## Opening note\nSummary text", False, 0),
))
def test_other_configured_reviewer_structural_declarations(evidence_path, body, inline, expected):
    reviewer = "other[bot]"
    transport, document = body_scenario(evidence_path, reviewer)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = body
    if inline:
        add_inline(transport, document, reviewer=reviewer, identity=None)
    result, output = execute(transport)
    assert result == expected, output
    if expected:
        transport.responses[COMMENTS_ENDPOINT].append(answer(None))
        result, output = execute(transport)
        assert result == 0, output


def test_reviewer_conversation_findings_use_their_source_comment(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[COMMENTS_ENDPOINT].append(record(CR, MARKER, id=701))
    result, output = execute(transport)
    assert result == 1
    assert "issuecomment-701" in output
    transport.responses[COMMENTS_ENDPOINT].append(record(
        OWNER, f"fixed; [{IDENTITY}]({source_url(701, kind='issuecomment')})", id=702
    ))
    result, output = execute(transport)
    assert result == 0, output


@pytest.mark.parametrize("number", (654, 757))
def test_recorded_vendor_sections_keep_their_real_accounting(number):
    fixture = json.loads((FIXTURES / f"tradecraft-{number}-body.trimmed.json").read_text(encoding="utf-8"))
    config = check.WorkConfig(frozenset({CR}), frozenset({"grimblaz"}))
    failures, _ = check._check_body_findings(fixture["repository"], number, config, [],
                                           [fixture["review"]], fixture["inline_comments"])
    assert len(failures) == 1
    assert "body finding" in failures[0].missing
    assert "unidentified" not in failures[0].missing


@pytest.mark.parametrize("comment_name", ("tradecraft-733.comment.md", "tradecraft-733-no-bundle.comment.md"))
def test_historical_proof_with_labeled_join_and_answer_overlays_passes(comment_name):
    transport, environ = recorded_scenario("world-tc733.trimmed.json", comment_name)
    repo = environ["GITHUB_REPOSITORY"]
    joins = json.loads((FIXTURES / "tradecraft-733-review-joins.json").read_text())
    inline = transport.responses[f"repos/{repo}/pulls/733/comments?per_page=100"]
    for item in inline:
        item["pull_request_review_id"] = joins[str(item["id"])]
    # Synthetic overlay: historical answer omitted the required finding identity.
    transport.responses[f"repos/{repo}/issues/733/comments?per_page=100"].append(record(
        "Grimblaz", "fixed; [cr-comment:v1:7d3d3fcdd8d9891aeabf8880]"
        f"(https://github.com/{repo}/pull/733#pullrequestreview-5291109788)", id=9001,
    ))
    output = io.StringIO()
    assert check.run(environ, transport=transport, output=output) == 0, output.getvalue()


def test_body_obligations_and_answers_on_later_api_pages(evidence_path):
    transport, _ = body_scenario(evidence_path)
    transport.responses[REVIEW_ENDPOINT][0]["body"] = MARKER
    transport.responses[COMMENTS_ENDPOINT].append(answer())

    class PagedTransport(FakeTransport):
        def get(self, endpoint, *, paginate=False):
            data = super().get(endpoint, paginate=paginate)
            if endpoint in (REVIEW_ENDPOINT, COMMENTS_ENDPOINT):
                assert paginate
                next_url = f"https://api.github.com/{endpoint}&page=2"
                opener = OpenerSpy([Response([], {"Link": f'<{next_url}>; rel="next"'}), Response(data)])
                result = check.GitHubTransport("token", opener=opener).get(endpoint, paginate=True)
                assert all(request.method == "GET" for request, _ in opener.calls)
                return result
            return data

    result, output = execute(PagedTransport(transport.responses))
    assert result == 0, output


def test_derived_shared_protocol_examples(evidence_path):
    fixture = json.loads((FIXTURES / "derived-review-body-examples.json").read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        transport, document = body_scenario(evidence_path, case["reviewer"])
        review = transport.responses[REVIEW_ENDPOINT][0]
        trailing = review.get("body", "") if case["reviewer"] == LAB else ""
        review["body"] = case["body"] + "\n" + trailing
        for identity in case.get("inline", []):
            add_inline(transport, document, reviewer=case["reviewer"], identity=identity,
                       thread_id=51 + len(transport.responses[INLINE_ENDPOINT]))
        for reply in case["answers"]:
            transport.responses[COMMENTS_ENDPOINT].append(answer(
                reply["identity"], review["id"], disposition=reply["disposition"]
            ))
        result, output = execute(transport)
        assert result == case["exit_code"], (case["name"], output)


SHARED_BODY_CASES = json.loads(
    (FIXTURES / "v1-review-body-dispositions.json").read_bytes()
)["cases"]
assert len(SHARED_BODY_CASES) == 67


@pytest.mark.parametrize("case", SHARED_BODY_CASES, ids=lambda case: case["name"])
def test_shared_review_body_dispositions(case):
    config = check.WorkConfig(frozenset(case["connected_reviewers"]),
                              frozenset(case["marker_producers"]))
    failures, verified = check._check_body_findings(
        case["repository"], case["pull_request"], config,
        case["conversation_comments"], case["reviews"], case["inline_comments"],
    )
    review_url = re.escape(
        f"https://github.com/{case['repository']}/pull/{case['pull_request']}#pullrequestreview-"
    )
    finding_pattern = re.compile(
        r"an authorized conversation disposition for (.+) body finding (\S+) at "
        + review_url + r"([1-9][0-9]*)$"
    )
    unidentified_pattern = re.compile(
        r"unidentified .+ review at " + review_url + r"([1-9][0-9]*);"
    )
    missing_findings = {}
    missing_reviews = set()
    unidentified_reviews = set()
    for failure in failures:
        finding = finding_pattern.fullmatch(failure.missing)
        if finding:
            reviewer, identity, source = finding.groups()
            # The gate prints one representative source per finding. Recover all
            # carrying review ids with its identity parser, preserving deduplication.
            sources = {
                review["id"] for review in case["reviews"]
                if check._author(review) == reviewer and review.get("state") != "PENDING"
                and identity in check._body_identities(review.get("body") or "", reviewer)[0]
            }
            assert int(source) in sources, (case["name"], failure)
            missing_findings[reviewer, identity] = sources
        else:
            review = unidentified_pattern.search(failure.missing)
            assert review and failure.missing.startswith(
                "an authorized whole-review disposition for "
            ), (case["name"], failure)
            missing_reviews.add(int(review[1]))
            unidentified_reviews.add(int(review[1]))
    for message in verified:
        review = unidentified_pattern.match(message)
        if review:
            unidentified_reviews.add(int(review[1]))
    expected = case["expected"]
    # ignored_authors is a producer diagnostic, not an obligation; this gate
    # does not emit it, so only the three obligation/classification fields compare.
    assert missing_findings == {
        (item["reviewer"], item["identity"]): set(item["sources"])
        for item in expected["missing_findings"]
    }, (case["name"], failures, verified)
    assert missing_reviews == set(expected["missing_reviews"]), (case["name"], failures, verified)
    assert unidentified_reviews == set(expected["unidentified_reviews"]), (
        case["name"], failures, verified
    )


@pytest.mark.parametrize("content,zero", (
    ("None.", True), ("No findings.", True), ("No findings were found.", True),
    ("None", False), ("none.", False), ("No findings were found", False),
    ("No findings.\nAdditional prose.", False), ("Nothing to report.", False),
))
@pytest.mark.parametrize("section", (
    "## Findings\n{}", "<details><summary>Findings</summary>{}</details>",
))
def test_only_closed_zero_statements_account_for_empty_sections(content, zero, section):
    review = record("other[bot]", section.format(content), id=41)
    failures, _ = check._check_body_findings(
        REPO, 17, check.WorkConfig(frozenset({"other[bot]"}), frozenset({OWNER})),
        [], [review], [],
    )
    assert bool(failures) == (not zero)


@pytest.mark.parametrize("url_field,current_url,other_url", (
    ("pull_request_url", f"https://api.github.com/repos/{REPO}/pulls/17",
     f"https://api.github.com/repos/{REPO}/pulls/18"),
    ("html_url", f"https://github.com/{REPO}/pull/17#discussion_r151",
     f"https://github.com/{REPO}/pull/18#discussion_r151"),
))
@pytest.mark.parametrize("same_pr", (False, True))
def test_inline_exemption_requires_reply_urls_on_this_pr(url_field, current_url, other_url, same_pr):
    transport, document = body_scenario("legacy-markers")
    reviews = transport.responses[REVIEW_ENDPOINT]
    reviews[0]["body"] = MARKER
    add_inline(transport, document)
    inline = transport.responses[INLINE_ENDPOINT]
    inline[-1][url_field] = current_url if same_pr else other_url
    failures, _ = check._check_body_findings(
        REPO, 17, check.WorkConfig(frozenset({CR}), frozenset({OWNER})),
        [], reviews, inline,
    )
    assert bool(failures) == (not same_pr)
