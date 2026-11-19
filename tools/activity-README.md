# Venomeum Activity Engine

A small program that creates **real on-chain activity every day** on our own
testnets — Arc Testnet and Robinhood Chain Testnet — using our two wallets:

- **Burner wallet** (`0x0904…77f1`) — signs transactions directly.
- **Circle agent wallet** (`0xea68…9087`, Arc only) — driven through the
  Circle CLI, the same way a person would use it.

Everything it touches is ours: our $VMH token, our Venomeum Swap pools, our
wallets, and worthless testnet coins. Think of it as a heartbeat for the
Venomeum testnet setup — it keeps the wallets, token and DEX exercised and
produces a verifiable trail of transactions.

## ⛔ Testnet only — forever

The engine checks the chain ID of every network it connects to and **refuses
to run on anything except 5042002 (Arc Testnet) and 46630 (Robinhood Chain
Testnet)**. There is no mainnet mode and no way to switch one on.

## What it does all day

Daily target: **1,000 confirmed transactions**, split like this:

| Portion | Share | What it does |
|---|---|---|
| Burner on Arc | 55% | $VMH transfers to the agent wallet, wrap/unwrap USDC↔WUSDC, tiny USDC transfers, buy→sell round trips on Venomeum Swap |
| Burner on Robinhood | 30% | $VMH self-transfers, wrap/unwrap ETH↔WETH, tiny ETH self-transfers, occasional round trips |
| Agent on Arc | 15% | $VMH transfers to the burner, tiny USDC transfers (via Circle CLI) |

Only transactions that actually confirm on-chain (receipt status = success)
are counted. Every confirmed transaction is written to `txlog.jsonl` with its
hash, and the running totals live in `state.json` (a fresh day, GMT+7,
starts from zero automatically).

## Safety rails

- **Balance floors** — a portion stops politely instead of draining a wallet:
  burner Arc stops at 2 USDC, burner Robinhood at 0.0015 ETH, agent at 2 USDC.
  The shortfall is logged, never hidden.
- **Human-ish pacing** — 3–8 seconds between burner transactions, 8–15
  seconds between agent actions (each one is an API call).
- **Failure handling** — a failed action is logged and skipped; 5 failures in
  a row (3 for the agent) stop that portion for the batch. If the Circle CLI
  ever reports an expired session or asks for terms acceptance, the agent
  portion is skipped — the engine never logs in or accepts terms by itself.
- **Repeat-safe** — run it as many times a day as you like; each `--batch N`
  run sends at most N transactions.

## How to run it

```bash
cd ~/workspace/vmh-activity
PY=~/workspace/vmh-token/venv/bin/python

$PY engine.py --status              # today's counts vs the 1,000 target
$PY engine.py --batch 45 --dry-run  # preview a batch: plan only, sends nothing
$PY engine.py --batch 45            # run a batch of up to 45 transactions
$PY engine.py --batch 200           # a bigger batch (same 55/30/15 split)
```

A full day (1,000 txns) can be run as one big batch or several smaller ones —
the state file keeps the day's score either way.

## Files

- `engine.py` — the engine itself.
- `state.json` — today's counters (auto-created, resets daily at GMT+7).
- `txlog.jsonl` — append-only log of every confirmed transaction.
- `RESULT.md` — the live test-batch report (numbers, gas, cost projection).
