# Security policy

## Scope

judgeledger is an offline, local tool. It makes no network calls, runs no server and stores no
credentials. The security-relevant surface is small and deliberate:

- **the hash chain is not a signature.** It detects accidental or opportunistic edits to the two
  files; it does not stop someone with write access from rewriting the history consistently. See
  `docs/integridade.md` §4.
- **the ledger is personal data.** A real ledger may reveal what you expected and when. Keep it out
  of the public repository; `examples/` is synthetic.
- **no classified information, no personal data.** The tool is designed for unclassified material
  and synthetic fixtures. The demo ledger uses `example.org` URLs and fictional organisations.

## Reporting a vulnerability

Open a private security advisory on GitHub
(<https://github.com/luizhsbrandao/judgeledger/security/advisories/new>) or email
`intellecta.contact@proton.me`. Please do not open a public issue for a vulnerability.

Expect an acknowledgement within a week. This is a single-maintainer project: fixes are best-effort,
but a report that includes a reproduction (the ledger files plus the command) is far more likely to
be fixed quickly.

## Supported versions

The latest minor release. There are no long-term support branches.
