# Review response — stale source_verdicts on the error path

## Review received

> The multi-source consensus mechanism is substantive and the submitted contract
> matches the deployment. One retry-path issue needs correction: if a later judged
> result cannot be parsed, the query becomes ERRORED and its timestamp/count advance,
> but source_verdicts still exposes the previous round's labels. Please clear or
> version those verdicts consistently on the error path, then resubmit matching
> updated repository and deployment source.

## Root cause

`resolve_query` is permissionlessly re-callable at any time (subject only to the
cooldown), from any prior state — a query resolved once successfully can be
re-resolved later, and that later round can fail to parse (e.g. the model returns
malformed JSON). On that failure path, the contract correctly:

- set `state = "ERRORED"`
- reset `resolved_answer = ""`
- still advanced `resolve_count` and `last_resolved_at`

but never touched `source_verdicts`. Since the first, successful round had already
populated `source_verdicts` with real per-source labels, a query in `ERRORED` state
kept exposing those old labels through `get_query` as if they were still meaningful —
even though nothing about the failed round supports them, and the state/answer fields
right next to them had already been correctly reset to reflect "we don't know."

## Fix

In [`contracts/source_consensus.py`](contracts/source_consensus.py), `resolve_query`'s
unparseable-output branch now also clears the verdicts array:

```python
parsed = _parse_source_verdicts(raw_result, len(source_urls), candidate_answers)
if not parsed["ok"]:
    query.state = STATE_ERRORED
    query.resolved_answer = ""
    # A stale source_verdicts array from an earlier successful round
    # must never survive a later failed re-resolution - it would
    # otherwise keep exposing per-source labels that don't
    # correspond to this (or any) accepted round.
    query.source_verdicts.clear()
    return
```

This puts `source_verdicts` in the same "reset together, consistently" group as
`resolved_answer` — every field that describes "what the last accepted round found"
now moves in lockstep, whether that round succeeded or failed to parse.

## Test added

[`tests/direct/test_source_consensus.py`](tests/direct/test_source_consensus.py) —
`test_resolve_query_clears_stale_source_verdicts_when_a_later_round_errors`:

1. Resolves a fresh query successfully → `CONSENSUS`, `source_verdicts` has 3 real
   entries.
2. Waits out the cooldown.
3. Re-resolves with mocked unparseable model output → asserts `state == "ERRORED"`
   **and** `source_verdicts == []`.

This reproduces exactly the sequence the review described: a query that has already
resolved once, then fails to parse on a later round.

Full suite: **30/30 direct tests passing** (29 pre-existing + 1 new), `genvm-lint`
clean.

## Deployment

- **Old (buggy) address:** `0x7bF80738dAaFD26d947657B0dE8370c748A91017` — superseded.
- **New (fixed) address:** `0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC`
- Explorer: https://explorer-studio.genlayer.com/address/0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC

All 3 integration tests re-run against the new deployment on StudioNet, with no
regressions:

- `test_full_surface_drives_create_and_resolve_and_reads_every_view` — real judged
  round, 2-of-3 majority `CONSENSUS`/`YES`.
- `test_resolve_query_with_one_unreachable_source_completes_without_genvm_or_consensus_error`
  — a genuinely dead domain mixed with two real, opposed sources correctly reached
  `NO_CONSENSUS`.
- `test_resolve_query_with_maximum_five_sources_completes_without_genvm_or_consensus_error`
  — the slowest round this contract can produce (5 fetches + 1 judgment) completed
  cleanly with a real 3-of-5 majority `CONSENSUS`.

Every judged round across every run of this contract has completed
`SUCCESS`/`ACCEPTED` at the GenVM and consensus level — zero fatal errors, zero
undetermined rounds.

Note on live-testing the fix itself: the exact failure branch (unparseable model
output) can't be forced on demand against a live network — a production LLM reliably
follows the requested JSON format, which is precisely why this defensive path exists
in the first place but is only exercisable via a mocked, direct-mode test. The
redeployed contract is the same source file; the fix is proven correct by the
regression test above, and the redeployment is proven regression-free by the three
live integration tests.

## Files changed

- `contracts/source_consensus.py` — the fix (one added line + comment in
  `resolve_query`'s error branch).
- `tests/direct/test_source_consensus.py` — one new regression test.
- `README.md` — updated deployment address, "Measured on live consensus" section, test
  count.
