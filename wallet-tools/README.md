# wallet-tools

Python tools that created and verified the Venomeum multichain burner wallet.

One BIP39 24-word mnemonic (no passphrase) derives, per BIP44/49/84/49-style paths:

- **BTC** SegWit (BIP84) + BTC testnet
- **EVM** — one address for every EVM chain
- **Solana**, **TRON**, **SUI**, **TON**, **NEAR** (implicit account)

## Files

| File | Purpose |
| --- | --- |
| `generate_wallet.py` | Generates a fresh mnemonic wallet and writes the backup + public-address files |
| `verify_wallet.py` | Re-derives every address from the private keys in a backup file and runs sign/verify round-trips (27 checks) |
| `patch_pubkeys.py` | Utility used during the original build to fix ed25519 public-key fields in the backup |

## Usage

```bash
python3 -m venv venv && source venv/bin/activate
pip install bip-utils mnemonic eth-account solders base58 ecdsa
python3 generate_wallet.py   # writes backup + addresses files
python3 verify_wallet.py     # verifies a backup file end-to-end
```

## ⚠️ Security

These tools **generate real keys**. Only ever run them in a private environment,
and treat every output backup file like cash: never commit it, never upload it,
never paste it anywhere. The wallet made with these tools is a **burner** —
testnet, faucets, and small amounts only.
