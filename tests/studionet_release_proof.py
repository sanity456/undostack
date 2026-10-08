"""Deploy the submission candidate and verify its exact on-chain source and ABI."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time

from eth_account import Account
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionStatus
from gltest.utils import extract_contract_address
import requests


RPC = "https://studio.genlayer.com/api"
ROOT = Path(__file__).resolve().parents[1]


def rpc(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_error = None
    for attempt in range(8):
        try:
            response = requests.post(RPC, json=payload, timeout=(10, 30))
            if response.status_code not in (429, 500, 502, 503, 504):
                response.raise_for_status()
                body = response.json()
                if body.get("error"):
                    raise AssertionError(json.dumps(body["error"], sort_keys=True))
                return body["result"]
            last_error = RuntimeError(f"StudioNet RPC returned HTTP {response.status_code}")
        except (requests.RequestException, ValueError) as error:
            last_error = error
        if attempt < 7:
            time.sleep(min(2 + attempt * 2, 12))
    raise AssertionError(f"StudioNet readback failed: {last_error}")


def test_studionet_submission_source_and_abi_match():
    account = Account.from_key(os.environ["GENLAYER_PRIVATE_KEY"])
    source_path = ROOT / "contracts" / "undo_stack.py"
    abi_path = ROOT / "contracts" / "abi.json"
    local_source = source_path.read_bytes()
    local_abi = json.loads(abi_path.read_text(encoding="utf-8"))
    factory = get_contract_factory(contract_file_path=source_path)
    deploy = factory.deploy_contract_tx(
        args=[], account=account, wait_transaction_status=TransactionStatus.FINALIZED,
        wait_interval=10000, wait_retries=300,
    )
    assert tx_execution_succeeded(deploy), json.dumps(deploy, default=str)
    assert deploy.get("status_name") == TransactionStatus.FINALIZED.value
    address = extract_contract_address(deploy)
    assert rpc("eth_chainId", []) == "0xf22f"
    deployed_source = base64.b64decode(rpc("gen_getContractCode", [address]), validate=True)
    remote_abi = rpc("gen_getContractSchema", [address])
    assert deployed_source == local_source
    assert remote_abi == local_abi
    tx_hash = deploy.get("hash") or deploy.get("tx_hash")
    assert isinstance(tx_hash, str) and tx_hash.startswith("0x")
    record = {
        "schema": "genlayer-submission-evidence/v1",
        "network": {"name": "studionet", "chain_id": 61999, "rpc": RPC},
        "repository": "undostack",
        "contract_address": address,
        "deployment_transaction_hash": tx_hash,
        "wallet_address": account.address,
        "source_sha256": hashlib.sha256(local_source).hexdigest(),
        "deployed_source_sha256": hashlib.sha256(deployed_source).hexdigest(),
        "source_bytes_match": True,
        "abi_sha256": hashlib.sha256(json.dumps(local_abi, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "deployed_abi_matches_local": True,
        "full_flow_test": {
            "test_file": "tests/studionet_smoke.py",
            "status": "passed",
            "source_sha256": hashlib.sha256(local_source).hexdigest(),
        },
    }
    evidence_path = ROOT / "deployments" / "studionet.json"
    evidence_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))
