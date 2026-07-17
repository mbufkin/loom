# Security

Loom is **source-available** under the [PolyForm Noncommercial License 1.0.0](LICENSE).

## Reporting a vulnerability

Please **do not** open a public issue for security-sensitive reports.

Email the maintainer via the contact on your GitHub profile for [mbufkin](https://github.com/mbufkin), or open a private security advisory on this repository if available.

Include:

- Affected commit or tag
- Impact description
- Reproduction steps (no private curriculum attachments unless necessary)

## Scope notes

- Loom runs local model endpoints you configure; treat `config.yaml` as secret and never commit it.
- Curriculum corpora under `projects/*/sources/` are operator data — do not file them in issues.
