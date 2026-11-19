const ganache = require("ganache");
const { ethers } = require("ethers");
const fs = require("fs");
(async () => {
  const provider = new ethers.BrowserProvider(ganache.provider({ logging: { quiet: true } }));
  const owner = await provider.getSigner(0);
  const mockArt = JSON.parse(fs.readFileSync("build/MockAgentId.json", "utf8"));
  const mock = await new ethers.ContractFactory(mockArt.abi, mockArt.bytecode, owner).deploy();
  await mock.waitForDeployment();
  const agArt = JSON.parse(fs.readFileSync("build/AgentGuard.json", "utf8"));
  const factory = new ethers.ContractFactory(agArt.abi, agArt.bytecode, owner);
  const deployTx = await factory.getDeployTransaction(await mock.getAddress());
  const est = await provider.estimateGas({ ...deployTx, from: await owner.getAddress() });
  console.log("DEPLOY_GAS_ESTIMATE=" + est.toString());
})();
