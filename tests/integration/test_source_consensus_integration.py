"""
Full-surface integration test against a StudioNet-deployed SourceConsensus.
Requires SOURCECONSENSUS_ADDRESS (see conftest.py).

resolve_query is the slowest judged write in this portfolio: up to
MAX_SOURCES real page fetches plus one exec_prompt, all inside a single
consensus round, so this uses a generous wait_interval/wait_retries.
"""

import pytest
from gltest.assertions import tx_execution_succeeded, tx_execution_failed

FAST_WAIT = dict(wait_interval=3000, wait_retries=30)
SLOW_WAIT = dict(wait_interval=6000, wait_retries=100)

# Real, stable, publicly-fetchable pages on different domains - not
# synthetic fixtures, and deliberately NOT all under one domain so page
# chrome/branding from a single site can't make every source agree by
# accident.
SOURCES = [
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://www.python.org/",
    "https://en.wikipedia.org/wiki/Photosynthesis",
]
QUESTION = "Is this page primarily about the Python programming language?"
ANSWERS = ["YES", "NO", "UNCLEAR"]
COOLDOWN = 3600


@pytest.mark.integration
def test_full_surface_drives_create_and_resolve_and_reads_every_view(deployed_contract, creator_account, resolver_account):
    c = deployed_contract
    creator = c.connect(creator_account)
    resolver = c.connect(resolver_account)

    # --- deterministic write ---------------------------------------------
    create_result = creator.create_query(args=[QUESTION, SOURCES, ANSWERS, COOLDOWN]).transact(**FAST_WAIT)
    assert tx_execution_succeeded(create_result), create_result
    query_id = int(c.query_count(args=[]).call()) - 1
    query = c.get_query(args=[query_id]).call()
    print("created query:", query)
    assert query["state"] == "NEVER_RESOLVED"
    assert query["resolve_count"] == 0

    # --- the slow judged write: 3 real fetches + 1 exec_prompt, one round --
    resolve_result = resolver.resolve_query(args=[query_id]).transact(**SLOW_WAIT)
    print("resolve_query receipt:", resolve_result)
    assert tx_execution_succeeded(resolve_result), (
        "resolve_query failed or returned UNDETERMINED - known retryable "
        "StudioNet behavior; rerun this test if so"
    )
    resolved = c.get_query(args=[query_id]).call()
    print("resolved query:", resolved)
    assert resolved["state"] in ("CONSENSUS", "NO_CONSENSUS", "INSUFFICIENT_SOURCES", "ERRORED"), resolved
    assert resolved["resolve_count"] == 1
    assert len(resolved["source_verdicts"]) == len(SOURCES)
    for v in resolved["source_verdicts"]:
        assert v["verdict"] == "FETCH_ERROR" or v["verdict"] in ANSWERS

    # --- cooldown enforcement ----------------------------------------------
    second_attempt = resolver.resolve_query(args=[query_id]).transact(**FAST_WAIT)
    assert tx_execution_failed(second_attempt), "resolve_query before cooldown should fail"

    # --- create_query input validation reverts on-chain too ----------------
    bad_create = creator.create_query(args=["Q", ["http://insecure.example.com"], ANSWERS, COOLDOWN]).transact(
        **FAST_WAIT
    )
    assert tx_execution_failed(bad_create), "non-https source_url should be rejected"

    # --- unknown id reverts --------------------------------------------------
    with pytest.raises(Exception):
        c.get_query(args=[999999]).call()


@pytest.mark.integration
def test_resolve_query_with_one_unreachable_source_completes_without_genvm_or_consensus_error(
    deployed_contract, creator_account, resolver_account
):
    """
    Two real, reachable, clearly-opposed sources plus one source on a
    domain that does not resolve at all. Proves a real fetch failure is
    absorbed as a per-source FETCH_ERROR by the contract - never a GenVM
    execution error, never a failed/undetermined consensus round.
    """
    c = deployed_contract
    creator = c.connect(creator_account)
    resolver = c.connect(resolver_account)

    sources = [
        "https://en.wikipedia.org/wiki/Dog",
        "https://en.wikipedia.org/wiki/Cat",
        "https://this-domain-does-not-exist-zzz999xyz.com/",
    ]
    question = "Is this page primarily about dogs?"

    create_result = creator.create_query(args=[question, sources, ANSWERS, COOLDOWN]).transact(**FAST_WAIT)
    assert tx_execution_succeeded(create_result), create_result
    query_id = int(c.query_count(args=[]).call()) - 1

    resolve_result = resolver.resolve_query(args=[query_id]).transact(**SLOW_WAIT)
    print("unreachable-source resolve_query receipt:", resolve_result)
    assert tx_execution_succeeded(resolve_result), (
        "resolve_query must succeed at the consensus/GenVM level even when "
        "one declared source is genuinely unreachable"
    )
    resolved = c.get_query(args=[query_id]).call()
    print("resolved query (one unreachable source):", resolved)
    assert resolved["state"] != "ERRORED", (
        "a real fetch failure must never surface as a parse/judgment ERRORED state"
    )
    verdicts = {v["source_index"]: v["verdict"] for v in resolved["source_verdicts"]}
    assert verdicts.get(2) == "FETCH_ERROR", "the unreachable domain must be recorded as FETCH_ERROR, not guessed"
    assert verdicts.get(0) in ANSWERS
    assert verdicts.get(1) in ANSWERS


@pytest.mark.integration
def test_resolve_query_with_maximum_five_sources_completes_without_genvm_or_consensus_error(
    deployed_contract, creator_account, resolver_account
):
    """Stress the upper bound: MAX_SOURCES=5 real fetches plus one
    exec_prompt, all inside a single consensus round, must still finalize
    cleanly - no GenVM execution error, no failed/undetermined round."""
    c = deployed_contract
    creator = c.connect(creator_account)
    resolver = c.connect(resolver_account)

    sources = [
        "https://en.wikipedia.org/wiki/HTML",
        "https://en.wikipedia.org/wiki/CSS",
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Photosynthesis",
        "https://en.wikipedia.org/wiki/Chess",
    ]
    question = "Is this page primarily about a programming or markup language?"

    create_result = creator.create_query(args=[question, sources, ANSWERS, COOLDOWN]).transact(**FAST_WAIT)
    assert tx_execution_succeeded(create_result), create_result
    query_id = int(c.query_count(args=[]).call()) - 1

    generous_wait = dict(wait_interval=6000, wait_retries=150)
    resolve_result = resolver.resolve_query(args=[query_id]).transact(**generous_wait)
    print("5-source resolve_query receipt:", resolve_result)
    assert tx_execution_succeeded(resolve_result), (
        "a 5-source judged round must complete at the consensus/GenVM level "
        "without erroring, even though it is the slowest round this "
        "contract can produce"
    )
    resolved = c.get_query(args=[query_id]).call()
    print("resolved query (5 sources):", resolved)
    assert resolved["state"] != "ERRORED"
    assert len(resolved["source_verdicts"]) == 5
    for v in resolved["source_verdicts"]:
        assert v["verdict"] == "FETCH_ERROR" or v["verdict"] in ANSWERS
