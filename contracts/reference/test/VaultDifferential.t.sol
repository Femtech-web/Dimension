// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC4626} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";

contract Underlying is ERC20 {
    constructor() ERC20("Underlying", "UND") {}
}

contract OzVault is ERC4626 {
    constructor(IERC20 asset_) ERC20("Vault", "VLT") ERC4626(asset_) {}
}

interface ITypedVault {
    function previewDeposit(uint256 totalAssets, uint256 totalShares, uint256 assets) external view returns (uint256);
    function previewMint(uint256 totalAssets, uint256 totalShares, uint256 shares) external view returns (uint256);
    function previewWithdraw(uint256 totalAssets, uint256 totalShares, uint256 assets) external view returns (uint256);
    function previewRedeem(uint256 totalAssets, uint256 totalShares, uint256 shares) external view returns (uint256);
}

/// The Fe vault's previews against OpenZeppelin's ERC4626 (v5.1.0) in the same
/// state: the same assets held, the same shares issued, the same amount, the
/// same result. OpenZeppelin names a rounding in each function; the Fe vault
/// names none. Outcomes go to cache/vault-outcomes.csv.
contract VaultDifferential is Test {
    string internal constant OUT = "cache/vault-outcomes.csv";

    Underlying internal asset;
    OzVault internal oz;
    ITypedVault internal fe;

    function setUp() public {
        asset = new Underlying();
        oz = new OzVault(asset);
        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile("../../ingots/vault/out/TypedVault.bin")));
        address deployed;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), "Fe vault failed to deploy");
        fe = ITypedVault(deployed);
    }

    /// A magnitude for holdings, supply or an amount: empty to ten, dust,
    /// ordinary, or huge, so rounding at every scale is exercised.
    function _magnitude(uint256 seed) internal pure returns (uint256) {
        uint256 regime = seed % 4;
        uint256 v = seed / 4;
        if (regime == 0) return bound(v, 0, 10);
        if (regime == 1) return bound(v, 0, 1e6);
        if (regime == 2) return bound(v, 1e6, 1e24);
        return bound(v, 1e24, 1e36);
    }

    /// Puts OpenZeppelin's vault in the state: `held` assets, `issued` shares.
    function _state(uint256 a, uint256 s) internal returns (uint256 held, uint256 issued) {
        held = _magnitude(a);
        issued = _magnitude(s);
        deal(address(asset), address(oz), held);
        deal(address(oz), address(this), issued, true);
        assertEq(oz.totalAssets(), held);
        assertEq(oz.totalSupply(), issued);
    }

    function _record(string memory fn, uint256 held, uint256 issued, uint256 amount, uint256 result) internal {
        vm.writeLine(OUT, string.concat(
            fn, ",", vm.toString(held), ",", vm.toString(issued), ",", vm.toString(amount), ",", vm.toString(result)
        ));
    }

    function testFuzz_previewDeposit(uint256 a, uint256 s, uint256 x) public {
        (uint256 held, uint256 issued) = _state(a, s);
        x = _magnitude(x);
        uint256 mine = fe.previewDeposit(held, issued, x);
        assertEq(mine, oz.previewDeposit(x), "previewDeposit");
        _record("previewDeposit", held, issued, x, mine);
    }

    function testFuzz_previewMint(uint256 a, uint256 s, uint256 x) public {
        (uint256 held, uint256 issued) = _state(a, s);
        x = _magnitude(x);
        uint256 mine = fe.previewMint(held, issued, x);
        assertEq(mine, oz.previewMint(x), "previewMint");
        _record("previewMint", held, issued, x, mine);
    }

    function testFuzz_previewWithdraw(uint256 a, uint256 s, uint256 x) public {
        (uint256 held, uint256 issued) = _state(a, s);
        x = _magnitude(x);
        uint256 mine = fe.previewWithdraw(held, issued, x);
        assertEq(mine, oz.previewWithdraw(x), "previewWithdraw");
        _record("previewWithdraw", held, issued, x, mine);
    }

    function testFuzz_previewRedeem(uint256 a, uint256 s, uint256 x) public {
        (uint256 held, uint256 issued) = _state(a, s);
        x = _magnitude(x);
        uint256 mine = fe.previewRedeem(held, issued, x);
        assertEq(mine, oz.previewRedeem(x), "previewRedeem");
        _record("previewRedeem", held, issued, x, mine);
    }
}
