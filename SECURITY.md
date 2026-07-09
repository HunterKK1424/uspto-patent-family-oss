# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue for a
vulnerability.

Email **hunterip0305@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce (please use public patent numbers only — no confidential data),
- the affected version (from the `patent_status` tool or `package.json`).

You can expect an acknowledgement on a best-effort basis. This is a small,
single-maintainer project, so please allow reasonable time for a response before any
public disclosure.

## Handling secrets

- Your `USPTO_API_KEY` is sent only to `api.uspto.gov` over HTTPS as the `x-api-key`
  header. The API base URL is hard-coded and cannot be redirected via environment
  variables.
- The key is redacted from **all** tool output (success and error paths) as defence in
  depth. Even so, **never paste your key or raw API response logs into an issue.**

## Supported versions

Only the latest release on `main` is supported.
