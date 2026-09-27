#!/usr/bin/env python3
"""Verify change-proof evidence for one GitHub pull request."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
import re
import sys
from typing import Mapping, TextIO
import urllib.error
import urllib.parse
import urllib.request


MARKER = re.compile(r"<!--\s*tradecraft:([a-z-]+):v1(?:\s+([^>]*?))?\s*-->", re.I)
ATTRIBUTE = re.compile(r"([a-z_]+)=([^\s]+)", re.I)
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\[bot\])?\Z")
SLUG = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\Z")
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
DOCUMENT_HEAD = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
PROOF_ENVELOPE = re.compile(
    r"<!--\s*tradecraft:proof:v1(?:\s+([^>]*?))?\s*-->", re.I
)
JSON_FENCE = re.compile(
    r"(?:\A|\r?\n)[ \t]*```(?:json)?[ \t]*\r?\n(.*?)(?:\r?\n)[ \t]*```[ \t]*(?=\r?\n|\Z)",
    re.I | re.S,
)
NO_USE_LINE = re.compile(r"^\s*Use: not required\s+(?:-|—)\s+\S.*$")
DISPOSITIONS = (
    "fixed",
    "fixed - nothing else found it",
    "fixed in #",
    "yours - in the release report",
    "declined -",
    "duplicate of ",
    "lapsed -",
)
REVIEW_NOTICE_PATTERNS = (
    ("Review limit reached", re.compile(r"\breview limit reached\b", re.I)),
    ("rate limited", re.compile(r"\brate limited\b", re.I)),
    (
        "review limited",
        re.compile(r"\breview (?:was |is )?limited\b|\blimited review\b", re.I),
    ),
    (
        "review skipped",
        re.compile(r"\breview (?:was |is )?skipped\b|\bskipped review\b", re.I),
    ),
    (
        "Ask your admin to upgrade for code reviews",
        re.compile(r"\bask your admin to upgrade for code reviews\b", re.I),
    ),
    (
        "Running",
        re.compile(
            r"^\|[^|\n]*\|[ \t]*(?:\*\*)?running(?:\*\*)?[ \t]*\|",
            re.I | re.M,
        ),
    ),
)
PATH_DEPARTURES_LEAD_IN = "**Path departures:**"
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
THEMATIC_BREAK = re.compile(
    r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"
)
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
CONTAINER_PROSE = re.compile(
    r"^ {0,3}(?:>[ \t]?|(?:[-+*]|\d{1,9}[.)])(?:[ \t]+|$))(.*)$"
)
HTML_BLOCK_TYPE_1_START = re.compile(
    r"^<(pre|script|style|textarea)(?=[ \t>]|$)", re.I
)
HTML_BLOCK_TYPE_6_START = re.compile(
    r"^</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|"
    r"col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
    r"footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|"
    r"link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    r"section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)"
    r"(?=[ \t]|/?>|$)",
    re.I,
)
HTML_BLOCK_TYPE_7_START = re.compile(
    r"^(?:"
    r"<[A-Za-z][A-Za-z0-9-]*"
    r"(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:[ \t]*=[ \t]*(?:[^ \t\n\f\r\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*"
    r"[ \t]*/?>"
    r"|</[A-Za-z][A-Za-z0-9-]*[ \t]*>"
    r")[ \t]*$"
)
HTML_COMMENT_END = re.compile(r"-->")
HTML_PROCESSING_INSTRUCTION_END = re.compile(r"\?>")
HTML_DECLARATION_END = re.compile(r">")
HTML_CDATA_END = re.compile(r"\]\]>")


class ProofError(RuntimeError):
    """The checker cannot evaluate the pull request safely."""


class GitHubNotFound(ProofError):
    """A requested GitHub resource does not exist at the selected revision."""


@dataclass(frozen=True)
class MarkerRecord:
    name: str
    attributes: dict[str, str]
    body: str
    author: str
    timestamp: str = ""
    source_id: int = 0
    observed_order: int = 0


@dataclass(frozen=True)
class WorkConfig:
    connected_reviewers: frozenset[str]
    marker_producers: frozenset[str]


@dataclass(frozen=True)
class Finding:
    missing: str
    satisfy: str


@dataclass(frozen=True)
class ProofCandidate:
    comment_id: int
    author: str
    envelope_head: str | None
    document: dict[str, object] | None
    error: str | None


class GitHubTransport:
    """Perform authenticated GitHub REST reads and nothing else."""

    def __init__(self, token: str, api_url: str = "https://api.github.com", opener=None):
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.opener = opener or urllib.request.build_opener()

    def request(self, method: str, endpoint: str) -> tuple[object, Mapping[str, str]]:
        if method != "GET":
            raise ProofError(f"HTTP method {method!r} is forbidden; change-proof permits GET only")
        url = endpoint if endpoint.startswith("https://") else f"{self.api_url}/{endpoint.lstrip('/')}"
        if not url.startswith(f"{self.api_url}/"):
            raise ProofError("GitHub pagination left the configured API origin")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "change-proof",
            },
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                payload = response.read()
                headers = response.headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="backslashreplace").strip()
            if exc.code == 404:
                raise GitHubNotFound(f"GitHub GET found no resource at {url}") from exc
            raise ProofError(f"GitHub GET failed for {url}: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProofError(f"GitHub GET failed for {url}: {exc.reason}") from exc
        try:
            return json.loads(payload.decode("utf-8")), headers
        except (UnicodeError, ValueError) as exc:
            raise ProofError(f"GitHub GET returned invalid JSON for {url}") from exc

    def get(self, endpoint: str, *, paginate: bool = False) -> object:
        next_endpoint: str | None = endpoint
        combined: list[object] = []
        page_kind: type[list] | type[dict] | None = None
        while next_endpoint is not None:
            value, headers = self.request("GET", next_endpoint)
            if not paginate:
                return value
            if isinstance(value, list):
                if page_kind not in (None, list):
                    raise ProofError(
                        f"GitHub paginated GET changed response shape at {next_endpoint}"
                    )
                page_kind = list
                combined.extend(value)
            elif isinstance(value, dict):
                if page_kind not in (None, dict):
                    raise ProofError(
                        f"GitHub paginated GET changed response shape at {next_endpoint}"
                    )
                page_kind = dict
                combined.append(value)
            else:
                raise ProofError(
                    f"GitHub paginated GET returned neither a list nor object for {next_endpoint}"
                )
            next_endpoint = _next_link(headers.get("Link"))
        return combined


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for item in header.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', item)
        if match and "next" in match.group(2).split():
            return match.group(1)
    return None


def _html_block_start(
    line: str, paragraph_open: bool
) -> tuple[re.Pattern[str] | None, bool] | None:
    source = line.lstrip(" ")
    if len(line) - len(source) > 3:
        return None

    type_1 = HTML_BLOCK_TYPE_1_START.match(source)
    if type_1 is not None:
        tag = re.escape(type_1.group(1))
        return re.compile(rf"</{tag}[ \t]*>", re.I), False
    if source.startswith("<!--"):
        return HTML_COMMENT_END, False
    if source.startswith("<?"):
        return HTML_PROCESSING_INSTRUCTION_END, False
    if re.match(r"^<![A-Za-z]", source):
        return HTML_DECLARATION_END, False
    if source.startswith("<![CDATA["):
        return HTML_CDATA_END, False
    if HTML_BLOCK_TYPE_6_START.match(source):
        return None, True
    if not paragraph_open and HTML_BLOCK_TYPE_7_START.fullmatch(source):
        return None, True
    return None


def _has_path_departures_paragraph(body: object) -> bool:
    if not isinstance(body, str) or not body:
        return False

    paragraph_open = False
    candidate = False
    fence: tuple[str, int] | None = None
    html_block_end: re.Pattern[str] | None = None
    html_block_until_blank = False

    for line in body.splitlines():
        if fence is not None:
            character, minimum = fence
            if re.fullmatch(
                rf" {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", line
            ):
                fence = None
            continue

        if html_block_end is not None:
            if html_block_end.search(line):
                html_block_end = None
            continue

        if html_block_until_blank:
            if not line.strip():
                html_block_until_blank = False
            continue

        html_block = _html_block_start(line, paragraph_open)
        if html_block is not None:
            if candidate:
                return True
            paragraph_open = False
            candidate = False
            end_pattern, html_block_until_blank = html_block
            if end_pattern is not None and not end_pattern.search(line):
                html_block_end = end_pattern
            continue

        if not line.strip():
            if candidate:
                return True
            paragraph_open = False
            candidate = False
            continue

        fence_match = FENCE_OPEN.match(line)
        if fence_match is not None:
            marker, info = fence_match.groups()
            if marker[0] == "~" or "`" not in info:
                if candidate:
                    return True
                paragraph_open = False
                candidate = False
                fence = (marker[0], len(marker))
                continue

        if paragraph_open and SETEXT_UNDERLINE.fullmatch(line):
            paragraph_open = False
            candidate = False
            continue

        if ATX_HEADING.match(line) or THEMATIC_BREAK.fullmatch(line):
            if candidate:
                return True
            paragraph_open = False
            candidate = False
            continue

        if line.startswith(("    ", "\t")):
            if paragraph_open:
                continue
            paragraph_open = False
            candidate = False
            continue

        container = CONTAINER_PROSE.match(line)
        if container is not None:
            if candidate:
                return True
            content = container.group(1)
            nested_fence = FENCE_OPEN.match(content)
            paragraph_open = bool(content.strip()) and not (
                ATX_HEADING.match(content)
                or THEMATIC_BREAK.fullmatch(content)
                or content.lstrip().startswith("<!--")
                or (
                    nested_fence is not None
                    and (
                        nested_fence.group(1)[0] == "~"
                        or "`" not in nested_fence.group(2)
                    )
                )
            )
            candidate = False
            continue

        if line.startswith(PATH_DEPARTURES_LEAD_IN) and not paragraph_open:
            paragraph_open = True
            candidate = True
            continue

        paragraph_open = True

    return candidate


def _object(value: object, source: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProofError(f"{source} must be a JSON object")
    return value


def _records(value: object, source: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ProofError(f"{source} must be a JSON object list")
    return value


def _author(item: dict[str, object]) -> str:
    user = item.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    return login.lower() if isinstance(login, str) and login else "unknown"


def _json_file_record(
    transport, repo: str, path: str, head: str
) -> tuple[dict[str, object], bytes]:
    quoted_path = urllib.parse.quote(path, safe="/")
    quoted_head = urllib.parse.quote(head, safe="")
    endpoint = f"repos/{repo}/contents/{quoted_path}?ref={quoted_head}"
    response = _object(transport.get(endpoint), path)
    if response.get("encoding") != "base64" or not isinstance(response.get("content"), str):
        raise ProofError(f"{path} must be a base64 GitHub contents response")
    try:
        content = base64.b64decode(response["content"], validate=False)
        value = json.loads(content.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProofError(f"{path} must contain UTF-8 JSON") from exc
    return _object(value, path), content


def _json_file(transport, repo: str, path: str, head: str) -> dict[str, object]:
    value, _content = _json_file_record(transport, repo, path, head)
    return value


def _optional_json_file_record(
    transport, repo: str, path: str, revision: str
) -> tuple[dict[str, object], bytes] | None:
    try:
        return _json_file_record(transport, repo, path, revision)
    except GitHubNotFound:
        return None


def _optional_json_file(transport, repo: str, path: str, revision: str) -> dict[str, object] | None:
    record = _optional_json_file_record(transport, repo, path, revision)
    return record[0] if record is not None else None


def load_use_rules(value: object) -> dict[str, object]:
    rules_object = _object(value, ".github/change-proof.json")
    if rules_object.get("schema_version") != 1:
        raise ProofError(".github/change-proof.json must be a schema-version-1 object")
    rules = rules_object.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ProofError(".github/change-proof.json must contain a nonempty rules list")
    for rule in rules:
        if (
            not isinstance(rule, dict)
            or not isinstance(rule.get("include"), list)
            or not isinstance(rule.get("exclude"), list)
        ):
            raise ProofError("each use rule must carry include and exclude lists")
    return rules_object


def load_work_config(value: object) -> WorkConfig:
    config = _object(value, ".tradecraft/work.json")
    if config.get("schema_version") != 1:
        raise ProofError(".tradecraft/work.json must be a schema-version-1 object")
    fields = ("product_repositories", "connected_reviewers", "marker_producers")
    if any(not isinstance(config.get(name), list) for name in fields):
        raise ProofError(
            ".tradecraft/work.json must carry product, reviewer and marker-producer lists"
        )
    for repository in config["product_repositories"]:
        if not isinstance(repository, str) or REPOSITORY_NAME.fullmatch(repository) is None:
            raise ProofError("each product repository must be an owner/repository string")
    identities: dict[str, frozenset[str]] = {}
    for field in ("connected_reviewers", "marker_producers"):
        normalized: set[str] = set()
        for login in config[field]:
            if not isinstance(login, str) or GITHUB_LOGIN.fullmatch(login) is None:
                raise ProofError(f"each {field} entry must be a GitHub login")
            normalized.add(login.lower())
        identities[field] = frozenset(normalized)
    return WorkConfig(identities["connected_reviewers"], identities["marker_producers"])


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _schema_object(
    value: object, path: str, fields: tuple[str, ...]
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProofError(f"proof document {path} must be an object")
    actual = set(value)
    expected = set(fields)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        raise ProofError(f"proof document {path} has invalid fields: {'; '.join(details)}")
    return value


def _schema_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProofError(f"proof document {path} must be a nonempty string")
    return value


def _schema_nullable_text(value: object, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ProofError(f"proof document {path} must be a string or null")


def _schema_enum(value: object, path: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ProofError(f"proof document {path} has an unknown value")
    return value


def _schema_head(value: object, path: str) -> str:
    if not isinstance(value, str) or DOCUMENT_HEAD.fullmatch(value) is None:
        raise ProofError(f"proof document {path} must be a full revision")
    return value


def _validate_source(value: object, path: str) -> dict[str, object]:
    source = _schema_object(
        value,
        path,
        ("kind", "repository", "id", "url", "author", "timestamp", "revision"),
    )
    _schema_string(source["kind"], f"{path}.kind")
    _schema_string(source["repository"], f"{path}.repository")
    identity = source["id"]
    if identity is not None and not isinstance(identity, str) and not _is_integer(identity):
        raise ProofError(f"proof document {path}.id must be an integer, string or null")
    for field in ("url", "author", "timestamp", "revision"):
        _schema_nullable_text(source[field], f"{path}.{field}")
    return source


def _validate_policy_source(value: object, path: str) -> dict[str, object]:
    source = _schema_object(value, path, ("repository", "path", "revision", "sha256"))
    for field in source:
        _schema_string(source[field], f"{path}.{field}")
    return source


def _validate_check(value: object, path: str) -> dict[str, object]:
    fields = (
        "id", "name", "app_id", "app_slug", "workflow_id", "run_id", "url",
        "head", "status", "conclusion", "started_at", "completed_at",
    )
    check = _schema_object(value, path, fields)
    _schema_string(check["name"], f"{path}.name")
    for field in ("id", "app_id", "workflow_id", "run_id"):
        if check[field] is not None and not _is_integer(check[field]):
            raise ProofError(f"proof document {path}.{field} must be an integer or null")
    for field in (
        "app_slug", "url", "head", "status", "conclusion", "started_at", "completed_at"
    ):
        _schema_nullable_text(check[field], f"{path}.{field}")
    return check


def _validate_declaration(value: object, path: str) -> dict[str, object]:
    fields = (
        "stage", "status", "reason", "dispatch_id", "completed_at", "revision",
        "requested_vendor", "requested_model", "requested_effort",
        "requested_classification", "actual_vendor", "actual_model", "actual_effort",
        "fallback_reason", "staffing_status", "same_vendor_reason",
    )
    declaration = _schema_object(value, path, fields)
    _schema_string(declaration["stage"], f"{path}.stage")
    _schema_enum(declaration["status"], f"{path}.status", frozenset({"declared", "unverifiable"}))
    for field in fields[2:]:
        _schema_nullable_text(declaration[field], f"{path}.{field}")
    if declaration["status"] == "unverifiable" and (
        not isinstance(declaration["reason"], str) or not declaration["reason"]
    ):
        raise ProofError(f"proof document {path}.reason is required for unverifiable status")
    return declaration


def validate_proof_document(value: object) -> dict[str, object]:
    """Validate proof v1 independently from the producer implementation."""
    fields = (
        "schema_version", "identity", "policy", "floor", "use", "reviewers",
        "dispositions", "declarations", "diagnostics",
    )
    document = _schema_object(value, "$", fields)
    if not _is_integer(document["schema_version"]) or document["schema_version"] != 1:
        raise ProofError("proof document schema_version must be integer 1")

    identity = _schema_object(
        document["identity"], "$.identity",
        ("work", "repository", "issue", "pull_request", "head", "producer_version"),
    )
    for field in ("work", "repository", "producer_version"):
        _schema_string(identity[field], f"$.identity.{field}")
    for field in ("issue", "pull_request"):
        if not _is_integer(identity[field]) or identity[field] < 1:
            raise ProofError(f"proof document $.identity.{field} must be a positive integer")
    _schema_head(identity["head"], "$.identity.head")

    policy = _schema_object(document["policy"], "$.policy", ("work_configuration", "use_rules"))
    _validate_policy_source(policy["work_configuration"], "$.policy.work_configuration")
    _validate_policy_source(policy["use_rules"], "$.policy.use_rules")

    floor = _schema_object(document["floor"], "$.floor", ("head", "source", "checks"))
    if floor["head"] is not None:
        _schema_head(floor["head"], "$.floor.head")
    if floor["source"] is not None:
        _validate_source(floor["source"], "$.floor.source")
    if not isinstance(floor["checks"], list):
        raise ProofError("proof document $.floor.checks must be an array")
    for index, item in enumerate(floor["checks"]):
        _validate_check(item, f"$.floor.checks[{index}]")

    use = _schema_object(
        document["use"], "$.use",
        (
            "required", "classification", "evidence_head", "applicability", "source",
            "intervening_commits", "reason",
        ),
    )
    if not isinstance(use["required"], bool):
        raise ProofError("proof document $.use.required must be a Boolean")
    _schema_enum(
        use["classification"], "$.use.classification", frozenset({"required", "not-required"})
    )
    if use["evidence_head"] is not None:
        _schema_head(use["evidence_head"], "$.use.evidence_head")
    _schema_enum(
        use["applicability"],
        "$.use.applicability",
        frozenset({"current-head", "ancestor", "generated", "missing"}),
    )
    if use["source"] is not None:
        _validate_source(use["source"], "$.use.source")
    if not isinstance(use["intervening_commits"], list):
        raise ProofError("proof document $.use.intervening_commits must be an array")
    for index, item in enumerate(use["intervening_commits"]):
        commit = _schema_object(item, f"$.use.intervening_commits[{index}]", ("sha", "paths"))
        _schema_head(commit["sha"], f"$.use.intervening_commits[{index}].sha")
        if not isinstance(commit["paths"], list) or not all(
            isinstance(path, str) for path in commit["paths"]
        ):
            raise ProofError(
                f"proof document $.use.intervening_commits[{index}].paths must be a string array"
            )
    _schema_nullable_text(use["reason"], "$.use.reason")

    if not isinstance(document["reviewers"], list):
        raise ProofError("proof document $.reviewers must be an array")
    for index, item in enumerate(document["reviewers"]):
        reviewer = _schema_object(
            item, f"$.reviewers[{index}]", ("login", "result", "source", "notices")
        )
        _schema_string(reviewer["login"], f"$.reviewers[{index}].login")
        _schema_enum(
            reviewer["result"],
            f"$.reviewers[{index}].result",
            frozenset({"present", "missing", "notice-only"}),
        )
        if reviewer["source"] is not None:
            _validate_source(reviewer["source"], f"$.reviewers[{index}].source")
        if not isinstance(reviewer["notices"], list) or not all(
            isinstance(notice, str) for notice in reviewer["notices"]
        ):
            raise ProofError(f"proof document $.reviewers[{index}].notices must be a string array")

    if not isinstance(document["dispositions"], list):
        raise ProofError("proof document $.dispositions must be an array")
    for index, item in enumerate(document["dispositions"]):
        disposition = _schema_object(
            item, f"$.dispositions[{index}]", ("thread_id", "reviewer", "source", "reply")
        )
        if not _is_integer(disposition["thread_id"]):
            raise ProofError(f"proof document $.dispositions[{index}].thread_id must be an integer")
        if not isinstance(disposition["reviewer"], str):
            raise ProofError(f"proof document $.dispositions[{index}].reviewer must be a string")
        _validate_source(disposition["source"], f"$.dispositions[{index}].source")
        if disposition["reply"] is not None:
            _validate_source(disposition["reply"], f"$.dispositions[{index}].reply")

    if not isinstance(document["declarations"], list):
        raise ProofError("proof document $.declarations must be an array")
    for index, item in enumerate(document["declarations"]):
        _validate_declaration(item, f"$.declarations[{index}]")

    if not isinstance(document["diagnostics"], list):
        raise ProofError("proof document $.diagnostics must be an array")
    for index, item in enumerate(document["diagnostics"]):
        diagnostic = _schema_object(
            item, f"$.diagnostics[{index}]", ("code", "message", "source")
        )
        _schema_string(diagnostic["code"], f"$.diagnostics[{index}].code")
        _schema_string(diagnostic["message"], f"$.diagnostics[{index}].message")
        if diagnostic["source"] is not None:
            _validate_source(diagnostic["source"], f"$.diagnostics[{index}].source")
    return document


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProofError(f"proof document contains duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> object:
    raise ProofError(f"proof document contains non-JSON numeric constant {value}")


def _proof_candidates(
    comments: list[dict[str, object]], authorized_authors: frozenset[str]
) -> list[ProofCandidate]:
    candidates: list[ProofCandidate] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        author = _author(comment)
        raw_id = comment.get("id")
        comment_id = raw_id if _is_integer(raw_id) else 0
        for envelope in PROOF_ENVELOPE.finditer(body):
            raw_attributes = envelope.group(1) or ""
            pairs = ATTRIBUTE.findall(raw_attributes)
            attributes = {key.lower(): value for key, value in pairs}
            unmatched = ATTRIBUTE.sub("", raw_attributes).strip()
            envelope_head = attributes.get("head")
            error: str | None = None
            document: dict[str, object] | None = None
            if (
                unmatched
                or len(pairs) != 1
                or set(attributes) != {"head"}
                or not isinstance(envelope_head, str)
                or DOCUMENT_HEAD.fullmatch(envelope_head) is None
            ):
                envelope_head = None
                error = "proof envelope must carry exactly one full head attribute"
            elif author not in authorized_authors:
                # The envelope is enough to report unauthorized current-head noise. Never
                # parse an untrusted producer's potentially adversarial JSON body.
                pass
            else:
                fenced = JSON_FENCE.findall(body[envelope.end():])
                if len(fenced) != 1:
                    error = "proof envelope must be followed by exactly one fenced JSON object"
                else:
                    try:
                        parsed = json.loads(
                            fenced[0],
                            object_pairs_hook=_unique_json_object,
                            parse_constant=_invalid_json_constant,
                        )
                        document = validate_proof_document(parsed)
                    except Exception as exc:
                        error = str(exc) or type(exc).__name__
            candidates.append(ProofCandidate(comment_id, author, envelope_head, document, error))
    return candidates


def use_required(paths: list[str], rules: dict[str, object]) -> bool:
    normalized = [path.replace("\\", "/") for path in paths]
    for rule in rules["rules"]:
        includes = rule["include"]
        excludes = rule["exclude"]
        for path in normalized:
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in includes) and not any(
                fnmatch.fnmatchcase(path, pattern) for pattern in excludes
            ):
                return True
    return False


def markers(records: list[dict[str, object]]) -> list[MarkerRecord]:
    found: list[MarkerRecord] = []
    for record in records:
        body = str(record.get("body") or "")
        author = _author(record)
        raw_timestamp = record.get("submitted_at") or record.get("created_at")
        timestamp = raw_timestamp if isinstance(raw_timestamp, str) else ""
        raw_source_id = record.get("id")
        if isinstance(raw_source_id, int) and not isinstance(raw_source_id, bool):
            source_id = raw_source_id
        elif isinstance(raw_source_id, str) and raw_source_id.isdigit():
            source_id = int(raw_source_id)
        else:
            source_id = 0
        for match in MARKER.finditer(body):
            attributes = {
                key.lower(): value for key, value in ATTRIBUTE.findall(match.group(2) or "")
            }
            found.append(MarkerRecord(
                match.group(1).lower(),
                attributes,
                body,
                author,
                timestamp,
                source_id,
                len(found),
            ))
    return found


def _valid_use(marker: MarkerRecord, head: str) -> bool:
    attributes = marker.attributes
    keys = set(attributes)
    if marker.name != "use":
        return False
    if keys not in (
        {"head", "status", "changed", "staffing_status"},
        {"head", "status", "changed", "staffing_status", "same_vendor_reason"},
    ):
        return False
    if (
        attributes.get("head") != head
        or attributes.get("status") != "pass"
        or attributes.get("changed") not in {"true", "false"}
        or attributes.get("staffing_status") not in {"qualified", "degraded"}
    ):
        return False
    reason = attributes.get("same_vendor_reason")
    if attributes["staffing_status"] == "degraded":
        return bool(reason and SLUG.fullmatch(reason))
    return reason is None


def _commit_files(transport, repo: str, revision: str) -> list[str]:
    endpoint = f"repos/{repo}/commits/{revision}?per_page=100"
    value = transport.get(endpoint, paginate=True)
    pages = value if isinstance(value, list) else [value]
    paths: list[str] = []
    for page in pages:
        commit = _object(page, endpoint)
        if "files" not in commit:
            raise ProofError(f"GitHub commit GET omitted files for {revision}")
        files = _records(commit["files"], endpoint)
        for item in files:
            for field in ("filename", "previous_filename"):
                path = item.get(field)
                if isinstance(path, str) and path not in paths:
                    paths.append(path)
    return paths


def _ancestor_application(
    transport,
    repo: str,
    ancestor: str,
    head: str,
    rules: dict[str, object],
) -> dict[str, object]:
    quoted_ancestor = urllib.parse.quote(ancestor, safe="")
    quoted_head = urllib.parse.quote(head, safe="")
    endpoint = f"repos/{repo}/compare/{quoted_ancestor}...{quoted_head}"
    comparison = _object(transport.get(endpoint), endpoint)
    merge_base = comparison.get("merge_base_commit")
    merge_base_sha = merge_base.get("sha") if isinstance(merge_base, dict) else None
    commits = _records(comparison.get("commits", []), endpoint)
    ahead_by = comparison.get("ahead_by")
    comparison_status = comparison.get("status")
    if (
        not isinstance(comparison_status, str)
        or comparison_status not in {"ahead", "identical"}
        or merge_base_sha != ancestor
    ):
        return {
            "applicable": False,
            "reason": f"use evidence head {ancestor} is not an ancestor of current head {head}",
        }
    if not isinstance(ahead_by, int) or isinstance(ahead_by, bool) or ahead_by != len(commits):
        return {
            "applicable": False,
            "reason": f"complete intervening history from {ancestor} is unavailable",
        }
    intervening: list[str] = []
    intervening_records: list[dict[str, object]] = []
    for commit in commits:
        revision = commit.get("sha")
        if not isinstance(revision, str) or FULL_SHA.fullmatch(revision) is None:
            return {
                "applicable": False,
                "reason": f"intervening commit from {ancestor} has no full revision",
            }
        paths = _commit_files(transport, repo, revision)
        intervening.append(revision)
        intervening_records.append({"sha": revision, "paths": paths})
        if use_required(paths, rules):
            return {
                "applicable": False,
                "reason": (
                    f"use evidence at {ancestor} is stale because intervening commit "
                    f"{revision} changes a use-bought path"
                ),
                "intervening_commits": intervening,
                "intervening_records": intervening_records,
            }
    return {
        "applicable": True,
        "reason": "every intervening commit changes only paths outside the use-bought policy",
        "intervening_commits": intervening,
        "intervening_records": intervening_records,
    }


def _ancestor_use(
    transport,
    repo: str,
    head: str,
    rules: dict[str, object],
    authorized: list[MarkerRecord],
) -> tuple[MarkerRecord | None, list[str], str | None]:
    candidates = []
    for marker in authorized:
        evidence_head = marker.attributes.get("head")
        if (
            marker.name == "use"
            and isinstance(evidence_head, str)
            and evidence_head != head
            and FULL_SHA.fullmatch(evidence_head) is not None
            and marker.attributes.get("changed") == "false"
            and _valid_use(marker, evidence_head)
        ):
            candidates.append(marker)
    candidates.sort(
        key=lambda marker: (marker.timestamp, marker.source_id, marker.observed_order),
        reverse=True,
    )
    newest_reason: str | None = None
    for marker in candidates:
        evidence_head = marker.attributes["head"]
        try:
            application = _ancestor_application(
                transport, repo, evidence_head, head, rules
            )
        except (OSError, UnicodeError, ValueError, ProofError) as exc:
            detail = str(exc) or type(exc).__name__
            reason = f"history unavailable from {evidence_head}: {detail}"
        else:
            reason = str(application.get("reason") or "use evidence is not applicable")
            if application.get("applicable"):
                revisions = application.get("intervening_commits", [])
                if not isinstance(revisions, list) or not all(
                    isinstance(revision, str) for revision in revisions
                ):
                    raise ProofError("applicable use history has an invalid internal shape")
                return marker, revisions, None
        if newest_reason is None:
            newest_reason = reason
    return None, [], newest_reason


def _strip_balanced_markdown_wrapper(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped[0] not in "`*_":
        return stripped
    marker = stripped[0]
    opening = len(stripped) - len(stripped.lstrip(marker))
    closing = len(stripped) - len(stripped.rstrip(marker))
    wrapper = marker * opening
    if wrapper not in {"`", "*", "**", "_", "__"} or closing != opening:
        return stripped
    return stripped[opening:-closing].strip()


def _valid_no_use(marker: MarkerRecord, head: str) -> bool:
    has_line = any(
        NO_USE_LINE.fullmatch(_strip_balanced_markdown_wrapper(line))
        for line in marker.body.splitlines()
    )
    return marker.name == "no-use" and marker.attributes == {"head": head} and has_line


def _disposition(body: str) -> bool:
    first_line = body.splitlines()[0] if body.splitlines() else ""
    normalized = (
        _strip_balanced_markdown_wrapper(first_line)
        .lower()
        .replace(chr(0x2014), "-")
        .strip()
    )
    for prefix in DISPOSITIONS:
        if not normalized.startswith(prefix):
            continue
        if not prefix[-1].isalnum() or len(normalized) == len(prefix):
            return True
        following = normalized[len(prefix)]
        if not (following.isalnum() or following == "_"):
            return True
    return False


def _review_notice(body: str) -> str | None:
    for name, pattern in REVIEW_NOTICE_PATTERNS:
        if pattern.search(body):
            return name
    return None


def _record_label(kind: str, item: dict[str, object]) -> str:
    identity = item.get("id")
    return f"{kind} #{identity}" if isinstance(identity, int) else kind


def _safe_text(value: object) -> str:
    if value is None:
        return "null"
    escaped = str(value).replace("\\", "\\\\")
    separators = {
        "\n": "\\n",
        "\r": "\\r",
        "\v": "\\v",
        "\f": "\\f",
        "\x1c": "\\x1c",
        "\x1d": "\\x1d",
        "\x1e": "\\x1e",
        "\x85": "\\x85",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }
    return "".join(separators.get(character, character) for character in escaped)


def _source_identity(value: object) -> str:
    if _is_integer(value):
        return str(value)
    return value if isinstance(value, str) else ""


def _resolve_source(
    source: dict[str, object],
    repo: str,
    comments: list[dict[str, object]],
    work_comments: list[dict[str, object]],
    reviews: list[dict[str, object]],
    review_comments: list[dict[str, object]],
) -> tuple[dict[str, object] | None, str | None]:
    if str(source["repository"]).lower() != repo.lower():
        return None, f"source repository {source['repository']} is outside {repo}"
    kind = str(source["kind"]).lower()
    if kind == "pull-request-comment":
        records = comments
    elif kind == "issue-comment":
        records = work_comments
    elif kind == "review":
        records = reviews
    elif kind in {"review-comment", "inline-review-comment"}:
        records = review_comments
    else:
        return None, f"source kind {source['kind']!r} is not a supported public evidence surface"
    identity = _source_identity(source["id"])
    record = next(
        (item for item in records if _source_identity(item.get("id")) == identity),
        None,
    )
    if record is None:
        return None, f"{kind} source {identity or 'without an id'} is not on its claimed surface"
    claimed_author = source.get("author")
    if isinstance(claimed_author, str) and claimed_author.lower() != _author(record):
        return None, f"{kind} source {identity} author differs from the public record"
    return record, None


def _valid_floor(marker: MarkerRecord, head: str) -> bool:
    return marker.name == "floor" and marker.attributes == {"head": head, "status": "pass"}


def _actions_run_id(check_run: dict[str, object], repo: str) -> int | None:
    details_url = check_run.get("details_url")
    if not isinstance(details_url, str):
        return None
    match = re.fullmatch(
        rf"https://github\.com/{re.escape(repo)}/actions/runs/(\d+)(?:/job/\d+)?/?",
        details_url,
        re.I,
    )
    return int(match.group(1)) if match else None


def _paginated_objects(value: object, endpoint: str, key: str) -> list[dict[str, object]]:
    pages = value if isinstance(value, list) else [value]
    records: list[dict[str, object]] = []
    expected_total: int | None = None
    for raw_page in pages:
        page = _object(raw_page, endpoint)
        page_records = _records(page.get(key), endpoint)
        total = page.get("total_count")
        if not _is_integer(total) or total < 0:
            raise ProofError(f"GitHub paginated GET omitted a valid total_count for {endpoint}")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ProofError(f"GitHub paginated GET changed total_count for {endpoint}")
        records.extend(page_records)
    if expected_total is None or len(records) != expected_total:
        raise ProofError(
            f"GitHub paginated GET was incomplete for {endpoint}: expected "
            f"{expected_total}, retrieved {len(records)}"
        )
    return records


def _run_references_gate(run: dict[str, object]) -> bool:
    references = run.get("referenced_workflows")
    if not isinstance(references, list):
        return False
    expected = re.compile(
        r"Grimblaz-and-Friends/change-proof/\.github/workflows/change-proof\.yml@[^@\s]+\Z",
        re.I,
    )
    for reference in references:
        if not isinstance(reference, dict):
            continue
        path = reference.get("path") or reference.get("ref")
        if isinstance(path, str) and expected.fullmatch(path):
            return True
    return False


def _run_jobs(transport, repo: str, run_id: int) -> list[dict[str, object]]:
    endpoint = f"repos/{repo}/actions/runs/{run_id}/jobs?filter=all&per_page=100"
    return _paginated_objects(transport.get(endpoint, paginate=True), endpoint, "jobs")


def _job_matches_check(job: dict[str, object], check_id: int) -> bool:
    check_url = job.get("check_run_url")
    return isinstance(check_url, str) and check_url.rstrip("/").endswith(f"/{check_id}")


def _is_proof_job(job: dict[str, object]) -> bool:
    name = job.get("name")
    return isinstance(name, str) and (name == "Change proof" or name.endswith(" / Change proof"))


def _public_floor_checks(
    transport,
    repo: str,
    head: str,
    current_run_id: int | None,
    current_run_attempt: int | None,
) -> tuple[list[dict[str, object]], list[Finding]]:
    endpoint = f"repos/{repo}/commits/{head}/check-runs?filter=all&per_page=100"
    check_runs = _paginated_objects(transport.get(endpoint, paginate=True), endpoint, "check_runs")
    run_cache: dict[int, dict[str, object]] = {}
    jobs_cache: dict[int, list[dict[str, object]]] = {}
    candidates: list[dict[str, object]] = []
    findings: list[Finding] = []
    for check_run in check_runs:
        raw_id = check_run.get("id")
        if not _is_integer(raw_id):
            raise ProofError("GitHub check-run record has no numeric id")
        app = check_run.get("app")
        app_object = app if isinstance(app, dict) else {}
        app_id = app_object.get("id") if _is_integer(app_object.get("id")) else None
        app_slug = app_object.get("slug") if isinstance(app_object.get("slug"), str) else None
        run_id = _actions_run_id(check_run, repo)
        workflow_id: int | None = None
        run: dict[str, object] | None = None
        if run_id is not None:
            if run_id not in run_cache:
                run_endpoint = f"repos/{repo}/actions/runs/{run_id}"
                run_cache[run_id] = _object(transport.get(run_endpoint), run_endpoint)
            run = run_cache[run_id]
            if run.get("id") != run_id:
                raise ProofError(f"Actions run {run_id} returned a contradictory run id")
            run_repository = run.get("repository")
            full_name = run_repository.get("full_name") if isinstance(run_repository, dict) else None
            if isinstance(full_name, str) and full_name.lower() != repo.lower():
                raise ProofError(f"Actions run {run_id} belongs to another repository")
            if run.get("head_sha") != head:
                raise ProofError(f"Actions run {run_id} belongs to another head")
            check_suite = check_run.get("check_suite")
            check_suite_id = check_suite.get("id") if isinstance(check_suite, dict) else None
            run_suite_id = run.get("check_suite_id")
            if (
                _is_integer(check_suite_id)
                and _is_integer(run_suite_id)
                and check_suite_id != run_suite_id
            ):
                raise ProofError(
                    f"check #{raw_id} and Actions run {run_id} name different check suites"
                )
            if _is_integer(run.get("workflow_id")):
                workflow_id = run["workflow_id"]

        exclude = False
        needs_association = run is not None and (
            (current_run_id is not None and run_id == current_run_id)
            or _run_references_gate(run)
        )
        if needs_association and run_id is not None:
            if run_id not in jobs_cache:
                jobs_cache[run_id] = _run_jobs(transport, repo, run_id)
            associated = [job for job in jobs_cache[run_id] if _job_matches_check(job, raw_id)]
            if len(associated) != 1:
                findings.append(Finding(
                    f"an unambiguous job association for proof check #{raw_id} in run {run_id}",
                    "make the Actions run expose one job record linked to that check before re-running",
                ))
                continue
            job_attempt = associated[0].get("run_attempt")
            is_current = (
                current_run_id is not None
                and run_id == current_run_id
                and (current_run_attempt is None or job_attempt == current_run_attempt)
            )
            if _is_proof_job(associated[0]) and (is_current or _run_references_gate(run or {})):
                exclude = True
        if exclude:
            continue

        candidates.append({
            "id": raw_id,
            "name": check_run.get("name"),
            "app_id": app_id,
            "app_slug": app_slug,
            "workflow_id": workflow_id,
            "run_id": run_id,
            "url": (
                run.get("html_url")
                if isinstance(run, dict) and isinstance(run.get("html_url"), str)
                else check_run.get("details_url")
            ),
            "head": check_run.get("head_sha"),
            "status": check_run.get("status"),
            "conclusion": check_run.get("conclusion"),
            "started_at": check_run.get("started_at"),
            "completed_at": check_run.get("completed_at"),
        })

    latest: dict[tuple[object, object, object], dict[str, object]] = {}
    for check in candidates:
        workflow_identity: object = check["workflow_id"]
        if workflow_identity is None and check["run_id"] is not None:
            workflow_identity = ("run", check["run_id"])
        elif workflow_identity is None:
            workflow_identity = ("app", check["app_id"] or "unknown-producer")
        group = (check["app_id"], workflow_identity, check["name"])
        sort_key = (str(check["started_at"] or ""), int(check["id"]))
        previous = latest.get(group)
        previous_key = (
            str(previous["started_at"] or ""), int(previous["id"])
        ) if previous is not None else None
        if previous_key is None or sort_key > previous_key:
            latest[group] = check
    return sorted(latest.values(), key=lambda item: int(item["id"])), findings


def _check_difference(expected: dict[str, object], actual: dict[str, object]) -> str | None:
    for field in (
        "id", "name", "app_id", "app_slug", "workflow_id", "run_id", "url", "head",
        "status", "conclusion", "started_at", "completed_at",
    ):
        if expected[field] != actual[field]:
            return f"{field} is {expected[field]!r}, public record is {actual[field]!r}"
    return None


def _same_intervening_records(expected: object, actual: object) -> bool:
    if not isinstance(expected, list) or not isinstance(actual, list) or len(expected) != len(actual):
        return False
    for supplied, fetched in zip(expected, actual):
        if not isinstance(supplied, dict) or not isinstance(fetched, dict):
            return False
        supplied_paths = supplied.get("paths")
        fetched_paths = fetched.get("paths")
        if (
            supplied.get("sha") != fetched.get("sha")
            or not isinstance(supplied_paths, list)
            or not isinstance(fetched_paths, list)
            or set(supplied_paths) != set(fetched_paths)
        ):
            return False
    return True


def _policy_rendering(
    document: dict[str, object],
    repo: str,
    policy_bytes: dict[tuple[str, str], bytes],
) -> tuple[list[str], list[str], list[str]]:
    verified: list[str] = []
    declared: list[str] = []
    diagnostics: list[str] = []
    policy = document["policy"]
    assert isinstance(policy, dict)
    known_paths = {
        "work_configuration": ".tradecraft/work.json",
        "use_rules": ".github/change-proof.json",
    }
    for name, expected_path in known_paths.items():
        source = policy[name]
        assert isinstance(source, dict)
        prefix = (
            f"policy {name} repository={_safe_text(source['repository'])} "
            f"path={_safe_text(source['path'])} revision={_safe_text(source['revision'])} "
            f"sha256={_safe_text(source['sha256'])}"
        )
        fetched_key = (str(source["path"]), str(source["revision"]))
        if (
            str(source["repository"]).lower() != repo.lower()
            or source["path"] != expected_path
            or fetched_key not in policy_bytes
        ):
            declared.append(prefix + " (not among the gate's fetched policy bytes)")
            continue
        actual_digest = hashlib.sha256(policy_bytes[fetched_key]).hexdigest()
        if source["sha256"] == actual_digest:
            verified.append(prefix)
        else:
            declared.append(prefix + f" fetched_sha256={actual_digest}")
            diagnostics.append(
                f"policy digest mismatch for {name}: producer={_safe_text(source['sha256'])} "
                f"fetched={actual_digest}; provenance remains declared under tradecraft #742"
            )
    return verified, declared, diagnostics


def _declaration_lines(document: dict[str, object]) -> list[str]:
    lines: list[str] = []
    declarations = document["declarations"]
    assert isinstance(declarations, list)
    fields = (
        "stage", "status", "reason", "dispatch_id", "completed_at", "revision",
        "requested_vendor", "requested_model", "requested_effort",
        "requested_classification", "actual_vendor", "actual_model", "actual_effort",
        "fallback_reason", "staffing_status", "same_vendor_reason",
    )
    for declaration in declarations:
        assert isinstance(declaration, dict)
        lines.append(" ".join(f"{field}={_safe_text(declaration[field])}" for field in fields))
    return lines


def evaluate_document(
    document: dict[str, object],
    envelope_head: str,
    comment_id: int,
    head: str,
    number: int,
    paths: list[str],
    rules: dict[str, object],
    config: WorkConfig,
    comments: list[dict[str, object]],
    work_comments: list[dict[str, object]],
    reviews: list[dict[str, object]],
    review_comments: list[dict[str, object]],
    transport,
    repo: str,
    policy_bytes: dict[tuple[str, str], bytes],
    current_run_id: int | None,
    current_run_attempt: int | None,
) -> tuple[list[Finding], list[str], list[str], list[str]]:
    failures: list[Finding] = []
    verified: list[str] = [f"selected proof-v1 comment #{comment_id}"]
    policy_verified, declared, diagnostics = _policy_rendering(document, repo, policy_bytes)
    verified.extend(policy_verified)
    declared.extend(_declaration_lines(document))
    for item in document["diagnostics"]:
        assert isinstance(item, dict)
        diagnostics.append(f"{_safe_text(item['code'])}: {_safe_text(item['message'])}")

    identity = document["identity"]
    assert isinstance(identity, dict)
    expected_work = f"{repo}#{identity['issue']}"
    identity_checks = (
        (envelope_head == head, "the proof envelope head to equal the live pull-request head"),
        (identity["head"] == head, "the proof identity head to equal the live pull-request head"),
        (str(identity["repository"]).lower() == repo.lower(), "the proof repository to equal the evaluated repository"),
        (identity["pull_request"] == number, "the proof pull-request number to equal the evaluated pull request"),
        (str(identity["work"]).lower() == expected_work.lower(), "the proof work identity to equal repository#issue"),
    )
    for passes, message in identity_checks:
        if not passes:
            failures.append(Finding(message, "recompose and post proof for the live pull-request identity"))
    if not failures:
        verified.append(f"proof identity matches {repo} pull request #{number} at {head}")

    floor = document["floor"]
    assert isinstance(floor, dict)
    if floor["head"] != head:
        failures.append(Finding(
            "a current-head floor record in the selected proof document",
            "run the floor at the current head and recompose proof",
        ))
    source = floor["source"]
    floor_source_verified = False
    if not isinstance(source, dict):
        failures.append(Finding(
            "an authorized public floor source",
            "post the successful current-head floor marker and recompose proof",
        ))
    else:
        record, source_error = _resolve_source(
            source, repo, comments, work_comments, reviews, review_comments
        )
        floor_markers = markers([record]) if record is not None else []
        if (
            source_error is not None
            or record is None
            or _author(record) not in config.marker_producers
            or not any(_valid_floor(marker, head) for marker in floor_markers)
        ):
            detail = source_error or "the source is unauthorized or lacks the exact current-head floor marker"
            failures.append(Finding(
                f"an authorized valid floor source: {detail}",
                "post the exact successful floor marker on its lawful source surface and recompose proof",
            ))
        else:
            floor_source_verified = True
            verified.append(f"floor source {_safe_text(source['kind'])} #{_safe_text(source['id'])} is authorized and current-head")

    actual_checks, check_findings = _public_floor_checks(
        transport, repo, head, current_run_id, current_run_attempt
    )
    failures.extend(check_findings)
    supplied_checks = floor["checks"]
    assert isinstance(supplied_checks, list)
    actual_by_id = {check["id"]: check for check in actual_checks}
    supplied_ids: list[object] = []
    for supplied in supplied_checks:
        assert isinstance(supplied, dict)
        supplied_ids.append(supplied["id"])
        actual = actual_by_id.get(supplied["id"])
        if actual is None:
            failures.append(Finding(
                f"public floor check #{supplied['id']} named by the proof document",
                "recompose proof from the visible current-head check runs",
            ))
            continue
        difference = _check_difference(supplied, actual)
        if difference is not None:
            failures.append(Finding(
                f"floor check #{supplied['id']} to match its public record: {difference}",
                "recompose proof from the visible current-head check and workflow records",
            ))
    omitted = sorted(set(actual_by_id) - set(supplied_ids))
    if omitted:
        failures.append(Finding(
            f"the complete public floor set; omitted check id(s): {', '.join(map(str, omitted))}",
            "recompose proof after collecting every current-head floor check",
        ))
    for check in actual_checks:
        conclusion = check["conclusion"]
        if (
            check["status"] != "completed"
            or not isinstance(conclusion, str)
            or conclusion not in {"success", "neutral", "skipped"}
        ):
            failures.append(Finding(
                f"a completed acceptable result for floor check #{check['id']}: "
                f"status={check['status']!r}, conclusion={check['conclusion']!r}",
                "complete or repair the named floor check and recompose proof",
            ))
        else:
            verified.append(
                f"floor check #{check['id']} {_safe_text(check['name'])} completed with "
                f"conclusion {_safe_text(check['conclusion'])}"
            )
    if floor_source_verified and not actual_checks and not check_findings:
        verified.append("no public floor checks are visible; the authorized floor attestation remains public")

    use = document["use"]
    assert isinstance(use, dict)
    bought = use_required(paths, rules)
    if bought:
        if use["required"] is not True or use["classification"] != "required":
            failures.append(Finding(
                "a proof use classification matching trusted policy: required",
                "recompose proof under the base-tip use rules",
            ))
        use_source = use["source"]
        evidence_head = use["evidence_head"]
        if not isinstance(use_source, dict) or not isinstance(evidence_head, str):
            failures.append(Finding(
                "a public use source and evidence head for use-bought paths",
                "complete the use session and recompose proof",
            ))
        else:
            record, source_error = _resolve_source(
                use_source, repo, comments, work_comments, reviews, review_comments
            )
            source_markers = markers([record]) if record is not None else []
            valid_source = (
                source_error is None
                and record is not None
                and _author(record) in config.marker_producers
                and any(_valid_use(marker, evidence_head) for marker in source_markers)
            )
            if not valid_source:
                failures.append(Finding(
                    f"an authorized valid public use source: {source_error or 'marker is invalid or unauthorized'}",
                    "post a lawful use marker on its claimed surface and recompose proof",
                ))
            elif evidence_head == head:
                if use["applicability"] != "current-head" or use["intervening_commits"]:
                    failures.append(Finding(
                        "current-head use evidence with no intervening history",
                        "recompose proof from the current-head use record",
                    ))
                else:
                    verified.append("trusted policy requires use and the public use source is current-head")
            else:
                try:
                    application = _ancestor_application(
                        transport, repo, evidence_head, head, rules
                    )
                except (OSError, UnicodeError, ValueError, ProofError) as exc:
                    application = {
                        "applicable": False,
                        "reason": (
                            f"history from {evidence_head} could not be read: "
                            f"{str(exc) or type(exc).__name__}"
                        ),
                    }
                expected_records = application.get("intervening_records", [])
                if (
                    use["applicability"] != "ancestor"
                    or not application.get("applicable")
                    or not _same_intervening_records(
                        use["intervening_commits"], expected_records
                    )
                ):
                    failures.append(Finding(
                        f"applicable complete ancestor-use history: {application.get('reason')}",
                        "post current-head use evidence or recompose proof with the complete use-free history",
                    ))
                else:
                    verified.append(
                        f"trusted policy requires use and ancestor evidence at {evidence_head} "
                        "remains applicable"
                    )
    else:
        valid_generated = (
            use["required"] is False
            and use["classification"] == "not-required"
            and use["evidence_head"] == head
            and use["applicability"] == "generated"
            and use["source"] is None
            and use["intervening_commits"] == []
            and isinstance(use["reason"], str)
            and bool(use["reason"])
        )
        if not valid_generated:
            failures.append(Finding(
                "a current-head generated no-use record matching trusted policy",
                "recompose proof under the base-tip use rules with a nonempty generated reason",
            ))
        else:
            verified.append("trusted policy classifies the changed paths as no-use and generated evidence is current-head")

    reviewer_entries = document["reviewers"]
    assert isinstance(reviewer_entries, list)
    reviewer_logins = [str(item["login"]).lower() for item in reviewer_entries if isinstance(item, dict)]
    duplicates = sorted({login for login in reviewer_logins if reviewer_logins.count(login) > 1})
    missing_reviewers = sorted(set(config.connected_reviewers) - set(reviewer_logins))
    extra_reviewers = sorted(set(reviewer_logins) - set(config.connected_reviewers))
    if duplicates or missing_reviewers or extra_reviewers:
        details = []
        if missing_reviewers:
            details.append(f"missing: {', '.join(missing_reviewers)}")
        if duplicates:
            details.append(f"duplicated: {', '.join(duplicates)}")
        if extra_reviewers:
            details.append(f"extra: {', '.join(extra_reviewers)}")
        failures.append(Finding(
            "exactly one proof entry for every trusted configured reviewer; "
            + "; ".join(details),
            "recompose proof from the base-tip reviewer configuration and complete public receipts",
        ))
    for entry in reviewer_entries:
        assert isinstance(entry, dict)
        login = str(entry["login"]).lower()
        source = entry["source"]
        if login not in config.connected_reviewers:
            continue
        if entry["result"] != "present" or not isinstance(source, dict):
            failures.append(Finding(
                f"a completed public review receipt for {login}",
                f"have {login} complete its review and recompose proof",
            ))
            continue
        record, source_error = _resolve_source(
            source, repo, comments, work_comments, reviews, review_comments
        )
        source_kind = str(source.get("kind") or "").lower()
        notice = (
            _review_notice(str(record.get("body") or ""))
            if record is not None and source_kind in {"review", "pull-request-comment"}
            else None
        )
        if source_error is not None or record is None or _author(record) != login or notice is not None:
            failures.append(Finding(
                f"a valid completed public review receipt for {login}: "
                f"{source_error or notice or 'source author differs'}",
                f"have {login} post a completed review receipt and recompose proof",
            ))
        else:
            verified.append(f"connected reviewer {login} credited by {_safe_text(source['kind'])} #{_safe_text(source['id'])}")
    if not config.connected_reviewers:
        verified.append("the caller configures no connected reviewers")

    replies: dict[int, list[dict[str, object]]] = {}
    owed: dict[int, dict[str, object]] = {}
    for record in review_comments:
        parent = record.get("in_reply_to_id")
        identity_value = record.get("id")
        if _is_integer(parent):
            replies.setdefault(parent, []).append(record)
        elif _is_integer(identity_value) and _author(record) in config.connected_reviewers:
            owed[identity_value] = record
    disposition_entries = document["dispositions"]
    assert isinstance(disposition_entries, list)
    by_thread: dict[int, list[dict[str, object]]] = {}
    for entry in disposition_entries:
        assert isinstance(entry, dict)
        by_thread.setdefault(int(entry["thread_id"]), []).append(entry)
    missing_threads = sorted(set(owed) - set(by_thread))
    extra_threads = sorted(set(by_thread) - set(owed))
    duplicate_threads = sorted(
        thread_id for thread_id, entries in by_thread.items() if len(entries) != 1
    )
    if missing_threads or extra_threads or duplicate_threads:
        details = []
        if missing_threads:
            details.append(f"missing: {', '.join(map(str, missing_threads))}")
        if duplicate_threads:
            details.append(f"duplicated: {', '.join(map(str, duplicate_threads))}")
        if extra_threads:
            details.append(f"extra: {', '.join(map(str, extra_threads))}")
        failures.append(Finding(
            "exactly one proof disposition entry for every visible top-level reviewer thread; "
            + "; ".join(details),
            "reply to every owed thread and recompose proof from the complete review-comment record",
        ))
    for thread_id, thread in owed.items():
        entries = by_thread.get(thread_id, [])
        if len(entries) != 1:
            continue
        entry = entries[0]
        source = entry["source"]
        reply_source = entry["reply"]
        source_record, source_error = _resolve_source(
            source, repo, comments, work_comments, reviews, review_comments
        )
        reply_record = None
        reply_error = "reply is missing"
        if isinstance(reply_source, dict):
            reply_record, reply_error = _resolve_source(
                reply_source, repo, comments, work_comments, reviews, review_comments
            )
        valid_reply = (
            source_error is None
            and source_record is thread
            and str(entry["reviewer"]).lower() == _author(thread)
            and reply_error is None
            and reply_record in replies.get(thread_id, [])
            and reply_record is not None
            and _author(reply_record) in config.marker_producers
            and _disposition(str(reply_record.get("body") or ""))
        )
        if not valid_reply:
            failures.append(Finding(
                f"an authorized disposition reply in reviewer thread {thread_id}",
                "reply in that thread with a closed disposition and recompose proof",
            ))
        else:
            verified.append(f"reviewer thread {thread_id} has an authorized disposition")
    if not owed:
        verified.append("every top-level inline reviewer comment has a marker-producer disposition")
    return failures, verified, declared, diagnostics


def evaluate(
    head: str,
    paths: list[str],
    rules: dict[str, object],
    config: WorkConfig,
    comments: list[dict[str, object]],
    reviews: list[dict[str, object]],
    review_comments: list[dict[str, object]],
    transport=None,
    repo: str = "",
) -> tuple[list[Finding], list[str]]:
    failures: list[Finding] = []
    verified: list[str] = []
    evidence = comments + reviews + review_comments
    authorized = [item for item in markers(evidence) if item.author in config.marker_producers]
    bought = use_required(paths, rules)
    current_use = [
        marker
        for marker in authorized
        if marker.name == "use" and marker.attributes.get("head") == head
    ]
    if bought:
        if any(_valid_use(marker, head) for marker in current_use):
            verified.append("changed paths buy a use and an authorized current-head use marker is valid")
        else:
            ancestor_marker: MarkerRecord | None = None
            intervening: list[str] = []
            rejected_reason: str | None = None
            if transport is not None and repo:
                ancestor_marker, intervening, rejected_reason = _ancestor_use(
                    transport, repo, head, rules, authorized
                )
            if ancestor_marker is not None:
                evidence_head = ancestor_marker.attributes["head"]
                revisions = ", ".join(intervening) if intervening else "none"
                verified.append(
                    "changed paths buy a use and authorized use marker at "
                    f"{evidence_head} remains valid after intervening commits: {revisions}"
                )
            else:
                missing = "an authorized, valid use marker for the current head"
                if rejected_reason is not None:
                    missing = f"{missing}; latest earlier-head candidate failed: {rejected_reason}"
                failures.append(Finding(
                    missing,
                    "post the completed use note with the exact tradecraft:use:v1 form at this head",
                ))
    else:
        if current_use:
            failures.append(Finding(
                "a truthful path classification because the current-head use marker is a false claim",
                "remove the false used claim and post an authorized tradecraft:no-use:v1 note",
            ))
        current_no_use = [
            marker
            for marker in authorized
            if marker.name == "no-use" and marker.attributes.get("head") == head
        ]
        if any(_valid_no_use(marker, head) for marker in current_no_use):
            verified.append(
                "changed paths do not buy a use and an authorized current-head no-use note has its line"
            )
        else:
            failures.append(Finding(
                "an authorized no-use marker and its 'Use: not required' line for the current head",
                "post the exact tradecraft:no-use:v1 marker followed by that line and the reason",
            ))

    missing_reviewers: list[str] = []
    for reviewer in sorted(config.connected_reviewers):
        credit: str | None = None
        notices: list[str] = []
        for kind, records in (("review", reviews), ("inline review comment", review_comments)):
            for item in records:
                if _author(item) != reviewer:
                    continue
                credit = _record_label(kind, item)
                break
            if credit is not None:
                break
        if credit is None:
            for item in comments:
                if _author(item) != reviewer:
                    continue
                notice = _review_notice(str(item.get("body") or ""))
                if notice is None:
                    credit = _record_label("pull-request comment", item)
                    break
                notices.append(notice)
        if credit is not None:
            verified.append(f"connected reviewer {reviewer} credited by {credit}")
        elif notices:
            named = ", ".join(f"{notice!r}" for notice in dict.fromkeys(notices))
            failures.append(Finding(
                f"connected reviewer run for {reviewer}; public notice(s) "
                f"{named} do not count, so a review is still owed",
                f"have {reviewer} post a completed review, inline review comment, or "
                "pull-request comment that is not a notice of not reviewing",
            ))
        else:
            missing_reviewers.append(reviewer)
    if missing_reviewers:
        failures.append(Finding(
            f"connected reviewer run(s): {', '.join(missing_reviewers)}",
            "have each listed reviewer post a review, inline review comment, or pull-request comment",
        ))
    if not config.connected_reviewers:
        verified.append("the caller configures no connected reviewers")

    replies: dict[int, list[dict[str, object]]] = {}
    for item in review_comments:
        parent = item.get("in_reply_to_id")
        if isinstance(parent, int):
            replies.setdefault(parent, []).append(item)
    undisposed: list[int] = []
    for item in review_comments:
        identity = item.get("id")
        if (
            not isinstance(identity, int)
            or item.get("in_reply_to_id") is not None
            or _author(item) not in config.connected_reviewers
        ):
            continue
        if not any(
            _author(reply) in config.marker_producers
            and _disposition(str(reply.get("body") or ""))
            for reply in replies.get(identity, [])
        ):
            undisposed.append(identity)
    if undisposed:
        failures.append(Finding(
            f"marker-producer disposition replies on top-level inline comment(s): "
            f"{', '.join(str(identity) for identity in undisposed)}",
            "reply in each thread with a closed disposition word at the start of the first line",
        ))
    else:
        verified.append("every top-level inline reviewer comment has a marker-producer disposition")
    return failures, verified


def _environment(
    environ: Mapping[str, str],
) -> tuple[str, str, int, str | None, str, int | None, int | None]:
    token = environ.get("GITHUB_TOKEN", "").strip()
    repo = environ.get("GITHUB_REPOSITORY", "").strip()
    number = environ.get("PULL_REQUEST_NUMBER", "").strip()
    head = environ.get("PULL_REQUEST_HEAD_SHA", "").strip() or None
    api_url = environ.get("GITHUB_API_URL", "https://api.github.com").strip()
    raw_run_id = environ.get("GITHUB_RUN_ID", "").strip()
    raw_run_attempt = environ.get("GITHUB_RUN_ATTEMPT", "").strip()
    if not token:
        raise ProofError("GITHUB_TOKEN is missing")
    if REPOSITORY_NAME.fullmatch(repo) is None:
        raise ProofError("GITHUB_REPOSITORY must be an owner/repository string")
    if not number.isdigit() or int(number) <= 0:
        raise ProofError("PULL_REQUEST_NUMBER must be a positive integer")
    if not api_url.startswith("https://"):
        raise ProofError("GITHUB_API_URL must use HTTPS")
    for name, value in (("GITHUB_RUN_ID", raw_run_id), ("GITHUB_RUN_ATTEMPT", raw_run_attempt)):
        if value and (not value.isdigit() or int(value) <= 0):
            raise ProofError(f"{name} must be a positive integer when supplied")
    return (
        token,
        repo,
        int(number),
        head,
        api_url,
        int(raw_run_id) if raw_run_id else None,
        int(raw_run_attempt) if raw_run_attempt else None,
    )


def run(
    environ: Mapping[str, str] | None = None,
    *,
    transport=None,
    output: TextIO | None = None,
) -> int:
    destination = output or sys.stdout
    try:
        (
            token, repo, number, event_head, api_url, current_run_id, current_run_attempt
        ) = _environment(environ or os.environ)
        github = transport or GitHubTransport(token, api_url)
        pull_endpoint = f"repos/{repo}/pulls/{number}"
        pull = _object(github.get(pull_endpoint), pull_endpoint)
        if bool(pull.get("draft")):
            print(
                f"change-proof: SKIP: pull request #{number} is draft; evidence is not evaluated",
                file=destination,
            )
            print(
                f"satisfy: mark pull request #{number} ready and re-run change-proof",
                file=destination,
            )
            return 1
        body_failures: list[Finding] = []
        body_verified: list[str] = []
        if _has_path_departures_paragraph(pull.get("body")):
            body_verified.append("pull request body has a **Path departures:** paragraph")
        else:
            body_failures.append(Finding(
                "a pull request body paragraph beginning with **Path departures:**",
                "add the **Path departures:** paragraph to the pull request body and re-run "
                "change-proof",
            ))
        head_object = pull.get("head")
        base_object = pull.get("base")
        resolved_head = head_object.get("sha") if isinstance(head_object, dict) else None
        base_ref = base_object.get("ref") if isinstance(base_object, dict) else None
        if not isinstance(resolved_head, str) or FULL_SHA.fullmatch(resolved_head) is None:
            raise ProofError("the pull request GET response has no full head SHA")
        head = resolved_head
        head_identity_failures: list[Finding] = []
        if event_head is not None and event_head != head:
            head_identity_failures.append(Finding(
                f"the event head {event_head} to equal the live pull-request head {head}",
                "start a current-head workflow run and re-run change-proof",
            ))
        if not isinstance(base_ref, str) or not base_ref:
            raise ProofError("the pull request base branch ref is missing from the GET response")
        quoted_base_ref = urllib.parse.quote(base_ref, safe="")
        base_ref_endpoint = f"repos/{repo}/git/ref/heads/{quoted_base_ref}"
        try:
            base_reference = _object(github.get(base_ref_endpoint), base_ref_endpoint)
        except GitHubNotFound as exc:
            raise ProofError(
                f"the pull request base branch reference refs/heads/{base_ref} does not exist"
            ) from exc
        base_tip_object = _object(
            base_reference.get("object"), f"{base_ref_endpoint} object"
        )
        base_tip = base_tip_object.get("sha")
        if not isinstance(base_tip, str) or not base_tip:
            raise ProofError(
                "the base branch reference object SHA is missing from the GET response"
            )

        policy_paths = (".github/change-proof.json", ".tradecraft/work.json")
        head_policy_records = {
            path: _optional_json_file_record(github, repo, path, head) for path in policy_paths
        }
        base_policy_records = {
            path: _optional_json_file_record(github, repo, path, base_tip) for path in policy_paths
        }
        head_policy = {
            path: record[0] if record is not None else None
            for path, record in head_policy_records.items()
        }
        base_policy = {
            path: record[0] if record is not None else None
            for path, record in base_policy_records.items()
        }
        absent_on_head = [path for path in policy_paths if head_policy[path] is None]
        absent_on_base = [path for path in policy_paths if base_policy[path] is None]
        preflight_failures = [*head_identity_failures, *body_failures]
        preflight_verified = [
            f"base branch {base_ref} tip resolved to commit {base_tip}",
            *body_verified,
        ]
        selected_policy: dict[str, dict[str, object] | None] | None
        if absent_on_base:
            preflight_failures.append(Finding(
                f"trusted policy on the pull request base branch tip; "
                f"absent: {', '.join(absent_on_base)}",
                "this pull request cannot prove itself; the owner merges it on the connected "
                "reviewers' evidence",
            ))
            selected_policy = None if absent_on_head else head_policy
        else:
            selected_policy = base_policy
            if any(head_policy[path] != base_policy[path] for path in policy_paths):
                preflight_verified.append(
                    "pull request changes policy and was judged by the base branch tip policy",
                )

        failures = preflight_failures
        verified = preflight_verified
        declared: list[str] = []
        diagnostics: list[str] = []
        evidence_path: str | None = None
        if selected_policy is not None:
            rules = load_use_rules(selected_policy[".github/change-proof.json"])
            config = load_work_config(selected_policy[".tradecraft/work.json"])
            files_endpoint = f"{pull_endpoint}/files?per_page=100"
            files = _records(github.get(files_endpoint, paginate=True), files_endpoint)
            changed_files = pull.get("changed_files")
            if (
                not isinstance(changed_files, int)
                or isinstance(changed_files, bool)
                or changed_files < 0
            ):
                raise ProofError("the pull request changed_files count is missing or invalid")
            if len(files) != changed_files:
                failures.append(Finding(
                    f"complete changed-file list: pull reports {changed_files}, retrieved "
                    f"{len(files)}; the change cannot be classified",
                    "make the GitHub pull-request files response contain every changed file "
                    "before evaluating use evidence",
                ))
            else:
                paths = [
                    str(item[field])
                    for item in files
                    for field in ("filename", "previous_filename")
                    if isinstance(item.get(field), str)
                ]
                comments_endpoint = f"repos/{repo}/issues/{number}/comments?per_page=100"
                reviews_endpoint = f"{pull_endpoint}/reviews?per_page=100"
                review_comments_endpoint = f"{pull_endpoint}/comments?per_page=100"
                comments = _records(github.get(comments_endpoint, paginate=True), comments_endpoint)
                reviews = _records(github.get(reviews_endpoint, paginate=True), reviews_endpoint)
                review_comments = _records(
                    github.get(review_comments_endpoint, paginate=True), review_comments_endpoint
                )
                candidates = _proof_candidates(comments, config.marker_producers)
                authorized = [
                    candidate for candidate in candidates
                    if candidate.author in config.marker_producers
                ]
                unscoped = [candidate for candidate in authorized if candidate.envelope_head is None]
                current = [candidate for candidate in authorized if candidate.envelope_head == head]
                unauthorized_current = [
                    candidate for candidate in candidates
                    if candidate.author not in config.marker_producers
                    and candidate.envelope_head == head
                ]
                for candidate in unauthorized_current:
                    diagnostics.append(
                        f"proof comment #{candidate.comment_id} is unauthorized and supplies no declarations"
                    )
                for candidate in authorized:
                    if (
                        candidate.envelope_head not in {None, head}
                        and candidate.error is not None
                    ):
                        diagnostics.append(
                            f"older proof comment #{candidate.comment_id} is invalid: {_safe_text(candidate.error)}"
                        )
                if unscoped or current:
                    evidence_path = "proof-v1"
                    if unscoped:
                        for candidate in unscoped:
                            failures.append(Finding(
                                f"a safely scoped authorized proof envelope in comment #{candidate.comment_id}: "
                                f"{candidate.error}",
                                "replace it with one exact proof-v1 envelope naming the current full head",
                            ))
                    if len(current) > 1:
                        failures.append(Finding(
                            "one authorized current-head proof document; competing comments: "
                            + ", ".join(f"#{candidate.comment_id}" for candidate in current),
                            "leave one authorized proof document for this head and re-run change-proof",
                        ))
                    elif len(current) == 1:
                        candidate = current[0]
                        if candidate.error is not None or candidate.document is None:
                            failures.append(Finding(
                                f"a valid selected proof-v1 document in comment #{candidate.comment_id}: "
                                f"{candidate.error or 'document is missing'}",
                                "recompose the proof document from the record and post it at this head",
                            ))
                        elif not unscoped:
                            identity = candidate.document["identity"]
                            assert isinstance(identity, dict)
                            work_issue = identity["issue"]
                            work_comments = comments
                            work_comments_error: str | None = None
                            if work_issue != number:
                                work_comments_endpoint = (
                                    f"repos/{repo}/issues/{work_issue}/comments?per_page=100"
                                )
                                try:
                                    work_comments = _records(
                                        github.get(work_comments_endpoint, paginate=True),
                                        work_comments_endpoint,
                                    )
                                except (OSError, UnicodeError, ValueError, ProofError) as exc:
                                    work_comments = []
                                    work_comments_error = str(exc) or type(exc).__name__
                            policy_bytes: dict[tuple[str, str], bytes] = {}
                            for revision, records in (
                                (head, head_policy_records),
                                (base_tip, base_policy_records),
                            ):
                                for path, record in records.items():
                                    if record is not None:
                                        policy_bytes[(path, revision)] = record[1]
                            document_failures, document_verified, document_declared, document_diagnostics = evaluate_document(
                                candidate.document,
                                candidate.envelope_head or "",
                                candidate.comment_id,
                                head,
                                number,
                                paths,
                                rules,
                                config,
                                comments,
                                work_comments,
                                reviews,
                                review_comments,
                                github,
                                repo,
                                policy_bytes,
                                current_run_id,
                                current_run_attempt,
                            )
                            if work_comments_error is not None:
                                document_failures.insert(0, Finding(
                                    f"readable work-issue comments for issue {work_issue}: "
                                    f"{work_comments_error}",
                                    "correct the named issue or its recorded source identity, then "
                                    "recompose proof",
                                ))
                            failures.extend(document_failures)
                            verified.extend(document_verified)
                            declared.extend(document_declared)
                            diagnostics.extend(document_diagnostics)
                else:
                    evidence_path = "legacy-markers"
                    evidence_failures, evidence_verified = evaluate(
                        head,
                        paths,
                        rules,
                        config,
                        comments,
                        reviews,
                        review_comments,
                        github,
                        repo,
                    )
                    failures.extend(evidence_failures)
                    verified.extend(evidence_verified)

        if not failures:
            refreshed_pull = _object(github.get(pull_endpoint), pull_endpoint)
            refreshed_head = refreshed_pull.get("head")
            refreshed_sha = refreshed_head.get("sha") if isinstance(refreshed_head, dict) else None
            if refreshed_sha != head:
                failures.append(Finding(
                    f"the pull-request head to remain {head} through evaluation; now {refreshed_sha}",
                    "run change-proof again on the new head",
                ))
        if failures:
            print("change-proof: FAIL", file=destination)
            if evidence_path is not None:
                print(f"evidence path: {evidence_path}", file=destination)
            for statement in verified:
                print(f"verified: {statement}", file=destination)
            for statement in declared:
                print(f"declared: {statement}", file=destination)
            for statement in diagnostics:
                print(f"diagnostic: {statement}", file=destination)
            for finding in failures:
                print(f"missing: {_safe_text(finding.missing)}", file=destination)
                print(f"satisfy: {_safe_text(finding.satisfy)}", file=destination)
            return 1
        print("change-proof: PASS", file=destination)
        if evidence_path is not None:
            print(f"evidence path: {evidence_path}", file=destination)
        for statement in verified:
            print(f"verified: {statement}", file=destination)
        for statement in declared:
            print(f"declared: {statement}", file=destination)
        for statement in diagnostics:
            print(f"diagnostic: {statement}", file=destination)
        return 0
    except (OSError, UnicodeError, ValueError, ProofError) as exc:
        print("change-proof: ERROR", file=destination)
        print(f"missing: a complete readable proof input: {_safe_text(exc)}", file=destination)
        print("satisfy: correct the named GitHub data or retry the incomplete read", file=destination)
        return 1


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")


def main() -> int:
    _utf8_stdio()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
