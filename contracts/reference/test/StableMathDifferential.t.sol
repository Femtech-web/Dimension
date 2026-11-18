// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

/// Sends identical calldata to Balancer V2's Solidity and to the Fe port and
/// requires the same outcome: same success flag and byte-identical return data,
/// reverts included.
contract StableMathDifferential is Test {
    address internal fe;
    address internal sol;

    uint256 internal constant AMP_PRECISION = 1e3;
    // Balancer's StableMath assumes balances fit in 2^112 times a 1e18 scaling factor.
    uint256 internal constant MAX_BALANCE = (1 << 112) * 1e18;

    function setUp() public {
        sol = deployCode("StableMathHarness.sol:StableMathHarness");
        bytes memory code = vm.parseBytes(
            string.concat("0x", vm.readFile("../../ingots/balancer_v2/out/StableMathFe.bin"))
        );
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), "Fe harness failed to deploy");
        fe = deployed;
    }

    string internal constant OUTCOMES = "cache/differential-outcomes.csv";

    /// Compares both implementations on `data` and records the outcome, so the
    /// report can show how many vectors succeeded and why the rest reverted.
    function _same(string memory fn, bytes memory data) internal {
        (bool okFe, bytes memory retFe) = fe.staticcall(data);
        (bool okSol, bytes memory retSol) = sol.staticcall(data);
        assertEq(okFe, okSol, "success differs");
        assertEq(retFe, retSol, "return data differs");
        vm.writeLine(OUTCOMES, string.concat(fn, ",", okSol ? "ok" : _reason(retSol)));
    }

    function _reason(bytes memory ret) internal pure returns (string memory) {
        // Balancer reverts with Error("BAL#xyz"): selector, offset, length 7, then the text.
        if (ret.length == 100 && bytes4(ret) == 0x08c379a0) {
            bytes memory text = new bytes(7);
            for (uint256 i = 0; i < 7; i++) text[i] = ret[68 + i];
            return string(text);
        }
        return string.concat("revert-", vm.toString(ret.length));
    }

    /// The magnitude a pool's balances share: 3/8 dust (where the November 2025
    /// exploit operated), 2/8 small, 2/8 ordinary, 1/8 extreme.
    function _scale(uint256 seed) internal pure returns (uint256) {
        uint256 regime = seed % 8;
        uint256 v = seed / 8;
        if (regime < 3) return bound(v, 1, 1e6);
        if (regime < 5) return bound(v, 1e6, 1e18);
        if (regime < 7) return bound(v, 1e18, 1e30);
        return bound(v, 1e30, MAX_BALANCE / 100);
    }

    /// A balance within 100x either side of the pool's scale. One pool in eight
    /// instead draws every balance independently, which reaches the extreme
    /// imbalances where Balancer's arithmetic overflows and must revert.
    function _balance(uint256 poolSeed, uint256 seed) internal pure returns (uint256) {
        if (poolSeed % 8 == 7) return bound(seed, 1, MAX_BALANCE);
        uint256 scale = _scale(poolSeed / 8);
        uint256 low = scale / 100 == 0 ? 1 : scale / 100;
        return bound(seed, low, scale * 100);
    }

    function _amp(uint256 seed) internal pure returns (uint256) {
        return bound(seed, 1, 5000) * AMP_PRECISION;
    }

    function _two(uint256 a, uint256 b) internal pure returns (uint256[2] memory r) {
        uint256 pool = uint256(keccak256(abi.encode(a, b)));
        r = [_balance(pool, a), _balance(pool, b)];
    }

    function _three(uint256 a, uint256 b, uint256 c) internal pure returns (uint256[3] memory r) {
        uint256 pool = uint256(keccak256(abi.encode(a, b, c)));
        r = [_balance(pool, a), _balance(pool, b), _balance(pool, c)];
    }

    /// The invariant as Balancer computes it, or an arbitrary one if that reverts,
    /// so the dependent functions still run on both sides.
    function _invariant(bytes memory call, uint256 fallbackSeed) internal view returns (uint256) {
        (bool ok, bytes memory ret) = sol.staticcall(call);
        return ok ? abi.decode(ret, (uint256)) : bound(fallbackSeed, 1, MAX_BALANCE);
    }

    // ---------------------------------------------------------------- primitives

    function testFuzz_mulDown(uint256 a, uint256 b) public {
        _same("mulDown", abi.encodeWithSignature("mulDown(uint256,uint256)", a, b));
    }

    function testFuzz_mulUp(uint256 a, uint256 b) public {
        _same("mulUp", abi.encodeWithSignature("mulUp(uint256,uint256)", a, b));
    }

    function testFuzz_divDown(uint256 a, uint256 b) public {
        _same("divDown", abi.encodeWithSignature("divDown(uint256,uint256)", a, b));
    }

    function testFuzz_divUp(uint256 a, uint256 b) public {
        _same("divUp", abi.encodeWithSignature("divUp(uint256,uint256)", a, b));
    }

    function testFuzz_complement(uint256 x) public {
        _same("complement", abi.encodeWithSignature("complement(uint256)", bound(x, 0, 3e18)));
    }

    function testFuzz_mathDivUp(uint256 a, uint256 b) public {
        _same("mathDivUp", abi.encodeWithSignature("mathDivUp(uint256,uint256)", a, b));
    }

    // ---------------------------------------------------------------- invariant

    function testFuzz_calculateInvariant2(uint256 amp, uint256 a, uint256 b) public {
        _same("calculateInvariant2", abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", _amp(amp), _two(a, b)));
    }

    function testFuzz_calculateInvariant3(uint256 amp, uint256 a, uint256 b, uint256 c) public {
        _same("calculateInvariant3", abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", _amp(amp), _three(a, b, c)));
    }

    // ---------------------------------------------------------------- swaps

    function testFuzz_calcOutGivenIn2(uint256 amp, uint256 a, uint256 b, bool dir, uint256 amount, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        (uint256 i, uint256 o) = dir ? (0, 1) : (1, 0);
        uint256 amountIn = bound(amount, 0, bal[i] * 2);
        _same("calcOutGivenIn2", abi.encodeWithSignature("calcOutGivenIn2(uint256,uint256[2],uint256,uint256,uint256,uint256)", ampv, bal, i, o, amountIn, inv));
    }

    function testFuzz_calcOutGivenIn3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 pair, uint256 amount, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), f);
        uint256 i = pair % 3;
        uint256 o = (i + 1 + (pair / 3) % 2) % 3;
        uint256 amountIn = bound(amount, 0, bal[i] * 2);
        _same("calcOutGivenIn3", abi.encodeWithSignature("calcOutGivenIn3(uint256,uint256[3],uint256,uint256,uint256,uint256)", ampv, bal, i, o, amountIn, inv));
    }

    function testFuzz_calcInGivenOut2(uint256 amp, uint256 a, uint256 b, bool dir, uint256 amount, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        (uint256 i, uint256 o) = dir ? (0, 1) : (1, 0);
        // Up to 110% of the balance, so withdrawing more than the pool holds is exercised too.
        uint256 amountOut = bound(amount, 0, bal[o] + bal[o] / 10);
        _same("calcInGivenOut2", abi.encodeWithSignature("calcInGivenOut2(uint256,uint256[2],uint256,uint256,uint256,uint256)", ampv, bal, i, o, amountOut, inv));
    }

    function testFuzz_calcInGivenOut3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 pair, uint256 amount, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), f);
        uint256 i = pair % 3;
        uint256 o = (i + 1 + (pair / 3) % 2) % 3;
        uint256 amountOut = bound(amount, 0, bal[o] + bal[o] / 10);
        _same("calcInGivenOut3", abi.encodeWithSignature("calcInGivenOut3(uint256,uint256[3],uint256,uint256,uint256,uint256)", ampv, bal, i, o, amountOut, inv));
    }

    // ---------------------------------------------------------------- joins and exits

    function testFuzz_calcBptOutGivenExactTokensIn2(uint256 amp, uint256 a, uint256 b, uint256 x, uint256 y, uint256 supply, uint256 fee, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        uint256[2] memory amounts = [bound(x, 0, bal[0]), bound(y, 0, bal[1])];
        _same("calcBptOutGivenExactTokensIn2", abi.encodeWithSignature("calcBptOutGivenExactTokensIn2(uint256,uint256[2],uint256[2],uint256,uint256,uint256)", ampv, bal, amounts, bound(supply, 1, 1e33), inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcBptOutGivenExactTokensIn3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 x, uint256 y, uint256 supply, uint256 fee) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), x);
        uint256[3] memory amounts = [bound(x, 0, bal[0]), bound(y, 0, bal[1]), bound(x ^ y, 0, bal[2])];
        _same("calcBptOutGivenExactTokensIn3", abi.encodeWithSignature("calcBptOutGivenExactTokensIn3(uint256,uint256[3],uint256[3],uint256,uint256,uint256)", ampv, bal, amounts, bound(supply, 1, 1e33), inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcTokenInGivenExactBptOut2(uint256 amp, uint256 a, uint256 b, bool idx, uint256 bpt, uint256 supply, uint256 fee, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        uint256 s = bound(supply, 1, 1e33);
        _same("calcTokenInGivenExactBptOut2", abi.encodeWithSignature("calcTokenInGivenExactBptOut2(uint256,uint256[2],uint256,uint256,uint256,uint256,uint256)", ampv, bal, idx ? 1 : 0, bound(bpt, 0, s), s, inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcTokenInGivenExactBptOut3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 idx, uint256 bpt, uint256 supply, uint256 fee) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), bpt);
        uint256 s = bound(supply, 1, 1e33);
        _same("calcTokenInGivenExactBptOut3", abi.encodeWithSignature("calcTokenInGivenExactBptOut3(uint256,uint256[3],uint256,uint256,uint256,uint256,uint256)", ampv, bal, idx % 3, bound(bpt, 0, s), s, inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcBptInGivenExactTokensOut2(uint256 amp, uint256 a, uint256 b, uint256 x, uint256 y, uint256 supply, uint256 fee, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        uint256[2] memory amounts = [bound(x, 0, bal[0]), bound(y, 0, bal[1])];
        _same("calcBptInGivenExactTokensOut2", abi.encodeWithSignature("calcBptInGivenExactTokensOut2(uint256,uint256[2],uint256[2],uint256,uint256,uint256)", ampv, bal, amounts, bound(supply, 1, 1e33), inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcBptInGivenExactTokensOut3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 x, uint256 y, uint256 supply, uint256 fee) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), y);
        uint256[3] memory amounts = [bound(x, 0, bal[0]), bound(y, 0, bal[1]), bound(x ^ y, 0, bal[2])];
        _same("calcBptInGivenExactTokensOut3", abi.encodeWithSignature("calcBptInGivenExactTokensOut3(uint256,uint256[3],uint256[3],uint256,uint256,uint256)", ampv, bal, amounts, bound(supply, 1, 1e33), inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcTokenOutGivenExactBptIn2(uint256 amp, uint256 a, uint256 b, bool idx, uint256 bpt, uint256 supply, uint256 fee, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        uint256 s = bound(supply, 1, 1e33);
        _same("calcTokenOutGivenExactBptIn2", abi.encodeWithSignature("calcTokenOutGivenExactBptIn2(uint256,uint256[2],uint256,uint256,uint256,uint256,uint256)", ampv, bal, idx ? 1 : 0, bound(bpt, 0, s), s, inv, bound(fee, 0, 1e17)));
    }

    function testFuzz_calcTokenOutGivenExactBptIn3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 idx, uint256 bpt, uint256 supply, uint256 fee) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), supply);
        uint256 s = bound(supply, 1, 1e33);
        _same("calcTokenOutGivenExactBptIn3", abi.encodeWithSignature("calcTokenOutGivenExactBptIn3(uint256,uint256[3],uint256,uint256,uint256,uint256,uint256)", ampv, bal, idx % 3, bound(bpt, 0, s), s, inv, bound(fee, 0, 1e17)));
    }

    // ---------------------------------------------------------------- balance solver

    function testFuzz_getTokenBalance2(uint256 amp, uint256 a, uint256 b, bool idx, uint256 shift, uint256 f) public {
        uint256 ampv = _amp(amp);
        uint256[2] memory bal = _two(a, b);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant2(uint256,uint256[2])", ampv, bal), f);
        // The solver also runs with invariants near, but not at, the true one.
        uint256 target = bound(shift, inv / 2 + 1, inv + inv / 2 + 1);
        _same("getTokenBalance2", abi.encodeWithSignature("getTokenBalance2(uint256,uint256[2],uint256,uint256)", ampv, bal, target, idx ? 1 : 0));
    }

    function testFuzz_getTokenBalance3(uint256 amp, uint256 a, uint256 b, uint256 c, uint256 idx, uint256 shift) public {
        uint256 ampv = _amp(amp);
        uint256[3] memory bal = _three(a, b, c);
        uint256 inv = _invariant(abi.encodeWithSignature("calculateInvariant3(uint256,uint256[3])", ampv, bal), shift);
        uint256 target = bound(shift, inv / 2 + 1, inv + inv / 2 + 1);
        _same("getTokenBalance3", abi.encodeWithSignature("getTokenBalance3(uint256,uint256[3],uint256,uint256)", ampv, bal, target, idx % 3));
    }
}
