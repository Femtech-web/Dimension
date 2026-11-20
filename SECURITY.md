# Security policy

Dimension is a library that protocols build on, so a flaw in it can become a
flaw in theirs. Please report a vulnerability privately, not in a public issue.

## Reporting

Use GitHub's private vulnerability reporting on this repository: **Security →
Report a vulnerability**. Include the affected version or commit, a minimal Fe
program or test that shows the problem, and its impact. You will get an
acknowledgement within three days.

## Scope

In scope:

- a way to obtain a trusted value without its check, such as an `Admitted` or
  `Settled` quantity, a `Price` or a `Rate` built from a raw number by
  production code;
- a rounding that favours the caller, in `admit`, `settle`, `scaled_by`,
  `exchange` or `value_of`;
- a boundary check that accepts what it is documented to reject;
- `Held` or `Supply` accepting an amount moving the wrong way, of another
  token, or in internal units;
- `preserves_share_value` returning a wrong answer.

Not vulnerabilities, because they are documented limits
([docs/guarantees.md](docs/guarantees.md)):

- a feed declared at the wrong address (`cli/feed_check.py` checks
  Chainlink feeds at review time);
- `given` or `owed` attached to a raw number with the wrong direction;
- `unsafe` code in your own ingot, or in a dependency you grant
  `allow_unsafe` (`dimension check` fails a project with either).

The Balancer V2 and Moonwell code in this repository reproduces past incidents
for research. It is deployed only on Base Sepolia, a testnet, for the live
demonstration (`deployments/base-sepolia.json`), holds nothing of value, and
is not in scope.

## Supported versions

Only the latest release receives fixes.
