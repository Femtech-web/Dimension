// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockRateProvider} from "../src/MockRateProvider.sol";

interface IVault {
    struct BatchSwapStep {
        bytes32 poolId;
        uint256 assetInIndex;
        uint256 assetOutIndex;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    function getPoolTokens(bytes32 poolId) external view returns (address[] memory, uint256[] memory, uint256);
    function queryBatchSwap(uint8 kind, BatchSwapStep[] memory swaps, address[] memory assets, FundManagement memory funds)
        external
        returns (int256[] memory);
}

interface IComposableStablePool {
    function getAmplificationParameter() external view returns (uint256 value, bool isUpdating, uint256 precision);
    function getSwapFeePercentage() external view returns (uint256);
    function getScalingFactors() external view returns (uint256[] memory);
    function getActualSupply() external view returns (uint256);
    function getLastJoinExitData() external view returns (uint256 amp, uint256 invariant);
    function getRateProviders() external view returns (address[] memory);
    function getTokenRateCache(address token) external view returns (uint256 rate, uint256 oldRate, uint256 duration, uint256 expires);
}

interface IRateProvider {
    function getRate() external view returns (uint256);
}

interface IFePool {
    function initialize(uint256[2] calldata balances, uint256 amp, uint256 fee, uint256 supply, uint256 storedInvariant, address rateProvider) external;
    function swapGivenIn(uint256 i, uint256 amount) external returns (uint256);
    function swapGivenOut(uint256 i, uint256 amount) external returns (uint256);
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function getState() external view returns (uint256[2] memory, uint256[2] memory, uint256, uint256);
}

/// The Fe faithful kernel against the deployed Balancer V2 pool that was drained
/// on 2025-11-03, on a mainnet fork at the block before the exploit. The Fe pool
/// is loaded with the real pool's state and every quote must equal what the real
/// Vault returns for the same swap. Results go to cache/pool-fidelity.csv.
contract PoolFidelity is Test {
    IVault internal constant VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    IComposableStablePool internal constant POOL = IComposableStablePool(0xDACf5Fa19b1f720111609043ac67A9818262850c);
    bytes32 internal constant POOL_ID = 0xdacf5fa19b1f720111609043ac67a9818262850c000000000000000000000635;
    address internal constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address internal constant OSETH = 0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38;
    uint256 internal constant BLOCK_BEFORE_EXPLOIT = 23_717_399;
    uint8 internal constant GIVEN_IN = 0;
    uint8 internal constant GIVEN_OUT = 1;
    string internal constant OUT = "cache/pool-fidelity.csv";

    IFePool internal fe;
    uint256[2] internal balances;

    function setUp() public {
        vm.createSelectFork(vm.envString("MAINNET_RPC_URL"), BLOCK_BEFORE_EXPLOIT);

        (address[] memory tokens, uint256[] memory registered,) = VAULT.getPoolTokens(POOL_ID);
        require(tokens[0] == WETH && tokens[2] == OSETH, "unexpected token order");
        balances = [registered[0], registered[2]];

        (uint256 amp,,) = POOL.getAmplificationParameter();
        (, uint256 storedInvariant) = POOL.getLastJoinExitData();
        uint256 rate = _rateThePoolWillUse();

        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile("../../ingots/balancer_v2/out/FaithfulPool.bin")));
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        fe = IFePool(deployed);
        fe.initialize(balances, amp, POOL.getSwapFeePercentage(), POOL.getActualSupply(), storedInvariant, address(new MockRateProvider(rate)));
    }

    /// osETH's rate as a swap will use it: the cached rate, or the provider's
    /// current one if the cache has expired (the pool refreshes it first).
    function _rateThePoolWillUse() internal view returns (uint256) {
        (uint256 cached,,, uint256 expires) = POOL.getTokenRateCache(OSETH);
        if (block.timestamp <= expires) return cached;
        return IRateProvider(POOL.getRateProviders()[2]).getRate();
    }

    function _real(uint8 kind, uint256 inIdx, uint256 outIdx, uint256 amount) internal returns (bool ok, uint256 result) {
        address[] memory assets = new address[](2);
        assets[0] = WETH;
        assets[1] = OSETH;
        IVault.BatchSwapStep[] memory swaps = new IVault.BatchSwapStep[](1);
        swaps[0] = IVault.BatchSwapStep(POOL_ID, inIdx, outIdx, amount, "");
        IVault.FundManagement memory funds = IVault.FundManagement(address(this), false, payable(address(this)), false);
        try VAULT.queryBatchSwap(kind, swaps, assets, funds) returns (int256[] memory deltas) {
            return (true, kind == GIVEN_IN ? uint256(-deltas[outIdx]) : uint256(deltas[inIdx]));
        } catch {
            return (false, 0);
        }
    }

    function _fe(uint8 kind, uint256 inIdx, uint256 amount) internal returns (bool ok, uint256 result) {
        uint256 snap = vm.snapshotState();
        if (kind == GIVEN_IN) {
            try fe.swapGivenIn(inIdx, amount) returns (uint256 r) {
                ok = true;
                result = r;
            } catch {}
        } else {
            try fe.swapGivenOut(inIdx, amount) returns (uint256 r) {
                ok = true;
                result = r;
            } catch {}
        }
        vm.revertToState(snap);
    }

    /// Amounts from 1 wei to a fifth of the pool, densest where rounding matters.
    function _amounts() internal pure returns (uint256[] memory amounts) {
        amounts = new uint256[](120);
        uint256 n;
        for (uint256 a = 1; a <= 20; a++) amounts[n++] = a;
        uint256 seed = uint256(keccak256("dimension"));
        for (uint256 decimals = 3; decimals <= 21; decimals++) {
            for (uint256 k = 0; k < 5; k++) {
                seed = uint256(keccak256(abi.encode(seed)));
                amounts[n++] = (10 ** decimals) + seed % (10 ** decimals);
            }
        }
        assembly {
            mstore(amounts, n)
        }
    }

    function test_quotesMatchTheDeployedPool() public {
        (, uint256[2] memory feFactors,,) = fe.getState();
        assertEq(POOL.getScalingFactors()[0], feFactors[0], "WETH scaling factor");

        uint256[] memory amounts = _amounts();
        uint256 compared;
        uint256 matched;
        for (uint256 kind = 0; kind < 2; kind++) {
            for (uint256 inIdx = 0; inIdx < 2; inIdx++) {
                for (uint256 n = 0; n < amounts.length; n++) {
                    uint256 amount = amounts[n];
                    if (amount * 5 > balances[1 - inIdx]) continue;
                    (bool realOk, uint256 real) = _real(uint8(kind), inIdx, 1 - inIdx, amount);
                    (bool feOk, uint256 mine) = _fe(uint8(kind), inIdx, amount);
                    compared++;
                    bool same = realOk == feOk && real == mine;
                    if (same) matched++;
                    vm.writeLine(OUT, string.concat(
                        kind == GIVEN_IN ? "givenIn," : "givenOut,", vm.toString(inIdx), ",", vm.toString(amount), ",",
                        realOk ? vm.toString(real) : "revert", ",", feOk ? vm.toString(mine) : "revert", ",", same ? "match" : "MISMATCH"
                    ));
                }
            }
        }
        assertEq(matched, compared, "every quote must match the deployed pool");
    }

    /// The exploit's operation: BPT in for an exact token amount out.
    function test_bptExitsAgainstTheDeployedPool() public {
        address bpt = address(POOL);
        address[] memory assets = new address[](3);
        assets[0] = WETH;
        assets[1] = bpt;
        assets[2] = OSETH;
        IVault.FundManagement memory funds = IVault.FundManagement(address(this), false, payable(address(this)), false);
        uint256[] memory amounts = _amounts();
        uint256 compared;
        uint256 matched;
        for (uint256 out = 0; out < 2; out++) {
            uint256 outAsset = out == 0 ? 0 : 2;
            for (uint256 n = 0; n < amounts.length; n++) {
                uint256 amount = amounts[n];
                if (amount * 5 > balances[out]) continue;
                IVault.BatchSwapStep[] memory swaps = new IVault.BatchSwapStep[](1);
                swaps[0] = IVault.BatchSwapStep(POOL_ID, 1, outAsset, amount, "");
                bool realOk;
                uint256 real;
                try VAULT.queryBatchSwap(GIVEN_OUT, swaps, assets, funds) returns (int256[] memory deltas) {
                    realOk = true;
                    real = uint256(deltas[1]);
                } catch {}
                uint256 snap = vm.snapshotState();
                bool feOk;
                uint256 mine;
                try fe.exitGivenOut(out, amount) returns (uint256 r) {
                    feOk = true;
                    mine = r;
                } catch {}
                vm.revertToState(snap);
                compared++;
                if (realOk == feOk && real == mine) matched++;
                vm.writeLine(OUT, string.concat(
                    "exitGivenOut,", vm.toString(out), ",", vm.toString(amount), ",", realOk ? vm.toString(real) : "revert", ",",
                    feOk ? vm.toString(mine) : "revert", ",", realOk == feOk && real == mine ? "match" : "MISMATCH"
                ));
            }
        }
        assertEq(matched, compared, "every exit must match the deployed pool");
    }
}
