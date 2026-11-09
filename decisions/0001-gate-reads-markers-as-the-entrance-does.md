# Decision 0001: the gate reads its markers as the practice entrance does

**Purpose:** keep what was chosen over what for how the gate reads `proof`, `use`, `floor` and `affirmed-brief` markers, when, and on what evidence. **Audience:** a maintainer weighing a change to those reads. **Success:** the reader can tell which alternatives were rejected and why without the issue or pull request.

This record is frozen. What the gate does now is in [`README.md`, "Evidence contract"](../README.md#evidence-contract), whose in-force list links here.

- **Decided:** 2026-11-08, when the owner affirmed the implementation brief on [change-proof#54](https://github.com/Grimblaz-and-Friends/change-proof/issues/54).
- **Built in:** [change-proof#57](https://github.com/Grimblaz-and-Friends/change-proof/pull/57).
- **Base the evidence was read at:** `31ae5742d11a70982084a46633dbc01174d8bd9c`.

## Occasion

On tradecraft pull request #885, an authorized use note quoted a proof envelope in inline code. The proof scan read every HTML comment in a comment body, so it took the quotation for a second current-head proof. The gate failed with `competing comments` even though the evidence was correct.

A probe at `31ae574` showed the same flaw in two other readers:
- `markers()` accepted a floor pass inside a blockquote.
- `_has_exact_affirmed_brief` counted an affirmed-brief marker quoted in inline code.

The cause was shared. The gate never adopted the source-reading rules the practice entrance follows, so the two disagreed about what a comment claims.

## Decision 1: the opening-line and quotation rules

**Chosen:** the gate reads all four marker kinds by both of the entrance's rules:
- **Quotation rule:** text inside inline code, a fenced or indented code block, or a blockquote is a quotation.
- **Opening rule:** a comment claims only the marker that is its whole, unquoted first nonblank line.

This applies on every surface the gate reads them from.

**Rejected:**
- **Fixing only the proof scan.** It would have left the floor, use and affirmed-brief readers disagreeing with the entrance.
- **The quotation rule alone, keeping a marker anywhere in the comment.** Under that rule, an artifact that carries the affirmed brief further down would still be chosen as "the latest affirmed brief" in place of the brief itself. Notes with prose above their marker would also keep counting at the gate after the entrance had refused them.
- **Counting a marker that merely begins the first line.** The entrance compares the marker with the whole trimmed line, so this would disagree with it on every first line that has text after the marker.

**Evidence:** a GET-only survey across six adopting repositories: Daemon, Organizations-of-Verra, tradecraft, Countdown-Clash, Windgust-Questbook and change-proof. It read all conversation and inline review comments, plus the reviews on each repository's latest 100 pull requests.
- It found about 1,300 proof, use, floor and affirmed-brief markers.
- 66 of them sat unquoted below their comment's first line, and none of those was a source of the pull requests then open.
- Most of the 66 were artifacts carrying the affirmed brief inside them. The rest were notes with prose above the marker, which the entrance already refused.

**Consequence chosen with it:** for each comment, the gate prints one non-fatal diagnostic line per kind that has an unquoted marker the opening rule set aside.
- This keeps a red gate traceable to the comment that holds the misplaced marker.
- Quoted markers are not listed. Artifacts and notes quote them routinely, and listing them would bury the lines that matter.

**Shown by:** these tests in `tests/test_check.py`:
- `test_quoted_marker_supplies_no_evidence_and_raises_no_failure`
- `test_marker_that_does_not_open_its_comment_supplies_no_evidence`
- `test_marker_opening_its_comment_after_blank_lines_or_a_short_indent_counts`
- `test_artifact_carrying_the_brief_does_not_supersede_the_brief`
- `test_misplaced_use_marker_is_named_without_changing_the_verdict`

## Decision 2: use and floor surfaces

**Chosen:** the gate takes `use` and `floor` sources only from pull-request comments and work-issue comments. A proof naming a review, review comment or inline review comment as one of those sources fails, and the message names the accepted surfaces.

**Rejected:** keeping reviews and review comments as use and floor surfaces of the gate's own, which the README then allowed. The entrance refuses those surfaces for use and floor. Keeping them would have left the gate and entrance disagreeing about where those claims can be made, even after Decision 1.

**Evidence:** every use or floor source named by the lab's posted proofs was an issue or pull-request comment. There were 361 such sources, so no adopter lost a surface it had used.

**Shown by:** these tests:
- `tests/test_check.py`: `test_review_surfaces_are_not_use_sources`
- `tests/test_check.py`: `test_review_surfaces_are_not_floor_sources`
- `tests/test_check.py`: `test_stale_use_pointer_remedy_never_offers_a_review`
- `tests/test_ci_floor.py`: `test_declared_fallback_refuses_a_review_surface_floor_source`

## Left unchanged

These reads keep their own rules and were not decided here:
- reviewer-thread dispositions;
- the `connected-review-attempt` receipt;
- reviewer finding identities;
- the `**Path departures:**` paragraph.
