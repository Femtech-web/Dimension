// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockRateProvider} from "../src/MockRateProvider.sol";

interface IVault {
    function getPoolTokens(bytes32 poolId) external view returns (address[] memory, uint256[] memory, uint256);
}

interface IComposableStablePool {
    function getAmplificationParameter() external view returns (uint256 value, bool isUpdating, uint256 precision);
    function getSwapFeePercentage() external view returns (uint256);
    function getScalingFactors() external view returns (uint256[] memory);
    function getActualSupply() external view returns (uint256);
    function getProtocolFeePercentageCache(uint256 feeType) external view returns (uint256);
    function updateTokenRateCache(address token) external;
}

interface IFePool {
    function initialize(
        uint256[2] calldata balances,
        uint256 amp,
        uint256 fee,
        uint256 supply,
        uint256 storedInvariant,
        uint256 protocolSwapFee,
        address rateProvider
    ) external;
    function swapGivenOut(uint256 i, uint256 amount) external returns (uint256);
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function joinGivenOut(uint256 i, uint256 bpt) external returns (uint256);
    function getRate() external view returns (uint256);
    function getState() external view returns (uint256[2] memory, uint256[2] memory, uint256, uint256);
}

/// The November 2025 exploit's own swaps on the osETH/wETH pool, replayed
/// through the three Fe kernels from the pool's real state just before each
/// attack transaction. The faithful kernel must compute every step exactly as
/// Balancer did and end where the pool ended; the typed and guarded kernels
/// show what the same steps do to them. Results go to cache/attack-replay.csv.
contract AttackReplay is Test {
    IVault internal constant VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    IComposableStablePool internal constant POOL = IComposableStablePool(0xDACf5Fa19b1f720111609043ac67A9818262850c);
    bytes32 internal constant POOL_ID = 0xdacf5fa19b1f720111609043ac67a9818262850c000000000000000000000635;
    address internal constant OSETH = 0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38;
    uint256 internal constant PROTOCOL_SWAP_FEE = 0;
    string internal constant OUT = "cache/attack-replay.csv";

    uint8 internal constant SWAP = 0;
    uint8 internal constant EXIT = 1;
    uint8 internal constant JOIN = 2;
    string[3] internal KINDS = ["swap", "exit", "join"];
    string[3] internal KERNELS = ["faithful", "typed", "guarded"];

    /// One step of the batch on this pool. `index` is the Fe pool's token index
    /// (0 WETH, 1 osETH) of the token in for swaps and joins, out for exits.
    struct Step {
        uint8 kind;
        uint256 index;
        uint256 amountIn;
        uint256 amountOut;
    }

    function _attack(uint256 n) internal pure returns (bytes32) {
        if (n == 1) return 0x6ed07db1a9fe5c0794d44cd36081d6a6df103fab868cdd75d581e3bd23bc9742;
        if (n == 2) return 0x1dc60f917e4d841f281e827cf82f93c7355e08f5855e9ae5b0a1764b38ed4b87;
        return 0xe1d5f36f0aa6f6a07865ac4feaae5bda839f489372eb3ece7d53fb10100a1eb1;
    }

    function _index(string memory token) internal pure returns (uint256) {
        return keccak256(bytes(token)) == keccak256("WETH") ? 0 : 1;
    }

    function _steps(uint256 n) internal returns (Step[] memory steps) {
        string memory path = string.concat("../../fixtures/balancer-v2-exploit/attack-", vm.toString(n), ".csv");
        steps = new Step[](128);
        uint256 count;
        for (string memory line = vm.readLine(path); bytes(line).length > 0; line = vm.readLine(path)) {
            if (bytes(line)[0] == "#") continue;
            string[] memory f = vm.split(line, ",");
            bool bptIn = keccak256(bytes(f[0])) == keccak256("BPT");
            bool bptOut = keccak256(bytes(f[1])) == keccak256("BPT");
            steps[count++] = Step({
                kind: bptIn ? EXIT : (bptOut ? JOIN : SWAP),
                index: bptIn ? _index(f[1]) : _index(f[0]),
                amountIn: vm.parseUint(f[2]),
                amountOut: vm.parseUint(f[3])
            });
        }
        vm.closeFile(path);
        assembly {
            mstore(steps, count)
        }
    }

    function _deploy(string memory name) internal returns (IFePool pool) {
        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile(string.concat("../../ingots/balancer_v2/out/", name, ".bin"))));
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), name);
        pool = IFePool(deployed);
    }

    /// The three kernels, loaded with the pool's state just before attack `n`:
    /// the rate cache refreshed as the attacker's first swap refreshed it, and
    /// the protocol fees due at that point paid (the actual supply), so the
    /// stored invariant is the current one.
    function _load(uint256 n) internal returns (IFePool[3] memory pools) {
        vm.createSelectFork(vm.envString("MAINNET_RPC_URL"), _attack(n));
        POOL.updateTokenRateCache(OSETH);
        (, uint256[] memory registered,) = VAULT.getPoolTokens(POOL_ID);
        uint256[2] memory balances = [registered[0], registered[2]];
        (uint256 amp,,) = POOL.getAmplificationParameter();
        uint256 fee = POOL.getSwapFeePercentage();
        uint256 protocolFee = POOL.getProtocolFeePercentageCache(PROTOCOL_SWAP_FEE);
        address provider = address(new MockRateProvider(POOL.getScalingFactors()[2]));
        pools = [_deploy("FaithfulPool"), _deploy("TypedPool"), _deploy("GuardedPool")];
        // With a supply of 1e18, getRate() is the invariant itself.
        pools[0].initialize(balances, amp, fee, 1e18, 0, protocolFee, provider);
        uint256 invariant = pools[0].getRate();
        for (uint256 k = 0; k < 3; k++) {
            pools[k].initialize(balances, amp, fee, POOL.getActualSupply(), invariant, protocolFee, provider);
        }
    }

    function _call(IFePool pool, Step memory s) internal returns (bool ok, bytes memory ret) {
        if (s.kind == SWAP) return address(pool).call(abi.encodeCall(IFePool.swapGivenOut, (s.index, s.amountOut)));
        if (s.kind == EXIT) return address(pool).call(abi.encodeCall(IFePool.exitGivenOut, (s.index, s.amountOut)));
        return address(pool).call(abi.encodeCall(IFePool.joinGivenOut, (s.index, s.amountOut)));
    }

    /// The step's computed amount, or why it reverted: Balancer's BAL# code, or
    /// the selector of Dimension's error.
    function _run(IFePool pool, Step memory s) internal returns (bool ok, uint256 computed, string memory reason) {
        bytes memory ret;
        (ok, ret) = _call(pool, s);
        if (ok) return (true, abi.decode(ret, (uint256)), "");
        if (ret.length == 100 && bytes4(ret) == 0x08c379a0) {
            bytes memory text = new bytes(7);
            for (uint256 i = 0; i < 7; i++) text[i] = ret[68 + i];
            return (false, 0, string(text));
        }
        return (false, 0, ret.length >= 4 ? vm.toString(abi.encodePacked(bytes4(ret))) : "revert");
    }

    /// Runs every step on one kernel, stopping at the first revert (which would
    /// revert the whole batch). Returns the steps completed and how many of
    /// them computed exactly what Balancer computed.
    function _replay(uint256 n, uint256 k, IFePool pool, Step[] memory steps) internal returns (uint256 done, uint256 matched) {
        uint256 start = pool.getRate();
        for (; done < steps.length; done++) {
            (bool ok, uint256 computed, string memory reason) = _run(pool, steps[done]);
            _stepRow(n, k, done, steps[done], ok ? vm.toString(computed) : reason, ok ? pool.getRate() : 0);
            if (!ok) break;
            if (computed == steps[done].amountIn) matched++;
        }
        _endRow(n, k, string.concat(vm.toString(done), ",", vm.toString(steps.length), ",", vm.toString(matched)), start, pool);
    }

    /// One step's outcome, and the value per BPT after it (0 if it reverted).
    function _stepRow(uint256 n, uint256 k, uint256 i, Step memory s, string memory result, uint256 rate) internal {
        string memory head = string.concat("step,", vm.toString(n), ",", KERNELS[k], ",", vm.toString(i), ",", KINDS[s.kind]);
        vm.writeLine(OUT, string.concat(
            head, ",", vm.toString(s.amountOut), ",", vm.toString(s.amountIn), ",", result, ",", vm.toString(rate)
        ));
    }

    function _endRow(uint256 n, uint256 k, string memory counts, uint256 start, IFePool pool) internal {
        (uint256[2] memory balances,, uint256 supply,) = pool.getState();
        string memory head = string.concat("end,", vm.toString(n), ",", KERNELS[k], ",", counts);
        vm.writeLine(OUT, string.concat(
            head, ",", vm.toString(start), ",", vm.toString(pool.getRate()), ",",
            vm.toString(balances[0]), ",", vm.toString(balances[1]), ",", vm.toString(supply)
        ));
    }

    function _replayAttack(uint256 n) internal {
        IFePool[3] memory pools = _load(n);
        Step[] memory steps = _steps(n);
        uint256[3] memory done;
        uint256[3] memory matched;
        for (uint256 k = 0; k < 3; k++) {
            (done[k], matched[k]) = _replay(n, k, pools[k], steps);
        }
        assertEq(done[0], steps.length, "the faithful kernel must complete the attack");
        assertEq(matched[0], steps.length, "every step must compute what Balancer computed");

        // The real transaction, on the same fork: the pool must end where the faithful kernel ended.
        (uint256[2] memory feBalances,, uint256 feSupply,) = pools[0].getState();
        vm.transact(_attack(n));
        (, uint256[] memory registered,) = VAULT.getPoolTokens(POOL_ID);
        uint256 realSupply = POOL.getActualSupply();
        vm.writeLine(OUT, string.concat(
            "real,", vm.toString(n), ",", vm.toString(registered[0]), ",", vm.toString(registered[2]), ",", vm.toString(realSupply)
        ));
        assertEq(feBalances[0], registered[0], "WETH balance after the attack");
        assertEq(feBalances[1], registered[2], "osETH balance after the attack");
        assertEq(feSupply, realSupply, "BPT supply after the attack");
    }

    function test_attack1() public {
        _replayAttack(1);
    }

    function test_attack2() public {
        _replayAttack(2);
    }

    function test_attack3() public {
        _replayAttack(3);
    }
}
