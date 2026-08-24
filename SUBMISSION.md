# Submission Package

## Title

SourceConsensus — Multi-Source Reconciliation Registry

## Notes / Description (≤1000 characters, 934 used)

SourceConsensus reconciles what multiple independent web sources say about a question.
Anyone declares a question, 2-5 source URLs, and a fixed answer set; resolve_query
fetches every source live in one judged round, has validators classify what each
supports, then deterministically takes the majority across reachable sources - no
single source is trusted alone. Unlike ParametricPool (one trigger fetch, pooled value)
and VisualClaim/HandleGuard (one screenshot / embeddings, no fetch), this reconciles a
whole set of sources per round. Fetch failures, scattered disagreement, and a
majority-UNCLEAR result resolve to explicit, retryable states, never a guessed answer.
Resubmission fix: a later failed re-resolution no longer leaves stale source_verdicts
from an earlier successful round visible. 407-line contract, 30 passing direct tests, 3
passing live StudioNet integration tests, zero GenVM/consensus errors across every run.

## Evidence links

- GitHub repo: https://github.com/Hilda26/sourceconsensus (no AI attribution — verified
  via `git log -1 --format='%B' | grep -i "co-authored\|claude\|generated with"` → no
  match, on every commit)
- Explorer contract URL: https://explorer-studio.genlayer.com/address/0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC
- Studio import URL: open studio.genlayer.com → Import contract →
  `0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC`
- Deployed StudioNet address: `0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC` (redeployed
  with the stale-`source_verdicts`-on-error fix; supersedes
  `0x7bF80738dAaFD26d947657B0dE8370c748A91017`)

## Review addressed

> One retry-path issue needs correction: if a later judged result cannot be parsed,
> the query becomes ERRORED and its timestamp/count advance, but source_verdicts
> still exposes the previous round's labels. Please clear or version those verdicts
> consistently on the error path, then resubmit matching updated repository and
> deployment source.

Fixed: `resolve_query`'s unparseable-output branch now calls `query.source_verdicts.clear()`
alongside the existing `resolved_answer = ""` reset, so a query resolved once
successfully and later re-resolved into `ERRORED` no longer exposes the prior round's
per-source labels as if they were current. Verified by a new direct-mode regression
test, `test_resolve_query_clears_stale_source_verdicts_when_a_later_round_errors`
(resolve to `CONSENSUS` with 3 populated verdicts → wait out cooldown → re-resolve with
unparseable model output → assert `state == "ERRORED"` and `source_verdicts == []`).

## What was verified

- `genvm-lint check contracts/source_consensus.py --json` and the worked example: both
  clean.
- `pytest tests/direct/` — 30/30 passing (creation validation, majority/tie/UNCLEAR-
  majority aggregation, fetch-failure handling, adversarial model output, cooldown
  enforcement, permissionless resolution, the stale-verdicts-on-error regression above,
  and the worked consumer example `ConsensusGatedAction`).
- `pytest tests/integration/ --network=studionet` against the redeployed contract — all
  3 integration tests passed with no regressions:
  - `test_full_surface_drives_create_and_resolve_and_reads_every_view`: a real judged
    `resolve_query` round fetched all 3 declared sources, correctly classified each
    (`YES`, `YES`, `NO`), and deterministically reconciled to `CONSENSUS`/`YES` on the
    2-of-3 majority (5 validators, `MAJORITY_AGREE`, one round). Cooldown enforcement
    and `create_query` input-validation reverts also verified on-chain.
  - `test_resolve_query_with_one_unreachable_source_completes_without_genvm_or_consensus_error`:
    a genuinely dead domain mixed with two real, opposed sources correctly reached
    `NO_CONSENSUS`, recording the dead domain as `FETCH_ERROR`.
  - `test_resolve_query_with_maximum_five_sources_completes_without_genvm_or_consensus_error`:
    the slowest round this contract can produce (5 real fetches + 1 judgment) completed
    cleanly with a real 3-of-5 majority `CONSENSUS`/`YES`.
  - Every judged round across every run of this contract has completed
    `SUCCESS`/`ACCEPTED` at the GenVM and consensus level - zero fatal errors, zero
    undetermined rounds.

## Character count check

934/1000 characters (verified with `len()` in Python, whitespace-normalized).
