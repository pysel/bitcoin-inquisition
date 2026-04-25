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
alias bcli='docker exec btc bitcoin-cli -rpcuser=student -rpcpassword=student -rpcwallet=student'
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

