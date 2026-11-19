# VENOMEUM 🐍✌️

**Venomeum Blockchain — $VMH**

Built by **Venom** ([@venomeum](https://github.com/venomeum)) with **venom.muse**.

> DYOR — don't trust, verify. Not your keys, not your coins.

## 🌐 Website

This repo is also the Venomeum website (GitHub Pages): **https://venomeum.github.io/venomeum/**

## What's in here

| Part | What it is |
| --- | --- |
| `index.html` | The Venomeum website, including a live read-only dashboard for the burner wallet |
| `contracts/` | The $VMH token (tax/burn/buyback), its BuybackBurner sink, the wrapped-native token, and the full deployment record |
| `tokens/vmh.json` | $VMH token metadata (name, symbol, logo, deployments) |
| `wallet-tools/` | Python tools that generated and verified the multichain burner wallet (BIP39 → BTC, EVM, Solana, TRON, SUI, TON, NEAR) |
| `wallet/addresses.json` | The burner wallet's **public** addresses only |
| `docs/faucet-plan.md` | The verified testnet faucet research + claim log |
| `assets/` | Venomeum logos |

## 🔥 Burner wallet

One BIP39 mnemonic, eight chains, generated and verified with 27/27 checks
(private keys re-derive to the addresses, sign/verify round-trips on every chain).

**Burner rules:** testnet / faucet / small amounts only. Never significant funds.

## 🚰 Faucet program

Daily automated testnet claims for the burner wallet (Circle USDC/EURC/cirBTC,
SUI, NEAR), every claim verified on-chain before it's reported.
Full research and results: [`docs/faucet-plan.md`](docs/faucet-plan.md).

## 🪙 $VMH token + Venomeum Swap (live on testnets, 2026-11-18)

**Venomeum (VMH)** — ERC-20, 1B supply. Tax on DEX trades only (wallet-to-wallet
transfers are free): **1% burned**, **1% automatic liquidity**, **1% automatic
buyback** (accrues, auto-swaps to the chain's native token, buys VMH back and
burns it). Neither testnet had a DEX, so we deployed our own Uniswap V2 —
**Venomeum Swap** — and the pools run on it. **Liquidity is removable:** LP
tokens sit in the provider's wallet and can be withdrawn at any time (proven
on-chain — 10% of every pool was withdrawn again after launch).

| Deployment | Contract | Pool pair |
| --- | --- | --- |
| Arc Testnet (burner) | `0xeF8a48269661Fd8d5FE1453A74d27Fe375178cef` | `0x39B3f0294E37C99a2395E443D6795e3B64742FD5` |
| Arc Testnet (Circle agent wallet) | `0x4666CA32A6af759d3dd4752ee1323778854BA6aB` | `0x97573A80f21Ab377D62c340b6C1a6f898133dF98` |
| Robinhood Chain Testnet (burner) | `0xA9808afB0213295778D0CEE459c182C1524858b4` | `0x496d70e4443566c4c94F8F2674e191699166cd21` |

Venomeum Swap (same addresses on both testnets): factory
`0x6e0F7bB0AfA4f4e0208e9A6F06a8759003E2D184`, router
`0xC83d7A0079Fc410Ddd4cE4aaD7bF2216350342Cb`, wrapped native
`0x5Df9ecECC7c0e7b43E7afC3b3238Aa19fB3A0C87`.
Verified end-to-end with real taxed trades: ~2,500 VMH burned per deployment
(tax burns + automatic buyback burns), auto-LP minted to the owner, buyback
fund spent to zero. Full record: [`contracts/deployments.json`](contracts/deployments.json).

## 🏷️ Venomeum Names + 🎯 sniper tool (live on testnets, 2026-11-18)

**Venomeum Names** — our ENS-style on-chain name service. Names end in
**.vmh**; each name is a **soul-bound NFT** (transfers and approvals revert —
a name can never be sold or moved, only burned by its owner). Free,
permissionless registration, ENS-style resolution (`resolve(label)` →
address) and reverse lookup (`primaryNameOf(address)` → "label.vmh").
Source: `contracts/VenomeumNames.sol`, record: `contracts/names-deployments.json`.

| Network | Names contract |
|---|---|
| Arc Testnet | `0x5a146cC69101e61f1C6700B5C9E781Eb507600A4` |
| Robinhood Chain Testnet | `0x510354Ae30f707CE37Ed2CD484F332df0066A739` |

First registrations (burner wallet, both chains): **venom.vmh** (#1) and
**venomeum.vmh** (#2). Soul-bound proof: a `transferFrom` attempt reverts
with `SOULBOUND` on both chains.

**Sniper tool** — `tools/sniper.py`: buy → immediately-sell round trips on
Venomeum Swap for on-chain trading activity. Slippage protection, dry-run
mode, hard testnet-only guardrails (refuses any other chain), 5-native cap.
Live demo: Arc 0.5 USDC → 400,444 VMH → 0.4982 USDC back (0.37% cost);
Robinhood 0.0002 ETH → 208,766 VMH → 0.000199 ETH back (0.48% cost).

## 🌐 Web3 browser — the agent's own dapp connection (built 2026-11-19)

A Chromium browser the agent fully controls via code (Puppeteer), with the
**Phantom** wallet extension loaded and the multichain **burner wallet**
imported into it — one recovery phrase, both an EVM account and a Solana
account (Bitget-style multichain). This is how the agent connects to dapps
and does wallet tasks itself: wallet-connect faucets, dapp sign-ins,
testnet tasks.

Verified after import — both addresses match the burner wallet exactly:
EVM `0x09045763Ea68FB7Ef0E0e51C26bcCf45846077f1`, Solana
`AjyRpt4jQ8WkS21J2HreLYHJf72wAWrAiJPWjP2N23Tz`. Dapp connection test
passes for both providers (`window.ethereum` + `window.solana`).

Source: `tools/web3-browser-setup.js`, `tools/web3-browser-check.js`,
`tools/web3-browser-lib.js`; full notes: `tools/web3-browser-README.md`.
**Burner / testnet only** — the wallet profile, password, and recovery
phrase live only in the agent's VM and are never in this repo.

## ⚠️ Security — read this first

**The wallet backup files (seed phrase + private keys) are NOT in this repo and
must NEVER be committed to GitHub — by anyone, ever.** They live only in private,
offline storage. The `.gitignore` in this repo blocks the backup filenames as a
second line of defence. Anything in this repo is public information only:
code, docs, logos, and public addresses.

## 🗺️ Roadmap (plans, in build)

- ✅ ERC-20 with burnable tax, automatic buyback, automatic liquidity — $VMH, live on Arc + Robinhood testnets
- ✅ Own Uniswap V2 pools (Venomeum Swap) with removable liquidity
- ✅ On-chain sniper tool + daily transaction activity for the EOA wallet — built, demoed live
- ✅ Soul-bound NFTs for name services (ENS / BASE.ETH style) — shipped as Venomeum Names (.vmh)
- ✅ Agent-controlled Web3 browser (EVM + Solana, Phantom) for dapp tasks — built and verified
- Venomeum Blockchain — the chain itself
