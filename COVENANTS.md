# Covenants Midterm Assignment Handbook

This repository is a fork of the actual Bitcoin Node that adds support for certain opcodes that haven't yet been adopted to the Bitcoin protocol by the community (OP_CTV is one of them). We will use this codebase to implement the ternary tree assignment.

This handbook specifies the instructions for running the local bitcoin-inquisition node (Section 1) and includes the explanation of types and objects that you will use in your assignment (Section 2). 

This is a very demanding assignment that will teach you a lot not only about Bitcoin, but software engineering in general. Make sure to plan accordingly and start early. 

If you have any questions about this assignment, email your TA Rithwik ([rkerur@ucsb.edu](mailto:rkerur@ucsb.edu)) or me ([akhtariev@ucsb.edu](mailto:akhtariev@ucsb.edu)).

---

## 1. Run the node

Pull the prebuilt image and start a regtest node:

```bash
docker pull pycel/bitcoin-inquisition:latest
docker tag pycel/bitcoin-inquisition:latest bitcoin-inquisition:latest

docker run -d --name btc \
  -p 18443:18443 -p 18444:18444 \
  -v btcdata:/home/bitcoin/.bitcoin \
  bitcoin-inquisition

docker logs -f btc
```

The `tag` step lets you refer to the image by its short name
`bitcoin-inquisition` everywhere in this doc and in `ctv.py`.

If you'd rather build the image yourself (~10–20 min, ≥4 GB RAM):

```bash
docker build --build-arg JOBS=8 -t bitcoin-inquisition .
```

then `docker run …` exactly as above.

Quick sanity check:

```bash
alias bcli='docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student -named'
bcli getblockchaininfo
```

Mine 101 blocks so you have a spendable coinbase:

```bash
bcli createwallet student
ADDR=$(bcli getnewaddress)
bcli generatetoaddress 101 "$ADDR"
```

---

## 2. The imports in `ctv.py`, in plain terms

The student file uses this import block:

```python
from test_framework.address   import program_to_witness
from test_framework.authproxy import AuthServiceProxy, JSONRPCException
from test_framework.messages  import (COIN, COutPoint, CTransaction,
                                       CTxIn, CTxOut, tx_from_hex)
from test_framework.script    import CScript, OP_CHECKTEMPLATEVERIFY
```

Everything below is "what the name means and what you'd actually type."
A Bitcoin transaction, for our purposes, is just **a list of inputs and a
list of outputs**. Each output has an *amount* and a *script* (a tiny
program that says "who can spend me"). These classes let you build that
in Python.

### Transaction parts (`test_framework.messages`)

#### `CTransaction`

The transaction itself. You set three things on it:

```python
tx = CTransaction()
tx.version = 2
tx.vin  = [...]   # inputs
tx.vout = [...]   # outputs
hex_to_broadcast = tx.serialize().hex()
```

#### `CTxOut(amount_sats, script)`

One output = "this many sats, locked with this script."

```python
out = CTxOut(1000, some_script)   # 1000 sats, locked by `some_script`
```

#### `CTxIn(outpoint)`

One input = "I'm spending an earlier output." You pass the earlier
output's location.

```python
vin = CTxIn(outpoint)
```

#### `COutPoint(txid_int, vout_index)`

The location of an earlier output: the txid of the tx that created it,
plus which output (0, 1, 2, …) within that tx.

```python
op = COutPoint(int(txid_hex, 16), 0)   # output #0 of that txid
```

#### `COIN`

The number `100_000_000`. Amounts inside scripts are in **sats**; the
RPC takes **BTC**. Use `COIN` to convert:

```python
from decimal import Decimal
btc_value = Decimal(40_000) / COIN   # 40000 sats → 0.0004 BTC
```

#### `tx_from_hex(hex_string)`

The inverse of `tx.serialize().hex()`: parses a hex-encoded transaction
back into a `CTransaction`. Useful when an RPC (e.g.
`signrawtransactionwithwallet`) hands you a hex string and you want the
txid:

```python
signed = w.signrawtransactionwithwallet(raw.serialize().hex())
txid   = tx_from_hex(signed["hex"]).rehash()
```

### Scripts (`test_framework.script`)

#### `CScript([...])`

Builds a script from a list of pieces. Behaves like `bytes` — you can
pass it anywhere bytes are expected. In this assignment, you only really
need two patterns:

```python
# From a list
s1 = CScript([template_hash, OP_CHECKTEMPLATEVERIFY])

# From raw bytes when you want exact control:
s2 = CScript(bytes([0x20]) + template_hash + bytes([OP_CHECKTEMPLATEVERIFY]))
```

#### `OP_CHECKTEMPLATEVERIFY`

The integer `0xb3` — the CTV opcode. Putting a 32-byte hash and this
opcode in a script creates a CTV-locked output.

### Addresses (`test_framework.address`)

- `program_to_witness(0, hash160)` — turns a 20-byte program into a
`bcrt1q…` address string. Use this if you want to display a leaf
address for inspection.

### Talking to the node (`test_framework.authproxy`)

#### `AuthServiceProxy(url)`

The RPC client. Every attribute access is an RPC call.

```python
rpc = AuthServiceProxy("http://student:student@localhost:18443")
print(rpc.getblockcount())
# Bare-CTV txs aren't standard for mempool relay — mine them directly:
rpc.generateblock(rpc.getnewaddress(), [tx.serialize().hex()])
```

#### `JSONRPCException`

The exception the client raises when the node rejects a call (bad tx,
wallet not loaded, etc.). Catch it if you want to read `e.error["message"]`.

---

## 3. The functions already filled in `ctv.py`

Beyond the imports, `ctv.py` ships with helpers and a harness that you
should read but **not modify**. Some you'll call directly from your three
TODOs; others run automatically and verify your work. They're grouped
below by what they do.

### Building CTV scripts

#### `template_hash_for_outputs(outputs, nIn=0, nVin=1)`

Computes the BIP 119 *StandardTemplateHash* for a transaction with `nVin`
inputs and the given `outputs`. This 32-byte hash is the commitment that
goes inside a CTV scriptPubKey.

```python
h = template_hash_for_outputs(children)   # 32 bytes
```

#### `ctv_script_for(children)`

Builds the **bare CTV scriptPubKey** that locks an output to spend into
exactly `children`. Layout: `<PUSH32 template_hash> OP_CHECKTEMPLATEVERIFY`.

```python
parent_spk = ctv_script_for([child0, child1, child2])
parent     = CTxOut(amount, parent_spk)
```

#### `raw_script_at(tree, level, idx)`

Recomputes the CTV scriptPubKey for the internal node at
`tree[level][idx]`. Returns `None` for leaves (they're plain recipient
outputs, not CTV). Useful for debugging.

### Deterministic leaf recipients

These produce **the same outputs every run**, so the grader knows exactly
which scriptPubKeys to look for. Do not change the namespaces.

#### `leaf_program(namespace, i)`

Returns a 20-byte recipient program for leaf index `i` under `namespace`,
computed as `sha256(f"{namespace}:{i}")[:20]`.

```python
program = leaf_program(NS_FULL, 7)   # always the same 20 bytes
```

#### `leaf_scriptpubkey(program)`

Wraps a 20-byte program into the 22-byte recipient scriptPubKey
(`0x00 0x14 <program>`).

```python
spk = leaf_scriptpubkey(program)         # 22 bytes
leaf = CTxOut(LEAF_AMOUNT, CScript(spk))
```

#### `leaf_programs(namespace, count)`

Convenience wrapper: returns the list of leaf programs for indices
`0..count-1` under `namespace`. Used by the balance checks.

### RPC helper

#### `rpc_for(wallet=None)`

Returns an `AuthServiceProxy` connected to the regtest node, optionally
scoped to a named wallet via `/wallet/<name>`.

```python
node = rpc_for()              # node-level RPC
w    = rpc_for("student")     # wallet-scoped RPC
```

### Wallet setup and root funding

#### `ensure_wallet_and_funds(min_blocks=101)`

Loads or creates the `student` wallet and mines blocks until at least
`min_blocks` mature coinbases exist, so subsequent funding transactions
have spendable coins. Returns the wallet RPC handle.

#### `fund_root(w, tree)`

Builds, signs, and mines one funding transaction whose `vout[0]` is the
bare-CTV root of `tree`. Returns the `COutPoint` of that root output —
this is what your first unroll transaction will spend.

### Broadcasting

#### `broadcast_and_mine(w, txs)`

Mines a list of transactions directly into a single block via
`generateblock`.

### Structural and balance checks

These are the assertions the grader runs against your work.

#### `verify_tree_shape(tree, depth, namespace)`

Static check on the tree your `ternary_secure_tree` returned: correct
number of levels, correct branching at each level, leaves match the
deterministic recipients for `namespace`, and each parent's amount equals
`sum(children) + FEE_PER_LEVEL`.

#### `assert_all_leaves_funded(namespace, count, expected_sats)`

Queries the UTXO set via `scantxoutset` and asserts that every one of
the `count` deterministic leaves under `namespace` holds at least
`expected_sats`. Used by demo 1 (full unroll).

#### `assert_leaf_state(namespace, count, funded_leaves, expected_sats)`

Like the above but asserts that **only** the leaves in `funded_leaves`
are funded and every other leaf is empty. Used by demo 2 (partial
unroll), where unrolling to one leaf necessarily funds its bottom-level
triplet but nothing else.

### Entry points

#### `demo_full_unroll(w)`

Builds the depth-3 tree, funds the root, runs your `unroll_tree`, mines
all 13 unroll transactions, and asserts that all 27 leaves are funded.

#### `demo_partial_unroll(w, target_leaf=13)`

Builds a fresh tree under a separate namespace, funds the root, runs your
`unroll_path` for `target_leaf`, mines exactly `TREE_DEPTH` path
transactions, and asserts only the bottom-level triplet containing
`target_leaf` is funded.

#### `main()`

Runs setup, then `demo_full_unroll`, then `demo_partial_unroll`. This is
what `python3 ctv.py` executes.

---

## 3. Tips

Consider these things when implementing the solution:

- Your solution doesn't break when different tree depths are used. This is a great time to apply what you learned in 130A about tree data structures :) 
- You understand the format of the tree that has to be returned from ternary_secure_tree. It is an array with tree[i] containing all the nodes on level i (tree[0] is a single root, tree[depth] contains *3 ** depth* children, etc).
- You propagate the *FEE_PER_LEVEL* correctly. The docs specify the right logic, but it is easy to miscalculate this. 
- If your solution is flexible enough (i.e. you properly utilize the BRANCHING variable), you will be able to create a tree with arbitrary branching (4-branching, 5-branching, etc) by modifying the BRANCHING variable. This is not a requirement, but you can play around with your solution by modifying this parameter.
- At least the included demos pass when you run your code.

---

Good luck!