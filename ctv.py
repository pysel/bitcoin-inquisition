#!/usr/bin/env python3
"""
Covenants Midterm — Ternary CTV Congestion-Control Tree
========================================================

You will build a ternary (3-child) CTV tree where:

  - Every LEAF is a P2WPKH payout (LEAF_AMOUNT sats).
  - Every INTERNAL node is a CTV-protected UTXO that, when spent, is forced
    to produce exactly its three committed children as outputs.
  - The ROOT is funded by a single normal wallet tx. From that one on-chain
    payment, the entire tree can be unrolled deterministically.

This file contains the full harness (RPC plumbing, wallet setup, funding,
broadcasting, deterministic leaf recipients, balance verification). You
implement the covenant logic in the three TODOs marked below.

Prerequisites
-------------
  docker run -d --name btc -p 18443:18443 -p 18444:18444 \\
      -v btcdata:/home/bitcoin/.bitcoin bitcoin-inquisition

Run
---
  python3 ctv.py
  # → will raise NotImplementedError until you complete the TODOs

Grading
-------
Leaf recipients are generated DETERMINISTICALLY from a fixed namespace, so
every run of this script (by you, or by the grader) targets the same 27
P2WPKH scriptPubKeys. The balance-check helpers at the bottom verify your
implementation by querying the node's UTXO set via `scantxoutset` — not by
trusting the Python objects you returned.

Design note: bare CTV
---------------------
Every internal node's scriptPubKey IS the CTV script:

    <PUSH32 <template-hash>> OP_CHECKTEMPLATEVERIFY

Spends have an empty scriptSig and no witness — CTV verifies against the
scriptPubKey directly. Because bare CTV outputs/spends aren't standard
for mempool relay, the harness uses `generateblock` to mine txs directly
into a block (that's also what the reference feature_checktemplateverify.py
test does).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "test" / "functional"))

import hashlib
from decimal import Decimal
from typing import List

from test_framework.address import program_to_witness
from test_framework.authproxy import AuthServiceProxy, JSONRPCException
from test_framework.messages import (
    COIN,
    COutPoint,
    CTransaction,
    CTxIn,
    CTxOut,
    tx_from_hex,
)
from test_framework.script import CScript, OP_CHECKTEMPLATEVERIFY


# -----------------------------------------------------------------------------
# Constants (tweak during debugging)
# -----------------------------------------------------------------------------

RPC_URL       = "http://student:student@localhost:18443"
WALLET        = "student"

BRANCHING     = 3           # ternary
TREE_DEPTH    = 3           # 3**3 = 27 leaves — fast to run, big enough to be real
LEAF_AMOUNT   = 1_000       # sats per leaf
FEE_PER_LEVEL = 1_000       # fee budget for each 1-in/3-out unroll tx

NS_FULL       = "ctv-midterm-full"
NS_PARTIAL    = "ctv-midterm-partial"


# =============================================================================
# Helpers you will USE (do not modify)
# =============================================================================

def template_hash_for_outputs(outputs, nIn: int = 0, nVin: int = 1) -> bytes:
    """BIP 119 StandardTemplateHash for a tx with `nVin` inputs & the given outputs."""
    c = CTransaction()
    c.version = 2
    c.vin = [CTxIn() for _ in range(nVin)]
    c.vout = outputs
    return c.get_standard_template_hash(nIn)


def ctv_script_for(children: List[CTxOut]) -> CScript:
    """Raw CTV scriptPubKey committing to `children` as the spend-tx outputs.

    Layout: <0x20> <32-byte template hash> <OP_CHECKTEMPLATEVERIFY=0xb3>
    """
    return CScript(
        bytes([0x20])
        + template_hash_for_outputs(children)
        + bytes([OP_CHECKTEMPLATEVERIFY])
    )


def raw_script_at(tree, level: int, idx: int):
    """Recompute the CTV script for the internal node tree[level][idx].

    Returns None for leaves (they are plain P2WPKH, not CTV).
    """
    if level == len(tree) - 1:
        return None
    children = tree[level + 1][BRANCHING * idx : BRANCHING * (idx + 1)]
    return ctv_script_for(children)


def rpc_for(wallet=None) -> AuthServiceProxy:
    url = RPC_URL + (f"/wallet/{wallet}" if wallet else "")
    return AuthServiceProxy(url)


# =============================================================================
# Deterministic leaf recipients (do not modify — grader relies on these)
# =============================================================================

def leaf_program(namespace: str, i: int) -> bytes:
    """Deterministic 20-byte P2WPKH program for leaf #i under `namespace`."""
    return hashlib.sha256(f"{namespace}:{i}".encode()).digest()[:20]


def leaf_scriptpubkey(program: bytes) -> bytes:
    """P2WPKH scriptPubKey: 0x00 0x14 <20-byte program>."""
    assert len(program) == 20
    return bytes([0x00, 0x14]) + program


def leaf_programs(namespace: str, count: int) -> List[bytes]:
    return [leaf_program(namespace, i) for i in range(count)]


# =============================================================================
# TODO #1 — Build the ternary CTV tree
# =============================================================================

def ternary_secure_tree(depth: int, namespace: str = NS_FULL) -> List[List[CTxOut]]:
    """
    Build a ternary CTV congestion-control tree.

    Returns
    -------
    tree : list of lists of CTxOut
        tree[0]            — 1 element, the root (CTV-locked)
        tree[depth]        — 3**depth leaves (plain P2WPKH)
        tree[k] for 0<k<depth — 3**k internal CTV-locked nodes

    Requirements
    ------------
    * LEAVES: leaf #i must pay to the address derived from
      `leaf_program(namespace, i)` — i.e. scriptPubKey = leaf_scriptpubkey(
      leaf_program(namespace, i)), and nValue = LEAF_AMOUNT. The grader
      verifies balances at these exact addresses, so order matters.

    * INTERNAL NODE at tree[k][i]:
        Its three children are tree[k+1][3*i], [3*i+1], [3*i+2].
        - nValue      = sum(child.nValue) + FEE_PER_LEVEL
        - scriptPubKey = ctv_script_for(those three children)   # bare CTV

    Implementation hint
    -------------------
    Build LEAVES first, then walk bottom-up one level at a time. Each parent
    depends on its children's *full* CTxOut (amount + scriptPubKey), so you
    must finalize the level below before you can finalize the level above.
    """
    # TODO: implement ternary_secure_tree
    raise NotImplementedError("TODO #1 — build the ternary tree")


# =============================================================================
# TODO #2 — Fully unroll the tree
# =============================================================================

def unroll_tree(tree, root_outpoint: COutPoint) -> List[CTransaction]:
    """
    Produce the transactions that completely unroll the tree.

    Each returned tx represents one "split" step: it spends a CTV-locked
    internal node and produces its three children as outputs.

    Per-tx shape
    ------------
        version = 2
        vin     = [CTxIn(parent_outpoint)]         # empty scriptSig, no witness
        vout    = [child_0, child_1, child_2]      # 3 CTxOuts verbatim from the tree

    Bare CTV means the parent's scriptPubKey IS the CTV script, and CTV
    verifies against it automatically. You don't populate any witness data.

    Ordering
    --------
    Each parent tx MUST appear BEFORE any of its children's txs, because the
    children's inputs reference outputs that don't exist until the parent's
    tx is submitted. BFS from the root is the simplest order.

    Total tx count
    --------------
    You should produce exactly (BRANCHING**depth - 1) / (BRANCHING - 1)
    transactions — one per internal node (including the root).

    Hint
    ----
    For each internal node at tree[k][i]:
      - Its children are tree[k+1][3*i .. 3*i+3].
      - Its outpoint is the (txid, vout) of whichever tx produced it. You
        know the root's outpoint; for deeper nodes, compute txid via
        CTransaction.rehash() (and `int(tx.hash, 16)`) and track the vout
        index as you go.
    """
    # TODO: implement unroll_tree
    raise NotImplementedError("TODO #2 — unroll the whole tree")


# =============================================================================
# Bonus TODO — partial unroll to a single leaf
# =============================================================================

def unroll_path(tree, leaf_index: int, root_outpoint: COutPoint) -> List[CTransaction]:
    """
    Return the MINIMAL sequence of txs that delivers leaf #leaf_index.

    You must produce exactly `depth` transactions (one per level). All other
    subtrees remain CTV-locked on-chain and can be unrolled later.

    Note: because CTV commits to the full output set, the bottom split still
    produces all three bottom-level siblings. So "minimal" means depth txs,
    not one funded leaf — the grader accounts for this.

    Hint: at level k (spending the parent), the child index on the path to
    `leaf_index` is (leaf_index // BRANCHING**(depth - k - 1)) % BRANCHING.
    """
    # TODO (bonus): implement unroll_path
    raise NotImplementedError("Bonus TODO — partial unroll")


# =============================================================================
# Harness (provided). You shouldn't need to touch anything below.
# =============================================================================

def banner(msg: str):
    print(f"\n{'=' * 72}\n {msg}\n{'=' * 72}")


def ensure_wallet_and_funds(min_blocks: int = 101):
    node = rpc_for()
    if WALLET not in node.listwallets():
        try:
            node.loadwallet(WALLET)
        except JSONRPCException:
            node.createwallet(WALLET)
    w = rpc_for(WALLET)
    height = node.getblockcount()
    if height < min_blocks:
        addr = w.getnewaddress()
        print(f"Chain at height {height}, mining {min_blocks - height} blocks")
        w.generatetoaddress(min_blocks - height, addr)
    print(f"Chain height: {node.getblockcount()}, wallet balance: {w.getbalance()} BTC")
    return w


def verify_tree_shape(tree, depth: int, namespace: str):
    """Static sanity check on the student's tree before we try to broadcast anything."""
    assert len(tree) == depth + 1, f"expected {depth+1} levels, got {len(tree)}"
    for k in range(depth + 1):
        expected = BRANCHING ** k
        assert len(tree[k]) == expected, f"level {k}: expected {expected} nodes, got {len(tree[k])}"

    # Leaves must match the deterministic recipients exactly (so the grader can verify).
    for i, leaf in enumerate(tree[depth]):
        assert leaf.nValue == LEAF_AMOUNT, f"leaf[{i}] nValue wrong"
        expected_spk = leaf_scriptpubkey(leaf_program(namespace, i))
        assert bytes(leaf.scriptPubKey) == expected_spk, \
            f"leaf[{i}] scriptPubKey must target leaf_program({namespace!r}, {i})"

    # Internal-node shape
    for k in range(depth):
        for idx, parent in enumerate(tree[k]):
            children = tree[k + 1][BRANCHING * idx : BRANCHING * (idx + 1)]
            expected_amt = sum(c.nValue for c in children) + FEE_PER_LEVEL
            assert parent.nValue == expected_amt, \
                f"tree[{k}][{idx}] nValue = {parent.nValue}, expected {expected_amt}"
            expected_spk = ctv_script_for(children)
            assert bytes(parent.scriptPubKey) == bytes(expected_spk), \
                f"tree[{k}][{idx}] scriptPubKey doesn't match CTV(children)"
    print(f"✓ tree shape correct: {len(tree)} levels, {len(tree[depth])} leaves, "
          f"root holds {tree[0][0].nValue} sat")


def fund_root(w, tree) -> COutPoint:
    """Build a funding tx whose vout 0 is the bare-CTV root, mine it directly."""
    u = max(w.listunspent(), key=lambda x: x["amount"])
    in_sats  = int(Decimal(str(u["amount"])) * COIN)
    root_amt = tree[0][0].nValue
    fee      = 500
    change_addr = w.getnewaddress()
    change_spk  = bytes.fromhex(w.getaddressinfo(change_addr)["scriptPubKey"])

    raw = CTransaction()
    raw.version = 2
    raw.vin  = [CTxIn(COutPoint(int(u["txid"], 16), u["vout"]))]
    raw.vout = [tree[0][0], CTxOut(in_sats - root_amt - fee, CScript(change_spk))]
    signed = w.signrawtransactionwithwallet(raw.serialize().hex())
    assert signed["complete"], f"sign failed: {signed.get('errors')}"

    funding_txid = tx_from_hex(signed["hex"]).rehash()
    w.generateblock(w.getnewaddress(), [signed["hex"]])
    print(f"✓ root UTXO: {funding_txid}:0 ({root_amt} sat, bare CTV)")
    return COutPoint(int(funding_txid, 16), 0)


def broadcast_and_mine(w, txs):
    """Mine all txs directly into one block (bare CTV spends are non-standard
    for relay, so we bypass the mempool via generateblock)."""
    hex_list = [tx.serialize().hex() for tx in txs]
    result = w.generateblock(w.getnewaddress(), hex_list)
    print(f"✓ mined {len(txs)} tx(s) in block {result['hash'][:16]}…")


# -----------------------------------------------------------------------------
# Balance checks via scantxoutset
# -----------------------------------------------------------------------------

def _scan_balances(programs: List[bytes]):
    """Return {scriptPubKey_hex: total_sats} for each program in `programs`."""
    node = rpc_for()
    try:
        node.scantxoutset("abort")  # clear any stuck prior scan
    except JSONRPCException:
        pass

    descs = [{"desc": f"raw({leaf_scriptpubkey(p).hex()})"} for p in programs]
    result = node.scantxoutset("start", descs)

    totals = {leaf_scriptpubkey(p).hex(): 0 for p in programs}
    for u in result["unspents"]:
        spk_hex = u["scriptPubKey"]
        if spk_hex in totals:
            totals[spk_hex] += int(Decimal(str(u["amount"])) * COIN)
    return totals


def assert_all_leaves_funded(namespace: str, count: int, expected_sats: int):
    programs = leaf_programs(namespace, count)
    totals = _scan_balances(programs)
    missing = []
    for i, p in enumerate(programs):
        got = totals[leaf_scriptpubkey(p).hex()]
        if got < expected_sats:
            missing.append((i, got))
    if missing:
        print(f"✗ {len(missing)} leaf addresses underfunded (showing first 5): {missing[:5]}")
        raise AssertionError("leaf balance check failed")
    print(f"✓ all {count} leaf addresses hold ≥ {expected_sats} sat each "
          f"(namespace={namespace!r})")


def assert_leaf_state(namespace: str, count: int,
                      funded_leaves: set, expected_sats: int):
    """For partial-unroll check: funded_leaves must have ≥expected_sats, the rest 0."""
    programs = leaf_programs(namespace, count)
    totals = _scan_balances(programs)
    bad = []
    for i, p in enumerate(programs):
        got = totals[leaf_scriptpubkey(p).hex()]
        if i in funded_leaves:
            if got < expected_sats:
                bad.append(("under", i, got))
        else:
            if got != 0:
                bad.append(("over", i, got))
    if bad:
        print(f"✗ partial-unroll balance mismatch: {bad[:10]}")
        raise AssertionError("partial balance check failed")
    print(f"✓ partial unroll: leaves {sorted(funded_leaves)} funded, rest empty "
          f"(namespace={namespace!r})")


# =============================================================================
# Demos
# =============================================================================

def demo_full_unroll(w):
    banner(f"Demo 1 — full unroll (depth={TREE_DEPTH}, {BRANCHING ** TREE_DEPTH} leaves)")
    tree = ternary_secure_tree(TREE_DEPTH, namespace=NS_FULL)
    verify_tree_shape(tree, TREE_DEPTH, NS_FULL)

    sample_addr = program_to_witness(0, leaf_program(NS_FULL, 0))
    print(f"  sample leaf[0] address: {sample_addr}")

    root_outpoint = fund_root(w, tree)
    txs = unroll_tree(tree, root_outpoint)
    expected = (BRANCHING ** TREE_DEPTH - 1) // (BRANCHING - 1)
    assert len(txs) == expected, f"expected {expected} txs, got {len(txs)}"
    broadcast_and_mine(w, txs)

    assert_all_leaves_funded(NS_FULL, BRANCHING ** TREE_DEPTH, LEAF_AMOUNT)


def demo_partial_unroll(w, target_leaf: int = 13):
    banner(f"Demo 2 (bonus) — partial unroll to leaf #{target_leaf}")
    tree = ternary_secure_tree(TREE_DEPTH, namespace=NS_PARTIAL)
    verify_tree_shape(tree, TREE_DEPTH, NS_PARTIAL)

    root_outpoint = fund_root(w, tree)
    path_txs = unroll_path(tree, target_leaf, root_outpoint)
    assert len(path_txs) == TREE_DEPTH, \
        f"expected {TREE_DEPTH} path txs, got {len(path_txs)}"
    broadcast_and_mine(w, path_txs)

    # A partial unroll to leaf L still funds L's two bottom-level siblings,
    # because the final split commits to all three children as outputs.
    # Everything ABOVE the bottom split stays CTV-locked.
    group_start = (target_leaf // BRANCHING) * BRANCHING
    funded = {group_start + j for j in range(BRANCHING)}
    print(f"  expected funded leaves (target's bottom-split triplet): {sorted(funded)}")
    assert_leaf_state(NS_PARTIAL, BRANCHING ** TREE_DEPTH,
                      funded_leaves=funded, expected_sats=LEAF_AMOUNT)


def main():
    banner("Setup — wallet & mature coinbases")
    w = ensure_wallet_and_funds()

    demo_full_unroll(w)
    demo_partial_unroll(w, target_leaf=13)

    banner("All leaves delivered on-chain. Nice work.")


if __name__ == "__main__":
    main()
