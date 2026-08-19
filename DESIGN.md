# Design — SourceConsensus

## 1. Non-determinism budget

Exactly **one** non-deterministic operation per `resolve_query` call:

- A single `gl.eq_principle.prompt_comparative` block whose leader fetches every one
  of the query's declared source URLs (`gl.nondet.web.render`, up to `MAX_SOURCES = 5`
  of them) and asks `gl.nondet.exec_prompt` to classify what each individually-fetched
  source supports, all inside the same round.

This is the structural thing that makes SourceConsensus different from the rest of the
portfolio: ParametricPool fetches exactly one trigger URL and VisualClaim captures
exactly one screenshot per judged round; SourceConsensus fetches an entire declared
*set* of sources in the same round and asks the model to classify each one
individually, so the contract can deterministically reconcile them afterward. The
reconciliation itself - majority vote, tie-breaking, quorum-of-reachable-sources - is
plain Python over the model's per-source classifications, never a second judgment call.
The model is never asked "what is the overall answer" - only "what does source i say" -
exactly the same "judgment feeds deterministic code, never the reverse" shape the other
three primitives use, applied to N independent pieces of evidence instead of one.

## 2. What stays deterministic

- Query creation and its immutable parameters (question, source URL list, candidate
  answer list, cooldown).
- The majority-vote aggregation (`_majority_verdict`): counting per-source labels and
  deciding `CONSENSUS`/`NO_CONSENSUS`/`INSUFFICIENT_SOURCES` is pure Python over the
  already-judged per-source array, with no further model call.
- Output sanitization: `_parse_source_verdicts` rejects any source index outside
  `[0, len(source_urls))`, any duplicate index, and any answer label outside the
  query's declared candidate set - the model can label sources, it cannot invent new
  ones or new answers.
- Every source index absent from the accepted result is recorded as `FETCH_ERROR`,
  never silently dropped from `source_verdicts` and never guessed at as any real
  answer label.

## 3. Equivalence principle (full text used in code)

```
Two responses are each independently fetching the same set of declared source URLs
for the same question and classifying what each individually-fetched source
supports, choosing one label per source from a fixed candidate-answer list. They are
EQUIVALENT if and only if they assign the SAME candidate-answer label to each source
they were both able to fetch, regardless of differences in wording, which excerpt of
a page they quote, or incidental phrasing. They are NOT equivalent if they assign a
different label to the same source, or if one reports being unable to fetch a source
that the other successfully read (a fetch outcome is not a judgment call - report
exactly what happened for each source you were asked about). Minor content
differences between fetches of the same page (ads, whitespace, cache timing) are
expected and must not change the assigned label. Use the UNCLEAR label only when a
specific source's own content is genuinely ambiguous or does not address the
question at all - never as a substitute for guessing between two more specific
candidate answers.
```

The per-source verdict array is compared entry by entry, the same discipline
ParametricPool and VisualClaim apply to their single verdict - just extended across N
sources instead of one. A validator disagreeing on even one source's label, or on
which sources were reachable at all, breaks equivalence for the whole round.

## 4. Failure and abstention semantics

- **Unparseable model output**, a duplicate or out-of-range source index, or an answer
  label outside the declared set: the whole round is discarded and the query moves to
  `ERRORED`, never `CONSENSUS`/`NO_CONSENSUS`. `resolve_count` and `last_resolved_at`
  still advance (so the cooldown clock ticks and a retry is always eventually
  possible), exactly mirroring VisualClaim's `check_count`/`last_checked_at` update
  order.
- **Fewer than `MIN_VALID_SOURCES_FOR_VERDICT = 2` sources reachable**: `INSUFFICIENT_SOURCES`,
  never a guess based on whatever the one (or zero) reachable source said. Reconciling
  across sources is the entire point of this primitive - a single surviving source is
  not reconciliation, no matter how confidently it answers.
- **A strict majority of reachable sources agree, but the agreed label is `UNCLEAR`**:
  still `NO_CONSENSUS`, not "consensus reached: the answer is UNCLEAR." A resolved
  `CONSENSUS` state always carries a specific, actionable answer label from the
  declared candidate set - "most sources couldn't tell" is a failure to reconcile, not
  a resolved fact, and a consumer contract gating on `state == CONSENSUS` must never
  have to special-case an `UNCLEAR` `resolved_answer`.
- **No strict majority at all** (a tie, or answers scattered across 3+ labels with none
  holding more than half): `NO_CONSENSUS`. `resolved_answer` is `""` in every
  non-`CONSENSUS` state - never a plausible-looking default answer.
- **Fail-safe direction:** always toward *not* asserting a reconciled answer on
  ambiguous or incomplete machine output. Nothing downstream should ever be able to
  read `resolved_answer` as meaningful unless `state == CONSENSUS` explicitly says so.
- `resolve_query` is always re-callable (subject only to the cooldown) from any prior
  state, including `ERRORED` - there is no terminal "stuck forever" state, matching the
  refreshable-snapshot philosophy VisualClaim's `reverify` already established, not
  ParametricPool's one-shot-settlement philosophy (a Query is a standing oracle
  question, not a personal claim with a single payout to protect from replay).

## 5. Storage layout

```
SourceVerdict:
  source_index: u256
  verdict: str                        # one of candidate_answers, or FETCH_ERROR

Query:
  id: u256
  creator: Address
  question: str                       # immutable
  source_urls: DynArray[str]          # immutable, 2..5 entries
  candidate_answers: DynArray[str]    # immutable, 2..6 entries, always includes UNCLEAR
  resolve_cooldown_seconds: u256      # immutable
  state: str                          # NEVER_RESOLVED | CONSENSUS | NO_CONSENSUS |
                                       # INSUFFICIENT_SOURCES | ERRORED
  resolved_answer: str                # meaningful only when state == CONSENSUS
  last_resolved_at: str
  resolve_count: u256
  source_verdicts: DynArray[SourceVerdict]   # length == len(source_urls), most recent
```

`queries: TreeMap[u256, Query]`, keyed by an incrementing counter - the same registry
pattern as the rest of the portfolio, unbounded in count with small fixed-shape
entries. `source_urls` and `candidate_answers` are capped at `MAX_SOURCES = 5` and
`MAX_ANSWERS = 6` respectively (both caller-declared at creation but bounded), since
both directly size the prompt the equivalence principle must reproduce identically
across validators.

## 6. The consumer interface

```python
@gl.contract_interface
class ISourceConsensus:
    class View:
        def get_query(self, query_id: u256) -> dict: ...
    class Write:
        pass
```

**Pull, not push**, for the same reason as the rest of the portfolio: a consumer calls
`create_query`, then polls `get_query` for `state`/`resolved_answer` after anyone calls
`resolve_query`. No callback is ever made into a consuming contract. See
`examples/consensus_gated_action.py` for a worked consumer that gates an action on
`state == "CONSENSUS"` and a specific `resolved_answer`.

## 7. Trust model

| Role | Powers | Cannot |
|---|---|---|
| Query creator | Declare the question, source list, answer list, and cooldown once, at creation | Cannot edit any of them afterward - no setter exists at all; cannot bias which sources get asked or supply their own evidence |
| Anyone (permissionless) | Call `resolve_query` on any query, including the very first resolution | Cannot resolve it to anything other than what the majority of judged, reachable sources actually supports |

Unlike VisualClaim, there is no "only the claimant may trigger the first check"
restriction anywhere: a Query is a shared, public reconciliation question from the
moment it's created, not a personal claim about the creator's own state, so gating the
first call would serve no protective purpose here. No privileged party can suppress or
bias an outcome: the creator's only power is exercised once, before any resolution
exists, and every subsequent state transition is either pure deterministic vote-counting
or a consensus-judged per-source classification neither the creator nor the resolver
controls.

## 8. Latency budget

- `create_query`: pure deterministic write, ~20-40s on StudioNet.
- `resolve_query`: one consensus round containing up to `MAX_SOURCES = 5` sequential
  page fetches plus one `exec_prompt` - the slowest judged write in the portfolio,
  since ParametricPool and VisualClaim each fetch exactly one thing per round. Expect
  meaningfully longer than either (multiple minutes for a 3-5 source query), which is
  why the integration test's wait budget is the most generous of the three.
