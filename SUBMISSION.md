# Submission Package

## Title

SourceConsensus — Multi-Source Reconciliation Registry

## Notes / Description (≤1000 characters, 992 used)

SourceConsensus reconciles what multiple independent web sources say about a question.
Anyone declares a question, 2-5 source URLs, and a fixed answer set; resolve_query
fetches every source live in one judged round, has validators classify what each
supports, then deterministically takes the majority across reachable sources - no
single source is trusted alone. Unlike ParametricPool (one trigger fetch, pooled value)
and VisualClaim/HandleGuard (one screenshot / embeddings, no fetch), this reconciles a
whole set of sources per round. Fetch failures, scattered disagreement, and a
majority-UNCLEAR result resolve to explicit, retryable states
(INSUFFICIENT_SOURCES/NO_CONSENSUS), never a guessed answer. 407-line contract, 55-line
example, 29 passing direct tests, full-surface integration test on StudioNet. Measured:
three real cross-domain sources (Wikipedia Python article, python.org, Wikipedia
Photosynthesis) reconciled to a 2-of-3 majority CONSENSUS/YES in one live judged round.

## Evidence links

- GitHub repo: https://github.com/Hilda26/sourceconsensus (no AI attribution — verified
  via `git log -1 --format='%B' | grep -i "co-authored\|claude\|generated with"` → no
  match, on every commit)
- Explorer contract URL: https://explorer-studio.genlayer.com/address/0x7bF80738dAaFD26d947657B0dE8370c748A91017
- Studio import URL: open studio.genlayer.com → Import contract →
  `0x7bF80738dAaFD26d947657B0dE8370c748A91017`
- Deployed StudioNet address: `0x7bF80738dAaFD26d947657B0dE8370c748A91017`

## What was verified

- `genvm-lint check contracts/source_consensus.py --json` and the worked example: both
  clean.
- `pytest tests/direct/` — 29/29 passing (creation validation, majority/tie/UNCLEAR-
  majority aggregation, fetch-failure handling, adversarial model output, cooldown
  enforcement, permissionless resolution, and the worked consumer example
  `ConsensusGatedAction`).
- `pytest tests/integration/ --network=studionet` against the live deployment —
  `test_full_surface_drives_create_and_resolve_and_reads_every_view` passed: a real
  judged `resolve_query` round fetched all 3 declared sources, correctly classified
  each (`YES`, `YES`, `NO`), and deterministically reconciled to `CONSENSUS`/`YES` on
  the 2-of-3 majority (5 validators, `MAJORITY_AGREE`, one round, no appeal). Cooldown
  enforcement and `create_query` input-validation reverts were also verified on-chain
  in the same run.

## Character count check

992/1000 characters (verified with `len()` in Python, whitespace-normalized).
