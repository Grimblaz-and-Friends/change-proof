from __future__ import annotations

import fnmatch
import json
import re
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


def test_self_policy_files_load_and_classify_repository_paths():
    work_value = json.loads(
        (ROOT / ".tradecraft" / "work.json").read_text(encoding="utf-8")
    )
    rules_value = json.loads(
        (ROOT / ".github" / "change-proof.json").read_text(encoding="utf-8")
    )

    work = check.load_work_config(work_value)
    rules = check.load_use_rules(rules_value)

    assert work_value["product_repositories"] == []
    assert work.connected_reviewers == frozenset(
        {
            "greptile-apps[bot]",
            "coderabbitai[bot]",
            "chatgpt-codex-connector[bot]",
        }
    )
    assert work.marker_producers == frozenset({"grimblaz"})

    expected = {
        "proof/check.py": True,
        ".github/workflows/change-proof.yml": True,
        ".github/workflows/self-change-proof.yml": True,
        "README.md": False,
        "tests/test_check.py": False,
        "tests/test_workflow.py": False,
        ".github/change-proof.json": False,
        ".tradecraft/work.json": False,
        ".github/workflows/ci.yml": False,
    }

    for path, required in expected.items():
        assert check.use_required([path], rules) is required


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


def test_self_caller_parses_and_targets_main():
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")

    value = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "self-change-proof.yml").read_text(
            encoding="utf-8"
        )
    )

    assert value["name"] == "Change proof (required)"
    assert value["on"] == {
        "pull_request": {
            "types": ["opened", "reopened", "synchronize", "ready_for_review"]
        }
    }
    assert list(value["jobs"]) == ["change-proof"]
    job = value["jobs"]["change-proof"]
    assert job["name"] == "Change proof (required)"
    assert job["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
    }
    assert job["uses"] == (
        "Grimblaz-and-Friends/change-proof/.github/workflows/change-proof.yml@main"
    )
    assert "steps" not in job


def test_readme_caller_example_names_its_job_and_reports_the_documented_context():
    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sections = re.findall(
        r"^## Call the workflow\n(.*?)(?=^## |\Z)",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert len(sections) == 1
    blocks = re.findall(
        r"^```yaml\n(.*?)^```$",
        sections[0],
        flags=re.MULTILINE | re.DOTALL,
    )

    assert len(blocks) == 1
    example = yaml.safe_load(blocks[0])

    jobs = example["jobs"]
    assert list(jobs) == ["change-proof"]

    job = jobs["change-proof"]
    assert "name" in job, (
        "the README caller example's job needs a name:, or a caller copied from "
        "it reports the context change-proof / Change proof"
    )
    caller_job_name = job["name"]
    assert caller_job_name == "Change proof"

    called = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "change-proof.yml").read_text(
            encoding="utf-8"
        )
    )
    context = f"{caller_job_name} / {called['jobs']['proof']['name']}"
    assert context == "Change proof / Change proof"

    required = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "self-change-proof.yml").read_text(
            encoding="utf-8"
        )
    )
    assert required["jobs"]["change-proof"]["name"] != caller_job_name
