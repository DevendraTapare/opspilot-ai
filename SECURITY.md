# Security policy and scope

OpsPilot is a local fictional incident lab. No production/cloud action tool is
implemented. Do not expose the current Compose or host APIs directly to the internet.
Read the [threat model](docs/THREAT_MODEL.md), [approval boundaries](docs/APPROVAL_SECURITY.md)
and [deployment prerequisites](docs/DEPLOYMENT_ARCHITECTURE.md).

For a vulnerability, contact the repository owner privately. If GitHub private
vulnerability reporting is enabled after publication, use it; otherwise use a
private contact listed by the owner. No reporting endpoint/address is invented
here. Do not put credentials, private logs or working exploit authority in a public
issue. Reproduce only in isolated local fixtures with synthetic identities.

No general prompt-injection resistance or production security certification is
claimed. Real-model behavior is unverified. Preserve evidence of failed controls
and never weaken authorization, quotas, fingerprints or expiry to make a demo pass.
