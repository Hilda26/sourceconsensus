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
