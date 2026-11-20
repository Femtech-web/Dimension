// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {MockRateProvider} from "../src/MockRateProvider.sol";
import {LiveRecorder, IExitPool} from "../src/LiveRecorder.sol";

interface IPool {
    function initialize(uint256[2] calldata balances, uint256 amp, uint256 fee, uint256 supply, uint256 storedInvariant, uint256 protocolSwapFee, address rateProvider) external;
}

interface IPriceOracle {
    function usdPrice() external view returns (uint256);
}

/// The live demonstration on Base Sepolia; scripts/live/deploy.py runs it.
///
/// Balancer: the three pool contracts, each attacked with the batch LivePlan
/// planned against Balancer's arithmetic, then the typed and guarded pools
/// with that batch up to the exit they reject. Moonwell: the oracle as Dimension
/// configures it, and MIP-X43's declaration tried against Chainlink's real
/// feeds, each outcome recorded by LiveRecorder. Then the typed vault.
contract Live is Script {
    address internal constant CBETH_ETH = 0x91b21900E91CD302EBeD05E45D8f270ddAED944d;
    address internal constant CBETH_USD = 0x3c65e28D357a37589e1C7C86044a9f44dDC17134;
    uint256 internal constant RATED = 1;
    string internal constant BALANCER = "../../ingots/balancer_v2/out/";

    LiveRecorder internal recorder;

    function _code(string memory path) internal view returns (bytes memory) {
        return vm.parseBytes(string.concat("0x", vm.readFile(path)));
    }

    function _deploy(string memory name, bytes memory code) internal returns (address deployed) {
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), name);
    }

    function _declared(address feed, uint8 decimals, uint256 maxAge) internal view returns (bytes memory) {
        return bytes.concat(
            _code("../../ingots/moonwell/out/DeclaredCbethUsdFeed.bin"),
            abi.encode(feed, decimals, maxAge, uint256(100e18), uint256(100_000e18))
        );
    }

    function _price(address oracle) internal {
        recorder.probe(oracle, abi.encodeCall(IPriceOracle.usdPrice, ()));
    }

    function run() external {
        string memory plan = vm.readFile("cache/live-plan.json");
        uint256 supply = vm.parseJsonUint(plan, ".supply");
        uint256[] memory exits = vm.parseJsonUintArray(plan, ".exits");

        vm.startBroadcast(vm.envUint("LIVE_KEY"));
        recorder = new LiveRecorder();

        // Balancer V2's _upscale: the osETH/wETH pool's rate and the dust state
        // the attacker reached, then the planned batch against each pool.
        MockRateProvider provider = new MockRateProvider(1.21e18);
        string[3] memory pools = ["FaithfulPool", "TypedPool", "GuardedPool"];
        address[3] memory deployed;
        for (uint256 k = 0; k < 3; k++) {
            deployed[k] = _deploy(pools[k], _code(string.concat(BALANCER, pools[k], ".bin")));
            IPool(deployed[k]).initialize([uint256(1000), 1000], 200_000, 0, supply, supply, 0, address(provider));
        }
        for (uint256 k = 0; k < 3; k++) {
            recorder.attack(IExitPool(deployed[k]), RATED, exits);
        }
        // The batch without the exit the typed and guarded pools reject.
        for (uint256 k = 1; k < 3; k++) {
            uint256 feasible = vm.parseJsonUint(plan, string.concat(".", pools[k], ".stopped_at"));
            uint256[] memory prefix = new uint256[](feasible);
            for (uint256 i = 0; i < feasible; i++) prefix[i] = exits[i];
            recorder.attack(IExitPool(deployed[k]), RATED, prefix);
        }

        // Moonwell MIP-X43: the oracle, then the mistake made as each layer sees it.
        _price(_deploy("CbethUsdOracle", _code("../../ingots/live/out/CbethUsdOracle.bin")));
        recorder.deploy(_declared(CBETH_ETH, 8, 1_800));
        _price(_deploy("DeclaredCbethEthAsUsd", _declared(CBETH_ETH, 18, 90_000)));
        _price(_deploy("DeclaredCbethUsd", _declared(CBETH_USD, 8, 90_000)));

        _deploy("TypedVault", _code("../../ingots/vault/out/TypedVault.bin"));
        vm.stopBroadcast();
    }
}
