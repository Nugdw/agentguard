// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Test-only stand-in for the Agent ID ERC-721: mint gives an
///         address a balance of 1, mirroring one-Agent-ID-per-user.
contract MockAgentId {
    mapping(address => uint256) private _bal;

    function mint(address to) external {
        _bal[to] = 1;
    }

    function balanceOf(address owner) external view returns (uint256) {
        return _bal[owner];
    }
}
