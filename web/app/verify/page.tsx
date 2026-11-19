import type { Metadata } from "next";
import Link from "next/link";
import { Claims, Status } from "@/components/Claims";
import { Code } from "@/components/Code";
import { PageHead, Section } from "@/components/PageHead";
import { allClaims, compileFail, differential, meta, mutants, probes, unit } from "@/lib/results";
import { BLOB } from "@/lib/site";

export const metadata: Metadata = { title: "Verify" };

const STEPS = [
  ["Install", "make toolchain && make reference-deps", "Fe 26.6.0 downloaded and checksum-verified; forge-std and OpenZeppelin pinned by commit."],
  ["See both incidents", "make demo", "Each mistake written in Fe, the compiler's verdict, the fix, and the evidence the fork runs saved."],
  ["Run everything offline", "make ci", "Formatting, unsafe policy, unit tests on both backends, compile-fail cases, probes, the differential test, the search, the EVM contracts and the vault. About a minute."],
  ["Against the real chains", "make replay fidelity moonwell", "The attacker's own transactions, the deployed pool, and Moonwell's market on Base: public RPCs by default."],
  ["Try to break it", "make mutants", "Plants each bug below in a scratch copy and requires the check meant for it to fail."],
];

export default function Verify() {
  const cases = compileFail.cases as { id: string; mechanism: string; observed: { error_code: string; twin: { ok: boolean } } }[];
  return (
    <>
      <PageHead
        eyebrow="For judges and auditors"
        title={
          <>
            Don&apos;t take our word for it. <em>Run it.</em>
          </>
        }
        lede={
          <>
            Everything on this page is rendered from the reports in <code>docs/results</code>, written by the runs
            below. Each claim is a question, its answer, and the evidence, and a claim that fails fails its run. These
            results were recorded with Fe {differential.fe.version} on {meta.platform}; CI repeats them on Linux.
          </>
        }
      />
      <Section eyebrow="Ten minutes, from a clean clone">
        <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 14 }}>
          {STEPS.map(([title, command, what], i) => (
            <li key={title} className="panel" style={{ display: "grid", gridTemplateColumns: "42px 1fr", gap: 14, alignItems: "start" }}>
              <span className="num" style={{ fontSize: 22, color: "var(--dim)" }}>
                0{i + 1}
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{title}</div>
                <div className="ink2" style={{ fontSize: 14.5, margin: "4px 0 10px" }}>
                  {what}
                </div>
                <Code>{`$ ${command}`}</Code>
              </div>
            </li>
          ))}
        </ol>
        <p style={{ marginTop: 20 }}>
          <Link href="/docs/judges">The guided tour, with where each claim lives in the code →</Link>
        </p>
      </Section>

      <Section eyebrow="Every claim" title="Questions, answered by runs.">
        <div style={{ display: "grid", gap: 26 }}>
          {allClaims().map((group) => (
            <div key={group.suite}>
              <h3 style={{ fontSize: 22, marginBottom: 10 }}>
                {group.title} <code style={{ fontSize: 13 }}>{group.command}</code>
              </h3>
              <Claims claims={group.claims} />
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow="Planted bugs" title="Would the checks notice if the code were wrong?">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bug planted</th>
                <th>Layer</th>
                <th>Caught by</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {mutants.mutants.map((m) => (
                <tr key={m.id}>
                  <td>{m.bug}</td>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>
                    {m.layer}
                  </td>
                  <td>
                    <Status holds={m.caught} yes="caught" no="missed" />
                    <div>
                      <code>{m.check}</code>
                    </div>
                  </td>
                  <td className="ink2" style={{ fontSize: 13, overflowWrap: "anywhere" }}>
                    {(m.evidence[0] ?? "").slice(0, 140)}
                    {(m.evidence[0] ?? "").length > 140 ? "…" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 14 }}>
          A mutant counts as caught only if its check fails for the reason expected of it; a failure for any other
          reason, such as a network error, is reported as inconclusive and fails the run.
          {mutants.fork_mutants_included
            ? " The last two need a fork: run all of them with make mutants FORKS=1."
            : " Two more need a fork: run them with make mutants FORKS=1."}
        </p>
      </Section>

      <Section eyebrow="Found along the way" title="A Fe compiler issue, reduced to 60 lines.">
        <p className="ink2">
          <code>fe build --help</code> describes <code>-O s</code> as size-oriented and &quot;currently similar to{" "}
          <code>2</code>&quot;. On Fe 26.6.0 a 60-line program is 364 bytes at <code>-O 2</code> and 513 at{" "}
          <code>-O s</code>: the size level skips the shared revert tails <code>-O 2</code> forms. In the Balancer pool it also
          emits a large solver three times instead of once, for +14% in all.
        </p>
        <p>
          Reported upstream as <a href="https://github.com/argotorg/fe/issues/2043">argotorg/fe#2043</a>, with{" "}
          <a href={`${BLOB}/tests/compiler_findings/os_skips_shared_tails`}>the reproducer kept in this repository</a>.
        </p>
      </Section>

      <Section eyebrow="What the compiler rejects" title={`${compileFail.summary.cases} constructions, each with a corrected twin.`}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Case</th>
                <th>Mechanism</th>
                <th>Error</th>
                <th>Twin</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => {
                const id = c.id.split("/")[1];
                return (
                  <tr key={id}>
                    <td>
                      <a className="num" style={{ fontSize: 13 }} href={`${BLOB}/tests/compile_fail/${id}/src/lib.fe`}>
                        {id}
                      </a>
                    </td>
                    <td>{c.mechanism}</td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>
                      {c.observed.error_code}
                    </td>
                    <td>
                      <Status holds={c.observed.twin.ok} yes="passes" no="fails" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="ink2" style={{ marginTop: 16 }}>
          Also: {unit.summary.ok} of {unit.summary.cases} unit suites pass on the EVM and natively, and {probes.summary.ok}{" "}
          of {probes.summary.cases} language probes reproduce their recorded diagnostics and bytecode hashes. Run any case
          live with <code>make show CASE=&lt;name&gt;</code>.
        </p>
      </Section>
    </>
  );
}
