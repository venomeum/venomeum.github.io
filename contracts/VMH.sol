// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Venomeum (VMH) — ERC-20 with:
 *  - Burnable tax: a slice of every DEX buy/sell tax is burned forever.
 *  - Automatic liquidity pool: a slice accrues in the contract and is
 *    auto-swapped + paired into the Uniswap V2 liquidity pool on sells.
 *  - Automatic buyback: a slice accrues, is auto-swapped to the chain's
 *    native token, and the accumulated fund auto-buys VMH and burns it.
 *
 * Tax only applies to trades against the liquidity pair (buys/sells),
 * never to plain wallet-to-wallet transfers. Owner and the contract
 * itself are fee-exempt. All thresholds and tax rates are owner-tunable.
 */

interface IBuybackBurner {
    function forward() external;
}

interface IUniswapV2Factory {
    function createPair(address tokenA, address tokenB) external returns (address pair);
    function getPair(address tokenA, address tokenB) external view returns (address pair);
}

interface IUniswapV2Router02 {
    function factory() external view returns (address);
    function WETH() external view returns (address);
    function swapExactTokensForETHSupportingFeeOnTransferTokens(
        uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external;
    function swapExactETHForTokensSupportingFeeOnTransferTokens(
        uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external payable;
    function addLiquidityETH(
        address token, uint amountTokenDesired, uint amountTokenMin, uint amountETHMin, address to, uint deadline
    ) external payable returns (uint amountToken, uint amountETH, uint liquidity);
}

contract Venomeum {
    string public constant name = "Venomeum";
    string public constant symbol = "VMH";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    address public owner;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => bool) public feeExempt;

    // --- Tax config (basis points of each buy/sell) ---
    uint256 public burnBps = 100;    // 1% burned
    uint256 public liqBps = 100;     // 1% to auto-liquidity
    uint256 public buybackBps = 100; // 1% to buyback reserve

    // --- DEX wiring ---
    IUniswapV2Router02 public router;
    address public pair;
    address public weth;

    // --- Accumulators (tokens held by this contract, by purpose) ---
    uint256 public liqAccum;
    uint256 public buybackAccum;
    uint256 public buybackFund; // native token (ETH / USDC on Arc) held for buybacks
    address public buybackBurner; // sink for buyback purchases (pair.swap forbids the token itself as recipient)

    uint256 public liqThreshold = 50_000 * 10 ** 18;
    uint256 public buybackSwapThreshold = 50_000 * 10 ** 18;
    uint256 public buybackFireThreshold = 0.5 ether;

    bool private inSwap;
    bool public tradingTaxEnabled = true;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event OwnershipTransferred(address indexed from, address indexed to);
    event TaxTaken(address indexed from, uint256 burnAmt, uint256 liqAmt, uint256 buybackAmt);
    event LiquidityAdded(uint256 tokens, uint256 nativeUsed, uint256 lpMinted);
    event BuybackReserveFunded(uint256 tokensSwapped, uint256 nativeReceived);
    event BuybackExecuted(uint256 nativeSpent, uint256 tokensBurned);
    event Burn(address indexed burner, uint256 value);

    modifier onlyOwner() { require(msg.sender == owner, "not owner"); _; }
    modifier lockSwap() { inSwap = true; _; inSwap = false; }

    constructor(address router_, address initialOwner) {
        require(initialOwner != address(0), "zero owner");
        owner = initialOwner;
        totalSupply = 1_000_000_000 * 10 ** uint256(decimals); // 1B VMH
        balanceOf[initialOwner] = totalSupply;
        feeExempt[initialOwner] = true;
        feeExempt[address(this)] = true;
        emit Transfer(address(0), initialOwner, totalSupply);
        if (router_ != address(0)) {
            router = IUniswapV2Router02(router_);
            weth = router.WETH();
        }
    }

    receive() external payable {}

    // ---------- ERC-20 ----------
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "allowance");
        if (allowed != type(uint256).max) allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }

    /// @notice Any holder can burn their own VMH.
    function burn(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
        emit Burn(msg.sender, amount);
    }

    // ---------- Core transfer with tax ----------
    function _transfer(address from, address to, uint256 amount) internal {
        require(to != address(0), "zero address");
        require(balanceOf[from] >= amount, "balance");

        // Automation runs FIRST, before this transfer moves any balance,
        // and only ever processes tax accrued by PREVIOUS trades. Firing it
        // after the balance update would let nested swaps rewrite the pair's
        // reserves mid-swap and break the outer trade's accounting — the
        // classic reason production tax tokens trigger at transfer start.
        if (to == pair && !inSwap && address(router) != address(0)) {
            if (liqAccum >= liqThreshold) swapAndLiquify();
            if (buybackAccum >= buybackSwapThreshold) fundBuybackReserve();
            if (buybackFund >= buybackFireThreshold) _executeBuyback();
        }

        bool isTrade = pair != address(0) && (from == pair || to == pair);
        bool takeFee = tradingTaxEnabled && isTrade && !inSwap
            && !feeExempt[from] && !feeExempt[to];

        balanceOf[from] -= amount;

        if (!takeFee) {
            balanceOf[to] += amount;
            emit Transfer(from, to, amount);
        } else {
            uint256 burnAmt = (amount * burnBps) / 10_000;
            uint256 liqAmt = (amount * liqBps) / 10_000;
            uint256 bbAmt = (amount * buybackBps) / 10_000;
            uint256 taxTotal = burnAmt + liqAmt + bbAmt;

            balanceOf[to] += amount - taxTotal;
            emit Transfer(from, to, amount - taxTotal);

            if (burnAmt > 0) {
                totalSupply -= burnAmt;
                emit Transfer(from, address(0), burnAmt);
            }
            uint256 toContract = liqAmt + bbAmt;
            if (toContract > 0) {
                balanceOf[address(this)] += toContract;
                liqAccum += liqAmt;
                buybackAccum += bbAmt;
                emit Transfer(from, address(this), toContract);
            }
            emit TaxTaken(from, burnAmt, liqAmt, bbAmt);
        }
    }

    // ---------- Automatic liquidity ----------
    function swapAndLiquify() public lockSwap {
        uint256 amount = liqAccum;
        if (amount == 0 || address(router) == address(0)) return;
        liqAccum = 0;
        uint256 half = amount / 2;
        uint256 otherHalf = amount - half;

        uint256 nativeBefore = address(this).balance;
        _swapTokensForNative(half);
        uint256 nativeReceived = address(this).balance - nativeBefore;
        if (nativeReceived == 0) { liqAccum = amount; return; } // swap failed silently; restore

        _approveThis(address(router), otherHalf);
        try router.addLiquidityETH{value: nativeReceived}(
            address(this), otherHalf, 0, 0, owner, block.timestamp + 600
        ) returns (uint256, uint256 usedNative, uint256 lp) {
            emit LiquidityAdded(otherHalf, usedNative, lp);
        } catch {
            liqAccum = otherHalf; // keep tokens for a later retry
        }
    }

    // ---------- Automatic buyback ----------
    /// @notice Swaps the accrued buyback-tax tokens into native and parks it in buybackFund.
    function fundBuybackReserve() public lockSwap {
        uint256 amount = buybackAccum;
        if (amount == 0 || address(router) == address(0)) return;
        buybackAccum = 0;
        uint256 nativeBefore = address(this).balance;
        _swapTokensForNative(amount);
        uint256 received = address(this).balance - nativeBefore;
        buybackFund += received;
        emit BuybackReserveFunded(amount, received);
    }

    /// @notice Owner can fire the buyback manually; sells also fire it
    /// automatically once buybackFund passes buybackFireThreshold.
    function executeBuyback() external onlyOwner lockSwap {
        require(buybackFund > 0, "no fund");
        _executeBuyback();
    }

    /// @dev Internal: spends buybackFund on VMH from the pool and burns
    /// everything bought. Purchases land in the BuybackBurner sink first
    /// (pair.swap forbids the token contract as recipient), which forwards
    /// them here to be burned. Never reverts the caller's trade: if the
    /// swap fails, the fund is restored for a later attempt.
    function _executeBuyback() internal {
        if (buybackFund == 0 || pair == address(0) || buybackBurner == address(0)) return;
        uint256 spend = buybackFund;
        buybackFund = 0;

        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = address(this);
        uint256 balBefore = balanceOf[address(this)];
        try router.swapExactETHForTokensSupportingFeeOnTransferTokens{value: spend}(
            0, path, buybackBurner, block.timestamp + 600
        ) {
            IBuybackBurner(buybackBurner).forward();
            uint256 bought = balanceOf[address(this)] - balBefore;
            if (bought > 0) {
                balanceOf[address(this)] -= bought;
                totalSupply -= bought;
                emit Transfer(address(this), address(0), bought);
            }
            emit BuybackExecuted(spend, bought);
        } catch {
            buybackFund = spend; // restore; try again on a later sell
        }
    }

    function _swapTokensForNative(uint256 amount) internal {
        _approveThis(address(router), amount);
        address[] memory path = new address[](2);
        path[0] = address(this);
        path[1] = weth;
        try router.swapExactTokensForETHSupportingFeeOnTransferTokens(
            amount, 0, path, address(this), block.timestamp + 600
        ) {} catch {}
    }

    function _approveThis(address spender, uint256 amount) internal {
        allowance[address(this)][spender] = amount;
        emit Approval(address(this), spender, amount);
    }

    // ---------- Owner wiring & config ----------
    function setRouter(address router_) external onlyOwner {
        router = IUniswapV2Router02(router_);
        if (router_ != address(0)) weth = router.WETH();
    }

    function createPair() external onlyOwner returns (address) {
        require(address(router) != address(0), "no router");
        IUniswapV2Factory factory = IUniswapV2Factory(router.factory());
        address existing = factory.getPair(address(this), weth);
        pair = existing != address(0) ? existing : factory.createPair(address(this), weth);
        return pair;
    }

    function setPair(address pair_) external onlyOwner { pair = pair_; }
    function setBuybackBurner(address burner_) external onlyOwner { buybackBurner = burner_; }

    function setTaxes(uint256 burn_, uint256 liq_, uint256 buyback_) external onlyOwner {
        require(burn_ + liq_ + buyback_ <= 1_000, "tax >10%");
        burnBps = burn_; liqBps = liq_; buybackBps = buyback_;
    }

    function setThresholds(uint256 liq_, uint256 bbSwap_, uint256 bbFire_) external onlyOwner {
        liqThreshold = liq_; buybackSwapThreshold = bbSwap_; buybackFireThreshold = bbFire_;
    }

    function setFeeExempt(address who, bool exempt) external onlyOwner { feeExempt[who] = exempt; }
    function setTradingTaxEnabled(bool on) external onlyOwner { tradingTaxEnabled = on; }

    function transferOwnership(address to) external onlyOwner {
        emit OwnershipTransferred(owner, to);
        owner = to;
    }
}
