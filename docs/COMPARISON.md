# Comparison with prior work

Dimension builds on known ideas. What it adds is where those ideas are
enforced, by Fe's compiler on EVM code, and how they are verified, against the
original code and the real chains.

| Work | What it does | How Dimension differs |
|---|---|---|
| [fe-fixedpoint](https://github.com/ridakalam52-design/fe-fixedpoint) (MIT; also a Fe Builders Challenge 2026 entry) | Fixed-point and WAD/RAY math for Fe with a runtime `Rounding` enum of seven modes. It is differential-tested against Solady, OpenZeppelin and PRBMath, and audits Fe's `core::fixed`. | Complementary. fe-fixedpoint computes a chosen rounding exactly; Dimension decides which rounding a call site gets, from the type of the value, and rejects the wrong one at compile time. Its exact primitives could serve as Dimension's `Rounding` implementations. |
| Fe `core::fixed`, `core::num` | `Wad`, `Ray` and `mul_div`, rounding down, with explicit `mul_up` and `div_up` | Dimension uses `mul_div` and `mul_div_ceil` from `core::num` underneath, and adds asset, pair, direction and stage to the type. |
| [Balancer V3 `ScalingHelpers`](https://github.com/balancer/balancer-v3-monorepo/blob/main/pkg/solidity-utils/contracts/helpers/ScalingHelpers.sol) | After the V2 lesson, separately named `toScaled18ApplyRateRoundDown` and `...RoundUp` helpers | The direction is in the function's name, and the caller still picks it. Nothing checks that a call site picked the right one. In Dimension the call site does not pick. |
| [roundme](https://github.com/crytic/roundme) (Trail of Bits, AGPL-3.0) | A human-assisted analyzer: given a formula and the direction its result must round, it derives the direction of each operation. It ships a Balancer V2 example. | roundme advises, at review time, on formulas written out separately. Dimension enforces the direction in the code itself, at every build. |
| [ScType](https://conf.researchr.org/details/icse-2024/icse-2024-research-track/127/Towards-Finding-Accounting-Errors-in-Smart-Contracts) (ICSE 2024) | Abstract type inference over Solidity, through Slither, that finds accounting errors (mixing units, scales and assets) after the fact | ScType detects these errors in existing Solidity; Dimension makes them unwritable in new Fe code. They suit different stages of a codebase's life. |
| [Remix workshop `RoundingDirectionExploit`](https://github.com/remix-project-org/remix-workshops/tree/master/RoundingDirectionExploit) (May 2026, no license) | A LearnEth tutorial on the rounding-direction bug class (three categories, nine incidents) with a hands-on reproduction of the Balancer V2 case in a simplified Solidity pool | Teaches the bug class and how to spot it in review. Dimension's kernel is a faithful port, verified against Balancer's code and the deployed pool, and the types make the bug unwritable. Nothing was copied. |
| [Quint model of the bug](https://github.com/informalsystems/quint-balancer-v2-rounding-bug) (Informal Systems, June 2026, no license) | A minimal model reproducing the bug. Its invariant is that the stored invariant must not exceed what the scaled balances support. | Dimension checks the same invariant on the executable kernel, on both backends, and prevents the violation by type and by a runtime guard. Nothing was copied. |
| Units of measure (F#), `uom` (Rust), `Coin<T>` (Move) | Phantom types for units or token identity | The same technique, applied to prices, scales and rounding direction on the EVM, with its cost measured: zero. |

## What is new

- **A direction derived from meaning and enforced by the compiler on EVM
  code, at no runtime cost.** The call site never names a rounding. The
  compiled code is byte-identical to the hand-written version.
- **The incident's own code, typed.** Balancer's StableMath, pool paths and
  protocol fees were ported faithfully. They were checked against the Solidity
  on 220,000 vectors, against the deployed pool on 669 quotes, and against the
  attack itself: all 360 of the attacker's steps compute the amounts Balancer
  computed. Then the types were applied to that same kernel. Putting Balancer's
  line back is a type error, and the attacker's own transactions revert.
- **The incident's own configuration, typed.** Moonwell's MIP-X43 setting,
  written against a registry of the real Base feeds, does not compile. Forks of
  Base across the eight days of the incident show the correct configuration
  pricing cbETH at the same value Moonwell's own oracle gave whenever it was
  right.

## What is not new

- Phantom types for units and identities.
- The observation that rounding direction should follow value flow. It is in
  roundme, in audit practice, and in Balancer V3's naming.
- The stored-invariant property, which the Quint model states.

Dimension's contribution is making those ideas mandatory in Fe, and proving on
the real incidents that they would have held.
