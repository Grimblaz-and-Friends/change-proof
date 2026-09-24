#!/usr/bin/env python3
"""Verify change-proof evidence for one GitHub pull request."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import fnmatch
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
    ("Running", re.compile(r"^\|[^\n]*\brunning\b[^\n]*\|\s*$", re.I | re.M)),
)


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


def _json_file(transport, repo: str, path: str, head: str) -> dict[str, object]:
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
    return _object(value, path)


def _optional_json_file(transport, repo: str, path: str, revision: str) -> dict[str, object] | None:
    try:
        return _json_file(transport, repo, path, revision)
    except GitHubNotFound:
        return None


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
    if comparison.get("status") not in {"ahead", "identical"} or merge_base_sha != ancestor:
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
    for commit in commits:
        revision = commit.get("sha")
        if not isinstance(revision, str) or FULL_SHA.fullmatch(revision) is None:
            return {
                "applicable": False,
                "reason": f"intervening commit from {ancestor} has no full revision",
            }
        paths = _commit_files(transport, repo, revision)
        intervening.append(revision)
        if use_required(paths, rules):
            return {
                "applicable": False,
                "reason": (
                    f"use evidence at {ancestor} is stale because intervening commit "
                    f"{revision} changes a use-bought path"
                ),
                "intervening_commits": intervening,
            }
    return {
        "applicable": True,
        "reason": "every intervening commit changes only paths outside the use-bought policy",
        "intervening_commits": intervening,
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
    return marker.attributes == {"head": head} and has_line


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
            credited = next((item for item in records if _author(item) == reviewer), None)
            if credited is not None:
                credit = _record_label(kind, credited)
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
                f"connected reviewer run for {reviewer}; pull-request comment notice(s) "
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


def _environment(environ: Mapping[str, str]) -> tuple[str, str, int, str | None, str]:
    token = environ.get("GITHUB_TOKEN", "").strip()
    repo = environ.get("GITHUB_REPOSITORY", "").strip()
    number = environ.get("PULL_REQUEST_NUMBER", "").strip()
    head = environ.get("PULL_REQUEST_HEAD_SHA", "").strip() or None
    api_url = environ.get("GITHUB_API_URL", "https://api.github.com").strip()
    if not token:
        raise ProofError("GITHUB_TOKEN is missing")
    if REPOSITORY_NAME.fullmatch(repo) is None:
        raise ProofError("GITHUB_REPOSITORY must be an owner/repository string")
    if not number.isdigit() or int(number) <= 0:
        raise ProofError("PULL_REQUEST_NUMBER must be a positive integer")
    if not api_url.startswith("https://"):
        raise ProofError("GITHUB_API_URL must use HTTPS")
    return token, repo, int(number), head, api_url


def run(
    environ: Mapping[str, str] | None = None,
    *,
    transport=None,
    output: TextIO | None = None,
) -> int:
    destination = output or sys.stdout
    try:
        token, repo, number, event_head, api_url = _environment(environ or os.environ)
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
        head_object = pull.get("head")
        base_object = pull.get("base")
        resolved_head = head_object.get("sha") if isinstance(head_object, dict) else None
        base_ref = base_object.get("ref") if isinstance(base_object, dict) else None
        head = event_head or (resolved_head if isinstance(resolved_head, str) else None)
        if not head:
            raise ProofError("the pull request head SHA is missing from both the event and GET response")
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
        head_policy = {
            path: _optional_json_file(github, repo, path, head) for path in policy_paths
        }
        base_policy = {
            path: _optional_json_file(github, repo, path, base_tip) for path in policy_paths
        }
        absent_on_head = [path for path in policy_paths if head_policy[path] is None]
        absent_on_base = [path for path in policy_paths if base_policy[path] is None]
        preflight_failures: list[Finding] = []
        preflight_verified = [
            f"base branch {base_ref} tip resolved to commit {base_tip}",
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
        if failures:
            print("change-proof: FAIL", file=destination)
            for statement in verified:
                print(f"verified: {statement}", file=destination)
            for finding in failures:
                print(f"missing: {finding.missing}", file=destination)
                print(f"satisfy: {finding.satisfy}", file=destination)
            return 1
        print("change-proof: PASS", file=destination)
        for statement in verified:
            print(f"verified: {statement}", file=destination)
        return 0
    except (OSError, UnicodeError, ValueError, ProofError) as exc:
        print("change-proof: ERROR", file=destination)
        print(f"missing: a complete readable proof input: {exc}", file=destination)
        print("satisfy: correct the named input or grant the three documented read permissions", file=destination)
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
