# Dimension

Financial correctness for Fe. Dimension makes the mistakes behind major DeFi
losses — a price in the wrong currency, an amount rounded in the attacker's
favour, an unchecked external number — fail at compile time or at a verified
boundary, and checks the remaining guarantees with shared kernels that run both
natively and on the EVM.

> Status: in development for the Fe Builders Challenge 2026. The language
> feasibility probes are complete and reproducible; the framework and its
> Balancer V2 and Moonwell demonstrations are being built.

## Quick start

Requires `curl`, `make` and Python 3.12. The pinned compiler is downloaded and
checksum-verified; nothing uses a globally installed `fe`.

```sh
make toolchain   # Fe 26.6.0 (5b3f96a) into .tools/
make probes      # re-run the feasibility probes against their golden files
```

See [tests/probes](tests/probes/README.md) for what each probe establishes.

## Compiler

Fe [26.6.0](https://github.com/argotorg/fe/releases/tag/v26.6.0), commit
`5b3f96af2ab10df11bf847551f4b81d1fe481110`. Checksums are in
[scripts/toolchain/fe.lock](scripts/toolchain/fe.lock).

## License

Apache-2.0, except the Balancer V2 port and its upstream reference sources,
which are GPL-3.0-or-later as Balancer's license requires. Each such directory
carries its own license file.
