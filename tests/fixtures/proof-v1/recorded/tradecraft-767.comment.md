<!-- tradecraft:proof:v1 head=4f12aa5efa0ae765cebd213f89eec7da754c3d6a -->

```json
{
  "declarations": [
    {
      "actual_effort": null,
      "actual_model": null,
      "actual_vendor": "codex",
      "completed_at": "2026-09-27T04:03:54.129544+00:00",
      "dispatch_id": "df04228909514016a085a61b524b822c",
      "fallback_reason": null,
      "reason": null,
      "requested_classification": null,
      "requested_effort": "xhigh",
      "requested_model": "gpt-5.6-sol",
      "requested_vendor": "codex",
      "revision": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
      "same_vendor_reason": null,
      "staffing_status": "qualified",
      "stage": "floor",
      "status": "declared"
    }
  ],
  "diagnostics": [],
  "dispositions": [],
  "floor": {
    "checks": [
      {
        "app_id": 867647,
        "app_slug": "greptile-apps",
        "completed_at": "2026-09-27T04:06:48Z",
        "conclusion": "success",
        "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
        "id": 108547334634,
        "name": "Greptile Review",
        "run_id": null,
        "started_at": "2026-09-27T04:05:21Z",
        "status": "completed",
        "url": "https://greptile.com/",
        "workflow_id": null
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-27T04:17:12Z",
        "conclusion": "success",
        "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
        "id": 108548930130,
        "name": "ask-declaration",
        "run_id": 36293856632,
        "started_at": "2026-09-27T04:17:04Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/actions/runs/36293856632",
        "workflow_id": 335259309
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-27T04:17:47Z",
        "conclusion": "success",
        "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
        "id": 108548930259,
        "name": "lint-and-test (ubuntu-latest)",
        "run_id": 36293856632,
        "started_at": "2026-09-27T04:17:05Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/actions/runs/36293856632",
        "workflow_id": 335259309
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-27T04:20:33Z",
        "conclusion": "success",
        "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
        "id": 108548930241,
        "name": "lint-and-test (windows-latest)",
        "run_id": 36293856632,
        "started_at": "2026-09-27T04:17:04Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/actions/runs/36293856632",
        "workflow_id": 335259309
      }
    ],
    "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
    "source": {
      "author": "grimblaz",
      "id": 5852487982,
      "kind": "pull-request-comment",
      "repository": "Grimblaz-and-Friends/tradecraft",
      "revision": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
      "timestamp": "2026-09-27T04:04:08Z",
      "url": "https://github.com/Grimblaz-and-Friends/tradecraft/pull/767#issuecomment-5852487982"
    }
  },
  "identity": {
    "head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
    "issue": 759,
    "producer_version": "0.156.0",
    "pull_request": 767,
    "repository": "Grimblaz-and-Friends/tradecraft",
    "work": "Grimblaz-and-Friends/tradecraft#759"
  },
  "policy": {
    "use_rules": {
      "path": "lib/use-rules.json",
      "repository": "Grimblaz-and-Friends/tradecraft",
      "revision": "6789582047cf306607573ecaff25ba1a4eda379d",
      "sha256": "11f48690d4ff8b19e31b632380e025413b32b2a0ac9de543f2b9e51a7b0907ee"
    },
    "work_configuration": {
      "path": ".tradecraft/work.json",
      "repository": "Grimblaz-and-Friends/tradecraft",
      "revision": "6789582047cf306607573ecaff25ba1a4eda379d",
      "sha256": "943da02760b23218e4fb0cef77e50f66eebe7bf19ef096f5cd48bdf2deafa506"
    }
  },
  "reviewers": [
    {
      "login": "chatgpt-codex-connector[bot]",
      "notices": [],
      "result": "present",
      "source": {
        "author": "chatgpt-codex-connector[bot]",
        "id": 5852495163,
        "kind": "pull-request-comment",
        "repository": "Grimblaz-and-Friends/tradecraft",
        "revision": null,
        "timestamp": "2026-09-27T04:05:29Z",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/pull/767#issuecomment-5852495163"
      }
    },
    {
      "login": "coderabbitai[bot]",
      "notices": [],
      "result": "present",
      "source": {
        "author": "coderabbitai[bot]",
        "id": 5852424198,
        "kind": "pull-request-comment",
        "repository": "Grimblaz-and-Friends/tradecraft",
        "revision": null,
        "timestamp": "2026-09-27T03:52:19Z",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/pull/767#issuecomment-5852424198"
      }
    },
    {
      "login": "greptile-apps[bot]",
      "notices": [],
      "result": "present",
      "source": {
        "author": "greptile-apps[bot]",
        "id": 5852502444,
        "kind": "pull-request-comment",
        "repository": "Grimblaz-and-Friends/tradecraft",
        "revision": null,
        "timestamp": "2026-09-27T04:06:46Z",
        "url": "https://github.com/Grimblaz-and-Friends/tradecraft/pull/767#issuecomment-5852502444"
      }
    }
  ],
  "schema_version": 1,
  "use": {
    "applicability": "generated",
    "classification": "not-required",
    "evidence_head": "4f12aa5efa0ae765cebd213f89eec7da754c3d6a",
    "intervening_commits": [],
    "reason": "the owner-affirmed mechanical lane exempts use even when changed paths match the schema-version-1 use policy",
    "required": false,
    "source": {
      "author": "grimblaz",
      "id": 5851221027,
      "kind": "issue-comment",
      "repository": "Grimblaz-and-Friends/tradecraft",
      "revision": null,
      "timestamp": "2026-09-27T00:20:37Z",
      "url": "https://github.com/Grimblaz-and-Friends/tradecraft/issues/759#issuecomment-5851221027"
    }
  }
}
```

### Readable proof

- evidence: Grimblaz-and-Friends/tradecraft#759 pull request #767 at 4f12aa5efa0ae765cebd213f89eec7da754c3d6a
- evidence: floor source present; 4 public check record(s)
- evidence: use classification not-required; applicability generated
- evidence: use reason the owner-affirmed mechanical lane exempts use even when changed paths match the schema-version-1 use policy; source https://github.com/Grimblaz-and-Friends/tradecraft/issues/759#issuecomment-5851221027
- evidence: reviewer chatgpt-codex-connector[bot]: present
- evidence: reviewer coderabbitai[bot]: present
- evidence: reviewer greptile-apps[bot]: present
- declared: floor: declared (df04228909514016a085a61b524b822c)

<!-- tradecraft:no-use:v1 head=4f12aa5efa0ae765cebd213f89eec7da754c3d6a -->
Use: not required - the owner-affirmed mechanical lane exempts use even when changed paths match the schema-version-1 use policy.
