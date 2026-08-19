# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

# ---------------------------------------------------------------------------
# ConsensusGatedAction - a worked consumer of the SourceConsensus primitive.
#
# Any contract that needs to act on "what do multiple independent sources
# actually agree happened" - a DAO paying out a bounty on a reconciled news
# event, a prediction market settling on a reconciled outcome - can gate on
# a SourceConsensus Query reaching CONSENSUS for a specific expected answer,
# instead of writing its own multi-source fetch-and-reconcile logic. This
# example contains none of SourceConsensus's fetch/judgment machinery, it
# only reads a verdict SourceConsensus already reached.
# ---------------------------------------------------------------------------


@gl.contract_interface
class ISourceConsensus:
    class View:
        def get_query(self, query_id: u256) -> dict: ...

    class Write:
        pass


class ConsensusGatedAction(gl.Contract):
    source_consensus_address: Address
    triggered: TreeMap[u256, bool]

    def __init__(self, source_consensus_address: str):
        addr = (
            source_consensus_address
            if isinstance(source_consensus_address, Address)
            else Address(source_consensus_address)
        )
        self.source_consensus_address = addr

    @gl.public.write
    def trigger_if_consensus_matches(self, query_id: u256, expected_answer: str) -> None:
        if query_id in self.triggered:
            raise gl.vm.UserError("already triggered for this query")

        query = ISourceConsensus(self.source_consensus_address).view().get_query(query_id)

        if query["state"] != "CONSENSUS":
            raise gl.vm.UserError("query has not reached CONSENSUS")
        if query["resolved_answer"] != expected_answer:
            raise gl.vm.UserError("resolved answer does not match what was expected")

        self.triggered[query_id] = True

    @gl.public.view
    def was_triggered(self, query_id: u256) -> bool:
        return self.triggered.get(query_id, False)
