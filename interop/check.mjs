// Runs the kernels' WebAssembly module in Node.js and prints, as JSON, the
// value per BPT after each exit of the batch on each kernel, and the check
// each kernel fails, for scripts/harness/wasm.py to compare with the EVM.
//
//   node interop/check.mjs web/public/kernels.wasm
import fs from "node:fs";

const { instance } = await WebAssembly.instantiate(fs.readFileSync(process.argv[2]), {});
const { exits, value_after, failure } = instance.exports;
const count = exits();
const started = performance.now();
const kernels = {};
for (const [kernel, name] of ["faithful", "typed", "guarded"].entries()) {
  const values = [];
  for (let n = 0; n <= count; n++) {
    const value = BigInt.asUintN(64, value_after(kernel, n));
    if (value === 0n) break;
    values.push(value.toString());
  }
  const code = failure(kernel) >>> 0;
  kernels[name] = { values, failure: code === 0xffffffff ? null : code };
}
console.log(JSON.stringify({ exits: count, kernels, milliseconds: Math.round(performance.now() - started) }));
