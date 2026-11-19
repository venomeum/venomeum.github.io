#!/usr/bin/env python3
"""Independent verification of the burner wallet backup.

For each chain, recompute the address FROM THE PRIVATE KEY (or via an
independent SLIP-0010 ed25519 derivation from the BIP39 seed computed with
plain PBKDF2) and compare to the address stored in the backup.
Also runs sign/verify round-trips where the format allows.
Prints PASS/FAIL only - never secrets.
"""
import hashlib
import hmac as hmac_mod
import json
import os
import unicodedata

import base58

BACKUP = os.path.expanduser("~/workspace/your_files/venomeum-burner-wallet-backup.json")
data = json.load(open(BACKUP))
mnemonic = data["mnemonic"]
accts = data["accounts"]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


# --- 0. Mnemonic checksum + seed via independent PBKDF2 (BIP39 spec) ---
from mnemonic import Mnemonic as PyMnemonic

check("mnemonic_checksum", PyMnemonic("english").check(mnemonic), "24 words, BIP39 checksum valid")
m = unicodedata.normalize("NFKD", mnemonic)
salt = unicodedata.normalize("NFKD", "mnemonic")  # no passphrase
seed_ind = hashlib.pbkdf2_hmac("sha512", m.encode(), salt.encode(), 2048, dklen=64)

from bip_utils import Bip39SeedGenerator

seed_bu = Bip39SeedGenerator(mnemonic).Generate("")
check("seed_cross_lib", seed_ind == seed_bu, "PBKDF2 seed matches bip_utils seed")


# --- SLIP-0010 ed25519 independent derivation ---
def slip10(seed, path):
    k, c = seed, b"ed25519 seed"
    key = hmac_mod.new(c, k, hashlib.sha512).digest()
    priv, chain = key[:32], key[32:]
    for idx in path:
        idx_h = idx + 0x80000000
        payload = b"\x00" + priv + idx_h.to_bytes(4, "big")
        key = hmac_mod.new(chain, payload, hashlib.sha512).digest()
        priv, chain = key[:32], key[32:]
    return priv


def ed_pub(priv32):
    from solders.keypair import Keypair

    return bytes(Keypair.from_seed(priv32).pubkey())


# --- 1. EVM: private key -> address via eth_account + sign/recover ---
from eth_account import Account
from eth_account.messages import encode_defunct

a = accts["evm_all_chains"]
acct = Account.from_key(a["private_key_hex"])
check("evm_privkey_to_address", acct.address.lower() == a["address"].lower(), a["address"])
msg = encode_defunct(text="venomeum burner verify")
sig = acct.sign_message(msg)
rec = Account.recover_message(msg, signature=sig.signature)
check("evm_sign_recover", rec.lower() == a["address"].lower(), "signed message recovers to address")


# --- 2. BTC SegWit: private key -> P2WPKH bech32, manual ---
import ecdsa
from ecdsa.util import sigencode_der


def hash160(b):
    return hashlib.new("ripemd160", hashlib.sha256(b).digest()).digest()


BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def bech32_polymod(vals):
    chk = 1
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    for v in vals:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    return chk


def bech32_encode(hrp, witver, witprog):
    data = [witver] + convertbits(witprog, 8, 5)
    vals = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp] + data
    poly = bech32_polymod(vals + [0] * 6) ^ 1
    cs = [(poly >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32[d] for d in data + cs)


def convertbits(data, fb, tb, pad=True):
    acc, bits, ret = 0, 0, []
    maxv = (1 << tb) - 1
    for v in data:
        acc = (acc << fb) | v
        bits += fb
        while bits >= tb:
            bits -= tb
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tb - bits)) & maxv)
    return ret


for key, hrp in (("bitcoin_mainnet_segwit", "bc"), ("bitcoin_testnet_segwit", "tb")):
    a = accts[key]
    sk = ecdsa.SigningKey.from_string(bytes.fromhex(a["private_key_hex"]), curve=ecdsa.SECP256k1)
    pub_c = sk.get_verifying_key().to_string("compressed")
    addr = bech32_encode(hrp, 0, hash160(pub_c))
    check(f"{key}_privkey_to_address", addr == a["address"], a["address"])
    # WIF decode check
    wif_raw = base58.b58decode_check(a["private_key_wif"])
    check(f"{key}_wif_matches", wif_raw[1:33].hex() == a["private_key_hex"], "WIF decodes to same private key")
    # ECDSA sign/verify round trip
    digest = hashlib.sha256(b"venomeum burner verify").digest()
    signature = sk.sign_digest(digest, sigencode=sigencode_der)
    ok = sk.get_verifying_key().verify_digest(signature, digest, sigdecode=__import__("ecdsa.util", fromlist=["sigdecode_der"]).sigdecode_der)
    check(f"{key}_sign_verify", ok, "ECDSA sign/verify ok")


# --- 3. TRON: private key -> address manual (keccak + base58check, 0x41 prefix) ---
from eth_utils import keccak as _keccak


def tron_address(priv_hex):
    sk = ecdsa.SigningKey.from_string(bytes.fromhex(priv_hex), curve=ecdsa.SECP256k1)
    pub_u = sk.get_verifying_key().to_string("uncompressed")[1:]
    h = _keccak(pub_u)
    return base58.b58encode_check(b"\x41" + h[-20:]).decode()


a = accts["tron"]
try:
    check("tron_privkey_to_address", tron_address(a["private_key_hex"]) == a["address"], a["address"])
except Exception as e:
    check("tron_privkey_to_address", False, str(e))


# --- 4-7. ed25519 chains via independent SLIP-0010 from the PBKDF2 seed ---
# Solana m/44'/501'/0'/0'
a = accts["solana"]
priv = slip10(seed_ind, [44, 501, 0, 0])
pub = ed_pub(priv)
addr = base58.b58encode(pub).decode()
check("solana_slip10_address", addr == a["address"], a["address"])
check("solana_privkey_seed_match", priv.hex() == a["private_key_seed_hex"], "stored seed = SLIP10 key")
from solders.keypair import Keypair
from solders.message import Message as SolMessage
from solders.hash import Hash as SolHash

kp = Keypair.from_seed(priv)
check("solana_keypair_file", str(kp.pubkey()) == a["address"], "solders keypair reproduces address")

# SUI m/44'/784'/0'/0'/0' ; address = blake2b256(0x00 || pubkey)
a = accts["sui"]
priv = slip10(seed_ind, [44, 784, 0, 0, 0])
pub = ed_pub(priv)
addr = "0x" + hashlib.blake2b(b"\x00" + pub, digest_size=32).hexdigest()
check("sui_slip10_address", addr == a["address"], a["address"])
check("sui_privkey_match", priv.hex() == a["private_key_hex"], "stored key = SLIP10 key")

# NEAR m/44'/397'/0'/0'/0' ; implicit address = hex(pubkey)
a = accts["near"]
priv = slip10(seed_ind, [44, 397, 0, 0, 0])
pub = ed_pub(priv)
check("near_slip10_address", pub.hex() == a["address"], a["address"])
check("near_privkey_match", priv.hex() == a["private_key_hex"], "stored key = SLIP10 key")
check(
    "near_secret_format",
    a["private_key_near_format"] == "ed25519:" + base58.b58encode(priv + pub).decode(),
    "ed25519: secret format consistent",
)

# TON m/44'/607'/0'/0'/0' ; key match via SLIP10, address via bip_utils Ton V4 encoder from pubkey
a = accts["ton"]
priv = slip10(seed_ind, [44, 607, 0, 0, 0])
pub = ed_pub(priv)
check("ton_privkey_match", priv.hex() == a["private_key_hex"], "stored key = SLIP10 key")
check("ton_pubkey_match", pub.hex() == a["public_key_hex"], "stored pubkey = SLIP10 pubkey")
try:
    from bip_utils import TonV4AddrEncoder, Bip44, Bip44Coins, Bip44Changes

    tctx = (
        Bip44.FromSeed(seed_ind, Bip44Coins.TON)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    enc = TonV4AddrEncoder(tctx.PublicKey().m_pub_key).Encode(is_bounceable=False)
    check("ton_address_from_pubkey", enc == a["address"], a["address"])
    check("ton_bip44_rederive", tctx.PublicKey().ToAddress() == a["address"], "bip44 re-derive matches")
except Exception as e:
    check("ton_address_from_pubkey", False, str(e))

# ed25519 sign/verify round trip (generic, solders) for SOL/SUI/NEAR/TON stored keys
from solders.signature import Signature

for key, field in (("solana", "private_key_seed_hex"), ("sui", "private_key_hex"), ("near", "private_key_hex"), ("ton", "private_key_hex")):
    a = accts[key]
    kp = Keypair.from_seed(bytes.fromhex(a[field]))
    sig = kp.sign_message(b"venomeum burner verify")
    ok = Signature.from_bytes(bytes(sig)).verify(kp.pubkey(), b"venomeum burner verify") if hasattr(sig, "__bytes__") else False
    # solders verify API: signature.verify(pubkey, message) returns bool in recent versions
    try:
        ok = sig.verify(kp.pubkey(), b"venomeum burner verify")
    except Exception:
        pass
    check(f"{key}_ed25519_sign_verify", bool(ok), "sign/verify ok")

print()
fails = [r for r in results if not r[1]]
print(f"TOTAL: {len(results) - len(fails)}/{len(results)} PASS" + ("" if not fails else f" - FAILURES: {[f[0] for f in fails]}"))
