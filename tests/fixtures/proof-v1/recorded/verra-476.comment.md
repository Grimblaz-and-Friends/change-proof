<!-- tradecraft:proof:v1 head=08f14b094614858c15a85a5347ed9eb82e4c227c -->

```json
{
  "declarations": [
    {
      "actual_effort": null,
      "actual_model": null,
      "actual_vendor": "codex",
      "completed_at": "2026-09-23T01:07:33.742955+00:00",
      "dispatch_id": "8fae4b12ae064c5a80e161404706a007",
      "fallback_reason": null,
      "reason": null,
      "requested_classification": null,
      "requested_effort": "xhigh",
      "requested_model": "gpt-5.6-sol",
      "requested_vendor": "codex",
      "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
      "same_vendor_reason": null,
      "staffing_status": "qualified",
      "stage": "floor",
      "status": "declared"
    },
    {
      "actual_effort": null,
      "actual_model": null,
      "actual_vendor": null,
      "completed_at": null,
      "dispatch_id": null,
      "fallback_reason": null,
      "reason": "no matching successful dispatch bundle",
      "requested_classification": null,
      "requested_effort": null,
      "requested_model": null,
      "requested_vendor": null,
      "revision": null,
      "same_vendor_reason": null,
      "staffing_status": null,
      "stage": "use",
      "status": "unverifiable"
    }
  ],
  "diagnostics": [
    {
      "code": "invalid-marker-claim",
      "message": "use marker: no matching successful dispatch bundle",
      "source": {
        "author": null,
        "id": 5787327005,
        "kind": "pull-request-comment",
        "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
        "revision": null,
        "timestamp": "2026-09-23T01:20:23Z",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#issuecomment-5787327005"
      }
    }
  ],
  "dispositions": [
    {
      "reply": {
        "author": "grimblaz",
        "id": 4078741203,
        "kind": "review-comment",
        "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
        "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "timestamp": "2026-09-23T03:17:52Z",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#discussion_r4078741203"
      },
      "reviewer": "greptile-apps[bot]",
      "source": {
        "author": "greptile-apps[bot]",
        "id": 4078509524,
        "kind": "review-comment",
        "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
        "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "timestamp": "2026-09-23T02:34:18Z",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#discussion_r4078509524"
      },
      "thread_id": 4078509524
    }
  ],
  "floor": {
    "checks": [
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:20:56Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006591696,
        "name": "CI skip notice",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:20:53Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:20:50Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006560625,
        "name": "Detect changes",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:20:45Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      },
      {
        "app_id": 867647,
        "app_slug": "greptile-apps",
        "completed_at": "2026-09-23T02:34:23Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107021398559,
        "name": "Greptile Review",
        "run_id": null,
        "started_at": "2026-09-23T02:31:35Z",
        "status": "completed",
        "url": "https://greptile.com/",
        "workflow_id": null
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:21:12Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006591742,
        "name": "Residue gate",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:20:52Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:27:29Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107007816307,
        "name": "build",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:26:40Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:24:32Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006560553,
        "name": "e2e",
        "run_id": 35805901025,
        "started_at": "2026-09-23T01:20:44Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805901025",
        "workflow_id": 227323064
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:21:44Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006591697,
        "name": "fast-checks",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:20:52Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      },
      {
        "app_id": 15368,
        "app_slug": "github-actions",
        "completed_at": "2026-09-23T01:26:37Z",
        "conclusion": "success",
        "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "id": 107006591741,
        "name": "tests",
        "run_id": 35805900974,
        "started_at": "2026-09-23T01:20:53Z",
        "status": "completed",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/actions/runs/35805900974",
        "workflow_id": 209490963
      }
    ],
    "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
    "source": {
      "author": "grimblaz",
      "id": 5787215547,
      "kind": "pull-request-comment",
      "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
      "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
      "timestamp": "2026-09-23T01:08:00Z",
      "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#issuecomment-5787215547"
    }
  },
  "identity": {
    "head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
    "issue": 471,
    "producer_version": "0.153.0",
    "pull_request": 476,
    "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
    "work": "Grimblaz-and-Friends/Organizations-of-Verra#471"
  },
  "policy": {
    "use_rules": {
      "path": ".github/change-proof.json",
      "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
      "revision": "d057fdfdd158f7dca29ad410f00f009a630ae02d",
      "sha256": "56d922160e40752ed5ebd47fc3e8df2238eeea2534fcbe4dfb65d6f2c7618fe0"
    },
    "work_configuration": {
      "path": ".tradecraft/work.json",
      "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
      "revision": "d057fdfdd158f7dca29ad410f00f009a630ae02d",
      "sha256": "b4ca4491e53627f0f901cf1c219cefcbfb7950a8c583f335023b47c932b7ff63"
    }
  },
  "reviewers": [
    {
      "login": "chatgpt-codex-connector[bot]",
      "notices": [],
      "result": "present",
      "source": {
        "author": "chatgpt-codex-connector[bot]",
        "id": 5787330070,
        "kind": "pull-request-comment",
        "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
        "revision": null,
        "timestamp": "2026-09-23T01:20:47Z",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#issuecomment-5787330070"
      }
    },
    {
      "login": "greptile-apps[bot]",
      "notices": [],
      "result": "present",
      "source": {
        "author": "greptile-apps[bot]",
        "id": 5286241977,
        "kind": "review",
        "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
        "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
        "timestamp": "2026-09-23T02:34:19Z",
        "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#pullrequestreview-5286241977"
      }
    }
  ],
  "schema_version": 1,
  "use": {
    "applicability": "current-head",
    "classification": "required",
    "evidence_head": "08f14b094614858c15a85a5347ed9eb82e4c227c",
    "intervening_commits": [],
    "reason": "use evidence names the current head",
    "required": true,
    "source": {
      "author": "grimblaz",
      "id": 5787327005,
      "kind": "pull-request-comment",
      "repository": "Grimblaz-and-Friends/Organizations-of-Verra",
      "revision": "08f14b094614858c15a85a5347ed9eb82e4c227c",
      "timestamp": "2026-09-23T01:20:23Z",
      "url": "https://github.com/Grimblaz-and-Friends/Organizations-of-Verra/pull/476#issuecomment-5787327005"
    }
  }
}
```

### Readable proof

- evidence: Grimblaz-and-Friends/Organizations-of-Verra#471 pull request #476 at 08f14b094614858c15a85a5347ed9eb82e4c227c
- evidence: floor source present; 8 public check record(s)
- evidence: use classification required; applicability current-head
- evidence: reviewer chatgpt-codex-connector[bot]: present
- evidence: reviewer greptile-apps[bot]: present
- evidence: disposition for thread 4078509524: present
- declared: floor: declared (8fae4b12ae064c5a80e161404706a007)
- declared: use: unverifiable (no matching successful dispatch bundle)
- diagnostic: invalid-marker-claim: use marker: no matching successful dispatch bundle
