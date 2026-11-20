# An ERC-4626 vault: reuse beyond the incidents

Balancer and Moonwell show Dimension preventing two specific failures. This
example shows it as a library for a different protocol class, with nothing
written for the occasion: a tokenized vault's share accounting, the most common
place a rounding direction is chosen by hand and audited after the fact.

## The rule EIP-4626 fixes, and how it is usually met

EIP-4626 requires a vault to round in its own favour:

- `deposit` and `redeem` round down: shares issued and assets paid out;
- `mint` and `withdraw` round up: assets charged and shares burned.

OpenZeppelin's ERC4626 meets this by naming a rounding mode in each of the four
functions, and every implementation must get all four right by hand.

## Written with Dimension

[`ingots/vault`](../ingots/vault) names no rounding. Each operation states the
amount the caller gives and which way it moves. `exchange` gives back the
other token moving the other way, rounded by that direction:

```fe
/// Shares for depositing `assets`: assets come in, shares go out.
pub fn preview_deposit<A>(_ v: Vault<A>, _ assets: Quantity<A, In, Given>) -> Quantity<
    Shares<A>,
    Out,
    Settled,
> {
    exchange(
        assets,
        numerator: v.total_shares.raw() + 1,
        denominator: v.total_assets.raw() + 1,
    )
}
```

`exchange` is a single function in Dimension's core. Its return type is
`Quantity<B, G::Opposite, Settled>`: `Flow` has an associated `Opposite`
(`In` for `Out`, `Out` for `In`), so the result's direction, and with it its
rounding, follows from the given amount's.

| Operation | Given | Given back | Rounding that follows |
|---|---|---|---|
| deposit | assets, `In` | shares, `Out` | down |
| mint | shares, `Out` | assets, `In` | up |
| withdraw | assets, `Out` | shares, `In` | up |
| redeem | shares, `In` | assets, `Out` | down |

Rounding shares up on a deposit would have to be written as a deposit whose
assets leave the vault. The return type then no longer matches, and the
compiler rejects it (case `vault_deposit_rounds_shares_up`):

```
expected `Quantity<Shares<A>, Out, Settled>`, but `Quantity<_, In, Settled>` is given
```

A developer could tell that lie consistently instead, declaring the deposit's
assets `Out` and its shares `In` in every signature. The vault's books then
refuse it. Its assets are a `Held<A>` and its shares a `Supply<Shares<A>>`,
which move only by their own token, in the matching direction:

```
v.total_assets = v.total_assets.credit(assets)
                                       ^^^^^^ expected `Quantity<A, In, _>`, but `Quantity<A, Out, Given>` is given
v.total_shares = v.total_shares.issue(shares)
                                      ^^^^^^ expected `Quantity<Shares<A>, Out, _>`, but `Quantity<Shares<A>, In, Settled>` is given
```

The same types refuse a redemption that credits the returning shares to the
supply, which would raise it instead of retiring them
(`share_supply_credited_as_held`): a `Supply` has no `credit`.

That is case `vault_deposit_labeled_as_leaving`.

Conversions count one virtual asset and one virtual share, as OpenZeppelin does
with a decimals offset of 0. This keeps a first depositor from inflating the
share price.

## How it is checked

| Check | Scale | Result | Run |
|---|---|---|---|
| Each preview against the exact rational result, on every vault state with holdings, supply and amount below 32 | 32,768 states, 4 previews, EVM and native | exact floor or ceil as EIP-4626 requires | `make unit` |
| Round trips: deposit then redeem; mint then redeem; mint then withdraw | the same 32,768 states | never pays the caller | `make unit` |
| The four previews against OpenZeppelin Contracts v5.1.0's ERC4626, in the same state, over empty, dust, ordinary and huge vaults | 40,000 vectors | all equal; in 33,684 of them the exact result is fractional, so the rounding direction decides | `make vault` |

The comparison with OpenZeppelin puts its real ERC4626 into each state:
forge-std sets the vault's asset balance and share supply, and the Fe contract
receives the same numbers. Agreement shows that the roundings Dimension derives
are exactly those that OpenZeppelin's audited code names.

## Limits

This is the vault's accounting: the four previews and the state updates. It is
not a full ERC-4626 token: there are no ERC-20 shares, transfers, allowances or
asset custody. The previews contract takes the vault's state with each call,
so a test can set it.
