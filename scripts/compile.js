const fs = require("fs");
const path = require("path");
const solc = require("solc");

const root = path.join(__dirname, "..");
const sources = {};
for (const f of ["AgentGuard.sol", "MockAgentId.sol"]) {
  sources[f] = {
    content: fs.readFileSync(path.join(root, "contracts", f), "utf8"),
  };
}
const input = {
  language: "Solidity",
  sources,
  settings: {
    optimizer: { enabled: true, runs: 200 },
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
  },
};
const out = JSON.parse(solc.compile(JSON.stringify(input)));
let failed = false;
for (const e of out.errors || []) {
  console.log(e.severity.toUpperCase() + ": " + e.formattedMessage);
  if (e.severity === "error") failed = true;
}
if (failed) process.exit(1);
fs.mkdirSync(path.join(root, "build"), { recursive: true });
for (const [file, contracts] of Object.entries(out.contracts)) {
  for (const [name, c] of Object.entries(contracts)) {
    fs.writeFileSync(
      path.join(root, "build", name + ".json"),
      JSON.stringify({ abi: c.abi, bytecode: c.evm.bytecode.object }, null, 2)
    );
    console.log(
      "COMPILED " + name + " bytecode=" + c.evm.bytecode.object.length / 2 + " bytes abi=" + c.abi.length + " entries"
    );
  }
}
