---
name: chatur-threat-model
description: Use when threat modelling a design with STRIDE — data flows, trust boundaries, threats, mitigations, accepted risks — before the design gate.
---

# Threat model (STRIDE)

Template: `assets/threat-model.md` (also `docs/templates/threat-model.md`).
Save as `docs/security/threat-model-<kebab-name>.md`.

## Steps
1. **Assets:** what is worth protecting (data classes, credentials, availability, money, reputation).
2. **Data flow:** a Mermaid diagram; mark every trust boundary (user↔service, service↔DB, third parties, CI).
3. **Threats:** for each component and each boundary-crossing flow, walk through
   Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege.
   Rate likelihood and impact (L/M/H).
4. **Mitigations:** a concrete control per threat, written as a testable security requirement
   (e.g. "all /admin routes require role=admin; 403 otherwise").
5. **Accepted risks:** owner plus justification; needs an ADR (ask chatur-architect).
6. **Verification:** how each mitigation will be tested (feeds the test plan).

## Common misses
Secrets in logs or CI output; missing rate limits; IDOR (object access without an ownership check);
SSRF in URL fetchers; deserialisation of untrusted input; overly broad CI tokens; dependency confusion.
