# Moonwell MIP-X43: the second demonstration

On 2026-02-15, a Moonwell governance proposal configured the cbETH market on
Base to price cbETH in USD with the cbETH/ETH exchange-rate feed alone. For
eight days the market valued cbETH at about 1.12 USD instead of about 2,200.
Liquidators seized collateral against almost nothing, and Moonwell was left
with 1,779,044 USD of bad debt
([incident summary](https://forum.moonwell.fi/t/mip-x43-cbeth-oracle-incident-summary/2068)).

This document shows the same configuration written with Dimension, where each
form of the mistake is stopped, and the fork runs that check it against the
real chain.

## What happened on chain

Every fact below was read from Base, and the fork test checks it again:

| | |
|---|---|
| Moonwell's oracle | `ChainlinkOracle` at `0xEC942bE8A8114bFD0396A5052c36027f2cA6a9d0` |
| The cbETH market | `0x3bf93770f2d4a794c3d9EBEfBAeBAE2a8f09A5E5` |
| Last block priced correctly | 42,194,662: the composite feed `0xB0Ba0C5D…18C5`, 2,206.68 USD |
| MIP-X43 executes | block 42,194,663, 2026-02-15 18:04:33 UTC, transaction [`0xd26baf29…ae812`](https://basescan.org/tx/0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812). cbETH's feed becomes the wrapper `0x67996D…495D`, whose `priceFeed()` is the cbETH/ETH rate |
| The fix executes | block 42,538,949, 2026-02-23 17:20:45 UTC, transaction [`0xd1c363de…043c5`](https://basescan.org/tx/0xd1c363dec8e159b5db38799fed885ad5a157aa1e237ccc74b312df7fad8043c5). The composite feed is restored |

The root cause is visible in Moonwell's repository. MIP-X43 iterated over a
list of markets priced by a single USD feed, and cbETH's entry named
`cbETHETH_ORACLE`. The registry already said the feed was cbETH/ETH, but only
in a string.

## The same configuration, with Dimension

[`ingots/moonwell/src/registry.fe`](../ingots/moonwell/src/registry.fe)
declares each feed once, with its pair in its type:

```fe
pub const CBETH_ETH: Feed<CBETH, ETH> = feed(
    Address::new(0x806b4Ac04501c29769051e42783cF04dCE41440b),
    decimals: 18,
    max_age: 90_000,
    min_wad: WAD,
    max_wad: 3 * WAD / 2,
)

pub const ETH_USD: Feed<ETH, USD> = feed(
    Address::new(0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70),
    decimals: 8,
    max_age: 1_800,
    min_wad: 100 * WAD,
    max_wad: 100_000 * WAD,
)
```

Each `max_age` is the feed's heartbeat plus a margin, taken from its update
history:

- cbETH/ETH updates every 86,400 s (largest gap seen: 86,426 s);
- ETH/USD updates at least every 1,200 s (largest gap seen: 1,201 s).

Each band is the range a sane answer must fall in.

The market's price is the composition, in
[`pricing.fe`](../ingots/moonwell/src/pricing.fe). Its type is checked:
`Price<CBETH, ETH> * Price<ETH, USD>` is `Price<CBETH, USD>`, and nothing else
is.

```fe
pub fn read(self) -> Price<T, USD> uses (call: mut Call, ctx: Ctx) {
    oracle::read(self.leg) * oracle::read(self.eth_usd)
}
```

## Where each form of the mistake is stopped

| Form of the mistake | Layer | Outcome |
|---|---|---|
| MIP-X43 as written: the cbETH/ETH feed used as cbETH's USD price | compile time | `error[8-0000]`: expected `Feed<CBETH, USD>`, but `Feed<CBETH, ETH>` is given |
| The registry itself lies: cbETH/ETH declared as cbETH/USD, with a USD feed's 8 decimals | bind time | the contract's constructor reverts: `WrongDecimals(feed, 8, 18)` |
| The registry lies with the feed's real decimals | read time | the first read reverts: `AnswerOutOfBand(feed, 1.1227e18, 100e18, 100000e18)` |
| A wrong feed with the declared decimals and an answer inside the declared band | review, before deployment | every on-chain check passes it. `make feeds` rejects it: see below |

A stale leg is refused as well. Past ETH/USD's declared 1,800 s, the read
reverts with `StaleAnswer`.

## Before deployment: `make feeds`

No check on chain can prove an address is the feed it is declared to be.
Chainlink can: its published directory lists every feed's address with its
pair, decimals and heartbeat. [`feed_check.py`](../cli/feed_check.py)
reads each `Feed<B, Q>` declaration from Fe source and requires, for each:

- **in Chainlink's directory:** the address is listed, as the pair `B/Q`,
  with the declared decimals and a heartbeat no longer than `max_age`;
- **on chain, at one block:** the feed reports those decimals and the listed
  description, points to the listed aggregator, and its answer is positive,
  fresh and inside the declared band.

`make feeds` runs it on Moonwell's registry, which passes all 10 checks for
both feeds. Then it runs it on [`tests/feeds`](../tests/feeds/src/lib.fe), two
wrong declarations that both compile:

| Declaration | On chain | feed-check |
|---|---|---|
| MIP-X43: the cbETH/ETH feed as `Feed<CBETH, USD>`, with its real 18 decimals | the first read is out of band | rejected: listed as CBETH / ETH. Chainlink's CBETH / USD feed is `0xd7818272…817d` |
| The cbETH/USD feed as `Feed<ETH, USD>` | **every check passes**: 8 decimals, fresh, about 2,036 USD, inside the band | rejected: listed as CBETH / USD |

The second is the case no type and no on-chain check can see: it prices ETH at
cbETH's price, about 14% high. The trust that remains is in Chainlink's own
directory, at review time.

```sh
python3 cli/feed_check.py src/registry.fe --network base   # your registry
```

## The fork runs

`make moonwell` runs
[`MoonwellFork.t.sol`](../contracts/reference/test/MoonwellFork.t.sol) on Base
forks. At each block it reads Moonwell's deployed oracle, deploys Dimension's
`CbethUsdOracle`, and reads it:

| Block | Time (UTC) | Moonwell's oracle | Dimension, same feeds |
|---|---|---|---|
| 42,194,662 | Feb 15 18:04:31 | 2,206.6837 | 2,206.6837, identical to the wei |
| **42,194,663**, MIP-X43 | Feb 15 18:04:33 | **1.1227** | 2,206.6837 |
| 42,225,961 | Feb 16 11:27:49 | 1.1227 | 2,209.5567 |
| 42,257,260 | Feb 17 04:51:07 | 1.1224 | 2,232.6376 |
| 42,288,558 | Feb 17 22:14:23 | 1.1225 | 2,243.1581 |
| 42,319,857 | Feb 18 15:37:41 | 1.1225 | 2,234.0663 |
| 42,351,156 | Feb 19 09:00:59 | 1.1225 | 2,213.2208 |
| 42,382,454 | Feb 20 02:24:15 | 1.1229 | 2,190.9733 |
| 42,413,753 | Feb 20 19:47:33 | 1.1229 | 2,203.5089 |
| 42,445,052 | Feb 21 13:10:51 | 1.1229 | 2,217.9224 |
| 42,476,350 | Feb 22 06:34:07 | 1.1229 | 2,217.9721 |
| 42,507,649 | Feb 22 23:57:25 | 1.1229 | 2,196.3561 |
| 42,538,948 | Feb 23 17:20:43 | 1.1229 | 2,091.1616 |
| **42,538,949**, the fix | Feb 23 17:20:45 | 2,091.1616 | 2,091.1616, identical to the wei |

The test asserts four things:

1. At every block, Dimension's price is the exact product of the two feeds'
   answers.
2. Inside the window, Moonwell's price is the bare rate.
3. Where Moonwell's oracle was right, the two prices are identical to the wei
   (`2206683650838065175827` and `2091161605700000000000`).
4. MIP-X43's wiring is as described: before MIP-X43 and after the fix, the
   composite feed; in between, a wrapper reading cbETH/ETH alone.

The same test checks the bind-time, read-time and staleness rejections against
the real feeds at the MIP-X43 block, with the full revert data.

## Limits

- The demonstration covers one market and its two feeds, on Base.
- It checks no L2 sequencer uptime feed.
- Each band is a judgement: a band that admits 1.12 USD for cbETH would let the
  read-time form through. The compile-time layer does not depend on bands.

Reproduce: `make moonwell`, with `BASE_RPC_URL` set to override the public
default.
