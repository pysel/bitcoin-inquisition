# Covenants on bitcoin-inquisition — student handbook

This repo is a fork of Bitcoin Core 29.x ("bitcoin-inquisition") that implements
several proposed covenant opcodes. In `regtest` they are all active from genesis,
so you can start experimenting immediately.

Active covenant opcodes (see `src/binana/*.json`):

| Name | BIP | Opcode | Source |
|---|---|---|---|
| `OP_CHECKTEMPLATEVERIFY` (CTV) | 119 | `0xb3` | `src/binana/ctv.json` |
| `OP_CAT` | — | `0x7e` | `src/binana/op_cat.json` |
| `OP_CHECKSIGFROMSTACK` (CSFS) | 348 | `0xcc` | `src/binana/checksigfromstack.json` |
| `OP_ANYPREVOUT` / `OP_ANYPREVOUTANYSCRIPT` (APO) | 118 | key-path tagged | `src/binana/anyprevout.json` |
| `OP_INTERNALKEY` | — | `0xcb` | `src/binana/internalkey.json` |
| Consensus Cleanup | — | n/a | `src/binana/consensuscleanup.json` |

Regtest wiring: `src/kernel/chainparams.cpp:604` (`INQ_DEPLOYMENTS_REGTEST`).
Flag definitions: `src/script/interpreter.h:154` (`INQ_VERIFY_FLAGS`).

---

## Files added to the repo

| Path | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build: compiles `bitcoind` + `bitcoin-cli`, produces a ~100MB runtime image. |
| `docker/entrypoint.sh` | Writes a default `bitcoin.conf` on first boot, execs `bitcoind`. |
| `.dockerignore` | Excludes `build*`, `.git`, generated headers from the build context. |
| `COVENANTS.md` | This document. |

---

## 1. Build and run

```bash
# Build the image (~10–20 min, needs ≥4 GB RAM; bump JOBS for faster builds)
docker build --build-arg JOBS=8 -t bitcoin-inquisition .

# Run a regtest node, persist chain state in a named volume
docker run -d --name btc \
  -p 18443:18443 -p 18444:18444 \
  -v btcdata:/home/bitcoin/.bitcoin \
  bitcoin-inquisition

# Tail logs
docker logs -f btc
```

Defaults baked into `docker/entrypoint.sh`:

- `chain=regtest`, `txindex=1`, `fallbackfee=0.0002`
- RPC user/pass: `student` / `student`
- RPC listens on `0.0.0.0:18443`, P2P on `0.0.0.0:18444`

Override via env vars: `CHAIN=signet`, `RPC_USER=...`, `RPC_PASSWORD=...`.

Quick sanity check:

```bash
alias bcli='docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student'
bcli getblockchaininfo
```

Mine 101 blocks so you have a spendable coinbase:

```bash
docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student createwallet student
ADDR=$(docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student getnewaddress)
docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student generatetoaddress 101 "$ADDR"
```

---

## 2. How to talk to the node

### 2.1 bitcoin-cli (easiest; limited for covenants)

Great for wallet ops, mining, inspection. **Not practical for building covenant
scripts** — the CLI has no way to emit raw opcodes or assemble witness stacks.

```bash
alias bcli='docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student'
bcli getblockchaininfo
bcli decodescript <hex>        # recognizes OP_CHECKTEMPLATEVERIFY
bcli sendrawtransaction <hex>  # you broadcast the hex you built elsewhere
```

Relevant RPCs for covenants:

- `decodescript` — at `src/rpc/rawtransaction.cpp:484`; recognizes `0xb3` and
  tags CTV scripts as `bare_default_check_template_verify_hash`.
- `sendrawtransaction` / `submitblock` — unchanged; they don't care which
  opcodes you use.
- `getdeploymentinfo` — returns standard BIP9 deployments. Inquisition opcodes
  are **not** behind a deployment flag on regtest (active at genesis), so you
  won't see them here.
- **Wallet descriptors do *not* support raw CTV scripts.** You cannot
  `importdescriptors` a CTV-protected output and let the wallet manage it.

### 2.2 HTTP JSON-RPC (any language)

Point any Bitcoin RPC client at `http://student:student@localhost:18443/`.

Python example:

```python
from bitcoinrpc.authproxy import AuthServiceProxy  # pip install python-bitcoinrpc
rpc = AuthServiceProxy("http://student:student@localhost:18443")
print(rpc.getblockchaininfo())
print(rpc.sendrawtransaction(hex_tx))
```

### 2.3 Python test_framework (recommended for covenant work)

The repo's `test/functional/test_framework/` is the **canonical library for
building covenant transactions** against this node. It is self-contained (no
pip install), handles tx serialization, taproot construction, CTV hash, and
signing.

Key modules:

- `test_framework.messages` — `CTransaction`, `CTxIn`, `CTxOut`, `COutPoint`,
  `CTxInWitness`, `sha256`. `CTransaction.get_standard_template_hash(nIn)` at
  `test/functional/test_framework/messages.py:639` implements the BIP 119 hash.
- `test_framework.script` — `CScript`, opcode constants
  (`OP_CHECKTEMPLATEVERIFY`, `OP_CAT`, `OP_CHECKSIGFROMSTACK`,
  `OP_INTERNALKEY`), and `taproot_construct(internal_pubkey, [(name, script, leafver)])`.
- `test_framework.wallet` — `MiniWallet` with deterministic keys, `sign_tx()`.
- `test_framework.blocktools` — `create_block`, `create_coinbase`,
  `add_witness_commitment` if you want to mine blocks directly (bypassing RPC).
- `test_framework.key` — `ECKey`, `compute_xonly_pubkey` for taproot.

To use it from a host script (outside a test harness), either:

1. **Run your script inside the container** after mounting `test/functional` in,
   or `docker cp` it out; or
2. **Copy `test/functional/test_framework/` into your assignment repo** — it
   has no external deps other than stdlib.

Reference examples to crib from:

- CTV: `test/functional/feature_checktemplateverify.py`
- OP_CAT: `test/functional/feature_opcat.py`

---

## 2.4 The imports in `ctv.py`, in plain terms

The student file uses this import block:

```python
from test_framework.address   import program_to_witness, script_to_p2wsh
from test_framework.authproxy import AuthServiceProxy, JSONRPCException
from test_framework.messages  import (COIN, COutPoint, CTransaction,
                                       CTxIn, CTxInWitness, CTxOut, sha256)
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

#### `CTxInWitness`
Each input needs some data to "unlock" the output it's spending (e.g. a
signature, or — for CTV — just the raw locking script). That data goes
here:
```python
tx.wit.vtxinwit = [CTxInWitness()]
tx.wit.vtxinwit[0].scriptWitness.stack = [my_unlock_bytes]
```

#### `COIN`
The number `100_000_000`. Amounts inside scripts are in **sats**; the
RPC takes **BTC**. Use `COIN` to convert:
```python
from decimal import Decimal
btc_value = Decimal(40_000) / COIN   # 40000 sats → 0.0004 BTC
```

#### `sha256(data)`
Plain SHA-256. Used here to hash a script when building a funding
address for it.

### Scripts (`test_framework.script`)

#### `CScript([...])`
Builds a script from a list of pieces. Behaves like `bytes` — you can
pass it anywhere bytes are expected. In this assignment, you only really
need two patterns:
```python
# From a list (Python figures out how to push each item):
s1 = CScript([template_hash, OP_CHECKTEMPLATEVERIFY])

# From raw bytes when you want exact control:
s2 = CScript(bytes([0x20]) + template_hash + bytes([OP_CHECKTEMPLATEVERIFY]))
```

#### `OP_CHECKTEMPLATEVERIFY`
The integer `0xb3` — the CTV opcode. Putting a 32-byte hash and this
opcode in a script creates a CTV-locked output.

### Addresses (`test_framework.address`)

You won't be manipulating address bytes yourself — these are two helpers
that give you a string you can hand to `sendtoaddress`:

- `script_to_p2wsh(script)` — "give me the address that pays into a UTXO
  locked by this custom script." Use this to fund a CTV root.
- `program_to_witness(0, hash160)` — "give me the address for this
  20-byte program." Use this if you ever need to display a leaf address.

### Talking to the node (`test_framework.authproxy`)

#### `AuthServiceProxy(url)`
The RPC client. Every attribute access is an RPC call.
```python
rpc = AuthServiceProxy("http://student:student@localhost:18443")
print(rpc.getblockcount())
rpc.sendrawtransaction(tx.serialize().hex())
```

#### `JSONRPCException`
The exception the client raises when the node rejects a call (bad tx,
wallet not loaded, etc.). Catch it if you want to read `e.error["message"]`.

---

## 3. Concrete CTV workflow (the one you'll show students)

The full pattern, distilled from `feature_checktemplateverify.py:61–419`:

```python
from io import BytesIO
from decimal import Decimal
from test_framework.messages import CTransaction, CTxIn, CTxOut, CTxInWitness, COutPoint, COIN, sha256
from test_framework.script import CScript, OP_CHECKTEMPLATEVERIFY
from bitcoinrpc.authproxy import AuthServiceProxy

rpc = AuthServiceProxy("http://student:student@localhost:18443/wallet/student")

# 1. Decide what spending the covenant UTXO must produce.
outputs = [CTxOut(50_000, bytes.fromhex("0014" + "11"*20))]  # e.g. one P2WPKH output
fee = 500

# 2. Compute the BIP 119 StandardTemplateHash for a single-input spend at vin index 0.
template_tx = CTransaction()
template_tx.version = 2
template_tx.vin = [CTxIn()]          # placeholder; CTV hash commits to vin count, not txid
template_tx.vout = outputs
template_hash = template_tx.get_standard_template_hash(nIn=0)

# 3. Build the covenant script: <32-byte hash> OP_CHECKTEMPLATEVERIFY.
ctv_script = CScript([template_hash, OP_CHECKTEMPLATEVERIFY])

# 4. Fund the covenant script. Simplest path: fund a P2WSH wrapping it.
p2wsh = CScript([0, sha256(ctv_script)])
amount = sum(o.nValue for o in outputs) + fee
funding_txid = rpc.sendtoaddress("", Decimal(amount) / COIN)  # or craft manually
# ... find the vout index of the P2WSH output on funding_txid ...

# 5. Spend: build the exact tx the template commits to, satisfy witness.
spend = CTransaction()
spend.version = 2
spend.vin = [CTxIn(COutPoint(int(funding_txid, 16), vout_index))]
spend.vout = outputs                         # must match byte-for-byte
spend.wit.vtxinwit = [CTxInWitness()]
spend.wit.vtxinwit[0].scriptWitness.stack = [ctv_script]  # P2WSH reveal

rpc.sendrawtransaction(spend.serialize().hex())
```

---

## 4. Running the built-in tests (good reference / smoke test)

The container's binaries are stripped down (no test suite shipped). To run the
functional tests you have to build locally:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j8
./build/test/functional/feature_checktemplateverify.py
./build/test/functional/feature_opcat.py
```

These are the most thorough worked examples of every covenant opcode.

---