"""Opt-in StudioNet consensus smoke test. Requires GENLAYER_PRIVATE_KEY."""
import json
import os
from pathlib import Path
import time

from eth_account import Account
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionHashVariant, TransactionStatus
from gltest.utils import extract_contract_address
import requests


_requests_post = requests.post
_READ_ONLY_RPC_METHODS = {
    "eth_call",
    "eth_chainId",
    "eth_getTransactionByHash",
    "eth_getTransactionCount",
    "gen_getContractCode",
    "gen_getContractSchema",
}


def _post_with_read_only_retries(url, *args, **kwargs):
    payload = kwargs.get("json")
    if not isinstance(payload, dict) or payload.get("method") not in _READ_ONLY_RPC_METHODS:
        return _requests_post(url, *args, **kwargs)
    kwargs.setdefault("timeout", (10, 30))
    last_error = None
    for attempt in range(8):
        try:
            response = _requests_post(url, *args, **kwargs)
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status_code not in (429, 500, 502, 503, 504) and "json" in content_type:
                return response
            last_error = RuntimeError(f"receipt poll returned HTTP {response.status_code}")
        except requests.exceptions.RequestException as error:
            last_error = error
        if attempt < 7:
            time.sleep(min(2 + attempt * 2, 12))
    raise last_error


requests.post = _post_with_read_only_retries


def test_studionet_reverse_dependency_rollback():
    private_key = os.environ["GENLAYER_PRIVATE_KEY"]
    account = Account.from_key(private_key)
    source = Path(__file__).resolve().parents[1] / "contracts" / "undo_stack.py"
    factory = get_contract_factory(contract_file_path=source)
    deploy = factory.deploy_contract_tx(args=[], account=account, wait_transaction_status=TransactionStatus.FINALIZED, wait_interval=10000, wait_retries=300)
    assert tx_execution_succeeded(deploy), json.dumps(deploy, default=str)
    contract = factory.build_contract(extract_contract_address(deploy), account=account)

    def send(tx):
        receipt = tx.transact(wait_transaction_status=TransactionStatus.FINALIZED, wait_interval=10000, wait_retries=300)
        assert tx_execution_succeeded(receipt), json.dumps(receipt, default=str)
        return receipt

    send(contract.create_flow(args=["smoke", "Community event at 18:00 using table T1 and chair set C1."]))
    flow_id = account.address.lower() + ":smoke"
    send(contract.add_step(args=[flow_id, "Reserve table T1 for the community event at 18:00.", "Release the reservation for table T1.", account.address, []]))
    send(contract.add_step(args=[flow_id, "Reserve chair set C1 for the community event at 18:00.", "Release the reservation for chair set C1.", account.address, [0]]))
    send(contract.activate(args=[flow_id]))
    binding = json.loads(contract.get_flow(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL))["plan_hash"]
    for index in range(2):
        send(contract.start_step(args=[flow_id, index, binding]))
        if index == 0:
            report = "Venue confirms table T1 is reserved for the community event at 18:00 under reference TAB-001; the reservation is active."
        else:
            report = "Venue confirms chair set C1 is reserved for the community event at 18:00 under reference CHA-001; the reservation is active."
        send(contract.report_step(args=[flow_id, index, report]))
        state = json.loads(contract.get_flow(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL))
        assert state["steps"][index]["state"] == "DONE", json.dumps(state, sort_keys=True)
    send(contract.cancel(args=[flow_id, "The event was cancelled."]))
    state = json.loads(contract.get_flow(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL))
    assert state["state"] == "UNWINDING", json.dumps(state, sort_keys=True)
    assert contract.ready_undos(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL) == [1], json.dumps(state, sort_keys=True)
    send(contract.report_undo(args=[flow_id, 1, "Venue confirms reference CHA-001 was cancelled, chair set C1 released, and no booking remains."]))
    assert contract.ready_undos(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL) == [0]
    send(contract.report_undo(args=[flow_id, 0, "Venue confirms reference TAB-001 was cancelled, table T1 released, and no booking remains."]))
    state = json.loads(contract.get_flow(args=[flow_id]).call(transaction_hash_variant=TransactionHashVariant.LATEST_FINAL))
    assert state["state"] == "ROLLED_BACK"
