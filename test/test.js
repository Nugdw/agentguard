const assert = require("assert");
const ganache = require("ganache");
const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

function load(name) {
  return JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "build", name + ".json"), "utf8")
  );
}

(async () => {
  const provider = new ethers.BrowserProvider(
    ganache.provider({ logging: { quiet: true } })
  );
  const owner = await provider.getSigner(0);
  const alice = await provider.getSigner(1); // Agent ID holder
  const bob = await provider.getSigner(2); // Agent ID holder
  const carol = await provider.getSigner(3); // NOT a holder

  const mockArt = load("MockAgentId");
  const mock = await new ethers.ContractFactory(
    mockArt.abi, mockArt.bytecode, owner
  ).deploy();
  await mock.waitForDeployment();
  await (await mock.mint(await alice.getAddress())).wait();
  await (await mock.mint(await bob.getAddress())).wait();

  const agArt = load("AgentGuard");
  const ag = await new ethers.ContractFactory(
    agArt.abi, agArt.bytecode, owner
  ).deploy(await mock.getAddress());
  await ag.waitForDeployment();
  console.log("deployed AgentGuard at", await ag.getAddress());

  const results = [];
  const check = (name, cond) => {
    results.push([name, !!cond]);
    if (!cond) console.log("FAIL:", name);
  };
  const reverts = async (name, promise) => {
    try {
      const tx = await promise;
      if (tx && tx.wait) await tx.wait();
      check(name, false);
    } catch (e) {
      check(name, true);
    }
  };

  // 1. Non-holder cannot register
  await reverts(
    "non-holder register reverts",
    ag.connect(carol).registerProject(ethers.ZeroAddress, "X", "https://x.example")
  );
  // 2. Holder registers a project
  const target = "0x000000000000000000000000000000000000dEaD";
  await (await ag.connect(alice).registerProject(target, "TestMint", "https://test.example")).wait();
  check("projectCount==1", (await ag.projectCount()) === 1n);
  // 3. Duplicate contract registration reverts
  await reverts(
    "duplicate register reverts",
    ag.connect(bob).registerProject(target, "Dup", "https://dup.example")
  );
  // 4. Non-holder cannot vote
  await reverts("non-holder vote reverts", ag.connect(carol).vote(1, 1, ""));
  // 5. Holder votes Safe -> score 10000 bps
  await (await ag.connect(alice).vote(1, 1, "looks fine")).wait();
  let s = await ag.getScore(1);
  check("score after 1 safe = 10000", s[0] === 1n && s[1] === 0n && s[3] === 10000n);
  // 6. Second holder votes Risky -> score 5000 bps
  await (await ag.connect(bob).vote(1, 2, "unverified source")).wait();
  s = await ag.getScore(1);
  check("score 1v1 = 5000", s[0] === 1n && s[1] === 1n && s[3] === 5000n);
  // 7. Changing a vote moves tallies (bob Risky -> Safe): 2 safe, 0 risky
  await (await ag.connect(bob).vote(1, 1, "verified now")).wait();
  s = await ag.getScore(1);
  check("after change = 2 safe", s[0] === 2n && s[1] === 0n && s[3] === 10000n);
  // 8. Re-voting same choice does not double count
  await (await ag.connect(bob).vote(1, 1, "still safe")).wait();
  s = await ag.getScore(1);
  check("re-vote no double count", s[0] === 2n && s[2] === 2n);
  // 9. uniqueInteractors = alice + bob = 2
  check("uniqueInteractors==2", (await ag.uniqueInteractors()) === 2n);
  // 10. Non-owner cannot deactivate; owner can; votes then blocked
  await reverts("non-owner deactivate reverts", ag.connect(alice).setProjectActive(1, false));
  await (await ag.connect(owner).setProjectActive(1, false)).wait();
  await reverts("vote on inactive reverts", ag.connect(alice).vote(1, 2, ""));
  // 11. Invalid project id reverts on read
  await reverts("getScore(99) reverts", ag.getScore(99));
  // 12. Plain BNB transfer is rejected
  await reverts(
    "plain transfer reverts",
    alice.sendTransaction({ to: await ag.getAddress(), value: 1n })
  );

  const failed = results.filter(([, ok]) => !ok);
  console.log("TESTS " + (results.length - failed.length) + "/" + results.length + " passed");
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
