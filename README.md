# SourceConsensus

A reusable GenLayer Intelligent Contract that lets any app pose a question against a
declared set of 2-5 independent web sources and get back a majority-reconciled answer —
never a single source trusted alone, never a claimant-supplied answer, and never a
guess when the sources disagree or most of them are unreachable. Any app that needs
"what do multiple independent sources actually say about this" decided fairly imports
this instead of writing its own multi-fetch reconciliation logic.

## The problem with the naive version

Trusting a single source is the obvious failure mode — one flaky page, one biased
outlet, one temporarily-wrong status page, and the whole downstream decision is wrong.
The naive fix, "just fetch a few sources and eyeball them," either falls to a
centralized operator's manual review (slow, unaccountable, a single point of bribery
or neglect) or a single LLM call summarizing whatever a backend fetched off-chain
(unrepeatable, and the fetch itself is invisible to anyone relying on the result). A
deterministic string/keyword match across sources is brittle by construction: the
same fact gets phrased differently by every outlet, and "do these pages agree" is
exactly the kind of judgment call that breaks a naive diff constantly.

## Why this needs validator consensus, not a backend

Delete GenLayer and multi-source reconciliation either trusts one backend's fetch-and-
summarize pipeline (invisible, unrepeatable, and a single point of failure or bias) or
trusts a single registrar's manual cross-check (unaccountable, slow). Run the
counterfactual against each alternative:

- **A backend fetch-and-summarize service** — the fetch itself is invisible to anyone
  relying on the result; nothing stops it from quietly dropping an inconvenient source.
- **A single LLM call over backend-supplied text** — combines an unverifiable fetch
  with an unrepeatable judgment; no way to check either step was done honestly.
- **Deterministic keyword matching across sources** — breaks on ordinary phrasing
  variation between outlets that has nothing to do with whether they actually agree.
- **A single registrar's manual cross-check** — unaccountable, slow, and a
  conflict-of-interest surface if the registrar has any stake in the outcome.

GenLayer's validator set independently fetches every declared source and independently
classifies what each one supports, reconciling under an equivalence principle that
requires agreement source-by-source, not just on a final summary. No single party —
not the query creator, not the resolver, not a validator — decides alone what the
sources collectively say, and the deterministic majority vote afterward is fully
auditable from the stored per-source verdicts.

## Why it isn't the patterns that don't belong in this category

- **Not an AI app with a blockchain attached.** The output is a state transition — a
  query is `CONSENSUS`, `NO_CONSENSUS`, `INSUFFICIENT_SOURCES`, or `ERRORED` — never
  advice a human reads and acts on manually.
- **Not a format-only validator.** The equivalence principle compares the per-source
  *verdict* array itself, entry by entry, never whether the model's JSON merely parses.
- **Not judging claimant-submitted evidence.** `resolve_query` takes no source content
  as an argument at all — every source is fetched contract-side, live, on every call. A
  creator can declare which URLs to ask, but cannot supply what the contract sees there.
- **Structurally distinct from this week's other two submissions.** ParametricPool
  fetches exactly one trigger URL per judged round and pays out real value;
  HandleGuard never fetches anything, judging embeddings-similarity instead;
  VisualClaim captures exactly one screenshot per judged round. SourceConsensus is the
  first of the three to fetch and reconcile a whole *set* of independent sources in a
  single round — an entirely different mechanism, not a relabeled copy of any of them.

## The non-deterministic core, and why the deterministic half is just as load-bearing

Exactly **one** non-deterministic operation, bundled into a single
`gl.eq_principle.prompt_comparative` block: a leader function that fetches every
declared source URL (`gl.nondet.web.render`, text mode, up to 5 of them) and asks
`gl.nondet.exec_prompt` to classify what each individually-fetched source supports
from a fixed candidate-answer list. The model never decides the overall answer — only
"what does source i say" — and the deterministic half is where the actual reconciliation
happens: majority-vote counting, quorum-of-reachable-sources gating, and refusing to
call a majority-UNCLEAR result a "consensus." Full rationale in `DESIGN.md`.

## Safety properties

| Property | Enforced by | Verified by |
|---|---|---|
| A query's sources, question, and answer set can never be edited after creation | no setter exists at all | `test_create_query_succeeds_and_stores_declared_fields` and the absence of any editing method |
| An unparseable, duplicate-index, or out-of-range-index model output never silently becomes a resolved answer | `resolve_query` routes all of these to `ERRORED`, never `CONSENSUS`/`NO_CONSENSUS` | `test_resolve_query_on_unparseable_output_errors_not_denied_or_consensus`, `test_resolve_query_discards_a_duplicate_source_index`, `test_resolve_query_discards_an_out_of_range_source_index` |
| A model can't invent an answer label outside the declared candidate set | `_parse_source_verdicts` checks every label against the query's own list | `test_resolve_query_discards_an_answer_label_not_in_the_candidate_set` |
| Too few reachable sources never becomes a guessed answer | `_majority_verdict` requires at least 2 valid sources before considering a majority at all | `test_resolve_query_below_min_valid_sources_yields_insufficient_sources`, `test_resolve_query_with_no_sources_reachable_at_all_yields_insufficient_sources` |
| A majority of sources saying UNCLEAR is never reported as a resolved answer | `_majority_verdict` explicitly excludes the UNCLEAR label from ever winning `CONSENSUS` | `test_resolve_query_majority_being_unclear_is_no_consensus_not_a_resolved_unclear_answer` |
| One unreachable source doesn't block reconciliation among the rest | `_majority_verdict` operates only over sources that were actually reachable | `test_resolve_query_reaches_consensus_despite_one_unreachable_source` |
| Anyone can push a stuck (`ERRORED`) query forward, not just the creator | `resolve_query` has no caller restriction, ever | `test_resolve_query_after_errored_can_be_retried_by_anyone_once_cooldown_allows` |
| A query is a shared public oracle from the first call, not a personal claim | no "creator/claimant only" gate on the first resolution, unlike VisualClaim's `reverify` | `test_resolve_query_is_permissionless_from_the_first_call` |

## Why it's reusable

The consumer integration is genuinely small — this is the whole thing, from
`examples/consensus_gated_action.py`:

```python
@gl.contract_interface
class ISourceConsensus:
    class View:
        def get_query(self, query_id: u256) -> dict: ...
    class Write:
        pass

query = ISourceConsensus(self.source_consensus_address).view().get_query(query_id)
if query["state"] == "CONSENSUS" and query["resolved_answer"] == expected_answer:
    ...  # grant whatever this contract controls
```

Any DAO, prediction market, or bounty contract that needs to act on "what multiple
independent sources agree happened" can gate on that instead of writing its own
multi-fetch reconciliation logic — the exact same "read a verdict, never re-derive it"
shape `SellerDirectory` (HandleGuard) and `ClaimGatedAccess` (ParametricPool) already
use, applied to a different underlying primitive.

## Testing

- **Direct-mode** (`tests/direct/`, `pytest tests/direct/`): 30 tests, no network, no
  live consensus — fast feedback on every deterministic branch, every failure/abstention
  path, and the worked consumer example, using gltest's built-in `mock_web`/`mock_llm`.
- **Integration** (`tests/integration/`, `pytest tests/integration/ --network=studionet`):
  requires `SOURCECONSENSUS_ADDRESS` set to a real StudioNet deployment; drives
  `create_query` and a real judged `resolve_query` against three real, stable,
  cross-domain pages, plus cooldown enforcement and input-validation reverts on-chain.

## Deployment

- Deployed StudioNet address: `0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC` (redeployed
  with the stale-`source_verdicts`-on-error fix; supersedes
  `0x7bF80738dAaFD26d947657B0dE8370c748A91017`, which had a real bug where a query
  resolved once successfully and later re-resolved into `ERRORED` kept exposing the
  prior round's per-source labels — see `SUBMISSION.md`/commit history)
- Explorer: https://explorer-studio.genlayer.com/address/0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC
- Studio import: open [studio.genlayer.com](https://studio.genlayer.com) → "Import
  contract" → paste `0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC`.

## Measured on live consensus

`test_full_surface_drives_create_and_resolve_and_reads_every_view` passed against the
address above. A query asking "Is this page primarily about the Python programming
language?" across three real, cross-domain sources —
[en.wikipedia.org/wiki/Python_(programming_language)](https://en.wikipedia.org/wiki/Python_(programming_language)),
[python.org](https://www.python.org/), and
[en.wikipedia.org/wiki/Photosynthesis](https://en.wikipedia.org/wiki/Photosynthesis) —
resolved in a single consensus round (5 validators, `MAJORITY_AGREE`, one round, no
appeal) to:

```
source_verdicts: [{index: 0, verdict: "YES"}, {index: 1, verdict: "YES"}, {index: 2, verdict: "NO"}]
state: CONSENSUS
resolved_answer: YES
```

The two Python-related sources were correctly classified `YES`, the unrelated
Photosynthesis page correctly classified `NO`, and the deterministic 2-of-3 majority
vote produced the reconciled answer — end to end, on real fetched content, in one
judged round. Cooldown enforcement and `create_query` input-validation reverts were
also verified on-chain in the same test run.

**Re-verified after the stale-`source_verdicts` fix** against
`0xdcbf2fa018BFDfDC118e255C53F40fe00Ae84aCC`: all 3 integration tests passed with no
regressions — the full-surface Python/Photosynthesis case above, the dead-domain
`FETCH_ERROR` case (`test_resolve_query_with_one_unreachable_source_completes_without_genvm_or_consensus_error`,
correctly reaching `NO_CONSENSUS`), and the 5-source stress case
(`test_resolve_query_with_maximum_five_sources_completes_without_genvm_or_consensus_error`,
correctly reaching `CONSENSUS`/`YES`). Every judged round across every run of this
contract has completed `SUCCESS`/`ACCEPTED` at the GenVM and consensus level - zero
fatal errors, zero undetermined rounds. The fix itself (clearing `source_verdicts` on
a failed re-resolution) is proven by the direct-mode regression test
`test_resolve_query_clears_stale_source_verdicts_when_a_later_round_errors`, since a
live network's LLM cannot be scripted to reliably produce unparseable output on
demand - the same reason no other LLM_ERROR path anywhere in this portfolio is ever
forced live either.
