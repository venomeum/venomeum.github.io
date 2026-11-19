#!/usr/bin/env python3
"""Venomeum Sniper — buy a token with native, then immediately sell it back.

A round-trip trader for our own Uniswap V2 fork (Venomeum Swap) on the
Arc and Robinhood Chain TESTNETS. It creates real on-chain trading activity
for your own wallet against your own pools: buy -> (optional pause) -> sell
everything you just received.

Safety rails built in:
  * Testnet only — the script refuses any chain id other than 5042002
    (Arc Testnet) and 46630 (Robinhood Chain Testnet). Mainnet is impossible.
  * Buy size is capped at 5 native units per round.
  * --dry-run quotes everything and sends nothing.

The burner wallet key is read at runtime from the local backup file and is
never printed.

Usage examples:
  python3 sniper.py --chain arc --amount 0.5 --dry-run
  python3 sniper.py --chain arc --amount 0.5
  python3 sniper.py --chain robinhood --amount 0.0002 --rounds 3
"""
import argparse, json, os, sys, time
from decimal import Decimal
from web3 import Web3

BACKUP = os.path.expanduser("~/workspace/your_files/venomeum-burner-wallet-backup.json")

ROUTER = "0xC83d7A0079Fc410Ddd4cE4aaD7bF2216350342Cb"
FACTORY = "0x6e0F7bB0AfA4f4e0208e9A6F06a8759003E2D184"
MAX_AMOUNT = Decimal("5")          # hard cap per round, native units
ALLOWED_CHAINS = {5042002, 46630}  # testnets only — mainnet refused

CHAINS = {
    "arc": {
        "name": "Arc Testnet", "rpc": "https://rpc.testnet.arc.network",
        "chain_id": 5042002, "native_symbol": "USDC",
        "wrapped_native": "0x5Df9ecECC7c0e7b43E7afC3b3238Aa19fB3A0C87",
        "default_token": "0xeF8a48269661Fd8d5FE1453A74d27Fe375178cef",  # $VMH
    },
    "robinhood": {
        "name": "Robinhood Chain Testnet", "rpc": "https://rpc.testnet.chain.robinhood.com",
        "chain_id": 46630, "native_symbol": "ETH",
        "wrapped_native": "0x5Df9ecECC7c0e7b43E7afC3b3238Aa19fB3A0C87",
        "default_token": "0xA9808afB0213295778D0CEE459c182C1524858b4",  # $VMH
    },
}

# Minimal ABIs (standard Uniswap V2 Router02 + ERC20 + Factory) — self-contained.
ROUTER_ABI = json.loads("""[
 {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"","type":"uint256[]"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},
 {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"}
]""")
FACTORY_ABI = json.loads("""[
 {"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
]""")
ERC20_ABI = json.loads("""[
 {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}
]""")
ZERO = "0x0000000000000000000000000000000000000000"


def fmt(raw, decimals):
    """Raw integer -> short human string."""
    d = Decimal(raw) / (Decimal(10) ** decimals)
    return f"{d:,.6f}".rstrip("0").rstrip(".") if d != d.to_integral_value() else f"{d:,.0f}"


def send(w3, acct, tx):
    """Legacy-gas send (Arc RPC rejects mixed EIP-1559 + gasPrice txs)."""
    tx.pop("maxFeePerGas", None)
    tx.pop("maxPriorityFeePerGas", None)
    tx["nonce"] = w3.eth.get_transaction_count(acct.address)
    tx["gasPrice"] = int(w3.eth.gas_price * 1.3) or 1
    tx["chainId"] = w3.eth.chain_id
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=300)
    if r.status != 1:
        raise RuntimeError(f"transaction reverted on-chain: {h.to_0x_hex()}")
    return h.to_0x_hex(), r


def main():
    ap = argparse.ArgumentParser(description="Venomeum Sniper: buy then immediately sell (testnet round trip).")
    ap.add_argument("--chain", choices=list(CHAINS), required=True)
    ap.add_argument("--token", default=None, help="token address (default: that chain's $VMH)")
    ap.add_argument("--amount", required=True, help="buy size in native units, e.g. 0.5")
    ap.add_argument("--slippage-bps", type=int, default=500, help="default 500 = 5%%")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--delay-sec", type=float, default=0, help="pause between buy and sell")
    ap.add_argument("--dry-run", action="store_true", help="quote everything, send nothing")
    ap.add_argument("--result-json", default=None, help="optional: write round records to this JSON file")
    args = ap.parse_args()

    amount_dec = Decimal(args.amount)
    if amount_dec <= 0:
        sys.exit("error: --amount must be positive")
    if amount_dec > MAX_AMOUNT:
        sys.exit(f"error: --amount capped at {MAX_AMOUNT} native units per round (safety rail)")
    if not (0 <= args.slippage_bps < 10000):
        sys.exit("error: --slippage-bps must be between 0 and 9999")
    if args.rounds < 1:
        sys.exit("error: --rounds must be >= 1")

    ch = CHAINS[args.chain]
    token_addr = Web3.to_checksum_address(args.token or ch["default_token"])
    wn = Web3.to_checksum_address(ch["wrapped_native"])
    router_addr = Web3.to_checksum_address(ROUTER)

    w3 = Web3(Web3.HTTPProvider(ch["rpc"], request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        sys.exit(f"error: cannot reach {ch['name']} RPC ({ch['rpc']})")
    chain_id = w3.eth.chain_id
    if chain_id not in ALLOWED_CHAINS or chain_id != ch["chain_id"]:
        sys.exit(f"error: refusing to run — chain id {chain_id} is not an allowed testnet")

    # Load the burner key at runtime; never printed.
    data = json.load(open(BACKUP))
    key = data["accounts"]["evm_all_chains"]["private_key_hex"]
    acct = w3.eth.account.from_key(key)
    me = acct.address

    router = w3.eth.contract(address=router_addr, abi=ROUTER_ABI)
    factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY), abi=FACTORY_ABI)
    token = w3.eth.contract(address=token_addr, abi=ERC20_ABI)

    pair = factory.functions.getPair(wn, token_addr).call()
    if pair == ZERO:
        sys.exit(f"error: no Venomeum Swap pair exists for {token_addr} vs wrapped native on {ch['name']}")

    try:
        tdec = token.functions.decimals().call()
        tsym = token.functions.symbol().call()
    except Exception:
        sys.exit(f"error: {token_addr} does not look like an ERC-20 token on {ch['name']}")

    amount_in = int(amount_dec * (Decimal(10) ** 18))  # native is 18 decimals on both chains
    slip = Decimal(10000 - args.slippage_bps) / Decimal(10000)
    nsym = ch["native_symbol"]

    print(f"=== Venomeum Sniper — {ch['name']} (chainId {chain_id}) ===")
    print(f"wallet : {me}")
    print(f"token  : {tsym} {token_addr}")
    print(f"pair   : {pair}")
    print(f"plan   : {args.rounds} round(s) x {args.amount} {nsym} buy -> sell, slippage {args.slippage_bps} bps"
          + ("  [DRY RUN — nothing will be sent]" if args.dry_run else ""))

    start_native = w3.eth.get_balance(me)
    start_token = token.functions.balanceOf(me).call()
    print(f"start  : {fmt(start_native, 18)} {nsym} | {fmt(start_token, tdec)} {tsym}")

    records = []
    for rnd in range(1, args.rounds + 1):
        print(f"\n--- round {rnd}/{args.rounds} ---")
        deadline = int(time.time()) + 300

        # ---- quote buy ----
        try:
            quote_buy = router.functions.getAmountsOut(amount_in, [wn, token_addr]).call()[-1]
        except Exception as e:
            sys.exit(f"error: buy quote failed (pair has no liquidity?): {e}")
        min_out = int(Decimal(quote_buy) * slip)
        print(f"buy quote : {args.amount} {nsym} -> ~{fmt(quote_buy, tdec)} {tsym} (min accepted {fmt(min_out, tdec)})")

        if args.dry_run:
            # Hypothetical sell quote on the quoted buy output.
            q_sell = router.functions.getAmountsOut(quote_buy, [token_addr, wn]).call()[-1]
            print(f"sell quote: ~{fmt(quote_buy, tdec)} {tsym} -> ~{fmt(q_sell, 18)} {nsym} "
                  f"(before the token's transfer tax; real recovery will be lower)")
            records.append({"round": rnd, "dry_run": True, "buy_quote_tokens": str(quote_buy),
                            "sell_quote_native": str(q_sell)})
            continue

        bal_before = token.functions.balanceOf(me).call()
        native_before_buy = w3.eth.get_balance(me)

        # ---- buy ----
        buy_tx = router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
            min_out, [wn, token_addr], me, deadline)
        buy_hash, buy_rcpt = send(w3, acct, buy_tx.build_transaction({"from": me, "value": amount_in}))
        received = token.functions.balanceOf(me).call() - bal_before
        if received <= 0:
            sys.exit(f"error: buy tx {buy_hash} mined but no tokens arrived")
        # Effective keep-rate of the buy leg (1.0 = no tax) — used to quote the sell realistically.
        keep = Decimal(received) / Decimal(quote_buy) if quote_buy else Decimal(1)
        print(f"buy tx    : {buy_hash}")
        print(f"received  : {fmt(received, tdec)} {tsym} (keep-rate vs quote: {keep:.4f})")

        if args.delay_sec > 0:
            print(f"waiting {args.delay_sec}s before selling...")
            time.sleep(args.delay_sec)

        # ---- approve if needed ----
        if token.functions.allowance(me, router_addr).call() < received:
            _, app_rcpt = send(w3, acct, token.functions.approve(router_addr, received).build_transaction({"from": me}))
            print(f"approve   : router approved for {fmt(received, tdec)} {tsym}")

        # ---- quote sell on the amount the pair will actually receive (post-tax) ----
        eff_in = int(Decimal(received) * keep)
        quote_sell = router.functions.getAmountsOut(max(eff_in, 1), [token_addr, wn]).call()[-1]
        min_native = int(Decimal(quote_sell) * slip)
        print(f"sell quote: {fmt(received, tdec)} {tsym} -> ~{fmt(quote_sell, 18)} {nsym} (min accepted {fmt(min_native, 18)})")

        native_before_sell = w3.eth.get_balance(me)
        sell_tx = router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
            received, min_native, [token_addr, wn], me, int(time.time()) + 300)
        sell_hash, sell_rcpt = send(w3, acct, sell_tx.build_transaction({"from": me}))
        sell_gas_cost = sell_rcpt.gasUsed * sell_rcpt.effectiveGasPrice
        recovered = w3.eth.get_balance(me) - native_before_sell + sell_gas_cost
        buy_gas_cost = buy_rcpt.gasUsed * buy_rcpt.effectiveGasPrice
        cost = amount_in - recovered
        print(f"sell tx   : {sell_hash}")
        print(f"recovered : {fmt(recovered, 18)} {nsym}")
        print(f"round-trip cost: {fmt(cost, 18)} {nsym} "
              f"({Decimal(cost) / Decimal(amount_in) * 100:.2f}% of buy size — sell tax + price impact; "
              f"gas buy {fmt(buy_gas_cost, 18)} / sell {fmt(sell_gas_cost, 18)} {nsym} on top)")
        records.append({
            "round": rnd, "dry_run": False, "buy_tx": buy_hash, "sell_tx": sell_hash,
            "amount_in_native": str(amount_in), "tokens_received": str(received),
            "native_recovered": str(recovered), "round_trip_cost_native": str(cost),
            "buy_gas_native": str(buy_gas_cost), "sell_gas_native": str(sell_gas_cost),
        })

    end_native = w3.eth.get_balance(me)
    end_token = token.functions.balanceOf(me).call()
    print(f"\nend    : {fmt(end_native, 18)} {nsym} | {fmt(end_token, tdec)} {tsym}")
    print(f"wallet native delta over run: {fmt(end_native - start_native, 18)} {nsym} "
          f"(includes gas; token delta {fmt(end_token - start_token, tdec)} {tsym})")

    if args.result_json:
        payload = {"chain": ch["name"], "chain_id": chain_id, "wallet": me, "token": token_addr,
                   "token_symbol": tsym, "pair": pair, "amount_per_round": args.amount,
                   "native_symbol": nsym, "start_native": str(start_native), "end_native": str(end_native),
                   "start_token": str(start_token), "end_token": str(end_token), "rounds": records}
        with open(args.result_json, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"results written to {args.result_json}")


if __name__ == "__main__":
    main()
