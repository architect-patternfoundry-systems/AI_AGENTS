# Cloudflare Access and ACL Governance Policy

## Purpose

This policy enforces coordinated migration requirements for Cloudflare Access and ACL changes to prevent half-migrated states and ensure operational safety. It encodes the operational truth from ACL_ACCESS_STRATEGY_BASELINE.md and ACL_AND_ACCESS_OWNERSHIP.md.

## Policy Statement

Cloudflare Access changes must follow coordinated migration with validation gates as defined in ACL_ACCESS_STRATEGY_BASELINE.md. No Access boundary change, DNS mutation, or OpenTofu apply is permitted unless the ownership table is current, validation gates are complete, and documentation agrees with Cloudflare state.

## Required Migration Sequence

### Step 1: Ownership Table Reconciliation
**Requirement**: Before any Access boundary change, the ownership table must be current and validated.

**Prerequisites**:
- Run discovery script to generate current ownership table
- Verify ownership table matches Cloudflare state
- Document any conflicts or discrepancies
- Update ownership table with current state

**Validation Gates**:
- All hostnames have valid DNS record IDs
- All hostnames have valid Access application IDs  
- No conflicts marked in ownership table
- Ownership table timestamp is recent (< 24 hours)

**Enforcement**: Block any Access boundary change if ownership table is stale or contains conflicts.

### Step 2: Access Boundary Definition
**Requirement**: Access boundary changes must be validated before proceeding to DNS mutation.

**Prerequisites**:
- Update canvas Access application domain to `*-canvas.patternfoundry.systems`
- Create signal Access application with `*-signal.patternfoundry.systems`
- Copy or create appropriate policies for both applications
- Validate new boundary state in Cloudflare

**Validation Gates**:
- Canvas app domain matches `*-canvas.patternfoundry.systems`
- Signal app exists with domain `*-signal.patternfoundry.systems`
- Both applications have appropriate policies
- Policy ownership is explicit for both apps
- No duplicate Access applications for same hostnames

**Enforcement**: Block DNS mutation until Access boundary validation is complete.

### Step 3: Import/Reconciliation
**Requirement**: Existing Cloudflare resources must be imported into OpenTofu state before declarative management.

**Prerequisites**:
- Import existing Access applications
- Import existing Access policies
- Import existing DNS records
- Import existing tunnel-route mappings
- Resolve any import conflicts

**Validation Gates**:
- All Access applications imported successfully
- All Access policies imported successfully
- All DNS records imported successfully
- No 409 conflicts during import
- OpenTofu state matches Cloudflare state

**Enforcement**: Block OpenTofu apply until import/reconciliation is complete.

### Step 4: DNS Mutation
**Requirement**: DNS changes must only occur after Access state and documentation agree.

**Prerequisites**:
- Access boundary changes validated
- Import/reconciliation complete
- Documentation updated to reflect new state
- Ownership table updated with new Access application IDs

**Validation Gates**:
- Documentation Access application IDs match Cloudflare state
- Ownership table reflects current state
- No half-migrated state (docs ≠ Cloudflare state)
- DNS record targets match intended tunnel

**Enforcement**: Block DNS mutation if documentation and Cloudflare state disagree.

## Prohibited Operations

### Half-Migrated States
- **Prohibited**: Any operation that creates a state where documentation says one thing and Cloudflare state reflects another
- **Detection**: Compare documentation Access application IDs with Cloudflare state
- **Enforcement**: Block operation and require state reconciliation

### Independent DNS Changes
- **Prohibited**: DNS record changes without corresponding Access boundary validation
- **Detection**: Check for DNS mutations without Access boundary validation completion
- **Enforcement**: Block DNS changes and require Access boundary validation first

### OpenTofu Apply Without Import
- **Prohibited**: OpenTofu apply operations without prior import/reconciliation of existing resources
- **Detection**: Check for OpenTofu apply without import state validation
- **Enforcement**: Block apply and require import/reconciliation first

### Signal Split Without Canvas Validation
- **Prohibited**: Creating signal Access application without validating canvas boundary change
- **Detection**: Check for signal app creation without canvas boundary validation
- **Enforcement**: Block signal split and require canvas validation first

## Enforcement Mechanisms

### Pre-Operation Validation
Before any Cloudflare Access operation, the system must:

1. **Check Ownership Table Freshness**
   ```python
   def validate_ownership_table_freshness():
       ownership_table = load_ownership_table()
       table_age = datetime.now() - ownership_table['timestamp']
       if table_age > timedelta(hours=24):
           raise PolicyViolation("Ownership table is stale (>24 hours old)")
   ```

2. **Validate No Conflicts**
   ```python
   def validate_no_conflicts():
       ownership_table = load_ownership_table()
       conflicts = [entry for entry in ownership_table if entry['status'] == 'CONFLICT']
       if conflicts:
           raise PolicyViolation(f"Ownership table contains {len(conflicts)} conflicts")
   ```

3. **Check Documentation Alignment**
   ```python
   def validate_documentation_alignment():
       docs_state = get_documented_access_state()
       cloudflare_state = get_cloudflare_access_state()
       if docs_state != cloudflare_state:
           raise PolicyViolation("Documentation and Cloudflare state disagree")
   ```

### Operation Blocking
The system must block operations that violate policy:

```python
def enforce_acl_policy(operation_type, operation_details):
    if operation_type == "access_boundary_change":
        validate_ownership_table_freshness()
        validate_no_conflicts()
        validate_documentation_alignment()
    elif operation_type == "dns_mutation":
        validate_access_boundary_validated()
        validate_import_reconciliation_complete()
        validate_documentation_alignment()
    elif operation_type == "opentofu_apply":
        validate_import_reconciliation_complete()
        validate_no_half_migrated_state()
```

## Compliance Checks

### Pre-Migration Check
Before any ACL migration, verify:
- [ ] Ownership table is current (< 24 hours old)
- [ ] No conflicts in ownership table
- [ ] Documentation matches Cloudflare state
- [ ] Import/reconciliation plan exists
- [ ] Validation gates defined

### Post-Step Validation
After each migration step, verify:
- [ ] Documentation updated with new state
- [ ] Ownership table updated with new state
- [ ] No half-migrated state created
- [ ] Next step prerequisites met

### Final Validation
After complete migration, verify:
- [ ] All validation gates passed
- [ ] Documentation matches final Cloudflare state
- [ ] Ownership table matches final state
- [ ] No orphaned resources
- [ ] Services functioning correctly

## Exception Handling

### Policy Violations
When a policy violation is detected:
1. Block the operation immediately
2. Log the violation with context
3. Provide specific remediation steps
4. Require manual override with justification

### Manual Override Process
For emergency situations requiring policy bypass:
1. Document the specific policy violation
2. Provide business justification for override
3. Implement temporary compensating controls
4. Schedule remediation within 24 hours
5. Require post-incident review

## Integration Points

### ACL Baseline Document
This policy enforces the coordinated change set defined in ACL_ACCESS_STRATEGY_BASELINE.md:
- Boundary narrowing and signal split-out as atomic operation
- Import/reconciliation before OpenTofu management
- Validation gates between each step
- Documentation alignment throughout

### Configuration Authority Matrix
This policy enforces mode isolation from CONFIGURATION_AUTHORITY_MATRIX.md:
- Dev and prod tunnel identities remain separate
- Access boundaries respect mode isolation
- No cross-mode configuration pollution

### Ownership Table
This policy requires the ownership table from ACL_AND_ACCESS_OWNERSHIP.md:
- Current state awareness before changes
- Conflict detection and resolution
- Import reconciliation guidance

## Monitoring and Alerting

### Policy Violation Alerts
Alert immediately on:
- Attempted operation without ownership table validation
- DNS mutation without Access boundary validation
- OpenTofu apply without import reconciliation
- Half-migrated state detected

### Compliance Metrics
Track:
- Policy compliance rate (should be 100%)
- Average time to resolve policy violations
- Number of manual overrides required
- Half-migrated state incidents

## Version History

- **v1.0.0** (2026-07-27): Initial policy based on ACL_ACCESS_STRATEGY_BASELINE.md
- **Source Documents**: ACL_ACCESS_STRATEGY_BASELINE.md, ACL_AND_ACCESS_OWNERSHIP.md, CONFIGURATION_AUTHORITY_MATRIX.md

## Validation

This policy is immediately testable against:
- Current ACL orchestration script (`orchestrate_access_boundary_step1.py`)
- Ownership table workflow (`discover_access_resources.py`)
- OpenTofu configuration in `/home/cortex/workspace/infrastructure_check/opentofu/cloudflare/envs/dev-host/`

## Related Policies

- **OpenTofu Import/Reconciliation Governance**: Required before OpenTofu management
- **Security Standards**: Required checks for credential management
- **Infrastructure Standards**: NFS paths, connectivity requirements