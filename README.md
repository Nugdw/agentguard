# AgentGuard — Agent ID-Verified Mint Safety Registry

On-chain safety registry for agent-targeted projects on BNB Chain, built for
the Binance Wallet Agent ID Hackathon (submission period 2026-11-18 08:00 UTC
to 2026-12-09 08:00 UTC).

Anyone can read project safety scores. Only verified Agent ID holders can
register projects and vote — every state-changing function checks
`balanceOf(msg.sender) > 0` on the official Agent ID contract
(`0x60B9262456dE011F7d15a54CdD8c48bAaa8B022F`, BNB Chain). One holder address
gets one vote per project and may change it at any time. Because each person
can claim only one non-transferable Agent ID, voting is Sybil-resistant by
design.

## Contract

- `contracts/AgentGuard.sol` — the registry (Solidity 0.8.24, MIT).
- `contracts/MockAgentId.sol` — test-only Agent ID stand-in. NOT deployed to
  mainnet.
- Constructor takes the Agent ID contract address, so mainnet deployment
  passes the official address above and the code is deployed unchanged.

### Owner permissions (full disclosure)
The owner may only (1) deactivate/reactivate a project (spam/impersonation
moderation — existing votes stay readable) and (2) transfer ownership.
The contract holds no user funds, has no withdrawal function, cannot mint,
cannot set fees/taxes, and cannot alter votes. Plain BNB transfers to it
revert. No proxy, no pause, no hidden functions.

### Build & test (verified 2026-11-19)
```
npm install
node scripts/compile.js   # solc 0.8.24, optimizer 200 runs -> build/*.json
node test/test.js         # local Ganache chain, MockAgentId: 13/13 passed
```
AgentGuard runtime bytecode: 6,105 bytes. Tests cover: non-holder register /
vote reverts, registration, duplicate registration revert, Safe/Risky voting,
score in basis points, vote changing, no double-count on re-vote,
unique-interactor counting, owner-only deactivation, inactive-project vote
revert, invalid id revert, plain-transfer rejection.

## Deployment checklist (mainnet, NOT yet done)
1. Deploy `AgentGuard` from the project's own wallet with constructor arg
   `0x60B9262456dE011F7d15a54CdD8c48bAaa8B022F`. Deployment is a one-time
   gas-only cost in BNB (estimate first, confirm before broadcasting).
2. Verify + publish source on BscScan (compiler 0.8.24, optimizer on,
   200 runs, MIT license) — required by the hackathon.
3. Push this repo public on GitHub; the repo URL doubles as the product
   access link until a dedicated front-end page is live.
4. Submit the hackathon project form: name, 1–3 sentence overview,
   BscScan contract link, website/product link, project X link.
5. Drive at least 30 unique Agent ID holder addresses to register or vote
   during the submission period (Innovation Award eligibility) — the
   contract's `uniqueInteractors` counter tracks exactly this metric.

## Hackathon form answers (ready to paste)
- **Project Name:** AgentGuard
- **Project Overview:** AgentGuard is an on-chain safety registry where only
  verified Agent ID holders can register agent-targeted projects and vote
  them Safe or Risky, with scores stored publicly on BNB Chain. It solves
  the flood of unverified, failed, and scam mints targeting Agentic Wallet
  users by making trust Sybil-resistant: one non-transferable Agent ID,
  one vote.
- **Project Contract Address(es):** _(fill after deployment + BscScan
  verification)_
- **Project Website / Product Access Link:** _(GitHub repo URL, then the
  front-end page when live)_
- **Project Social Media Link (X):** https://x.com/dwiutama45
