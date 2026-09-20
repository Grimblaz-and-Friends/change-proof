from __future__ import annotations

import fnmatch
import json
from pathlib import Path

import pytest

from proof import check


ROOT = Path(__file__).resolve().parents[1]


def normalized_bytes(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def embedded_script():
    workflow = normalized_bytes(ROOT / ".github" / "workflows" / "change-proof.yml")
    marker = b"      run: |\n"
    prefix, separator, remainder = workflow.partition(marker)
    assert separator and prefix
    script = remainder
    lines = script.splitlines(keepends=True)
    assert all(line == b"\n" or line.startswith(b"          ") for line in lines)
    return b"".join(b"\n" if line == b"\n" else line[10:] for line in lines)


def test_workflow_embeds_checker_verbatim_after_line_ending_normalization():
    assert embedded_script() == normalized_bytes(ROOT / "proof" / "check.py")


def practice_use_required(paths, rules):
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


def test_use_rule_matching_agrees_with_practice_on_fixture_paths():
    fixture = {
        "schema_version": 1,
        "rules": [
            {
                "name": "runtime-or-user-surface",
                "include": ["src/**", "public/**", "package.json"],
                "exclude": ["**/tests/**", "**/*.test.ts"],
            }
        ],
    }
    path_sets = [
        ["src/main.ts"],
        ["src/deep/view.ts", "docs/readme.md"],
        ["src/unit.test.ts"],
        ["src\\windows\\path.ts"],
        ["public/icon.svg"],
        ["docs/readme.md", ".github/workflows/ci.yml"],
    ]

    assert [check.use_required(paths, fixture) for paths in path_sets] == [
        practice_use_required(paths, fixture) for paths in path_sets
    ]


def test_workflow_parses_as_yaml_when_pyyaml_is_available():
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")

    value = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "change-proof.yml").read_text(encoding="utf-8")
    )

    assert value["on"] == {"workflow_call": None}
    assert "permissions" not in value
    assert list(value["jobs"]) == ["proof"]
    proof = value["jobs"]["proof"]
    assert proof["if"] == "github.event_name == 'pull_request'"
    assert proof["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
    }

    proof_steps = proof["steps"]
    assert sum("run" in step for step in proof_steps) == 1
    assert not any(
        "actions/checkout@" in step.get("uses", "")
        for step in proof_steps
    )
    assert proof_steps[0]["uses"] == (
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
    )
    assert proof_steps[-1]["run"].encode() == embedded_script()
