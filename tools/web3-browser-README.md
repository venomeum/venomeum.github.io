# Web3 Browser (agent-controlled, in-VM)

> Published copies: in this repo the scripts are named
> `web3-browser-lib.js`, `web3-browser-setup.js`, and
> `web3-browser-check.js`. The live build runs in the agent's VM under
> `~/workspace/web3-browser/` with the short names below. The wallet
> profile, password, and recovery phrase are never published.

A Chromium browser that Muse fully controls via code (Puppeteer), with the
**Phantom** wallet extension loaded and the multichain **burner wallet**
imported into it. One recovery phrase gives both an EVM account and a Solana
account — Bitget-style multichain, single wallet.

**Burner / testnet use only.** The imported wallet is the Venomeum burner
wallet (testnet/faucet funds). Never use this profile for mainnet funds.

## Verified accounts (public addresses)

| Chain  | Address                                      |
| ------ | -------------------------------------------- |
| EVM    | `0x09045763Ea68FB7Ef0E0e51C26bcCf45846077f1` |
| Solana | `AjyRpt4jQ8WkS21J2HreLYHJf72wAWrAiJPWjP2N23Tz` |

Both were verified against the burner backup after import, and the dapp
connection test passes for both providers.

## Layout

| Path               | What it is |
| ------------------ | ---------- |
| `lib.js` (repo: `web3-browser-lib.js`)     | Shared helpers: launch (persistent profile + extension + proxy), approval/unlock watcher, provider waits. |
| `setup.js` (repo: `web3-browser-setup.js`) | One-time (idempotent) import of the burner recovery phrase into Phantom + address verification. Skips the import if the profile already holds the wallet. |
| `check.js` (repo: `web3-browser-check.js`) | Reusable connection test: relaunches the profile, connects a benign page (example.org) through `window.ethereum` and `window.solana`, prints only the two public addresses + EVM chain ID. |
| `profile/`         | Persistent Chromium user-data dir (holds the Phantom vault). Keep it — deleting it means re-running setup. |
| `phantom/`         | Phantom extension, unpacked (v26.41.0, ID `bfnaelmomeimhlpmgjnjophhpkkoljpa`). |
| `.wallet-password` | The Phantom unlock password, `chmod 600`. Never print or share it. |
| `package.json`     | Node project (puppeteer 25.18.1 + wallet derivation libs). |

The recovery phrase itself is **not** stored here. `setup.js` reads it
in-memory from `~/workspace/your_files/venomeum-burner-wallet-backup.json`
at import time only; it is never logged or written anywhere by these scripts.

## Run

Everything must run under Xvfb (extensions need a headed-capable browser):

```bash
cd ~/workspace/web3-browser
xvfb-run -a node setup.js   # import + verify (safe to re-run)
xvfb-run -a node check.js   # connection test on example.org
```

Expected `check.js` output ends with:
`SUCCESS: both providers connected, addresses match the burner backup`

## Environment notes (hard-won)

- All VM egress goes through an authenticated HTTP proxy from the env vars.
  Chromium can't do proxy auth via flags, so `lib.js` runs a tiny local
  forwarder on `127.0.0.1:18080` that injects the credentials upstream.
- The proxy MITMs TLS with a local CA, so Chromium is launched with
  `--ignore-certificate-errors`.
- Phantom's sensitive screens ignore untrusted JS `click()` events:
  unlocking works by trusted-typing the password into the notification
  window and pressing **Enter**; approvals use trusted CDP clicks.
  `watchApprovals` in `lib.js` handles both automatically.
- The extension service worker must be "woken" (briefly open its popup
  page) before dapp provider injection is reliable — `lib.js` does this.
- Phantom derives Solana at `m/44'/501'/0'/0'` and EVM at
  `m/44'/60'/0'/0/0` — both match the burner backup exactly.
