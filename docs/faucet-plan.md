# Venomeum Burner Wallet — Verified Faucet Plan
Checked: 2026-11-17 (GMT+7). Rules: free only, no KYC, never enter a seed phrase or private key on any site.

Scope (user-confirmed 2026-11-17): this faucet program is for the **burner wallet only**. The Circle agent wallet is separate — it only supports ARC USDC and is covered by its own daily claim; no other faucets/chains apply to it.

Wallet addresses are in `venomeum-burner-wallet-addresses.json` (same folder in Drive: muse.ai).

## ⚠️ Key blockers for this wallet
- EVM mainnet balance is empty → faucets gated on a mainnet balance (Alchemy, Google Cloud, QuickNode per most sources, BNB Chain official, Chainstack) will refuse this address until it holds ~0.001 ETH / 0.002 BNB mainnet.
- Wallet-connect faucets (Chainlink, thirdweb) conflict with the "keys stay in VM" rule — decision pending. Paste-address faucets are used first.
- Bitcoin testnet moved to **testnet4** (testnet3 deprecated). tb1 addresses work on testnet4.
- TON testnet claims need the **testnet-form address**: `0QAyzCfLeYKY08QLXm7ZvZGzyaggRCJp-nw3JmVub2qpxC4C` (same key as mainnet UQ… address). The Telegram bot rejects mainnet-form addresses.

## Verified ✅ — claimable now (no mainnet gate)
| Chain | Faucet | URL | Amount | Needs |
|---|---|---|---|---|
| SUI testnet+devnet | Sui official | faucet.sui.io | ~0.5 SUI/req | paste address only |
| Solana devnet | Solana Foundation | faucet.solana.com | up to 5 SOL, 2 req / 8h | paste; GitHub login raises limits |
| TRON Nile/Shasta | TRON official | nileex.io / shasta.tronex.io | varies, 1/24h per token | reCAPTCHA only |
| TRON Nile/Shasta | TronFAQBot (Telegram, in TRON dev group) | `!nile <addr>` / `!shasta <addr>` | 2,000 TRX / 24h | Telegram (have it) |
| TON testnet | Testgiver bot (official route) | t.me/testgiver_ton_bot | 2 GRAM, 1/hour | Telegram + captcha; use testnet-form address |
| NEAR testnet | NEAR docs faucet | docs.near.org/getting-started/faucet | small amount | paste implicit (hex) account ID |
| NEAR testnet | near-faucet.io (linked from NEAR docs) | near-faucet.io | NEAR + test tokens | paste address |
| BTC testnet4 | mempool.space faucet | mempool.space/testnet4/faucet | varies | GitHub login (have it) |
| BTC testnet4 | Coinfaucet.eu | coinfaucet.eu | varies | CAPTCHA |
| Sepolia | pk910 PoW faucet | sepolia-faucet.pk910.de | scales with mining time | nothing — browser mining |
| Base Sepolia (+Sepolia, SOL devnet) | Coinbase CDP faucet | portal.cdp.coinbase.com | up to 0.1 ETH / 24h + test USDC | free CDP account, no balance gate |
| Base Sepolia etc. | Superchain faucet | console.optimism.io/faucet | 0.01 ETH/day | GitHub link (have it) |
| Sepolia/BSC/Arb Sepolia/BTC/SOL/NEAR/TRON/SUI | Zalalena (third-party, ID company CV. ZalalenA Multimedia, new Apr 2026) | faucet.zalalena.com | tiny drips, 10/day, 60-min cooldown | hCaptcha only. Verified paying (Oct 2026 check) but balances fluctuate; burner-only, not endorsed by any chain |

## Verified ✅ but needs a decision (wallet connect)
| Chainlink | faucets.chain.link | 0.5 ETH + 25 LINK on ~60 testnets (Sepolia, Base Sepolia, Arbitrum Sepolia, Amoy…) | wallet connect only, no balance gate |
| thirdweb | thirdweb.com chain pages | 0.01 native/day on 500+ testnets incl. NEAR testnet | wallet connect |

**Chainlink attempt 2026-11-17:** the faucet also has a manual paste-address flow (no wallet/key needed). Claims were filled (25 LINK × Sepolia/Base Sepolia/Arbitrum Sepolia) but Cloudflare's "Verify you are human" checkbox could not be passed by the browser agent. Also learned: native ETH is not offered on Base/Arbitrum Sepolia there, and Sepolia ETH requests require holding ≥1 LINK on mainnet. User decision 2026-11-17: **skip Chainlink for now** (can be retried later with a manual checkbox tick by the user).

## Verified ✅ but gated (need a little mainnet balance first)
- Alchemy (0.1 / 24h per chain): needs ≥0.001 ETH mainnet + tx history
- Google Cloud Web3 faucet (0.05 Sepolia ETH): Google login + 0.001 ETH mainnet
- QuickNode (0.05 drips, 1/12h): small mainnet balance per most sources
- BNB Chain official (0.3 tBNB/day, also Telegram @bnbchain_official_bot): needs ≥0.002 BNB mainnet
- Chainstack (up to 0.5 / 24h, best API automation): account + API key + mainnet balance
- GetBlock (Amoy): free account

## Not verified / avoid ❌
- Infura Sepolia faucet — DEAD (redirects to homepage).
- Polygon official faucet — RETIRED (docs point to third parties; Amoy gas token is now POL).
- GizmoLab tools faucet — wallet-connect required, no official endorsement, absent from all roundups. Not recommended; official Solana faucet is strictly better.
- Blockchair "awesome faucets" — mostly mainnet earn/casino reward sites, NOT developer faucets. Avoid.
- faucetlink.to — one-person link directory; re-verify every destination.
- Any site asking for a seed phrase/private key, or promising free MAINNET coins for a connect+signature — scam/drainer. There are no legit mainnet faucets.

**pk910 PoW Sepolia attempt 2026-11-17:** contrary to expectations, the faucet gates mining behind a Cloudflare Turnstile checkbox — the browser agent could not pass it (same wall as everywhere else), address never entered, nothing mined. **User then mined/claimed it themselves the same evening — VERIFIED on-chain by Muse:** tx 0x41735894c4e6e8c832738008fc32e985737b2bc5c72ffef360c35c6e46b75812, +0.05 Sepolia ETH to the burner (its Sepolia balance is now exactly 0.05 ETH).

**BTC testnet4 attempt 2026-11-17:** mempool.space faucet — GitHub sign-in worked, but the faucet refused with "Your account does not allow you to access the faucet" (request button disabled). Likely cause: the venomeum GitHub account was created the same day; mempool gates the faucet on account standing. Revisit once the account has aged, or find another verified testnet4 faucet.

**Zalalena Robinhood — claimed by user manually 2026-11-17, VERIFIED on-chain by Muse:** tx 0xe18d000335fc6cd75fb2038062eb638281c3f650b992a394fc861df1b3cb61d2 — 0.01 ETH native + 5 each of test stock tokens (TSLA, AMD, AMZN, …) from the verified Faucet contract to the burner. (My browser attempt was Cloudflare-blocked; the user claimed it from their own device.)

**Solana + Zalalena attempts 2026-11-17:** Solana web faucet — GitHub (venomeum) connected, higher limit unlocked, 5 SOL selected, but Cloudflare Turnstile blocked the final claim; alternate RPC airdrop endpoints returned nothing (balance still 0). Zalalena Robinhood Chain — address pasted, but a Cloudflare overlay covers the form and never clears. User decision 2026-11-17: **skip both for now**; focus on no-captcha routes (pk910 PoW Sepolia + mempool.space BTC testnet4 started same evening).

**TRON Nile attempt 2026-11-17:** official faucet filled (1,000 TRX + 1,000 test USDT forms) but Cloudflare's challenge domain is blocked on the agent browser route — verification could not pass. User decision 2026-11-17: **skip TRON for now**. Biggest TRON drip remains the manual Telegram route (TronFAQBot, 2,000 TRX/day).

## Already running
- Circle faucet: daily auto-claim of 20 testnet USDC on ARC-TESTNET (agent wallet) — scheduled ~18:57 GMT+7 daily.

## Recurring plan (proposed)
- Daily: SUI (web/API), Solana devnet, TRON Nile, Zalalena top-ups, Circle ARC (running).
- Hourly-capable: TON testgiver (manual, Telegram).
- Weekly/as needed: pk910 PoW Sepolia mining session, mempool tBTC, NEAR, CDP Base Sepolia.
