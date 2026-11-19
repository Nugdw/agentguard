#!/usr/bin/env python3
"""Deploy AgentGuard + MockAgentId to BSC Testnet (chain 97) from the
MUSE BETA dev vault address #0. The private key is derived in memory
from the vault and never printed or written anywhere."""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/hatch/workspace/muse-beta-1.0")
from muse import core, vault as vault_mod  # noqa: E402

RPCS = [
    "https://data-seed-prebsc-1-s1.binance.org:8545",
    "https://bsc-testnet-rpc.publicnode.com",
    "https://data-seed-prebsc-2-s1.binance.org:8545",
]
CHAIN_ID = 97
EXPECTED = "0xc151Ab1a8Ab306Fb8DC81E755d9e582405Fc61E0"
ROOT = "/home/hatch/workspace/agentguard"


def rpc(method, params):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    last = None
    for url in RPCS:
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0"},
            )
            out = json.load(urllib.request.urlopen(req, timeout=25))
            if "error" in out:
                raise RuntimeError(str(out["error"]))
            return out["result"]
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"all RPCs failed for {method}: {last}")


def load(name):
    with open(f"{ROOT}/build/{name}.json") as f:
        return json.load(f)


def send(priv, sender, to_bytes, data_bytes, gas, gas_price, nonce, value=0):
    fields = [nonce, gas_price, gas, to_bytes, value, data_bytes]
    raw = core.sign_legacy(fields, priv, CHAIN_ID)
    txh = rpc("eth_sendRawTransaction", ["0x" + raw.hex()])
    for _ in range(60):
        time.sleep(3)
        rec = rpc("eth_getTransactionReceipt", [txh])
        if rec:
            if rec["status"] != "0x1":
                raise RuntimeError(f"tx {txh} reverted")
            return txh, rec
    raise RuntimeError(f"tx {txh} not mined in time")


def enc_addr(a):
    return bytes(12) + bytes.fromhex(a[2:])


def call(to, data_hex):
    return rpc("eth_call", [{"to": to, "data": data_hex}, "latest"])


def main():
    with open("/home/hatch/workspace/muse-beta-1.0/state/passphrase.txt") as f:
        passphrase = f.read().strip()
    v = vault_mod.Vault(
        "/home/hatch/workspace/muse-beta-1.0/state/vault.json"
    ).unlock(passphrase)
    address, priv = core.derive_account(
        v.data["mnemonic"], 0, v.data.get("passphrase", "")
    )
    assert address.lower() == EXPECTED.lower(), f"address mismatch: {address}"
    print("deployer:", address)

    bal = int(rpc("eth_getBalance", [address, "latest"]), 16)
    print("tBNB balance wei:", bal)
    if bal == 0:
        print("NOT_FUNDED: claim tBNB from a faucet first")
        return 2
    gas_price = int(rpc("eth_gasPrice", []), 16)
    nonce = int(rpc("eth_getTransactionCount", [address, "latest"]), 16)

    mock = load("MockAgentId")
    ag = load("AgentGuard")

    # 1. Deploy MockAgentId
    data = bytes.fromhex(mock["bytecode"])
    est = int(rpc("eth_estimateGas",
                  [{"from": address, "data": "0x" + data.hex()}]), 16)
    txh, rec = send(priv, address, b"", data, int(est * 1.2) + 10000,
                    gas_price, nonce)
    mock_addr = rec["contractAddress"]
    print("MockAgentId:", mock_addr, "tx:", txh, "gasUsed:", int(rec["gasUsed"], 16))
    nonce += 1

    # 2. Deploy AgentGuard(mock)
    data = bytes.fromhex(ag["bytecode"]) + enc_addr(mock_addr)
    est = int(rpc("eth_estimateGas",
                  [{"from": address, "data": "0x" + data.hex()}]), 16)
    txh, rec = send(priv, address, b"", data, int(est * 1.2) + 10000,
                    gas_price, nonce)
    ag_addr = rec["contractAddress"]
    print("AgentGuard:", ag_addr, "tx:", txh, "gasUsed:", int(rec["gasUsed"], 16))
    nonce += 1

    # 3. Live test: mint mock Agent ID to deployer, register, vote Safe
    sel_mint = core.keccak256(b"mint(address)")[:4]
    txh, rec = send(priv, address, bytes.fromhex(mock_addr[2:]),
                    sel_mint + enc_addr(address), 100000, gas_price, nonce)
    print("mock mint tx:", txh)
    nonce += 1

    def enc_str(s):
        b = s.encode()
        pad = (32 - len(b) % 32) % 32
        return len(b).to_bytes(32, "big") + b + bytes(pad)

    sel_reg = core.keccak256(b"registerProject(address,string,string)")[:4]
    head = enc_addr("0x000000000000000000000000000000000000dEaD")
    name_b = enc_str("AgentGuard Self-Test")
    uri_b = enc_str("https://example.org/agentguard-selftest")
    off1 = 96
    off2 = off1 + len(name_b)
    data = (sel_reg + head + off1.to_bytes(32, "big") +
            off2.to_bytes(32, "big") + name_b + uri_b)
    txh, rec = send(priv, address, bytes.fromhex(ag_addr[2:]), data,
                    400000, gas_price, nonce)
    print("registerProject tx:", txh)
    nonce += 1

    sel_vote = core.keccak256(b"vote(uint256,uint8,string)")[:4]
    note_b = enc_str("self-test vote")
    data = (sel_vote + (1).to_bytes(32, "big") + (1).to_bytes(32, "big") +
            (96).to_bytes(32, "big") + note_b)
    txh, rec = send(priv, address, bytes.fromhex(ag_addr[2:]), data,
                    300000, gas_price, nonce)
    print("vote Safe tx:", txh)
    nonce += 1

    sel_score = "0x" + core.keccak256(b"getScore(uint256)")[:4].hex()
    out = call(ag_addr, sel_score + (1).to_bytes(32, "big").hex())
    words = [int(out[2 + i * 64: 2 + (i + 1) * 64], 16) for i in range(4)]
    print("getScore(1) safe/risky/total/bps:", words)
    assert words == [1, 0, 1, 10000], "score mismatch"
    sel_uniq = "0x" + core.keccak256(b"uniqueInteractors()")[:4].hex()
    uniq = int(call(ag_addr, sel_uniq), 16)
    print("uniqueInteractors:", uniq)
    assert uniq == 1

    record = {
        "network": "bsc-testnet",
        "chainId": 97,
        "deployer": address,
        "mockAgentId": mock_addr,
        "agentGuard": ag_addr,
        "explorer": f"https://testnet.bscscan.com/address/{ag_addr}",
    }
    import os
    os.makedirs(f"{ROOT}/deployments", exist_ok=True)
    with open(f"{ROOT}/deployments/testnet.json", "w") as f:
        json.dump(record, f, indent=2)
    print("LIVE_TEST_OK", json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
