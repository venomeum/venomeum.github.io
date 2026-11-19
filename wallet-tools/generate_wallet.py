#!/usr/bin/env python3
"""Generate ONE BIP39 mnemonic and derive multichain burner-wallet accounts.

Standards (cross-checked against the public BIP39 test vector, Ian Coleman):
- BTC SegWit: BIP84  m/84'/0'/0'/0/0   (testnet m/84'/1'/0'/0/0)
- EVM:        BIP44  m/44'/60'/0'/0/0  (same address on every EVM chain)
- TRON:       BIP44  m/44'/195'/0'/0/0
- Solana:     SLIP10 m/44'/501'/0'/0'  (Phantom/Solflare style, bip_utils acct+change)
- SUI:        BIP44  m/44'/784'/0'/0'/0'
- NEAR:       BIP44  m/44'/397'/0'/0'/0' (implicit account = hex ed25519 pubkey)
- TON:        BIP44  m/44'/607'/0'/0'/0' (multichain-wallet style, Wallet V4 address)

Secrets are written ONLY to the backup files. Stdout gets addresses only.
"""
import json
import os
import stat
from datetime import datetime, timezone

import base58
from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39SeedGenerator,
    Bip39WordsNum,
    Bip44,
    Bip44Changes,
    Bip44Coins,
    Bip84,
    Bip84Coins,
)

OUT_DIR = os.path.expanduser("~/workspace/your_files")
os.makedirs(OUT_DIR, exist_ok=True)

mnemonic = Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24)
seed = Bip39SeedGenerator(mnemonic).Generate("")  # no passphrase


def bip44(coin, change=True, index=True):
    ctx = Bip44.FromSeed(seed, coin).Purpose().Coin().Account(0)
    if change:
        ctx = ctx.Change(Bip44Changes.CHAIN_EXT)
    if index:
        ctx = ctx.AddressIndex(0)
    return ctx


def pub_raw(ctx):
    # secp256k1 coins only. NOTE: bip_utils RawCompressed() returns 33 bytes
    # for ed25519 coins (not the raw pubkey) - ed25519 pubkeys must come
    # from ed_pub_from_priv() below instead.
    pub = ctx.PublicKey()
    try:
        return pub.RawCompressed().ToBytes()
    except Exception:
        return pub.Raw().ToBytes()


def ed_pub_from_priv(priv_bytes):
    from solders.keypair import Keypair

    return bytes(Keypair.from_seed(priv_bytes).pubkey())


def bip84(coin):
    return (
        Bip84.FromSeed(seed, coin)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )


accounts = {}

# --- Bitcoin SegWit (BIP84) ---
c = bip84(Bip84Coins.BITCOIN)
accounts["bitcoin_mainnet_segwit"] = {
    "chain": "Bitcoin (mainnet, Native SegWit)",
    "standard": "BIP84",
    "derivation_path": "m/84'/0'/0'/0/0",
    "address": c.PublicKey().ToAddress(),
    "private_key_wif": c.PrivateKey().ToWif(),
    "private_key_hex": c.PrivateKey().Raw().ToHex(),
    "public_key_hex": c.PublicKey().RawCompressed().ToHex(),
}
c = bip84(Bip84Coins.BITCOIN_TESTNET)
accounts["bitcoin_testnet_segwit"] = {
    "chain": "Bitcoin (testnet, Native SegWit)",
    "standard": "BIP84",
    "derivation_path": "m/84'/1'/0'/0/0",
    "address": c.PublicKey().ToAddress(),
    "private_key_wif": c.PrivateKey().ToWif(),
    "private_key_hex": c.PrivateKey().Raw().ToHex(),
    "public_key_hex": c.PublicKey().RawCompressed().ToHex(),
}

# --- EVM (one address, all EVM chains mainnet + testnet) ---
c = bip44(Bip44Coins.ETHEREUM)
evm_address = c.PublicKey().ToAddress()
accounts["evm_all_chains"] = {
    "chain": "All EVM chains (Ethereum, Base, BSC, Polygon, Arbitrum, Optimism, Avalanche, Arc, zkSync, Linea, Scroll + all EVM testnets e.g. Sepolia, Base Sepolia, Arc Testnet)",
    "standard": "BIP44",
    "derivation_path": "m/44'/60'/0'/0/0",
    "address": evm_address,
    "private_key_hex": "0x" + c.PrivateKey().Raw().ToHex(),
    "public_key_hex": c.PublicKey().RawUncompressed().ToHex(),
}

# --- TRON ---
c = bip44(Bip44Coins.TRON)
accounts["tron"] = {
    "chain": "TRON (mainnet + Nile/Shasta testnets, same key)",
    "standard": "BIP44",
    "derivation_path": "m/44'/195'/0'/0/0",
    "address": c.PublicKey().ToAddress(),
    "private_key_hex": c.PrivateKey().Raw().ToHex(),
    "public_key_hex": c.PublicKey().RawUncompressed().ToHex(),
}

# --- Solana (bip_utils: account + change = m/44'/501'/0'/0') ---
c = bip44(Bip44Coins.SOLANA, change=True, index=False)
sol_seed = c.PrivateKey().Raw().ToBytes()
from solders.keypair import Keypair

kp = Keypair.from_seed(sol_seed)
sol_secret_b58 = base58.b58encode(bytes(kp)).decode()
accounts["solana"] = {
    "chain": "Solana (mainnet + devnet/testnet, same keypair)",
    "standard": "BIP44 / SLIP-0010 ed25519",
    "derivation_path": "m/44'/501'/0'/0'",
    "address": c.PublicKey().ToAddress(),
    "private_key_base58_keypair": sol_secret_b58,  # Phantom/Solflare import format (64-byte)
    "private_key_seed_hex": sol_seed.hex(),
    "public_key_base58": str(kp.pubkey()),
}

# --- SUI ---
c = bip44(Bip44Coins.SUI)
sui_priv = c.PrivateKey().Raw().ToBytes()
try:
    from bip_utils.bech32 import Bech32Encoder

    suipriv = Bech32Encoder.Encode("suiprivkey", 0, b"\x00" + sui_priv)
except Exception:
    suipriv = None
accounts["sui"] = {
    "chain": "SUI (mainnet + testnet/devnet, same key)",
    "standard": "BIP44 ed25519",
    "derivation_path": "m/44'/784'/0'/0'/0'",
    "address": c.PublicKey().ToAddress(),
    "private_key_hex": sui_priv.hex(),
    "private_key_suiprivkey": suipriv,
    "public_key_hex": ed_pub_from_priv(sui_priv).hex(),
}

# --- NEAR ---
c = bip44(Bip44Coins.NEAR_PROTOCOL)
near_priv = c.PrivateKey().Raw().ToBytes()
near_pub = ed_pub_from_priv(near_priv)
accounts["near"] = {
    "chain": "NEAR Protocol (implicit account; same key on testnet)",
    "standard": "BIP44 ed25519",
    "derivation_path": "m/44'/397'/0'/0'/0'",
    "address": c.PublicKey().ToAddress(),  # implicit account id = hex pubkey
    "private_key_hex": near_priv.hex(),
    "private_key_near_format": "ed25519:" + base58.b58encode(near_priv + near_pub).decode(),
    "public_key_hex": near_pub.hex(),
    "public_key_near_format": "ed25519:" + base58.b58encode(near_pub).decode(),
}

# --- TON ---
c = bip44(Bip44Coins.TON)
accounts["ton"] = {
    "chain": "TON / GRAM (mainnet Wallet V4, non-bounceable address shown; same key works on testnet)",
    "standard": "BIP44 ed25519 (multichain-wallet style, e.g. Trust/OKX/SafePal import from BIP39)",
    "derivation_path": "m/44'/607'/0'/0'/0'",
    "address": c.PublicKey().ToAddress(),
    "private_key_hex": c.PrivateKey().Raw().ToHex(),
    "public_key_hex": ed_pub_from_priv(c.PrivateKey().Raw().ToBytes()).hex(),
    "note": "Native TON wallets (Tonkeeper etc.) use TON's own 24-word mnemonic, which is a different system. Import this BIP39 phrase into a multichain wallet (Trust Wallet, OKX, SafePal, Bitget) to get this exact TON address.",
}

created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
backup = {
    "wallet_name": "Venomeum Multichain Burner Wallet",
    "created_utc": created,
    "type": "BIP39 burner wallet - TESTNET / FAUCET / SMALL AMOUNTS ONLY",
    "mnemonic_words": 24,
    "mnemonic": str(mnemonic),
    "passphrase": "",
    "warning": "Anyone with this mnemonic controls ALL accounts below on every chain. Keep it offline. This wallet was generated inside an AI agent VM - treat it as a hot burner wallet, never store significant funds in it.",
    "accounts": accounts,
}

json_path = os.path.join(OUT_DIR, "venomeum-burner-wallet-backup.json")
with open(json_path, "w") as f:
    json.dump(backup, f, indent=2)
os.chmod(json_path, stat.S_IRUSR | stat.S_IWUSR)

txt_lines = [
    "VENOMEUM MULTICHAIN BURNER WALLET - BACKUP",
    f"Created (UTC): {created}",
    "Type: BIP39, 24 words, no passphrase",
    "",
    "MNEMONIC (keep secret, offline):",
    str(mnemonic),
    "",
]
for key, a in accounts.items():
    txt_lines.append(f"[{key}] {a['chain']}")
    txt_lines.append(f"  Path:    {a['derivation_path']} ({a['standard']})")
    txt_lines.append(f"  Address: {a['address']}")
    for k, v in a.items():
        if k.startswith("private_key") and v:
            txt_lines.append(f"  {k}: {v}")
    txt_lines.append("")
txt_lines.append(backup["warning"])
txt_path = os.path.join(OUT_DIR, "venomeum-burner-wallet-backup.txt")
with open(txt_path, "w") as f:
    f.write("\n".join(txt_lines))
os.chmod(txt_path, stat.S_IRUSR | stat.S_IWUSR)

public = {
    "wallet_name": "Venomeum Multichain Burner Wallet - PUBLIC ADDRESSES ONLY (safe to share)",
    "created_utc": created,
    "addresses": {
        k: {"chain": a["chain"], "derivation_path": a["derivation_path"], "address": a["address"]}
        for k, a in accounts.items()
    },
}
pub_path = os.path.join(OUT_DIR, "venomeum-burner-wallet-addresses.json")
with open(pub_path, "w") as f:
    json.dump(public, f, indent=2)

# Stdout: addresses only, never secrets
print("GENERATED OK - 24-word BIP39, accounts:")
for k, a in accounts.items():
    print(f"  {k}: {a['address']}  ({a['derivation_path']})")
print("Files:", json_path, txt_path, pub_path)
