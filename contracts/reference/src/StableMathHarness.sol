// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity ^0.7.0;
pragma experimental ABIEncoderV2;

import "@balancer-labs/v2-solidity-utils/contracts/math/FixedPoint.sol";
import "@balancer-labs/v2-solidity-utils/contracts/math/Math.sol";
import "@balancer-labs/v2-pool-stable/contracts/StableMath.sol";

/// Balancer V2's own StableMath, FixedPoint and Math behind the ABI the Fe port
/// exposes in ingots/balancer_v2/src/harness.fe.
contract StableMathHarness {
    function mulDown(uint256 a, uint256 b) external pure returns (uint256) {
        return FixedPoint.mulDown(a, b);
    }

    function mulUp(uint256 a, uint256 b) external pure returns (uint256) {
        return FixedPoint.mulUp(a, b);
    }

    function divDown(uint256 a, uint256 b) external pure returns (uint256) {
        return FixedPoint.divDown(a, b);
    }

    function divUp(uint256 a, uint256 b) external pure returns (uint256) {
        return FixedPoint.divUp(a, b);
    }

    function complement(uint256 x) external pure returns (uint256) {
        return FixedPoint.complement(x);
    }

    function mathDivUp(uint256 a, uint256 b) external pure returns (uint256) {
        return Math.divUp(a, b);
    }

    function calculateInvariant2(uint256 amp, uint256[2] calldata balances) external pure returns (uint256) {
        return StableMath._calculateInvariant(amp, _two(balances));
    }

    function calculateInvariant3(uint256 amp, uint256[3] calldata balances) external pure returns (uint256) {
        return StableMath._calculateInvariant(amp, _three(balances));
    }

    function calcOutGivenIn2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256 indexIn,
        uint256 indexOut,
        uint256 amountIn,
        uint256 invariant
    ) external pure returns (uint256) {
        return StableMath._calcOutGivenIn(amp, _two(balances), indexIn, indexOut, amountIn, invariant);
    }

    function calcOutGivenIn3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256 indexIn,
        uint256 indexOut,
        uint256 amountIn,
        uint256 invariant
    ) external pure returns (uint256) {
        return StableMath._calcOutGivenIn(amp, _three(balances), indexIn, indexOut, amountIn, invariant);
    }

    function calcInGivenOut2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256 indexIn,
        uint256 indexOut,
        uint256 amountOut,
        uint256 invariant
    ) external pure returns (uint256) {
        return StableMath._calcInGivenOut(amp, _two(balances), indexIn, indexOut, amountOut, invariant);
    }

    function calcInGivenOut3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256 indexIn,
        uint256 indexOut,
        uint256 amountOut,
        uint256 invariant
    ) external pure returns (uint256) {
        return StableMath._calcInGivenOut(amp, _three(balances), indexIn, indexOut, amountOut, invariant);
    }

    function calcBptOutGivenExactTokensIn2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256[2] calldata amountsIn,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcBptOutGivenExactTokensIn(amp, _two(balances), _two(amountsIn), supply, invariant, fee);
    }

    function calcBptOutGivenExactTokensIn3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256[3] calldata amountsIn,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcBptOutGivenExactTokensIn(amp, _three(balances), _three(amountsIn), supply, invariant, fee);
    }

    function calcTokenInGivenExactBptOut2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256 index,
        uint256 bptOut,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcTokenInGivenExactBptOut(amp, _two(balances), index, bptOut, supply, invariant, fee);
    }

    function calcTokenInGivenExactBptOut3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256 index,
        uint256 bptOut,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcTokenInGivenExactBptOut(amp, _three(balances), index, bptOut, supply, invariant, fee);
    }

    function calcBptInGivenExactTokensOut2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256[2] calldata amountsOut,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcBptInGivenExactTokensOut(amp, _two(balances), _two(amountsOut), supply, invariant, fee);
    }

    function calcBptInGivenExactTokensOut3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256[3] calldata amountsOut,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return
            StableMath._calcBptInGivenExactTokensOut(amp, _three(balances), _three(amountsOut), supply, invariant, fee);
    }

    function calcTokenOutGivenExactBptIn2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256 index,
        uint256 bptIn,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcTokenOutGivenExactBptIn(amp, _two(balances), index, bptIn, supply, invariant, fee);
    }

    function calcTokenOutGivenExactBptIn3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256 index,
        uint256 bptIn,
        uint256 supply,
        uint256 invariant,
        uint256 fee
    ) external pure returns (uint256) {
        return StableMath._calcTokenOutGivenExactBptIn(amp, _three(balances), index, bptIn, supply, invariant, fee);
    }

    function getTokenBalance2(
        uint256 amp,
        uint256[2] calldata balances,
        uint256 invariant,
        uint256 index
    ) external pure returns (uint256) {
        return StableMath._getTokenBalanceGivenInvariantAndAllOtherBalances(amp, _two(balances), invariant, index);
    }

    function getTokenBalance3(
        uint256 amp,
        uint256[3] calldata balances,
        uint256 invariant,
        uint256 index
    ) external pure returns (uint256) {
        return StableMath._getTokenBalanceGivenInvariantAndAllOtherBalances(amp, _three(balances), invariant, index);
    }

    function _two(uint256[2] calldata a) private pure returns (uint256[] memory r) {
        r = new uint256[](2);
        r[0] = a[0];
        r[1] = a[1];
    }

    function _three(uint256[3] calldata a) private pure returns (uint256[] memory r) {
        r = new uint256[](3);
        r[0] = a[0];
        r[1] = a[1];
        r[2] = a[2];
    }
}
