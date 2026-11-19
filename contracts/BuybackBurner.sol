// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20Mini {
    function balanceOf(address who) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @notice Companion sink for Venomeum's automatic buyback.
/// Uniswap V2 pair.swap() rejects the token contract itself as the swap
/// recipient ("INVALID_TO"), so buyback purchases land here first; the
/// VMH contract then calls forward() to pull them in and burn them.
contract BuybackBurner {
    address public immutable vmh;

    constructor(address vmh_) {
        vmh = vmh_;
    }

    function forward() external {
        require(msg.sender == vmh, "only vmh");
        uint256 bal = IERC20Mini(vmh).balanceOf(address(this));
        if (bal > 0) {
            require(IERC20Mini(vmh).transfer(vmh, bal), "transfer failed");
        }
    }
}
