"""
Direct-mode tests for SourceConsensus.

Naming convention: each test name states the property being verified, not
the mechanics used to verify it.
"""

import json

from .conftest import warp_to

CONTRACT = "contracts/source_consensus.py"

QUESTION = "Did the outage affecting example.com resolve on the stated date?"
ANSWERS = ["YES", "NO", "UNCLEAR"]
SOURCES = [
    "https://source-a.example.com/status",
    "https://source-b.example.com/status",
    "https://source-c.example.com/status",
]
SOURCE_PATTERNS = [r"source-a\.example\.com", r"source-b\.example\.com", r"source-c\.example\.com"]
COOLDOWN = 3600


def _deploy(direct_deploy, direct_vm, sender):
    direct_vm.sender = sender
    return direct_deploy(CONTRACT)


def _create_query(contract, direct_vm, sender, **overrides):
    direct_vm.sender = sender
    args = dict(
        question=QUESTION,
        source_urls=SOURCES,
        candidate_answers=ANSWERS,
        resolve_cooldown_seconds=COOLDOWN,
    )
    args.update(overrides)
    return contract.create_query(
        args["question"], args["source_urls"], args["candidate_answers"], args["resolve_cooldown_seconds"]
    )


def _mock_sources(direct_vm, bodies_by_index: dict) -> None:
    """bodies_by_index: {source index: page body}. Indices not present are
    left unmocked, so gltest's direct web-render raises for them - a real
    fetch failure, not a scripted one."""
    for i, body in bodies_by_index.items():
        direct_vm.mock_web(SOURCE_PATTERNS[i], {"status": 200, "body": body})


def _mock_verdict(direct_vm, per_source: list) -> None:
    direct_vm.mock_llm(
        r"reconciling what multiple independent web sources say",
        json.dumps({"per_source": per_source}),
    )


# ---------------------------------------------------------------------
# Deploy / initial state
# ---------------------------------------------------------------------


def test_fresh_deploy_has_zero_queries(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    assert int(c.query_count()) == 0


# ---------------------------------------------------------------------
# create_query - input validation
# ---------------------------------------------------------------------


def test_create_query_succeeds_and_stores_declared_fields(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    q = c.get_query(query_id)
    assert q["question"] == QUESTION
    assert q["source_urls"] == SOURCES
    assert q["candidate_answers"] == ANSWERS
    assert q["state"] == "NEVER_RESOLVED"
    assert q["resolve_count"] == 0


def test_create_query_rejects_empty_question(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("question must be"):
        _create_query(c, direct_vm, direct_owner, question="")


def test_create_query_rejects_too_few_sources(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("source_urls must have between"):
        _create_query(c, direct_vm, direct_owner, source_urls=[SOURCES[0]])


def test_create_query_rejects_too_many_sources(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    too_many = [f"https://s{i}.example.com" for i in range(6)]
    with direct_vm.expect_revert("source_urls must have between"):
        _create_query(c, direct_vm, direct_owner, source_urls=too_many)


def test_create_query_rejects_non_https_source_url(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("https://"):
        _create_query(c, direct_vm, direct_owner, source_urls=["http://insecure.example.com", SOURCES[1]])


def test_create_query_rejects_duplicate_source_urls(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("unique"):
        _create_query(c, direct_vm, direct_owner, source_urls=[SOURCES[0], SOURCES[0]])


def test_create_query_rejects_missing_unclear_label(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("UNCLEAR"):
        _create_query(c, direct_vm, direct_owner, candidate_answers=["YES", "NO"])


def test_create_query_rejects_duplicate_answer_labels(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("unique"):
        _create_query(c, direct_vm, direct_owner, candidate_answers=["YES", "YES", "UNCLEAR"])


def test_create_query_rejects_out_of_range_cooldown(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("resolve_cooldown_seconds"):
        _create_query(c, direct_vm, direct_owner, resolve_cooldown_seconds=0)


# ---------------------------------------------------------------------
# resolve_query - the judged aggregation path
# ---------------------------------------------------------------------


def test_resolve_query_is_permissionless_from_the_first_call(direct_deploy, direct_vm, direct_owner, direct_alice):
    """Unlike a personal claim, a Query is a shared public oracle - anyone,
    not just the creator, may trigger the very first resolution."""
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes it resolved", 1: "yes, resolved", 2: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "YES"}])
    direct_vm.sender = direct_alice
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "CONSENSUS"


def test_resolve_query_majority_of_three_sources_reaches_consensus(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "no"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "NO"}])
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "CONSENSUS"
    assert q["resolved_answer"] == "YES"
    verdicts = {v["source_index"]: v["verdict"] for v in q["source_verdicts"]}
    assert verdicts == {0: "YES", 1: "YES", 2: "NO"}


def test_resolve_query_scattered_sources_yield_no_consensus(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "no", 2: "unclear"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "NO"}, {"index": 2, "answer": "UNCLEAR"}])
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "NO_CONSENSUS"
    assert q["resolved_answer"] == ""


def test_resolve_query_majority_being_unclear_is_no_consensus_not_a_resolved_unclear_answer(
    direct_deploy, direct_vm, direct_owner
):
    """A strict majority saying UNCLEAR must never be reported as a
    'consensus answer of UNCLEAR' - that is semantically a failure to
    reconcile, not a resolved fact."""
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "hard to tell", 1: "unclear", 2: "yes"})
    _mock_verdict(
        direct_vm,
        [{"index": 0, "answer": "UNCLEAR"}, {"index": 1, "answer": "UNCLEAR"}, {"index": 2, "answer": "YES"}],
    )
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "NO_CONSENSUS"
    assert q["resolved_answer"] == ""


def test_resolve_query_reaches_consensus_despite_one_unreachable_source(direct_deploy, direct_vm, direct_owner):
    """Source index 2 has no mock at all - direct-mode web-render raises
    for it, a real fetch failure - but the other two still agree."""
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}])
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "CONSENSUS"
    assert q["resolved_answer"] == "YES"
    verdicts = {v["source_index"]: v["verdict"] for v in q["source_verdicts"]}
    assert verdicts == {0: "YES", 1: "YES", 2: "FETCH_ERROR"}


def test_resolve_query_below_min_valid_sources_yields_insufficient_sources(direct_deploy, direct_vm, direct_owner):
    """Only one of three sources is reachable - not enough independent
    evidence to reconcile anything, regardless of what that one source says."""
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}])
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "INSUFFICIENT_SOURCES"
    assert q["resolved_answer"] == ""


def test_resolve_query_with_no_sources_reachable_at_all_yields_insufficient_sources(
    direct_deploy, direct_vm, direct_owner
):
    """No mocks at all -> every fetch raises inside leader() -> the
    contract-level {"per_source": []} short-circuit, not a parse error."""
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "INSUFFICIENT_SOURCES"
    assert all(v["verdict"] == "FETCH_ERROR" for v in q["source_verdicts"])


def test_resolve_query_on_unparseable_output_errors_not_denied_or_consensus(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    direct_vm.mock_llm(r"reconciling what multiple independent web sources say", "not json at all, sorry")
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["state"] == "ERRORED"
    assert q["resolved_answer"] == ""


def test_resolve_query_discards_an_answer_label_not_in_the_candidate_set(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(
        direct_vm,
        [{"index": 0, "answer": "MAYBE"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "YES"}],
    )
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "ERRORED"


def test_resolve_query_discards_a_duplicate_source_index(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(
        direct_vm,
        [{"index": 0, "answer": "YES"}, {"index": 0, "answer": "NO"}, {"index": 2, "answer": "YES"}],
    )
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "ERRORED"


def test_resolve_query_discards_an_out_of_range_source_index(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(
        direct_vm,
        [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 99, "answer": "YES"}],
    )
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "ERRORED"


def test_resolve_query_rejects_before_cooldown_elapses(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner, resolve_cooldown_seconds=3600)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "YES"}])
    c.resolve_query(query_id)
    with direct_vm.expect_revert("cooldown"):
        c.resolve_query(query_id)


def test_resolve_query_permitted_again_after_cooldown_elapses(direct_deploy, direct_vm, direct_owner):
    from datetime import datetime, timedelta

    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner, resolve_cooldown_seconds=3600)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "YES"}])
    c.resolve_query(query_id)
    first_resolved_at = c.get_query(query_id)["last_resolved_at"]

    resolved_dt = datetime.fromisoformat(first_resolved_at.replace("Z", "+00:00"))
    warp_to(direct_vm, (resolved_dt + timedelta(seconds=3601)).isoformat())

    direct_vm.clear_mocks()
    _mock_sources(direct_vm, {0: "no", 1: "no", 2: "no"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "NO"}, {"index": 1, "answer": "NO"}, {"index": 2, "answer": "NO"}])
    c.resolve_query(query_id)
    q = c.get_query(query_id)
    assert q["resolve_count"] == 2
    assert q["resolved_answer"] == "NO"


def test_resolve_query_after_errored_can_be_retried_by_anyone_once_cooldown_allows(
    direct_deploy, direct_vm, direct_owner, direct_alice
):
    from datetime import datetime, timedelta

    c = _deploy(direct_deploy, direct_vm, direct_owner)
    query_id = _create_query(c, direct_vm, direct_owner, resolve_cooldown_seconds=1)
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    direct_vm.mock_llm(r"reconciling what multiple independent web sources say", "garbage")
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "ERRORED"

    errored_at = c.get_query(query_id)["last_resolved_at"]
    errored_dt = datetime.fromisoformat(errored_at.replace("Z", "+00:00"))
    warp_to(direct_vm, (errored_dt + timedelta(seconds=2)).isoformat())

    direct_vm.clear_mocks()
    _mock_sources(direct_vm, {0: "yes", 1: "yes", 2: "yes"})
    _mock_verdict(direct_vm, [{"index": 0, "answer": "YES"}, {"index": 1, "answer": "YES"}, {"index": 2, "answer": "YES"}])
    direct_vm.sender = direct_alice
    c.resolve_query(query_id)
    assert c.get_query(query_id)["state"] == "CONSENSUS"


# ---------------------------------------------------------------------
# Unknown ids
# ---------------------------------------------------------------------


def test_operations_on_unknown_query_id_revert(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_vm, direct_owner)
    with direct_vm.expect_revert("unknown query_id"):
        c.get_query(999)
