// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

/// Typed code built on Dimension against the same code written by hand on raw
/// u256 (tests/zero_cost), both deployed from cache/zero-cost/<pair>-<variant>.bin
/// at whatever level the harness built them. Every function of each pair is
/// called on the same inputs in both: results, reverts included, must be equal,
/// and gas is summed over the calls that succeed. Results go to cache/zero-cost.csv.
contract ZeroCost is Test {
    string internal constant OUT = "cache/zero-cost.csv";
    uint256 internal constant INPUTS = 512;

    function _deploy(string memory name) internal returns (address deployed) {
        bytes memory code = vm.parseBytes(string.concat("0x", vm.readFile(string.concat("cache/zero-cost/", name, ".bin"))));
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
        }
        require(deployed != address(0), name);
    }

    /// Values of every magnitude, from 0 to 2^256 - 1, the same for every run.
    function _value(uint256 i, uint256 salt) internal pure returns (uint256) {
        uint256 r = uint256(keccak256(abi.encode(i, salt)));
        return r >> (r % 257);
    }

    /// Calls `target`, measuring only the call: no return data is copied while
    /// gas is counted, so identical code always measures identical gas.
    function _call(address target, bytes memory data) internal returns (bool ok, bytes memory out, uint256 used) {
        assembly {
            let before := gas()
            ok := call(gas(), target, 0, add(data, 0x20), mload(data), 0, 0)
            used := sub(before, gas())
            out := mload(0x40)
            mstore(out, returndatasize())
            returndatacopy(add(out, 0x20), 0, returndatasize())
            mstore(0x40, add(add(out, 0x20), and(add(returndatasize(), 31), not(31))))
        }
    }

    function _compare(string memory pair, string memory name, address typed, address raw, bytes[] memory calls) internal {
        uint256 gasTyped;
        uint256 gasRaw;
        uint256 succeeded;
        uint256 equal;
        for (uint256 i = 0; i < calls.length; i++) {
            (bool okTyped, bytes memory outTyped, uint256 usedTyped) = _call(typed, calls[i]);
            (bool okRaw, bytes memory outRaw, uint256 usedRaw) = _call(raw, calls[i]);
            if (okTyped == okRaw && keccak256(outTyped) == keccak256(outRaw)) equal++;
            if (okTyped && okRaw) {
                succeeded++;
                gasTyped += usedTyped;
                gasRaw += usedRaw;
            }
        }
        vm.writeLine(OUT, string.concat(
            pair, ",", name, ",", vm.toString(calls.length), ",", vm.toString(equal), ",",
            vm.toString(succeeded), ",", vm.toString(gasTyped), ",", vm.toString(gasRaw)
        ));
    }

    function test_rounding() public {
        address typed = _deploy("rounding-typed");
        address raw = _deploy("rounding-raw");
        string[4] memory names = ["admitIn", "admitOut", "settleIn", "settleOut"];
        for (uint256 f = 0; f < 4; f++) {
            bytes[] memory calls = new bytes[](INPUTS);
            bytes4 selector = bytes4(keccak256(bytes(string.concat(names[f], "(uint256)"))));
            for (uint256 i = 0; i < INPUTS; i++) {
                calls[i] = abi.encodeWithSelector(selector, _value(i, f));
            }
            _compare("rounding", names[f], typed, raw, calls);
        }
    }

    function test_vault() public {
        address typed = _deploy("vault-typed");
        address raw = _deploy("vault-raw");
        string[4] memory names = ["previewDeposit", "previewMint", "previewWithdraw", "previewRedeem"];
        for (uint256 f = 0; f < 4; f++) {
            bytes[] memory calls = new bytes[](INPUTS);
            bytes4 selector = bytes4(keccak256(bytes(string.concat(names[f], "(uint256,uint256,uint256)"))));
            for (uint256 i = 0; i < INPUTS; i++) {
                calls[i] = abi.encodeWithSelector(selector, _value(i, 3 * f + 10), _value(i, 3 * f + 11), _value(i, 3 * f + 12));
            }
            _compare("vault", names[f], typed, raw, calls);
        }
    }
}
