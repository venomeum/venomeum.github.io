#!/usr/bin/env python3
"""Fix ed25519 public-key fields in the backup.

bip_utils' RawCompressed() returns 33 bytes for ed25519 keys (not the raw
32-byte public key). Recompute the true public keys from the stored private
keys with solders (independent ed25519 implementation) and patch:
- sui.public_key_hex
- near.public_key_hex, near.public_key_near_format, near.private_key_near_format
- ton.public_key_hex
Addresses and private keys are NOT touched (they already verified).
Then regenerate the .txt backup from the patched JSON.
"""
import json
import os
import stat

import base58
from solders.keypair import Keypair

OUT_DIR = os.path.expanduser("~/workspace/your_files")
json_path = os.path.join(OUT_DIR, "venomeum-burner-wallet-backup.json")
data = json.load(open(json_path))
accts = data["accounts"]


def true_pub(priv_hex):
    return bytes(Keypair.from_seed(bytes.fromhex(priv_hex)).pubkey())


# SUI
a = accts["sui"]
a["public_key_hex"] = true_pub(a["private_key_hex"]).hex()
# NEAR
a = accts["near"]
pub = true_pub(a["private_key_hex"])
priv = bytes.fromhex(a["private_key_hex"])
a["public_key_hex"] = pub.hex()
a["public_key_near_format"] = "ed25519:" + base58.b58encode(pub).decode()
a["private_key_near_format"] = "ed25519:" + base58.b58encode(priv + pub).decode()
# TON
a = accts["ton"]
a["public_key_hex"] = true_pub(a["private_key_hex"]).hex()

with open(json_path, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(json_path, stat.S_IRUSR | stat.S_IWUSR)

lines = [
    "VENOMEUM MULTICHAIN BURNER WALLET - BACKUP",
    f"Created (UTC): {data['created_utc']}",
    "Type: BIP39, 24 words, no passphrase",
    "",
    "MNEMONIC (keep secret, offline):",
    data["mnemonic"],
    "",
]
for key, a in accts.items():
    lines.append(f"[{key}] {a['chain']}")
    lines.append(f"  Path:    {a['derivation_path']} ({a['standard']})")
    lines.append(f"  Address: {a['address']}")
    for k, v in a.items():
        if k.startswith("private_key") and v:
            lines.append(f"  {k}: {v}")
    lines.append("")
lines.append(data["warning"])
txt_path = os.path.join(OUT_DIR, "venomeum-burner-wallet-backup.txt")
with open(txt_path, "w") as f:
    f.write("\n".join(lines))
os.chmod(txt_path, stat.S_IRUSR | stat.S_IWUSR)
print("PATCHED OK - pubkeys fixed, txt regenerated")
