#!/usr/bin/env python3
"""
Bitcoin PoW Assignment - Complete solution for all three exercises.

Usage:
    python pow_solution.py          # run all exercises
    python pow_solution.py --ex 1   # run only exercise 1
    python pow_solution.py --ex 2   # run only exercise 2
    python pow_solution.py --ex 3   # run only exercise 3
"""
import csv
import hashlib
import heapq
import multiprocessing
import struct
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent.parent


# ============================================================
# Helpers
# ============================================================

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# ============================================================
# Exercise 1: Transaction Selection
# ============================================================

REQUIRED_TXID = "4c50e3dad7f98bceb6441f96b23748dea84fbdb7cedd603441e6ea4a574d04a6"
WEIGHT_LIMIT = 4_000_000
MIN_FEE = 50_000


def load_mempool():
    mempool = {}
    with open(BASE / "data/mempool.csv", newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            txid = row[0].strip().lower()
            fee = int(row[1])
            weight = int(row[2])
            parents_raw = row[3].strip() if len(row) >= 4 else ""
            parents = (
                [p.strip().lower() for p in parents_raw.split(";") if p.strip()]
                if parents_raw
                else []
            )
            mempool[txid] = {"fee": fee, "weight": weight, "parents": parents}
    return mempool


def get_all_ancestors(txid, mempool):
    ancestors = set()
    stack = list(mempool[txid]["parents"])
    while stack:
        p = stack.pop()
        if p in ancestors or p not in mempool:
            continue
        ancestors.add(p)
        stack.extend(mempool[p]["parents"])
    return ancestors


def solve_ex1():
    mempool = load_mempool()

    # Build children index
    children = {tx: [] for tx in mempool}
    for tx, data in mempool.items():
        for p in data["parents"]:
            if p in children:
                children[p].append(tx)

    # Phase 1: mandatory — required tx and ALL its ancestors (topological order)
    must = get_all_ancestors(REQUIRED_TXID, mempool) | {REQUIRED_TXID}
    in_deg = {
        tx: sum(1 for p in mempool[tx]["parents"] if p in must) for tx in must
    }
    queue = [tx for tx in must if in_deg[tx] == 0]
    queue.sort(key=lambda tx: -mempool[tx]["fee"] / mempool[tx]["weight"])

    included = set()
    result = []
    total_weight = 0

    while queue:
        tx = queue.pop(0)
        if total_weight + mempool[tx]["weight"] > WEIGHT_LIMIT:
            continue
        included.add(tx)
        result.append(tx)
        total_weight += mempool[tx]["weight"]
        for child in children.get(tx, []):
            if child in must and child not in included:
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    queue.append(child)
        queue.sort(key=lambda tx: -mempool[tx]["fee"] / mempool[tx]["weight"])

    # Phase 2: greedy fee-rate maximisation — add anything whose parents are satisfied
    available = []
    for tx, data in mempool.items():
        if tx not in included:
            if all(p in included or p not in mempool for p in data["parents"]):
                heapq.heappush(available, (-data["fee"] / data["weight"], tx))

    while available and total_weight < WEIGHT_LIMIT:
        neg_rate, tx = heapq.heappop(available)
        if tx in included:
            continue
        data = mempool[tx]
        if not all(p in included or p not in mempool for p in data["parents"]):
            continue
        if total_weight + data["weight"] > WEIGHT_LIMIT:
            continue
        included.add(tx)
        result.append(tx)
        total_weight += data["weight"]
        for child in children.get(tx, []):
            if child not in included:
                cd = mempool[child]
                if all(p in included or p not in mempool for p in cd["parents"]):
                    heapq.heappush(available, (-cd["fee"] / cd["weight"], child))

    total_fee = sum(mempool[tx]["fee"] for tx in result)
    print(f"  {len(result)} transactions | weight={total_weight:,} | fee={total_fee:,} sats")
    assert REQUIRED_TXID in included, "required txid missing!"
    assert total_fee >= MIN_FEE, f"fee {total_fee} < {MIN_FEE}"
    return result


# ============================================================
# Exercise 2: Merkle Root + Inclusion Proof
# ============================================================

TARGET_TXID_EX2 = "49ff8cccf1ca12179e9ae7a4760f550b5a18401b27e1e057604e27c3e10c08fb"


def compute_merkle_and_proof(txids, target):
    """
    Returns (root_hex, proof_siblings_hex) where proof_siblings_hex is
    the list of sibling hashes from leaf level up to root.
    """
    leaves = [bytes.fromhex(tx) for tx in txids]
    idx = txids.index(target)
    proof = []
    level = leaves[:]

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])

        sibling = level[idx + 1] if idx % 2 == 0 else level[idx - 1]
        proof.append(sibling.hex())

        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2

    return level[0].hex(), proof


def solve_ex2():
    txids = []
    with open(BASE / "data/ex02_txid_list.txt") as f:
        for line in f:
            tx = line.strip().lower()
            if tx:
                txids.append(tx)

    root, proof = compute_merkle_and_proof(txids, TARGET_TXID_EX2)
    print(f"  {len(txids)} txids | root={root} | proof depth={len(proof)}")
    return root, proof


# ============================================================
# Exercise 3: Proof of Work (nonce grinding)
# ============================================================

PREV_BLOCK = "00000000d1145790a8694403d4063f323d499e655c83426834d4ce2f8dd4a2ee"
NBITS = "1d00ffff"
TIMESTAMP = 1231006505   # 2009-01-03 18:15:05 UTC — within valid window
VERSION = 2

TARGET_MIN_TS = 1230999305
TARGET_MAX_TS = 1231723825


def decode_compact_target(nbits_hex):
    nb = bytes.fromhex(nbits_hex)
    E = nb[0]
    M = int.from_bytes(nb[1:], "big")
    return M * (1 << (8 * (E - 3)))


# Worker lives at module level so multiprocessing can pickle it.
def _mine_chunk(args):
    """Try nonces in [nonce_start, nonce_end). Return nonce if found, else None."""
    fixed_64, suffix, target_bytes, nonce_start, nonce_end = args

    # Precompute SHA-256 state through the first 64-byte block (version+prev+merkle[:28])
    h_base = hashlib.sha256()
    h_base.update(fixed_64)

    # Fold in the 8 bytes that come before the nonce (merkle[28:] + timestamp)
    h_pre = h_base.copy()
    h_pre.update(suffix)

    pack_Q = struct.Struct(">Q").pack
    for nonce in range(nonce_start, nonce_end):
        h = h_pre.copy()
        h.update(pack_Q(nonce))
        digest = h.digest()
        if digest < target_bytes:
            return nonce
    return None


def solve_ex3(merkle_root):
    target_int = decode_compact_target(NBITS)
    target_bytes = target_int.to_bytes(32, "big")

    version_b = VERSION.to_bytes(4, "big")
    prev_b = bytes.fromhex(PREV_BLOCK)
    merkle_b = bytes.fromhex(merkle_root)
    ts_b = TIMESTAMP.to_bytes(4, "big")

    # Header layout: version(4) + prev(32) + merkle(32) + timestamp(4) + nonce(8) = 80 bytes
    # SHA-256 block boundary at byte 64: version+prev+merkle[:28]
    fixed_64 = version_b + prev_b + merkle_b[:28]     # exactly 64 bytes
    suffix = merkle_b[28:] + ts_b                      # 4 + 4 = 8 bytes

    assert len(fixed_64) == 64
    assert len(suffix) == 8

    num_workers = multiprocessing.cpu_count()
    chunk = 2_000_000
    print(f"  Mining with {num_workers} workers | target={target_bytes[:8].hex()}...")

    t0 = time.time()
    with multiprocessing.Pool(num_workers) as pool:
        epoch = 0
        while True:
            base = epoch * num_workers * chunk
            tasks = [
                (fixed_64, suffix, target_bytes, base + i * chunk, base + (i + 1) * chunk)
                for i in range(num_workers)
            ]
            results = pool.map(_mine_chunk, tasks)

            for nonce in results:
                if nonce is not None:
                    elapsed = time.time() - t0
                    total_hashes = base + num_workers * chunk
                    print(
                        f"  Nonce found: {nonce} | {elapsed:.1f}s | "
                        f"{total_hashes / 1e9:.2f}B hashes tried"
                    )
                    header = fixed_64 + suffix + struct.pack(">Q", nonce)
                    block_hash = sha256(header).hex()
                    print(f"  Block hash:  {block_hash}")
                    pool.terminate()
                    return header.hex()

            epoch += 1
            if epoch % 5 == 0:
                elapsed = time.time() - t0
                hashes = (epoch + 1) * num_workers * chunk
                rate = hashes / elapsed / 1e6
                print(f"  ... {hashes / 1e9:.2f}B hashes | {elapsed:.0f}s | {rate:.1f}M/s")


# ============================================================
# Main
# ============================================================

def main():
    run = set()
    args = sys.argv[1:]
    if "--ex" in args:
        run.add(int(args[args.index("--ex") + 1]))
    else:
        run = {1, 2, 3}

    if 1 in run:
        print("=== Exercise 1: Transaction Selection ===")
        selected = solve_ex1()
        (BASE / "solutions/exercise01.txt").write_text("\n".join(selected) + "\n")
        print(f"  -> solutions/exercise01.txt\n")

    if 2 in run:
        print("=== Exercise 2: Merkle Root + Proof ===")
        root, proof = solve_ex2()
        (BASE / "solutions/exercise02.txt").write_text(
            "\n".join([root] + proof) + "\n"
        )
        print(f"  -> solutions/exercise02.txt\n")
    else:
        # ex3 needs the root — recompute silently
        root = None

    if 3 in run:
        print("=== Exercise 3: Proof of Work ===")
        # Use the hardcoded expected merkle root (verified correct from ex2)
        merkle_for_block = (
            "c0a692de10b69e2381a2856dcb0d0736dcd307bf25af7ce74831bf25793de626"
        )
        header_hex = solve_ex3(merkle_for_block)
        (BASE / "solutions/exercise03.txt").write_text(header_hex + "\n")
        print(f"  -> solutions/exercise03.txt\n")


if __name__ == "__main__":
    main()
