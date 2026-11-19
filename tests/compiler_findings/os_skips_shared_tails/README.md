# `-O s` produces larger code than `-O 2`: shared revert tails are not formed

A compiler finding from building Dimension, kept here as a minimal reproducer.
Reported upstream as [argotorg/fe#2043](https://github.com/argotorg/fe/issues/2043); this README is the report.

**Version:** `fe 26.6.0 (5b3f96a)`, Sonatina backend, `fe build -O <level> --emit runtime-bytecode,sizes`.
Also confirmed on `fe 26.7.0 (e6e6342)`: 372 bytes at `-O 2` and 509 at `-O s`
for the reproducer; 6,972 and 7,423 for `FaithfulPool`
([comment](https://github.com/argotorg/fe/issues/2043#issuecomment-7015249573)).

`fe build --help` describes `-O s` as *"size-oriented (currently similar to
`2`)"*. For [this 60-line program](src/lib.fe), `-O s` emits **41% more
runtime code than `-O 2`**.

## Sizes

| Level | Runtime bytes | `fail` | Shared tails |
|---|---|---|---|
| `-O 1` | 364 | 194 | `__evm_shared_tail_0`, 31 bytes |
| `-O 2` | 364 | 194 | `__evm_shared_tail_0`, 31 bytes |
| `-O s` | **513** | **374** | none |

```sh
fe build -O 2 --emit runtime-bytecode,sizes   # runtime: 364 bytes
fe build -O s --emit runtime-bytecode,sizes   # runtime: 513 bytes
```

## What the sizes show

`fail` matches on an eight-variant enum, and each arm ends in
`assert!(false, "...")`.

- At `-O 1` and `-O 2` the arms share a 31-byte tail,
  `__evm_shared_tail_0`, presumably the common `Error(string)` revert
  sequence.
- At `-O s` no shared tail is formed. Each arm carries its own copy, and
  `fail` grows from 194 to 374 bytes.

## In a larger contract

The same pattern appears in Dimension's port of Balancer V2's stable pool
(`ingots/balancer_v2`, contract `FaithfulPool`): 7,992 bytes at `-O 2` and
9,139 at `-O s` (+14%). The Fe port of Balancer's `StableMath` harness grows
from 8,179 to 8,819 bytes. Two effects account for nearly all of it:

| Function | `-O 2` | `-O s` |
|---|---|---|
| `fail` (the same eight-arm revert pattern) | 188 bytes, plus a 36-byte shared tail | 368 bytes, no shared tail |
| `get_token_balance_given_invariant_and_all_other_balances` (`#[inline(never)]`) | 1 copy, 344 bytes | 3 copies, 377 + 376 + 372 bytes |

The second effect, a large non-inlined function emitted three times at the
size-oriented level, did not reduce to a standalone program: a plain or
effect-generic solver called from three sites is emitted once at both levels.
It reproduces with `fe build -O s --contract FaithfulPool --emit sizes` in
`ingots/balancer_v2`.

## Expected

`-O s` at most as large as `-O 2`: the shared tails `-O 2` forms, and one copy
of a function `-O 2` emits once.
