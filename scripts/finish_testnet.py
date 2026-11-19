#!/usr/bin/env python3
"""Finish the AgentGuard testnet live test after the deploys + mock mint
already landed (deploy_testnet.py stopped on a dropped RPC connection
whose mint transaction had in fact been accepted: nonce 3, balanceOf 1).

Performs: registerProject -> vote Safe -> getScore/uniqueInteractors
asserts -> writes deployments/testnet.json. Idempotent guard: refuses to
register if projectCount is already > 0.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/hatch/workspace/muse-beta-1.0")
sys.path.insert(0, "/home/hatch/workspace/.kvenv/lib/python3.12/site-packages")

from muse import core, vault as vault_mod  # noqa: E402
from muse import tx as tx_mod  # noqa: E402

ROOT = "/home/hatch/workspace/agentguard"
VAULT = "/home/hatch/workspace/muse-beta-1.0/state/vault.json"
PASS = "/home/hatch/workspace/muse-beta-1.0/state/passphrase.txt"
CHAIN_ID = 97
EXPECTED = "0x7FE3C3944bA1aD65c86BD563DeEe7a0990dE4DB5"
MOCK = "0x7ea373fab1feb768b0a5b17990e5d8a655b90965"
AG = "0x6e84b8a8a1c99e46e68beacaf7d1fe413504b405"
RPCS = [
    "https://data-seed-prebsc-1-s2.binance.org:8545",
    "https://data-seed-prebsc-2-s2.binance.org:8545",
    "https://data-seed-prebsc-1-s1.binance.org:8545",
    "https://data-seed-prebsc-2-s1.binance.org:8545",
]


def rpc(method, params):
    last = None
    for attempt in range(3):
        for url in RPCS:
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"jsonrpc": "2.0", "id": 1,
                                     "method": method, "params": params}).encode(),
                    headers={"Content-Type": "application/json",
                             "User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    out = json.load(r)
                if "error" in out:
                    raise RuntimeError(str(out["error"]))
                return out["result"]
            except Exception as e:  # noqa: BLE001
                last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"all RPCs failed for {method}: {last}")


def call(to, data_hex):
    return rpc("eth_call", [{"to": to, "data": data_hex}, "latest"])


def send(priv, frm, to_bytes, data, gas, gas_price, nonce):
    fields = [nonce, gas_price, gas, to_bytes, 0, data]
    raw = tx_mod.sign_legacy(fields, priv, CHAIN_ID)
    txh = rpc("eth_sendRawTransaction", ["0x" + raw.hex()])
    for _ in range(40):
        rec = rpc("eth_getTransactionReceipt", [txh])
        if rec:
            if int(rec["status"], 16) != 1:
                raise RuntimeError(f"tx reverted: {txh}")
            return txh, rec
        time.sleep(3)
    raise RuntimeError(f"no receipt for {txh}")


def enc_addr(a):
    return bytes(12) + bytes.fromhex(a[2:])


def enc_str(s):
    b = s.encode()
    pad = (32 - len(b) % 32) % 32
    return len(b).to_bytes(32, "big") + b + bytes(pad)


def main():
    with open(PASS) as f:
        passphrase = f.read().strip()
    v = vault_mod.Vault(VAULT)
    v.unlock(passphrase)
    address, priv = core.derive_account(v.data["mnemonic"], 0)
    assert address.lower() == EXPECTED.lower(), address

    nonce = int(rpc("eth_getTransactionCount", [address, "latest"]), 16)
    print("nonce:", nonce)
    assert nonce == 3, f"expected nonce 3 (2 deploys + mint), got {nonce}"
    bal = int(call(MOCK, "0x70a08231" + address[2:].lower().rjust(64, "0")), 16)
    assert bal == 1, f"mock balanceOf {bal}"
    gas_price = int(rpc("eth_gasPrice", []), 16)
    print("gasPrice wei:", gas_price)

    sel_count = "0x" + core.keccak256(b"projectCount()")[:4].hex()
    count = int(call(AG, sel_count), 16)
    print("projectCount:", count)
    assert count == 0, "project already registered"

    sel_reg = core.keccak256(b"registerProject(address,string,string)")[:4]
    head = enc_addr("0x000000000000000000000000000000000000dEaD")
    name_b = enc_str("AgentGuard Self-Test")
    uri_b = enc_str("https://example.org/agentguard-selftest")
    off1 = 96
    off2 = off1 + len(name_b)
    data = (sel_reg + head + off1.to_bytes(32, "big") +
            off2.to_bytes(32, "big") + name_b + uri_b)
    txh, _ = send(priv, address, bytes.fromhex(AG[2:]), data, 400000, gas_price, nonce)
    print("registerProject tx:", txh)
    nonce += 1

    sel_vote = core.keccak256(b"vote(uint256,uint8,string)")[:4]
    note_b = enc_str("self-test vote")
    data = (sel_vote + (1).to_bytes(32, "big") + (1).to_bytes(32, "big") +
            (96).to_bytes(32, "big") + note_b)
    txh, _ = send(priv, address, bytes.fromhex(AG[2:]), data, 300000, gas_price, nonce)
    print("vote Safe tx:", txh)
    nonce += 1

    sel_score = "0x" + core.keccak256(b"getScore(uint256)")[:4].hex()
    out = call(AG, sel_score + (1).to_bytes(32, "big").hex())
    words = [int(out[2 + i * 64: 2 + (i + 1) * 64], 16) for i in range(4)]
    print("getScore(1) safe/risky/total/bps:", words)
    assert words == [1, 0, 1, 10000], "score mismatch"
    sel_uniq = "0x" + core.keccak256(b"uniqueInteractors()")[:4].hex()
    uniq = int(call(AG, sel_uniq), 16)
    print("uniqueInteractors:", uniq)
    assert uniq == 1

    record = {
        "network": "bsc-testnet",
        "chainId": 97,
        "deployer": address,
        "mockAgentId": MOCK,
        "agentGuard": AG,
        "explorer": f"https://testnet.bscscan.com/address/{AG}",
    }
    import os
    os.makedirs(f"{ROOT}/deployments", exist_ok=True)
    with open(f"{ROOT}/deployments/testnet.json", "w") as f:
        json.dump(record, f, indent=2)
    print("LIVE_TEST_OK", json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
