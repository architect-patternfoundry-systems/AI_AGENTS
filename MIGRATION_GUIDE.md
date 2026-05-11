# AGENTS.md Migration Guide

This guide explains how to migrate from scattered AGENTS.md files to the new hierarchical AI_AGENTS governance system.

## Current State Analysis

### Existing AGENTS.md Files
1. **`/home/cortex/workspace/AGENTS.md`** (293 lines) - Workspace-level governance
   - Should be migrated to AI_AGENTS/global/
   - Split into infrastructure.md, operations.md, security.md
   - ADRs moved to global/adr/

2. **`/home/cortex/workspace/application/apps/toneroot/web/frontend/AGENTS.md`** (5 lines) - Next.js-specific
   - Already covered by AI_AGENTS/domains/nextjs/rules.md
   - Can be replaced with reference to AI_AGENTS

3. **`/home/cortex/workspace/application/story-controller/AGENTS.md`** (285 lines) - Kubebuilder-specific
   - Already covered by AI_AGENTS/domains/kubernetes/kubebuilder.md
   - Can be replaced with reference to AI_AGENTS

4. **`/home/cortex/workspace/mediastore-operator/apps/sovereignty-dash/AGENTS.md`** (5 lines) - Duplicate Next.js rules
   - Duplicate of #2, can be removed
   - Replace with reference to AI_AGENTS

## Migration Strategy

### Phase 1: Establish AI_AGENTS Repository ✅
- [x] Create AI_AGENTS repository with hierarchical structure
- [x] Migrate global governance to AI_AGENTS/global/
- [x] Extract domain patterns to AI_AGENTS/domains/
- [x] Create context override structure
- [x] Push to GitHub

### Phase 2: Update Repository AGENTS.md Files
Replace existing AGENTS.md files with references to AI_AGENTS:

#### For Workspace AGENTS.md
```markdown
# AI Agent Governance

This workspace uses the centralized AI_AGENTS governance system.

## Governance Source
- Repository: https://github.com/architect-patternfoundry-systems/AI_AGENTS
- Local path: /home/cortex/workspace/AI_AGENTS

## Quick Links
- [Global Infrastructure](AI_AGENTS/global/infrastructure.md)
- [Global Operations](AI_AGENTS/global/operations.md)
- [Global Security](AI_AGENTS/global/security.md)
- [ADR-013: Drop-Folder Worker](AI_AGENTS/global/adr/ADR-013-drop-folder-worker.md)
- [ADR-014: Ingestion Gateway](AI_AGENTS/global/adr/ADR-014-ingestion-gateway.md)

## Repository-Specific Overrides
See AI_AGENTS/context/workspace/overrides.md for workspace-specific policies.

## Domain-Specific Rules
Domain-specific rules are loaded automatically based on detected technology stack.
See AI_AGENTS/domains/ for available domain patterns.
```

#### For Next.js Projects
```markdown
# AI Agent Governance - Next.js

This project uses Next.js-specific rules from the centralized AI_AGENTS system.

## Next.js Rules
See: [AI_AGENTS/domains/nextjs/rules.md](../../../../../AI_AGENTS/domains/nextjs/rules.md)

## Global Governance
See: [AI_AGENTS/global/](../../../../../AI_AGENTS/global/)
```

#### For Kubebuilder Projects
```markdown
# AI Agent Governance - Kubebuilder

This project uses Kubebuilder-specific rules from the centralized AI_AGENTS system.

## Kubebuilder Rules
See: [AI_AGENTS/domains/kubernetes/kubebuilder.md](../../../../../AI_AGENTS/domains/kubernetes/kubebuilder.md)

## Global Governance
See: [AI_AGENTS/global/](../../../../../AI_AGENTS/global/)
```

### Phase 3: Agent Integration
Update agent loading logic to use hierarchical system:

```python
def load_agent_rules(work_dir: str) -> dict:
    rules = {}

    # 1. Load global governance
    ai_agents_path = find_ai_agents_path(work_dir)
    if ai_agents_path:
        rules.update(load_from_path(f"{ai_agents_path}/global/"))

        # 2. Detect and load domain rules
        if has_nextjs(work_dir):
            rules.update(load_from_path(f"{ai_agents_path}/domains/nextjs/"))
        if has_kubebuilder(work_dir):
            rules.update(load_from_path(f"{ai_agents_path}/domains/kubernetes/kubebuilder.md"))

        # 3. Load context overrides
        rules.update(load_from_path(f"{ai_agents_path}/context/workspace/"))

        # 4. Load repository-specific overrides
        repo_name = get_repo_name(work_dir)
        repo_override = f"{ai_agents_path}/context/repositories/{repo_name}.md"
        if os.path.exists(repo_override):
            rules.update(load_from_path(repo_override))

    # 5. Load repository-specific rules (local AGENTS.md)
    local_agents = find_local_agents_md(work_dir)
    if local_agents:
        rules.update(load_from_path(local_agents))

    return rules
```

### Phase 4: Deprecate Duplicate Content
- Remove duplicate Next.js rules from sovereignty-dash
- Consolidate any repository-specific rules into AI_AGENTS context
- Update all references to point to AI_AGENTS

### Phase 5: Establish Review Process
- Create PR template for governance changes
- Define approval requirements for different rule types
- Set up automated checks for rule consistency
- Document change management process

## Rule Priority

When rules conflict, apply in this order (highest to lowest priority):

1. Repository-specific AGENTS.md (local override)
2. Repository-specific context override (AI_AGENTS/context/repositories/{repo}.md)
3. Workspace context override (AI_AGENTS/context/workspace/overrides.md)
4. Domain-specific rules (AI_AGENTS/domains/)
5. Global governance (AI_AGENTS/global/)

## Benefits of New System

### For Agents
- **Context-aware loading**: Rules loaded based on working directory
- **No duplication**: Single source of truth for common patterns
- **Easy maintenance**: Update once, apply everywhere
- **Clear hierarchy**: Understand rule priority and overrides

### For Developers
- **Version control**: Governance changes tracked in git
- **Collaboration**: PR-based review process
- **Documentation**: Centralized, searchable documentation
- **Consistency**: Standards applied consistently across projects

### For Operations
- **Audit trail**: Clear history of governance changes
- **Rollback**: Revert governance changes if needed
- **Compliance**: Easier to demonstrate compliance with standards
- **Onboarding**: New team members understand standards quickly

## Testing Migration

1. **Test in one repository first** (e.g., story-controller)
2. **Verify agent loads rules correctly**
3. **Check for missing or conflicting rules**
4. **Validate agent behavior with new rules**
5. **Roll out to other repositories incrementally**

## Rollback Plan

If issues arise:
1. Restore original AGENTS.md files from git
2. Revert agent loading logic changes
3. Document issues and root cause
4. Fix issues in AI_AGENTS
5. Retry migration

## Next Steps

1. ✅ AI_AGENTS repository created and pushed
2. ⏳ Update workspace AGENTS.md with reference to AI_AGENTS
3. ⏳ Update repository AGENTS.md files with references
4. ⏳ Implement agent loading logic changes
5. ⏳ Test migration in one repository
6. ⏳ Roll out to all repositories
7. ⏳ Deprecate duplicate content
8. ⏳ Establish review process