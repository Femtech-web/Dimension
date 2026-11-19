// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

interface IFeed {
    function description() external view returns (string memory);
    function decimals() external view returns (uint8);
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
}

interface IMoonwellOracle {
    function getFeed(string memory symbol) external view returns (address);
    function getUnderlyingPrice(address mToken) external view returns (uint256);
}

interface IOevWrapper {
    function priceFeed() external view returns (address);
}

interface IFeOracle {
    function usdPrice() external view returns (uint256);
}

/// Moonwell's cbETH market on Base forks taken inside the eight days MIP-X43
/// left it priced by the cbETH/ETH exchange rate, and on either side of them.
/// Moonwell's deployed oracle and the Fe oracle read the same Chainlink feeds
/// at the same block. Results go to cache/moonwell-fork.csv.
contract MoonwellFork is Test {
    IMoonwellOracle internal constant MOONWELL_ORACLE = IMoonwellOracle(0xEC942bE8A8114bFD0396A5052c36027f2cA6a9d0);
    address internal constant MOONWELL_CBETH = 0x3bf93770f2d4a794c3d9EBEfBAeBAE2a8f09A5E5;
    address internal constant COMPOSITE_BEFORE = 0xB0Ba0C5D7DA4ec400C1C3E5ef2485134F89918C5;
    address internal constant MIP_X43_WRAPPER = 0x67996D1ff7a3711a91E2839d1059Fcb950C0495D;
    IFeed internal constant CBETH_ETH = IFeed(0x806b4Ac04501c29769051e42783cF04dCE41440b);
    IFeed internal constant ETH_USD = IFeed(0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70);

    uint256 internal constant LAST_CORRECT = 42_194_662;
    /// 2026-02-15 18:04:33 UTC, transaction 0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812.
    uint256 internal constant MIP_X43 = 42_194_663;
    uint256 internal constant LAST_WRONG = 42_538_948;
    /// 2026-02-23 17:20:45 UTC, transaction 0xd1c363dec8e159b5db38799fed885ad5a157aa1e237ccc74b312df7fad8043c5.
    uint256 internal constant FIXED = 42_538_949;
    uint256 internal constant SAMPLES = 12;

    string internal constant OUT = "cache/moonwell-fork.csv";

    // Dimension's oracle errors, as the Fe contracts encode them.
    error WrongDecimals(address feed, uint8 declared, uint8 reported);
    error StaleAnswer(address feed, uint256 updatedAt, uint256 now);
    error AnswerOutOfBand(address feed, uint256 wad, uint256 minWad, uint256 maxWad);

    function _fork(uint256 blockNumber) internal {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"), blockNumber);
    }

    function _deploy(string memory name, bytes memory args) internal returns (address deployed) {
        bytes memory code = bytes.concat(
            vm.parseBytes(string.concat("0x", vm.readFile(string.concat("../../ingots/moonwell/out/", name, ".bin")))), args
        );
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
    }

    /// cbETH/ETH times ETH/USD, both scaled to 18 decimals, rounded down.
    function _composite() internal view returns (uint256) {
        (, int256 rate,,,) = CBETH_ETH.latestRoundData();
        (, int256 ethUsd,,,) = ETH_USD.latestRoundData();
        return uint256(rate) * (uint256(ethUsd) * 1e10) / 1e18;
    }

    function test_mipX43WiredTheExchangeRateAsTheUsdPrice() public {
        _fork(LAST_CORRECT);
        assertEq(MOONWELL_ORACLE.getFeed("cbETH"), COMPOSITE_BEFORE, "composite oracle before MIP-X43");

        _fork(MIP_X43);
        assertEq(CBETH_ETH.description(), "CBETH / ETH");
        assertEq(CBETH_ETH.decimals(), 18);
        assertEq(ETH_USD.description(), "ETH / USD");
        assertEq(ETH_USD.decimals(), 8);
        assertEq(MOONWELL_ORACLE.getFeed("cbETH"), MIP_X43_WRAPPER, "MIP-X43's wrapper");
        assertEq(IOevWrapper(MIP_X43_WRAPPER).priceFeed(), address(CBETH_ETH), "the wrapper reads cbETH/ETH alone");
        (, int256 rate,,,) = CBETH_ETH.latestRoundData();
        assertEq(MOONWELL_ORACLE.getUnderlyingPrice(MOONWELL_CBETH), uint256(rate), "Moonwell's cbETH price is the bare rate");

        _fork(FIXED);
        assertEq(MOONWELL_ORACLE.getFeed("cbETH"), COMPOSITE_BEFORE, "composite oracle restored");
    }

    /// The Fe oracle and Moonwell's at the last correct block, at evenly spaced
    /// blocks through the window, and at the block that fixed it.
    function test_pricesThroughTheWindow() public {
        uint256[] memory blocks = new uint256[](SAMPLES + 2);
        blocks[0] = LAST_CORRECT;
        for (uint256 k = 0; k < SAMPLES; k++) {
            blocks[k + 1] = MIP_X43 + (LAST_WRONG - MIP_X43) * k / (SAMPLES - 1);
        }
        blocks[SAMPLES + 1] = FIXED;

        for (uint256 k = 0; k < blocks.length; k++) {
            _fork(blocks[k]);
            uint256 moonwell = MOONWELL_ORACLE.getUnderlyingPrice(MOONWELL_CBETH);
            address fe = _deploy("CbethUsdOracle", "");
            require(fe != address(0), "the Fe oracle must bind the real feeds");
            uint256 mine = IFeOracle(fe).usdPrice();
            assertEq(mine, _composite(), "Fe price is cbETH/ETH times ETH/USD");
            bool inWindow = blocks[k] >= MIP_X43 && blocks[k] <= LAST_WRONG;
            if (inWindow) {
                assertLt(moonwell, 2e18, "Moonwell priced cbETH at the bare exchange rate");
            } else {
                assertEq(mine, moonwell, "where Moonwell was right, the Fe price is identical");
            }
            vm.writeLine(OUT, string.concat(
                "price,", vm.toString(blocks[k]), ",", vm.toString(block.timestamp), ",", inWindow ? "mip-x43" : "composite", ",",
                vm.toString(moonwell), ",", vm.toString(mine)
            ));
        }
    }

    /// MIP-X43's mistake, made in the registry instead: the cbETH/ETH feed
    /// declared as cbETH/USD with the decimals a USD feed reports.
    function test_bindRejectsTheRateDeclaredAsAUsdFeed() public {
        _fork(MIP_X43);
        bytes memory args = abi.encode(address(CBETH_ETH), uint8(8), uint256(1_800), uint256(100e18), uint256(100_000e18));
        vm.expectRevert(abi.encodeWithSelector(WrongDecimals.selector, address(CBETH_ETH), uint8(8), uint8(18)));
        this.deployDeclared(args);
        vm.writeLine(OUT, "reject,bind,cbETH/ETH declared as cbETH/USD with 8 decimals,WrongDecimals");
    }

    /// The same mistake with the feed's real decimals declared: it binds, and
    /// the first read is outside any band a USD price of cbETH could be given.
    function test_readRejectsTheRateEvenWithItsRealDecimals() public {
        _fork(MIP_X43);
        address declared = this.deployDeclared(
            abi.encode(address(CBETH_ETH), uint8(18), uint256(90_000), uint256(100e18), uint256(100_000e18))
        );
        (, int256 rate,,,) = CBETH_ETH.latestRoundData();
        vm.expectRevert(
            abi.encodeWithSelector(AnswerOutOfBand.selector, address(CBETH_ETH), uint256(rate), uint256(100e18), uint256(100_000e18))
        );
        IFeOracle(declared).usdPrice();
        vm.writeLine(OUT, "reject,read,cbETH/ETH declared as cbETH/USD with 18 decimals,AnswerOutOfBand");
    }

    function test_readRejectsAStaleLeg() public {
        _fork(MIP_X43);
        address fe = _deploy("CbethUsdOracle", "");
        (,,, uint256 updatedAt,) = ETH_USD.latestRoundData();
        vm.warp(updatedAt + 1_801);
        vm.expectRevert(abi.encodeWithSelector(StaleAnswer.selector, address(ETH_USD), updatedAt, updatedAt + 1_801));
        IFeOracle(fe).usdPrice();
        vm.writeLine(OUT, "check,read,ETH/USD older than its declared 1800 s,StaleAnswer");
    }

    /// External so that expectRevert can see a reverting constructor.
    function deployDeclared(bytes memory args) external returns (address deployed) {
        bytes memory code = bytes.concat(
            vm.parseBytes(string.concat("0x", vm.readFile("../../ingots/moonwell/out/DeclaredCbethUsdFeed.bin"))), args
        );
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
            if iszero(deployed) {
                returndatacopy(0, 0, returndatasize())
                revert(0, returndatasize())
            }
        }
    }
}
