// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// A rate provider returning a fixed rate, as Balancer's IRateProvider.
contract MockRateProvider {
    uint256 public immutable rate;

    constructor(uint256 rate_) {
        rate = rate_;
    }

    function getRate() external view returns (uint256) {
        return rate;
    }
}
