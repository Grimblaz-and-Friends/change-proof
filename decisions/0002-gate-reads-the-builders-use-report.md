# Decision 0002: the gate reads the builder's use report

**Purpose:** keep what was chosen over what when the gate learned to take a builder's use report as use evidence, when, and on what evidence. **Audience:** a maintainer weighing a change to how the gate reads use sources. **Success:** the reader can tell which alternatives were rejected and why without the issue or pull request.

This record is frozen. What the gate does now is in [`README.md`, "Evidence contract"](../README.md#evidence-contract), whose in-force list links here.

- **Decided:** 2026-11-25, when the owner affirmed the implementation brief recorded on [change-proof#58](https://github.com/Grimblaz-and-Friends/change-proof/issues/58).
- **Built in:** [change-proof#59](https://github.com/Grimblaz-and-Friends/change-proof/pull/59).
- **Base the evidence was read at:** `966476916407b843e294dcb8ee2aae064c19ee73`.

## Occasion

On the builder route, the practice entrance takes use evidence from the builder's use report: a `check-report` comment it posts on the change's issue for a successful use seat. A `use` marker counts for nothing there. The gate read only `use` markers, so it refused the one evidence that route produces. Builder-route proofs on tradecraft pull requests #1029, #1030 and #1023 all failed on one line, `missing: an authorized valid public use source: marker is invalid or unauthorized`. That line named neither the marker the gate found nor the fact that failed.

A replay of #1030's recorded GitHub records showed the cause. Under the gate at `9664769`, every requirement passed except that one line. A scratch gate that also took a successful use report passed.

## Decision 1: the gate reads the report

**Chosen:** a resolved use source counts when it opens with a `use` marker the gate accepted before, or with a `check-report` marker that reports a successful use seat by the public facts the entrance counts it by. The `use` marker's acceptance is unchanged.

**Rejected:** the entrance posting a `use` marker on the builder route for the gate to read. That would give the builder route two use records for one session, and the owner chose that the gate read the report.

## Decision 2: the work issue is the only surface

**Chosen:** a report counts only as a comment on the proof's work issue. A report on the pull request is refused, and so is a report on an `issue-comment` source when the proof names the pull request as its own work issue.

**Rejected:** extending the `use` marker's pull-request-comment surface to reports. The entrance posts and counts reports only on the change's issue, so the gate would credit a surface the entrance never counts. Decision 0001's second decision closed the same gap for `use` and `floor`.

## Decision 3: how strictly attributes are read

**Chosen:** the attributes the entrance writes are held to the values it writes:
- `stage=use`, `outcome=success`, `tree=held`, and `head` equal to the proof's evidence head;
- the `use` marker's staffing rule for `staffing_status` and `same_vendor_reason`;
- `dispatch` present, and `dispatch_sha256` a 64-character lowercase hex digest, by shape only;
- `criterion` and `row` absent, since each names another reader's report;
- `builder_vendor`, when present, equal to `declared`.

Any other attribute name is ignored and named in a non-fatal diagnostic. Attributes are split on whitespace as the entrance splits them, because the marker reader's attribute pattern drops names that contain digits, such as `dispatch_sha256`, and widening that pattern would change what a `use` marker carries.

**Rejected:**
- **A closed attribute set, like the `use` marker's.** The gate would refuse a report the day the entrance adds an attribute, which is this defect again.
- **Reading only the facts the brief names and ignoring every other attribute.** The gate would then credit a criterion or row reader's report pointed at with `stage=use` mistyped, or a report form the entrance never posts.

**Left to the entrance and the holder,** because the gate cannot read them: whether the dispatch digest recomposes, the bundle, the stored return, and whether a `builder_vendor=declared` seat was staffed against a hand-started record.

## Decision 4: an earlier report carries by the history rule

**Chosen:** a report naming an earlier head carries to the current head by the gate's existing history rule alone. It is not asked for `changed=false`. A `use` marker at an earlier head keeps that requirement.

**Rejected:** asking a report for a `changed` flag it does not carry. The entrance composes a proof from an earlier report whenever the commits since buy no use, so asking more would refuse a proof the entrance composed. On the builder route, what a use found is answered finding by finding in the builder's readiness record, not by one flag.

## Decision 5: the refusal line names what was found

**Chosen:** when the gate resolves a use source and refuses it, the existing line keeps its words and gains what the comment opens with and every fact that failed. That holds for a `use` marker, a report, another marker or no marker. When no marker opens the comment, the line says whether a `check-report` marker sits quoted or below the opening line.

A misplaced `use` marker is not named on that line. Its own set-aside diagnostic names it, and decision 0001 holds that a note may quote or misplace a marker without changing the verdict.

For a source of a review kind, the owner was asked to choose between two readings, because the brief's checks could not both hold:
- **Reading A:** the existing refusal line, which a test pins whole, stays byte for byte, and a `diagnostic:` line beside it names what the gate found at that review or review comment.
- **Reading B:** the refusal line itself gains what was found, and the pinning test is edited in its one expected string.

The gate is built on reading A, the holder's recommendation. Under it, every existing test passes unedited. The pinned line already names what was found there, a source of a review kind, and the fact that failed, that the kind is not a use surface. The diagnostic adds what the record opens with. The case against A is that the row asks that "its line" name what was found, and under A only the line beside it names the marker. The owner had not ruled when this was built. A ruling for B replaces this paragraph's choice.

**Rejected:** a new wording for the refusal line. The line's words stay, so a reader or tool matching them keeps working.

**Chosen with it:** when the refused comment opens with a `check-report` marker, the remedy asks for the document's use source to be corrected or the builder's use check to be run again, so that a new use report is posted. Every other refusal keeps the remedy that offers a lawful `use` marker.

**Rejected:** keeping the one remedy for every refusal. The entrance composes a builder-route proof from a use report and never from a `use` marker, so a holder told to post a marker would post evidence the proof never names.

## Shown by

These tests in `tests/test_check.py`:
- `test_tc1030_world_keeps_the_get_record_and_the_exact_producer_comments`
- `test_tc1030_builder_use_report_replay_passes`
- `test_tc1030_altered_report_is_refused_naming_what_was_found_and_the_fact`
- `test_tc1030_report_from_a_non_producer_supplies_no_use`
- `test_tc1030_report_that_is_quoted_or_does_not_open_its_comment_supplies_no_use`
- `test_tc1030_report_on_the_pull_request_does_not_count`
- `test_report_is_refused_when_the_work_issue_is_the_pull_request`
- `test_tc1030_report_on_a_review_kind_keeps_the_kind_refusal_and_names_what_was_found`
- `test_tc1030_report_with_an_attribute_the_gate_does_not_read_still_counts`
- `test_tc1030_malformed_report_is_refused_naming_the_attribute`
- `test_tc1030_hand_started_builders_declared_vendor_report_counts`
- `test_refused_use_marker_line_names_what_was_found_and_the_fact`
- `test_refused_report_remedy_asks_for_a_new_use_report_not_a_use_marker`
- `test_use_marker_facts_are_empty_exactly_when_the_marker_is_lawful`
- `test_report_at_an_earlier_commit_carries_over_a_commit_that_buys_no_use`
- `test_report_at_an_earlier_commit_is_staled_by_an_authored_use_buying_commit`
- `test_report_and_marker_carry_alike_by_base_membership_or_merge`
- `test_misplaced_use_marker_is_named_without_changing_the_verdict`, unchanged
- `test_review_surfaces_are_not_use_sources`, unchanged

## Left unchanged

These were not decided here:
- the `use` marker's acceptance, and every `use`-marker verdict;
- the kinds the set-aside sweeps list, which do not include `check-report`, because the entrance posts every report as its comment's opening line;
- floor, reviewer and disposition evidence;
- every endpoint the gate reads: a report comes from the work-issue comments and a review-kind source from the reviews the gate already fetched.
