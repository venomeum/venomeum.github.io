# Venomeum Sniper 🎯

A tiny command-line tool that **buys a token with native currency and
immediately sells it back** on Venomeum Swap (our own Uniswap V2 fork).
One buy + one sell = one "round trip". It is a simple way to create real
trading activity for your own wallet on **testnet**.

> ⚠️ **Testnet only.** The tool hard-refuses mainnet: it only runs on
> Arc Testnet (chainId 5042002) and Robinhood Chain Testnet (chainId 46630).
> Buy size is capped at **5 native units** per round.

## What you need

- Python 3 with `web3` installed (in this workspace: `~/workspace/vmh-token/venv`)
- The burner wallet backup file at `~/workspace/your_files/venomeum-burner-wallet-backup.json`
  (the tool reads the EVM key from it at runtime — the key is never printed)
- A little testnet native for the buy + gas (USDC on Arc, ETH on Robinhood Chain)

## Quick start

Always do a **dry run first** — it quotes the buy and the sell and sends nothing:

```bash
cd ~/workspace/vmh-sniper
~/workspace/vmh-token/venv/bin/python sniper.py --chain arc --amount 0.5 --dry-run
```

Happy with the quotes? Run it for real:

```bash
~/workspace/vmh-token/venv/bin/python sniper.py --chain arc --amount 0.5
~/workspace/vmh-token/venv/bin/python sniper.py --chain robinhood --amount 0.0002
```

## Options

| Flag | What it does | Default |
|---|---|---|
| `--chain` | `arc` or `robinhood` (required) | — |
| `--token` | Token address to trade | that chain's $VMH |
| `--amount` | Buy size in native units, e.g. `0.5` (required, max 5) | — |
| `--slippage-bps` | How much worse than the quote you accept. 500 bps = 5% | `500` |
| `--rounds` | How many buy→sell round trips to do | `1` |
| `--delay-sec` | Pause in seconds between the buy and the sell | `0` |
| `--dry-run` | Quote everything, send nothing | off |
| `--result-json` | Save the round records to a JSON file | off |

## What a round trip costs

You never get back 100% of what you put in. The difference ("round-trip cost")
is the DEX swap fee + price impact, and — for wallets that are not fee-exempt —
the token's transfer tax ($VMH charges 3% on sells). The tool prints the exact
cost after every round, plus the gas for each transaction.

**Beginner note:** the burner wallet owns $VMH, and the token contract makes
the owner fee-exempt — so the demo numbers in `RESULT.md` show swap fee +
price impact only, no tax. Any other wallet trading $VMH would also pay the
3% sell tax (and 3% on buys).

## How it works (plain English)

1. Ask the router "how many tokens do I get for X native?" (`getAmountsOut`)
2. Buy with `swapExactETHForTokensSupportingFeeOnTransferTokens`
   (the "SupportingFeeOnTransfer" version is required for taxed tokens like $VMH)
3. Measure how many tokens actually arrived in the wallet
4. Approve the router to spend those tokens (only if needed)
5. Sell them all back with `swapExactTokensForETHSupportingFeeOnTransferTokens`
6. Print both transaction hashes, what came back, and the exact cost

Transactions are sent with legacy gas pricing because the Arc RPC rejects
transactions that mix EIP-1559 fields with a plain `gasPrice`.
