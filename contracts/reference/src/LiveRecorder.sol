// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

interface IExitPool {
    function exitGivenOut(uint256 j, uint256 amount) external returns (uint256);
    function getRate() external view returns (uint256);
}

/// The live demonstration's recorder on Base Sepolia (script/Live.s.sol). It
/// runs an attacker's batch against a pool, calls a contract, or deploys one,
/// and records the outcome in an event: on success the result, on failure the
/// exact revert data. A failure with no revert data, as running out of gas
/// gives, is not a recordable outcome, so it reverts the transaction instead.
contract LiveRecorder {
    /// The batch ran to the end, or reverted with `reason` and with it every
    /// exit before the failing one. The rates are value per pool share.
    event Attack(address indexed pool, uint256 exits, bool succeeded, uint256 rateBefore, uint256 rateAfter, bytes reason);
    event Call(address indexed target, bytes data, bool succeeded, bytes result);
    event Deployment(address deployed, bytes32 initCodeHash, bytes reason);

    error Inconclusive();

    /// The attacker's batch of exact-out exits: one failing exit fails them all.
    function run(IExitPool pool, uint256 index, uint256[] calldata amounts) external {
        for (uint256 i = 0; i < amounts.length; i++) {
            pool.exitGivenOut(index, amounts[i]);
        }
    }

    function attack(IExitPool pool, uint256 index, uint256[] calldata amounts) external returns (bool succeeded) {
        uint256 before = pool.getRate();
        bytes memory reason;
        try this.run(pool, index, amounts) {
            succeeded = true;
        } catch (bytes memory revertData) {
            _conclusive(revertData);
            reason = revertData;
        }
        emit Attack(address(pool), amounts.length, succeeded, before, pool.getRate(), reason);
    }

    function probe(address target, bytes calldata data) external returns (bool succeeded, bytes memory result) {
        (succeeded, result) = target.call(data);
        if (!succeeded) _conclusive(result);
        emit Call(target, data, succeeded, result);
    }

    /// Deploys `initCode`; `deployed` is zero when its constructor reverts.
    function deploy(bytes calldata initCode) external returns (address deployed) {
        bytes memory code = initCode;
        bytes memory reason;
        assembly {
            deployed := create(0, add(code, 0x20), mload(code))
            if iszero(deployed) {
                reason := mload(0x40)
                mstore(reason, returndatasize())
                returndatacopy(add(reason, 0x20), 0, returndatasize())
                mstore(0x40, add(add(reason, 0x20), and(add(returndatasize(), 31), not(31))))
            }
        }
        if (deployed == address(0)) _conclusive(reason);
        emit Deployment(deployed, keccak256(code), reason);
    }

    function _conclusive(bytes memory reason) internal pure {
        if (reason.length == 0) revert Inconclusive();
    }
}
