#!/usr/bin/env python3
"""Venomeum Activity Engine — daily on-chain activity on our own TESTNETS.

Generates real, confirmed transactions every day across the user's two
wallets (multichain burner + Circle agent wallet) on Arc Testnet and
Robinhood Chain Testnet: $VMH transfers, wrap/unwrap of the native token,
tiny native transfers, and sniper-style buy->sell round trips on Venomeum
Swap. Everything runs against the user's own token, own DEX and own
wallets, with worthless testnet funds — this is activity/testing volume,
nothing more.

HARD SAFETY RULES (do not remove):
  * TESTNET ONLY, FOREVER. The engine verifies the chain id of every RPC
    it touches and refuses anything other than 5042002 (Arc Testnet) and
    46630 (Robinhood Chain Testnet). There is no mainnet code path.
  * Balance floors: a wallet/chain portion stops gracefully when its
    native balance falls to its floor — the engine never drains a wallet.
  * Only status=1 receipts are counted. Every confirmed tx is appended to
    txlog.jsonl and counted in state.json (keyed by GMT+7 date).

Usage:
  python3 engine.py --status            # today's counts vs the 1,000 target
  python3 engine.py --batch 45 --dry-run  # preview a batch plan, send nothing
  python3 engine.py --batch 45          # execute a batch of up to 45 txns
  python3 engine.py --batch 200         # bigger batch (same quota split)

The burner key is read at runtime from the local backup file and is never
printed. The agent wallet is driven only through the Circle CLI.
"""
import argparse, json, os, random, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from web3 import Web3

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.join(HERE, "txlog.jsonl")
BACKUP = os.path.expanduser("~/workspace/your_files/venomeum-burner-wallet-backup.json")

GMT7 = timezone(timedelta(hours=7))

DAILY_TARGET = 1000                       # confirmed txns per day (GMT+7)
QUOTAS = {"burner_arc": 0.55, "burner_rh": 0.30, "agent_arc": 0.15}
MAX_BATCH = 2000                          # sanity cap for a single --batch

ALLOWED_CHAINS = {5042002, 46630}         # testnets only — anything else refused

BURNER = "0x09045763Ea68FB7Ef0E0e51C26bcCf45846077f1"
AGENT = "0xea68c5f665b86d4f8fba2faad2c8b5af5aed9087"
ROUTER = "0xC83d7A0079Fc410Ddd4cE4aaD7bF2216350342Cb"
WNATIVE = "0x5Df9ecECC7c0e7b43E7afC3b3238Aa19fB3A0C87"   # WUSDC on Arc / WETH on RH
VMH_ARC = "0xeF8a48269661Fd8d5FE1453A74d27Fe375178cef"   # burner-deployment $VMH (Arc)
VMH_RH = "0xA9808afB0213295778D0CEE459c182C1524858b4"    # burner-deployment $VMH (RH)

# Native-balance floors (in wei / smallest units, 18 decimals on both chains).
FLOORS = {
    "burner_arc": int(Decimal("2") * 10**18),        # 2 USDC
    "burner_rh": int(Decimal("0.0015") * 10**18),    # 0.0015 ETH
    "agent_arc": int(Decimal("2") * 10**18),         # 2 USDC
}

CHAINS = {
    "arc": {"name": "Arc Testnet", "rpc": "https://rpc.testnet.arc.network",
            "chain_id": 5042002, "native_symbol": "USDC", "vmh": VMH_ARC},
    "robinhood": {"name": "Robinhood Chain Testnet", "rpc": "https://rpc.testnet.chain.robinhood.com",
                  "chain_id": 46630, "native_symbol": "ETH", "vmh": VMH_RH},
}

SLIPPAGE_BPS = 500  # 5% for round-trip swaps

# --------------------------------------------------------------------------
# Minimal ABIs
# --------------------------------------------------------------------------
ERC20_ABI = json.loads("""[
 {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
 {"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}
]""")
WNATIVE_ABI = json.loads("""[
 {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"},
 {"inputs":[{"internalType":"uint256","name":"wad","type":"uint256"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}
]""")
ROUTER_ABI = json.loads("""[
 {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"","type":"uint256[]"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},
 {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"}
]""")

# --------------------------------------------------------------------------
# State + log
# --------------------------------------------------------------------------

def today_gmt7():
    return datetime.now(GMT7).strftime("%Y-%m-%d")


def now_gmt7_iso():
    return datetime.now(GMT7).isoformat(timespec="seconds")


def load_state():
    today = today_gmt7()
    if os.path.exists(STATE_FILE):
        try:
            st = json.load(open(STATE_FILE))
            if st.get("date") == today:
                st.setdefault("counts", {})
                st.setdefault("gas_wei", {})
                return st
        except Exception:
            pass
    return {"date": today, "counts": {}, "gas_wei": {}}


def save_state(st):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE_FILE)


def record_tx(st, wallet, chain, action, tx_hash, gas_wei):
    """Count one confirmed tx: bump state + append to the JSONL log."""
    key = f"{wallet}|{chain}|{action}"
    st["counts"][key] = st["counts"].get(key, 0) + 1
    gkey = f"{wallet}|{chain}"
    st["gas_wei"][gkey] = str(int(st["gas_wei"].get(gkey, "0")) + int(gas_wei))
    save_state(st)
    entry = {"ts": now_gmt7_iso(), "wallet": wallet, "chain": chain,
             "action": action, "tx": tx_hash, "gas_wei": str(gas_wei)}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def fmt(raw, decimals=18):
    d = Decimal(int(raw)) / (Decimal(10) ** decimals)
    if d == d.to_integral_value():
        return f"{d:,.0f}"
    if Decimal(0) < abs(d) < Decimal("0.001"):
        return f"{d:,.10f}".rstrip("0").rstrip(".")
    return f"{d:,.6f}".rstrip("0").rstrip(".")


def dec_range(lo, hi, places):
    """Random Decimal in [lo, hi] with the given decimal places."""
    scale = 10 ** places
    return Decimal(random.randint(int(Decimal(lo) * scale), int(Decimal(hi) * scale))) / Decimal(scale)


def allocate(n):
    """Split n across the quota portions (largest remainder, sums to n)."""
    raw = {k: n * q for k, q in QUOTAS.items()}
    base = {k: int(v) for k, v in raw.items()}
    left = n - sum(base.values())
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[:left]:
        base[k] += 1
    return base


# --------------------------------------------------------------------------
# Burner wallet driver (direct web3, legacy gas, pending nonce)
# --------------------------------------------------------------------------
class BurnerChain:
    def __init__(self, chain_key):
        ch = CHAINS[chain_key]
        self.key = chain_key
        self.cfg = ch
        self.w3 = Web3(Web3.HTTPProvider(ch["rpc"], request_kwargs={"timeout": 60}))
        if not self.w3.is_connected():
            raise RuntimeError(f"cannot reach {ch['name']} RPC")
        cid = self.w3.eth.chain_id
        if cid not in ALLOWED_CHAINS or cid != ch["chain_id"]:
            raise RuntimeError(f"REFUSING chain id {cid} — testnet only")
        data = json.load(open(BACKUP))
        key = data["accounts"]["evm_all_chains"]["private_key_hex"]
        self.acct = self.w3.eth.account.from_key(key)
        self.me = self.acct.address
        if self.me.lower() != BURNER.lower():
            raise RuntimeError("backup key does not match the expected burner address")
        self.vmh = self.w3.eth.contract(address=Web3.to_checksum_address(ch["vmh"]), abi=ERC20_ABI)
        self.wn = self.w3.eth.contract(address=Web3.to_checksum_address(WNATIVE), abi=WNATIVE_ABI)
        self.router = self.w3.eth.contract(address=Web3.to_checksum_address(ROUTER), abi=ROUTER_ABI)
        self.wn_addr = Web3.to_checksum_address(WNATIVE)
        self.vmh_addr = Web3.to_checksum_address(ch["vmh"])

    # -- balances -----------------------------------------------------------
    def native_balance(self):
        return self.w3.eth.get_balance(self.me)

    def vmh_balance(self):
        return self.vmh.functions.balanceOf(self.me).call()

    def wn_balance(self):
        return self.wn.functions.balanceOf(self.me).call()

    # -- generic send -------------------------------------------------------
    def send(self, tx):
        """Legacy-gas send; waits for the receipt; returns (hash, receipt, gas_cost_wei).
        Raises unless the receipt status is 1."""
        tx.pop("maxFeePerGas", None)
        tx.pop("maxPriorityFeePerGas", None)
        tx["nonce"] = self.w3.eth.get_transaction_count(self.me, "pending")
        tx["gasPrice"] = int(self.w3.eth.gas_price * 1.3) or 1
        tx["chainId"] = self.w3.eth.chain_id
        if "gas" not in tx:
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.25)
        signed = self.acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        r = self.w3.eth.wait_for_transaction_receipt(h, timeout=240)
        if r.status != 1:
            raise RuntimeError(f"tx reverted on-chain: {h.to_0x_hex()}")
        return h.to_0x_hex(), r, r.gasUsed * r.effectiveGasPrice

    # -- single-tx actions --------------------------------------------------
    def vmh_transfer(self, to, amount_wei):
        tx = self.vmh.functions.transfer(Web3.to_checksum_address(to), int(amount_wei)).build_transaction({"from": self.me})
        return self.send(tx)

    def native_transfer(self, to, amount_wei):
        tx = {"from": self.me, "to": Web3.to_checksum_address(to), "value": int(amount_wei)}
        return self.send(tx)

    def wrap(self, amount_wei):
        tx = self.wn.functions.deposit().build_transaction({"from": self.me, "value": int(amount_wei)})
        return self.send(tx)

    def unwrap(self, amount_wei):
        tx = self.wn.functions.withdraw(int(amount_wei)).build_transaction({"from": self.me})
        return self.send(tx)

    # -- sniper-style round trip (buy then immediately sell) ----------------
    def round_trip(self, buy_amount_wei, on_tx):
        """Buy VMH with native, then sell everything received.
        on_tx(action, hash, gas_wei) is called for each confirmed leg so the
        caller can count/log it. Returns the number of confirmed txns."""
        w3, me = self.w3, self.me
        slip = Decimal(10000 - SLIPPAGE_BPS) / Decimal(10000)
        path_buy = [self.wn_addr, self.vmh_addr]
        path_sell = [self.vmh_addr, self.wn_addr]
        n = 0

        quote_buy = self.router.functions.getAmountsOut(int(buy_amount_wei), path_buy).call()[-1]
        min_out = int(Decimal(quote_buy) * slip)
        bal_before = self.vmh_balance()
        buy_tx = self.router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
            min_out, path_buy, me, int(time.time()) + 300)
        h, _r, gas = self.send(buy_tx.build_transaction({"from": me, "value": int(buy_amount_wei)}))
        on_tx("swap_buy", h, gas)
        n += 1

        received = self.vmh_balance() - bal_before
        if received <= 0:
            raise RuntimeError(f"buy {h} mined but no VMH arrived")

        # One large approval up front keeps later round trips at exactly 2 txns.
        if self.vmh.functions.allowance(me, Web3.to_checksum_address(ROUTER)).call() < received:
            app = self.vmh.functions.approve(Web3.to_checksum_address(ROUTER), 10**27).build_transaction({"from": me})
            h2, _r2, gas2 = self.send(app)
            on_tx("approve", h2, gas2)
            n += 1

        keep = Decimal(received) / Decimal(quote_buy) if quote_buy else Decimal(1)
        eff_in = max(int(Decimal(received) * keep), 1)
        # First attempt at the normal slippage. The token's start-of-sell
        # automation (swapAndLiquify/buyback against the same pair) can move
        # a thin pool's price mid-sell and make the router's min-out check
        # revert — if that happens, retry once with a wide tolerance: the
        # amounts are testnet dust and completing the round trip matters more.
        for attempt, slip_try in enumerate((slip, Decimal("0.65"))):
            quote_sell = self.router.functions.getAmountsOut(eff_in, path_sell).call()[-1]
            min_native = int(Decimal(quote_sell) * slip_try)
            sell_tx = self.router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                received, min_native, path_sell, me, int(time.time()) + 300)
            try:
                h3, _r3, gas3 = self.send(sell_tx.build_transaction({"from": me}))
                break
            except Exception:
                if attempt == 1:
                    raise
                print("  ! sell leg reverted — retrying with wide slippage tolerance")
        on_tx("swap_sell", h3, gas3)
        n += 1
        return n


# --------------------------------------------------------------------------
# Circle agent wallet driver (CLI subprocess; Arc Testnet only)
# --------------------------------------------------------------------------
class AgentBlocked(Exception):
    """Session expired / terms required / auth problem — stop, never log in."""


class AgentArc:
    def __init__(self, arc_burner_chain):
        # Reuse the Arc web3 connection to verify receipts + read balances.
        self.w3 = arc_burner_chain.w3
        if self.w3.eth.chain_id != 5042002:
            raise RuntimeError("agent driver requires the Arc Testnet connection")
        self.consecutive_failures = 0

    def native_balance(self):
        return self.w3.eth.get_balance(Web3.to_checksum_address(AGENT))

    def _cli(self, argv):
        env = dict(os.environ)
        env["NODE_USE_ENV_PROXY"] = "1"
        p = subprocess.run(["circle"] + argv, capture_output=True, text=True,
                           timeout=240, env=env)
        return p

    def transfer(self, to, amount_decimal, token=None):
        """One agent transfer via the CLI. Returns (tx_hash, network_fee_wei).
        Raises AgentBlocked on auth/terms problems, RuntimeError otherwise."""
        argv = ["wallet", "transfer", Web3.to_checksum_address(to),
                "--amount", str(amount_decimal),
                "--address", AGENT, "--chain", "ARC-TESTNET", "--output", "json"]
        if token:
            argv += ["--token", Web3.to_checksum_address(token)]
        try:
            p = self._cli(argv)
        except subprocess.TimeoutExpired:
            self.consecutive_failures += 1
            raise RuntimeError("circle CLI timed out")
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        low = out.lower()
        if any(s in low for s in ("session expired", "not authenticated", "please log in",
                                  "login required", "terms acceptance", "accept the terms",
                                  "terms of service must be accepted")):
            raise AgentBlocked("Circle CLI reports an auth/terms problem — agent portion skipped")
        tx_hash, fee_wei = None, 0
        try:
            start = p.stdout.index("{")
            data = json.loads(p.stdout[start:]).get("data", {})
            if data.get("state") == "COMPLETE" and data.get("txHash"):
                tx_hash = data["txHash"]
                fee_wei = int(Decimal(str(data.get("networkFee", "0"))) * 10**18)
        except Exception:
            pass
        if not tx_hash:
            self.consecutive_failures += 1
            raise RuntimeError(f"agent transfer failed (rc={p.returncode}): {out.strip()[:300]}")
        # Verify the receipt on-chain before counting it.
        r = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if r.status != 1:
            self.consecutive_failures += 1
            raise RuntimeError(f"agent tx {tx_hash} reverted on-chain")
        self.consecutive_failures = 0
        return tx_hash, fee_wei


# --------------------------------------------------------------------------
# Batch runners
# --------------------------------------------------------------------------
def pace(lo, hi):
    time.sleep(random.uniform(lo, hi))


def run_burner_portion(st, portion, chain_key, quota, drivers):
    """Run up to `quota` confirmed txns for one burner portion.
    Returns (confirmed, stop_reason_or_None)."""
    bc = drivers[chain_key]
    floor = FLOORS[portion]
    nsym = bc.cfg["native_symbol"]
    done, consec_fail = 0, 0
    print(f"\n--- {portion}: target {quota} txns on {bc.cfg['name']} "
          f"(native {fmt(bc.native_balance())} {nsym}, floor {fmt(floor)} {nsym}) ---")

    def counted(action, h, gas):
        record_tx(st, "burner", chain_key, action, h, gas)
        print(f"  [{done + 1}] {action}: {h} (gas {fmt(gas)} {nsym})")

    while done < quota:
        if bc.native_balance() <= floor:
            return done, f"native balance at/below floor ({fmt(bc.native_balance())} {nsym})"
        # Weighted action menu.
        if chain_key == "arc":
            menu = [("vmh_transfer", 30), ("wrap", 20), ("native_transfer", 20),
                    ("unwrap", 15), ("round_trip", 15)]
        else:
            menu = [("vmh_self_transfer", 35), ("wrap", 20), ("eth_self_transfer", 20),
                    ("unwrap", 15), ("round_trip", 10)]
        action = random.choices([a for a, _ in menu], weights=[w for _, w in menu])[0]
        try:
            if action == "vmh_transfer":
                amt = int(Decimal(random.randint(10, 500)) * 10**18)
                h, _r, gas = bc.vmh_transfer(AGENT, amt)
                counted("vmh_transfer", h, gas); done += 1
            elif action == "vmh_self_transfer":
                amt = int(Decimal(random.randint(10, 500)) * 10**18)
                h, _r, gas = bc.vmh_transfer(bc.me, amt)
                counted("vmh_self_transfer", h, gas); done += 1
            elif action == "native_transfer":
                amt = int(dec_range("0.001", "0.01", 3) * 10**18)
                h, _r, gas = bc.native_transfer(AGENT, amt)
                counted("native_transfer", h, gas); done += 1
            elif action == "eth_self_transfer":
                amt = int(Decimal("0.00001") * 10**18)
                h, _r, gas = bc.native_transfer(bc.me, amt)
                counted("eth_self_transfer", h, gas); done += 1
            elif action == "wrap":
                if chain_key == "arc":
                    amt = int(dec_range("0.01", "0.05", 3) * 10**18)
                else:
                    amt = int(dec_range("0.00005", "0.0002", 5) * 10**18)
                if bc.native_balance() - amt <= floor:
                    continue  # would breach the floor — pick something else
                h, _r, gas = bc.wrap(amt)
                counted("wrap", h, gas); done += 1
            elif action == "unwrap":
                wbal = bc.wn_balance()
                if wbal <= 0:
                    continue  # nothing wrapped yet — pick something else
                # Unwrap 40–100% of the wrapped balance so native doesn't
                # slowly accumulate inside the wrapper over many days.
                amt = int(Decimal(wbal) * Decimal(random.randint(40, 100)) / Decimal(100))
                h, _r, gas = bc.unwrap(amt)
                counted("unwrap", h, gas); done += 1
            elif action == "round_trip":
                buy = int(Decimal("0.5") * 10**18) if chain_key == "arc" else int(Decimal("0.0001") * 10**18)
                if bc.native_balance() - buy <= floor:
                    continue
                before = done

                def on_tx(a, h, gas, _before=before):
                    nonlocal done
                    counted(a, h, gas)
                    done += 1

                bc.round_trip(buy, on_tx)
            consec_fail = 0
        except Exception as e:
            consec_fail += 1
            print(f"  ! {action} failed ({consec_fail} in a row): {str(e)[:200]}")
            if consec_fail >= 5:
                return done, f"stopped after 5 consecutive failures (last: {str(e)[:120]})"
            time.sleep(3)
            continue
        if done < quota:
            pace(3, 8)
    return done, None


def run_agent_portion(st, quota, agent):
    """Run up to `quota` confirmed agent txns on Arc. Returns (confirmed, stop_reason)."""
    floor = FLOORS["agent_arc"]
    done = 0
    print(f"\n--- agent_arc: target {quota} txns on Arc Testnet "
          f"(native {fmt(agent.native_balance())} USDC, floor {fmt(floor)} USDC) ---")
    while done < quota:
        if agent.native_balance() <= floor:
            return done, f"agent native balance at/below floor ({fmt(agent.native_balance())} USDC)"
        action = random.choices(["vmh_transfer", "native_transfer"], weights=[60, 40])[0]
        try:
            if action == "vmh_transfer":
                amt = Decimal(random.randint(100, 1000))
                h, fee = agent.transfer(BURNER, amt, token=VMH_ARC)
            else:
                h, fee = agent.transfer(BURNER, Decimal("0.01"))
            record_tx(st, "agent", "arc", action, h, fee)
            done += 1
            print(f"  [{done}] agent {action}: {h} (network fee {fmt(fee)} USDC)")
        except AgentBlocked as e:
            return done, f"AGENT BLOCKED: {e}"
        except Exception as e:
            print(f"  ! agent {action} failed ({agent.consecutive_failures} in a row): {str(e)[:200]}")
            if agent.consecutive_failures >= 3:
                return done, "stopped after 3 consecutive agent failures"
            time.sleep(3)
            continue
        if done < quota:
            pace(8, 15)
    return done, None


# --------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------
def portion_totals(st):
    totals = {}
    for key, n in st["counts"].items():
        wallet, chain, _action = key.split("|")
        pk = f"{wallet}_{chain}"
        totals[pk] = totals.get(pk, 0) + n
    return totals


def print_status(st):
    totals = portion_totals(st)
    total = sum(totals.values())
    print(f"=== Venomeum Activity Engine — {st['date']} (GMT+7) ===")
    print(f"daily target : {DAILY_TARGET} confirmed txns")
    print(f"confirmed    : {total}  ({total / DAILY_TARGET * 100:.1f}% of target)")
    for pk, label in (("burner_arc", "burner / Arc"), ("burner_robinhood", "burner / Robinhood"),
                      ("agent_arc", "agent / Arc")):
        gkey = {"burner_arc": "burner|arc", "burner_robinhood": "burner|robinhood",
                "agent_arc": "agent|arc"}[pk]
        unit = "ETH" if pk == "burner_robinhood" else "USDC"
        print(f"  {label:<20} {totals.get(pk, 0):>5} txns   gas {fmt(st['gas_wei'].get(gkey, '0'))} {unit}")
    print("per-action:")
    for key in sorted(st["counts"]):
        print(f"  {key:<42} {st['counts'][key]}")
    return total


# Typical gas per action type (for dry-run estimates only).
TYPICAL_GAS = {"vmh_transfer": 52000, "vmh_self_transfer": 52000, "native_transfer": 45000,
               "eth_self_transfer": 21000, "wrap": 46000, "unwrap": 42000,
               "swap_buy": 190000, "swap_sell": 210000, "approve": 46000}
MENUS = {
    "burner_arc": [("vmh_transfer", 30), ("wrap", 20), ("native_transfer", 20),
                   ("unwrap", 15), ("round_trip", 15)],
    "burner_rh": [("vmh_self_transfer", 35), ("wrap", 20), ("eth_self_transfer", 20),
                  ("unwrap", 15), ("round_trip", 10)],
    "agent_arc": [("vmh_transfer", 60), ("native_transfer", 40)],
}


def dry_run_plan(n, drivers):
    alloc = allocate(n)
    print(f"=== DRY RUN — batch of {n} (no transactions will be sent) ===")
    print(f"allocation: {alloc}")
    for portion, quota in alloc.items():
        menu = MENUS[portion]
        sim = {}
        cnt = 0
        while cnt < quota:
            a = random.choices([x for x, _ in menu], weights=[w for _, w in menu])[0]
            if a == "round_trip":
                sim["swap_buy"] = sim.get("swap_buy", 0) + 1
                sim["swap_sell"] = sim.get("swap_sell", 0) + 1
                cnt += 2
            else:
                sim[a] = sim.get(a, 0) + 1
                cnt += 1
        gas_est = sum(TYPICAL_GAS.get(a, 50000) * c for a, c in sim.items())
        if portion == "agent_arc":
            ag = drivers.get("agent")
            bal = fmt(ag.native_balance()) if ag else "?"
            print(f"{portion:<12} {quota:>4} txns  balance {bal} USDC (floor {fmt(FLOORS[portion])})  "
                  f"mix {sim}  est. network fees ~{quota * 0.0045:.3f} USDC")
        else:
            bc = drivers["arc" if portion == "burner_arc" else "robinhood"]
            gp = bc.w3.eth.gas_price
            est = Decimal(gas_est) * Decimal(int(gp * 1.3)) / Decimal(10**18)
            print(f"{portion:<12} {quota:>4} txns  balance {fmt(bc.native_balance())} {bc.cfg['native_symbol']} "
                  f"(floor {fmt(FLOORS[portion])})  mix {sim}  est. gas ~{est:.6f} {bc.cfg['native_symbol']}")
    print("dry run complete — nothing sent, state untouched.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Venomeum daily activity engine (TESTNET ONLY).")
    ap.add_argument("--batch", type=int, default=None, help="execute a batch of up to N txns now")
    ap.add_argument("--dry-run", action="store_true", help="with --batch: plan only, send nothing")
    ap.add_argument("--status", action="store_true", help="print today's counts and exit")
    args = ap.parse_args()

    st = load_state()
    if args.status:
        print_status(st)
        return
    if args.batch is None:
        ap.error("give --batch N (optionally with --dry-run) or --status")
    if args.batch <= 0:
        sys.exit("error: --batch must be positive")
    if args.batch > MAX_BATCH:
        sys.exit(f"error: --batch capped at {MAX_BATCH}")

    # Connect (read-only until sends start). Chain ids are verified inside.
    drivers = {"arc": BurnerChain("arc"), "robinhood": BurnerChain("robinhood")}
    agent = None
    alloc = allocate(args.batch)

    if args.dry_run:
        try:
            agent = AgentArc(drivers["arc"])
        except Exception as e:
            print(f"agent driver unavailable: {e}")
        dry_run_plan(args.batch, {**drivers, "agent": agent} if agent else drivers)
        return

    gas_before = dict(st["gas_wei"])
    results = {}

    done, reason = run_burner_portion(st, "burner_arc", "arc", alloc["burner_arc"], drivers)
    results["burner_arc"] = (done, reason)
    done, reason = run_burner_portion(st, "burner_rh", "robinhood", alloc["burner_rh"], drivers)
    results["burner_rh"] = (done, reason)

    if alloc["agent_arc"] > 0:
        import shutil
        if not shutil.which("circle"):
            results["agent_arc"] = (0, "circle CLI not found — agent portion skipped")
        else:
            try:
                agent = AgentArc(drivers["arc"])
                done, reason = run_agent_portion(st, alloc["agent_arc"], agent)
                results["agent_arc"] = (done, reason)
            except AgentBlocked as e:
                results["agent_arc"] = (0, f"AGENT BLOCKED: {e}")
            except Exception as e:
                results["agent_arc"] = (0, f"agent driver error: {str(e)[:160]}")

    print("\n=== batch summary ===")
    total_done = 0
    for portion, (done, reason) in results.items():
        total_done += done
        line = f"{portion:<12} {done} confirmed"
        if reason:
            line += f"  (stopped: {reason})"
        print(line)
    for gkey in ("burner|arc", "burner|robinhood", "agent|arc"):
        spent = int(st["gas_wei"].get(gkey, "0")) - int(gas_before.get(gkey, "0"))
        if spent:
            unit = "ETH" if gkey.endswith("robinhood") else "USDC"
            print(f"gas spent {gkey:<18} {fmt(spent)} {unit}")
    print(f"batch total: {total_done} confirmed txns")
    print_status(st)


if __name__ == "__main__":
    main()
