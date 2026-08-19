"""
Tests for the worked consumer example (examples/consensus_gated_action.py).
Proves the example genuinely reads SourceConsensus's judged verdict rather
than re-implementing any reconciliation of its own.
"""

from gltest.direct.loader import create_address

from .conftest import install_call_contract_hook

CONTRACT = "examples/consensus_gated_action.py"
SOURCE_CONSENSUS_ADDRESS_SEED = "some_source_consensus"


def _sc_addr_hex(seed=SOURCE_CONSENSUS_ADDRESS_SEED):
    addr = create_address(seed)
    return "0x" + (addr if isinstance(addr, bytes) else bytes(addr.as_bytes)).hex()


def _query_payload(state: str, resolved_answer: str) -> dict:
    return {
        "id": 1,
        "creator": "0x" + "11" * 20,
        "question": "Did event X occur?",
        "source_urls": ["https://a.example.com", "https://b.example.com"],
        "candidate_answers": ["YES", "NO", "UNCLEAR"],
        "resolve_cooldown_seconds": 3600,
        "state": state,
        "resolved_answer": resolved_answer,
        "last_resolved_at": "2026-01-01T00:00:00+00:00",
        "resolve_count": 1,
        "source_verdicts": [],
    }


def test_trigger_succeeds_when_consensus_matches_expected_answer(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _sc_addr_hex())
    install_call_contract_hook(direct_vm, {"get_query": _query_payload("CONSENSUS", "YES")})

    c.trigger_if_consensus_matches(1, "YES")
    assert c.was_triggered(1) is True


def test_trigger_rejects_when_query_has_not_reached_consensus(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _sc_addr_hex())
    install_call_contract_hook(direct_vm, {"get_query": _query_payload("NO_CONSENSUS", "")})

    with direct_vm.expect_revert("has not reached CONSENSUS"):
        c.trigger_if_consensus_matches(1, "YES")
    assert c.was_triggered(1) is False


def test_trigger_rejects_when_resolved_answer_does_not_match_expectation(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _sc_addr_hex())
    install_call_contract_hook(direct_vm, {"get_query": _query_payload("CONSENSUS", "NO")})

    with direct_vm.expect_revert("does not match"):
        c.trigger_if_consensus_matches(1, "YES")


def test_trigger_cannot_be_triggered_twice_for_the_same_query(direct_deploy, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT, _sc_addr_hex())
    install_call_contract_hook(direct_vm, {"get_query": _query_payload("CONSENSUS", "YES")})

    c.trigger_if_consensus_matches(1, "YES")
    with direct_vm.expect_revert("already triggered"):
        c.trigger_if_consensus_matches(1, "YES")
