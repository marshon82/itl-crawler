"""SimHash near-duplicate detection over page text."""

from __future__ import annotations

import hashlib
from collections import defaultdict


def _tokens(text: str) -> list[str]:
    words = [w for w in (text or "").lower().split() if len(w) > 2]
    if len(words) < 3:
        return words
    return [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]


def compute(text: str, bits: int = 64) -> int:
    acc = [0] * bits
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")
        for i in range(bits):
            acc[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i, v in enumerate(acc):
        if v > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def groups(store, max_distance: int = 3) -> list[list[str]]:
    rows = store.conn.execute(
        "SELECT url, simhash FROM pages WHERE simhash IS NOT NULL AND status BETWEEN 200 AND 299"
    ).fetchall()
    if not rows:
        return []
    buckets: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for url, sh in rows:
        buckets[sh >> 48].append((url, sh))
    parent = {url: url for url, _ in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    items = list(rows)
    keys = sorted(buckets)
    for i, key in enumerate(keys):
        pool = list(buckets[key])
        if i + 1 < len(keys) and keys[i + 1] - key <= 1:
            pool.extend(buckets[keys[i + 1]])
        for i1, (u, a) in enumerate(pool):
            for v, b in pool[i1 + 1:]:
                if hamming(a, b) <= max_distance:
                    union(u, v)

    clustered: dict[str, list[str]] = defaultdict(list)
    for url, _ in items:
        clustered[find(url)].append(url)
    return [members for members in clustered.values() if len(members) > 1]


def mark_duplicates(store) -> int:
    found = groups(store)
    return sum(len(g) - 1 for g in found)
