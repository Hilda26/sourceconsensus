import os
import pytest
from gltest import get_contract_factory, get_accounts, get_default_account

CONTRACT_PATH = "source_consensus.py"


def _address_from_env() -> str | None:
    return os.environ.get("SOURCECONSENSUS_ADDRESS")


@pytest.fixture(scope="session")
def deployed_contract():
    """
    Connects to an already-deployed SourceConsensus instead of deploying a
    fresh one. Set SOURCECONSENSUS_ADDRESS to the address printed by:

        genlayer deploy --contract contracts/source_consensus.py

    Tests in this module are skipped (not failed) when the env var is
    absent, so `pytest tests/integration` is safe to run before deploying.
    """
    address = _address_from_env()
    if not address:
        pytest.skip(
            "SOURCECONSENSUS_ADDRESS not set - deploy manually first with "
            "`genlayer deploy --contract contracts/source_consensus.py` and "
            "export the printed address."
        )
    factory = get_contract_factory(contract_file_path=CONTRACT_PATH)
    return factory.build_contract(contract_address=address)


@pytest.fixture(scope="session")
def creator_account():
    return get_default_account()


@pytest.fixture(scope="session")
def resolver_account():
    accounts = get_accounts()
    if len(accounts) > 1:
        return accounts[1]
    from gltest import create_account

    return create_account()
