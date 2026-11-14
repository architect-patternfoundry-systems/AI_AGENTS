# ADR-022: SMB-First Authentication Strategy

## Status
Accepted

## Context
The ecosystem-auth library provides multi-tenant OIDC authentication for ToneRoot and future PatternFoundry applications. The initial implementation supports both local session auth and OIDC federation. The question is: what should the **default** auth mode be for a fresh deployment?

Enterprise SaaS products typically assume customers have an identity provider (Okta, Azure AD, Google Workspace) and make OIDC/SAML a prerequisite. This assumption does not hold for SMBs, which are the primary early adopters of ToneRoot:

- Many SMBs do not have a cloud identity provider.
- Requiring external IdP configuration creates friction at first use.
- SMBs buy on immediate value, not governance capability.
- Enterprise buyers can layer in SSO later; SMBs cannot easily adopt a product that requires it upfront.

## Decision
The platform adopts a **tiered auth model** where local auth is the default and OIDC is an optional enhancement. The tiers are:

### Tier 1: Turnkey Local Auth (Default)
- Email/password or session-based auth works out of the box.
- Single default tenant auto-created on first install.
- No external IdP required.
- `/api/auth/me` returns `auth_mode: "local"`, `oidc_enabled: false`.
- This is the zero-configuration path. The app is fully usable without any identity plumbing.

### Tier 2: Optional OIDC SSO
- For SMBs that already have Google Workspace, Microsoft 365, or another provider.
- Guided setup adds provider config only when the customer explicitly enables it.
- Local admin accounts continue to work alongside OIDC users.
- A local admin can remain on local auth even when OIDC is enabled for other users.
- `/api/auth/me` returns `auth_mode: "local"` or `"oidc"` per user, `oidc_enabled: true`.

### Tier 3: Enterprise Federation
- For orgs with Okta, Azure AD, Keycloak, or custom SAML/OIDC providers.
- Per-tenant OIDC config with attribute mapping.
- Governance: audit logging, user provisioning policies, role mapping.
- May enforce OIDC-only auth (disable local password) via tenant policy.

### Design Rules
1. **Fresh install = Tier 1.** No OIDC config required, no external dependencies.
2. **OIDC is additive, never subtractive.** Enabling OIDC does not disable local auth unless explicitly configured by a Tier 3 tenant policy.
3. **Local admin survives OIDC enablement.** At least one local admin account must always be able to authenticate, preventing lockout if the IdP goes down.
4. **The UI presents OIDC as "optional SSO"**, not as a required enterprise gate.
5. **No cloud identity bill for Tier 1.** The product must never require a third-party identity service to function at its default tier.

## Consequences
- **Positive:** Fastest path to adoption for SMBs. No identity prerequisite.
- **Positive:** Enterprise buyers are not blocked; they configure Tier 2/3 when ready.
- **Positive:** Resilience — local admin fallback survives IdP outages.
- **Negative/Constraint:** Must maintain and test two auth paths (local + OIDC) indefinitely.
- **Negative/Constraint:** Tier 3 governance features (audit, provisioning policies) are deferred and should not block Tier 1/2 usability.

## Implementation Status

### Verified (2026-07-01)
- Fresh install defaults to local auth: ✅
- `/api/auth/me` returns correct Tier 1 context: ✅ (`auth_mode: "local"`, `oidc_enabled: false`)
- OIDC middleware skips cleanly when no provider configured: ✅
- Existing user sessions survive migration 0036: ✅
- ecosystem-auth Tilt integration operational (17/17 tests): ✅

### Remaining
- Tier 2: Guided OIDC setup UI (admin panel)
- Tier 2: Test with Google Workspace and Microsoft 365
- Tier 3: Per-tenant OIDC policy enforcement
- Tier 3: Audit logging for auth events
