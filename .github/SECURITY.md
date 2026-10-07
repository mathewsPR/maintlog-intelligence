# Security policy: Maintlog Intelligence

This policy covers maintlog-intelligence. Other projects may have their own policies.

## Private reports

Use GitHub's private "Report a vulnerability" option at:
https://github.com/mathewsPR/maintlog-intelligence/security/advisories

**Setup pending:** the chat does not confirm that private vulnerability reporting
is enabled. The administrator must enable and verify this route before describing
it as operational. Until then, no private reporting channel is established here.
Do not put sensitive vulnerability details, credentials, or records in public issues.

Include the affected version or commit, a synthetic reproduction, expected and
observed behavior, and likely impact. Share only the data needed to reproduce it.
The maintainer assesses reports and coordinates fixes and disclosure. There is no
promised response time. Experimental development supports the latest main branch.

## Boundaries

Maintenance narratives and model replies are untrusted input. Source validation
does not establish semantic correctness. Reports can contain sensitive records.
The application does not approve equipment operation or control equipment.
Keep the local model endpoint on loopback and do not expose it publicly.

The current local backend needs no cloud key. Future credentials belong in
environment variables or a secret manager; workflows use GitHub Secrets.
Never write keys into source, example files, reports, or logs. Revoke exposed keys.

CI scans runtime source with Bandit and installed dependencies with pip-audit.
These checks detect some known risks; they do not certify the software as secure.
