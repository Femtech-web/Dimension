// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockRateProvider} from "../src/MockRateProvider.sol";
import {LiveRecorder, IExitPool} from "../src/LiveRecorder.sol";

interface IPool {
    function initialize(uint256[2] calldata balances, uint256 amp, uint256 fee, uint256 supply, uint256 storedInvariant, uint256 protocolSwapFee, address rateProvider) external;
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function getRate() external view returns (uint256);
    function getState() external view returns (uint256[2] memory, uint256[2] memory, uint256, uint256);
}

/// Plans the live attack for Base Sepolia (scripts/live): the greedy sequence of
/// exact-out exits against Balancer's arithmetic, on the pool PoolAttack uses,
/// then the same sequence on the typed and guarded pools. Writes the plan and
/// each pool's expected outcome to cache/live-plan.json.
contract LivePlan is Test {
    uint256 internal constant RATED = 1;
    uint256 internal constant CAP = 96;
    string[3] internal NAMES = ["FaithfulPool", "TypedPool", "GuardedPool"];

    function _deploy(string memory name) internal returns (IPool pool) {
        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile(string.concat("../../ingots/balancer_v2/out/", name, ".bin"))));
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), name);
        pool = IPool(deployed);
    }

    /// The batch against one pool: whether it succeeds, the value per BPT before
    /// and after, and where it stops, exit by exit: the failing exit and its
    /// revert data, or the end, and the pool's state there.
    function _run(string memory name, IPool pool, LiveRecorder recorder, uint256[] memory amounts)
        internal
        returns (string memory)
    {
        uint256 snap = vm.snapshotState();
        vm.serializeUint(name, "start", pool.getRate());
        bool ok;
        try recorder.run(IExitPool(address(pool)), RATED, amounts) {
            ok = true;
        } catch {}
        vm.serializeUint(name, "end", pool.getRate());
        vm.revertToState(snap);
        snap = vm.snapshotState();
        uint256 stoppedAt = amounts.length;
        bytes memory reason;
        for (uint256 i = 0; i < amounts.length; i++) {
            try pool.exitGivenOut(RATED, amounts[i]) {}
            catch (bytes memory revertData) {
                (stoppedAt, reason) = (i, revertData);
                break;
            }
        }
        (uint256[2] memory balances,, uint256 supply,) = pool.getState();
        uint256[] memory state = new uint256[](3);
        (state[0], state[1], state[2]) = (balances[0], balances[1], supply);
        vm.serializeUint(name, "stopped_at", stoppedAt);
        vm.serializeBytes(name, "reason", reason);
        vm.serializeUint(name, "state_at_stop", state);
        vm.serializeUint(name, "rate_at_stop", pool.getRate());
        vm.revertToState(snap);
        return vm.serializeBool(name, "batch_succeeds", ok);
    }

    function test_plan() public {
        MockRateProvider provider = new MockRateProvider(1.21e18);
        IPool[3] memory pools;
        for (uint256 k = 0; k < 3; k++) pools[k] = _deploy(NAMES[k]);
        pools[0].initialize([uint256(1000), 1000], 200_000, 0, 1e18, 0, 0, address(provider));
        uint256 supply = pools[0].getRate();
        for (uint256 k = 0; k < 3; k++) {
            pools[k].initialize([uint256(1000), 1000], 200_000, 0, supply, supply, 0, address(provider));
        }

        // The greedy plan, against Balancer's arithmetic.
        uint256[] memory plan = new uint256[](200);
        uint256 n;
        uint256 snapAll = vm.snapshotState();
        for (; n < 200; n++) {
            (uint256[2] memory balances,,,) = pools[0].getState();
            uint256 best;
            uint256 lowest = type(uint256).max;
            for (uint256 a = 1; a <= CAP && a * 2 <= balances[RATED]; a++) {
                uint256 snap = vm.snapshotState();
                try pools[0].exitGivenOut(RATED, a) {
                    uint256 rate = pools[0].getRate();
                    if (rate < lowest) {
                        lowest = rate;
                        best = a;
                    }
                } catch {}
                vm.revertToState(snap);
            }
            if (best == 0) break;
            pools[0].exitGivenOut(RATED, best);
            plan[n] = best;
        }
        vm.revertToState(snapAll);
        uint256[] memory amounts = new uint256[](n);
        for (uint256 i = 0; i < n; i++) amounts[i] = plan[i];

        // The same batch against each pool.
        LiveRecorder recorder = new LiveRecorder();
        string memory json = "plan";
        vm.serializeUint(json, "supply", supply);
        vm.serializeUint(json, "exits", amounts);
        for (uint256 k = 0; k < 3; k++) {
            json = vm.serializeString("plan", NAMES[k], _run(NAMES[k], pools[k], recorder, amounts));
        }
        vm.writeJson(json, "cache/live-plan.json");
    }
}
