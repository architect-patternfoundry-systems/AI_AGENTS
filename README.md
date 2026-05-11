# AI_AGENTS - Governance for AI Agent Workflows

Centralized governance repository for AI agent rules, patterns, and architectural decisions across multi-repository workspaces.

## Purpose

This repository provides:
- **Global governance**: Cross-cutting infrastructure and operational standards
- **Architectural decisions**: ADRs for significant technical choices
- **Domain patterns**: Reusable patterns for specific technologies
- **Context-aware loading**: Agents load rules based on working directory context

## Structure

```
AI_AGENTS/
├── README.md                    # This file
├── global/                      # Layer 1: Global governance (applies everywhere)
│   ├── infrastructure.md        # NFS paths, security, deployment standards
│   ├── operations.md            # Monitoring, logging, alerting standards
│   ├── security.md              # Security policies and requirements
│   └── adr/                     # Architectural Decision Records
│       ├── ADR-013-drop-folder-worker.md
│       └── ADR-014-ingestion-gateway.md
├── domains/                     # Layer 2: Domain-specific patterns
│   ├── nextjs/                  # Next.js/React patterns
│   │   └── rules.md
│   ├── kubernetes/              # K8s operator patterns
│   │   └── kubebuilder.md
│   ├── python/                  # Python patterns
│   │   └── rules.md
│   └── infrastructure/          # Infrastructure as code patterns
│       └── flux.md
└── context/                     # Layer 3: Context-specific overrides
    ├── workspace/               # Workspace-level overrides
    │   └── overrides.md
    └── repositories/            # Repository-specific overrides
        └── example.md
```

## Agent Loading Strategy

Agents should load rules in this order:

1. **Load global rules** from `global/` directory
2. **Load domain rules** based on detected technology stack
3. **Load context overrides** based on working directory
4. **Apply repository-specific rules** if present in local AGENTS.md

### Example Loading Logic

```python
def load_agent_rules(work_dir: str) -> dict:
    rules = {}

    # 1. Load global governance
    rules.update(load_from_path("AI_AGENTS/global/"))

    # 2. Detect and load domain rules
    if has_nextjs(work_dir):
        rules.update(load_from_path("AI_AGENTS/domains/nextjs/"))
    if has_kubebuilder(work_dir):
        rules.update(load_from_path("AI_AGENTS/domains/kubernetes/kubebuilder.md"))

    # 3. Load context overrides
    rules.update(load_from_path("AI_AGENTS/context/"))

    # 4. Load repository-specific rules (local AGENTS.md)
    local_agents = find_local_agents_md(work_dir)
    if local_agents:
        rules.update(load_from_path(local_agents))

    return rules
```

## Rule Priority (Highest to Lowest)

1. Repository-specific AGENTS.md (local override)
2. Context overrides
3. Domain-specific rules
4. Global governance

## Usage

### For Workspace Setup

Clone this repository to your workspace root:

```bash
cd /home/cortex/workspace
git clone https://github.com/your-org/AI_AGENTS.git
```

### For Repository Integration

Each repository can reference this repository via:

1. **Git submodule** (recommended for tight coupling):
   ```bash
   git submodule add https://github.com/your-org/AI_AGENTS.git .ai-agents
   ```

2. **Symlink** (for development):
   ```bash
   ln -s /home/cortex/workspace/AI_AGENTS /path/to/repo/.ai-agents
   ```

3. **Configuration reference** (loose coupling):
   ```yaml
   # .ai-agents.yaml
   governance_repo: /home/cortex/workspace/AI_AGENTS
   ```

### For Agent Integration

Agents should look for `.ai-agents/` directory in the working directory or parent directories, then load rules according to the priority hierarchy.

## Contributing

- **Global rules**: Require review and consensus (affect all work)
- **Domain rules**: Require domain expert review
- **Context overrides**: Can be project-specific
- **ADRs**: Follow ADR template and require approval

## Migration Strategy

1. **Phase 1**: Create AI_AGENTS repository with current global governance
2. **Phase 2**: Extract domain patterns from existing AGENTS.md files
3. **Phase 3**: Update agents to use hierarchical loading
4. **Phase 4**: Deprecate duplicate AGENTS.md files
5. **Phase 5**: Establish review process for governance changes

## Related Repositories

- `infrastructure` - Infrastructure deployment and configuration
- `application` - Application source code (ToneRoot, StoryLoom)
- `storyloom` - StoryLoom web application
- `mediastore-operator` - Kubernetes operator for media storage