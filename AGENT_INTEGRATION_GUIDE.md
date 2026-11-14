# AI_AGENTS Policy Loading Guide for AI Agents

## 🤖 Overview

This guide explains how AI agents can use the improved AI_AGENTS policy loading mechanism to automatically load and apply governance policies based on operational context.

## 🚀 Quick Start

### **For AI Agents (Simple Integration)**

```python
import sys
from pathlib import Path

# Add AI_AGENTS to path
ai_agents_path = Path("/home/cortex/workspace/AI_AGENTS")
sys.path.insert(0, str(ai_agents_path))

# Import the integration helper
from agent_integration import load_policies_for_agent, get_active_rules, check_compliance

# Load policies for current context
policy_data = load_policies_for_agent()

# Get active rules
rules = get_active_rules()

# Check compliance
compliance = check_compliance("all")
```

### **Command Line Usage**

```bash
# Load policies and show summary
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --load

# Get active rules
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --rules

# Check compliance
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --check infrastructure

# Output as JSON for programmatic use
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --load --json
```

## 🏗️ Architecture

### **Policy Loading Pipeline**

```
┌─────────────────┐
│  AI Agent       │
│  (Request)      │
└────────┬──────────┘
         │
         ▼
┌─────────────────┐
│  Agent          │
│  Integration    │
│  Helper         │
└────────┬──────────┘
         │
         ▼
┌─────────────────┐
│  Policy Loader  │
│  (Context Detect)│
└────────┬──────────┘
         │
         ▼
┌─────────────────┐
│  Policy Hierarchy│
│  (Priority Order)│
└────────┬──────────┘
         │
         ▼
┌─────────────────┐
│  Policy Cache   │
│  (Performance)  │
└────────┬──────────┘
         │
         ▼
┌─────────────────┐
│  Policy Output  │
│  (For Agent)    │
└─────────────────┘
```

### **Policy Priority (Highest to Lowest)**

1. **Repository-specific AGENTS.md** - Local override
2. **Repository-specific context override** - Repository policies
3. **Workspace context override** - Workspace-wide policies
4. **Domain-specific rules** - Technology-specific patterns
5. **Global governance** - Base standards

## 📋 Available Functions

### **load_policies_for_agent()**

Loads complete policy information for agent consumption.

**Returns:**
```python
{
    "status": "loaded" | "partial",
    "context": "/current/working/directory",
    "repository": "repo-name",
    "tech_stack": ["python", "docker"],
    "workspace_context": "workspace" | "external",
    "policy_summary": {
        "total_policies": 28,
        "by_level": {
            "global": 26,
            "domain": 0,
            "context": 2
        }
    },
    "applicable_policies": [
        "/path/to/policy1.md",
        "/path/to/policy2.md"
    ],
    "high_priority_content": {
        "/path/to/policy1.md": "content...",
        "/path/to/policy2.md": "content..."
    },
    "environment_variables": {
        "AI_AGENTS_POLICIES_LOADED": "true",
        "AI_AGENTS_CONTEXT": "workspace",
        "AI_AGENTS_REPO": "repo-name",
        "AI_AGENTS_TECH_STACK": "python,docker"
    }
}
```

### **get_active_rules()**

Gets active rules organized by category.

**Returns:**
```python
{
    "infrastructure": [
        {
            "source": "/path/to/infrastructure.md",
            "content": "policy content..."
        }
    ],
    "operations": [...],
    "security": [...],
    "domain_specific": [...],
    "context_overrides": [...]
}
```

### **check_compliance(rule_type)**

Checks compliance with specific rule type.

**Parameters:**
- `rule_type`: "infrastructure", "operations", "security", "domain", "context", "all"

**Returns:**
```python
{
    "compliant": True | False,
    "active_rules": {...},
    "recommendations": "guidance text"
}
```

## 🔧 Advanced Usage

### **Custom Policy Loading**

```python
from load_policies import PolicyLoader

# Create custom loader
loader = PolicyLoader(
    ai_agents_root="/custom/path/AI_AGENTS",
    workspace_root="/custom/path/workspace"
)

# Detect context
loader.detect_context()

# Validate policies
valid, issues = loader.validate_policies()

# Get specific policy content
content = loader.load_policy_content("/path/to/policy.md")

# Get policy summary
summary = loader.get_policy_summary()
```

### **Policy Caching**

The system automatically caches policies for 1 hour to improve performance:

```python
# Cache is handled automatically
# Cache location: /tmp/ai_agents_cache/
# Cache TTL: 1 hour (configurable)

# Force cache refresh
loader = PolicyLoader()
loader.cache_ttl = timedelta(seconds=0)  # Disable cache
```

### **Context-Specific Behavior**

```python
# Policies load differently based on context

# Workspace context
# - Loads workspace overrides
# - Loads repository-specific policies
# - Prioritizes local AGENTS.md

# External context
# - Loads global policies only
# - No workspace-specific overrides
# - Standard domain rules
```

## 🎯 Use Cases

### **Use Case 1: Code Generation**

```python
from agent_integration import load_policies_for_agent, check_compliance

def generate_code(task_description):
    # Load policies
    policies = load_policies_for_agent()
    
    # Check compliance before generating
    compliance = check_compliance("security")
    if not compliance["compliant"]:
        return "Error: Security compliance check failed"
    
    # Generate code following policies
    # ... code generation logic ...
    
    return generated_code
```

### **Use Case 2: Infrastructure Changes**

```python
from agent_integration import get_active_rules

def plan_infrastructure_change(change_description):
    # Get infrastructure rules
    rules = get_active_rules()
    infra_rules = rules["infrastructure"]
    
    # Validate change against rules
    for rule in infra_rules:
        if not validate_against_rule(change_description, rule):
            return f"Violation: {rule['source']}"
    
    return "Change compliant with infrastructure policies"
```

### **Use Case 3: Security Validation**

```python
from agent_integration import check_compliance

def validate_security_implementation(code):
    # Check security compliance
    compliance = check_compliance("security")
    
    if not compliance["compliant"]:
        return {
            "valid": False,
            "violations": compliance["active_rules"],
            "recommendations": compliance["recommendations"]
        }
    
    return {"valid": True}
```

## 🔍 Context Detection

The system automatically detects:

### **Repository Context**
- Git repository detection
- Repository name
- Repository root path

### **Technology Stack**
- **Node.js/Next.js**: package.json, Next.js dependencies
- **Go/Kubebuilder**: go.mod, Project.mk
- **Python**: requirements.txt, pyproject.toml, setup.py
- **Kubernetes/Flux**: Chart.yaml, flux-system
- **Docker**: Dockerfile, docker-compose.yml

### **Workspace Context**
- **Workspace**: Working within /home/cortex/workspace
- **External**: Working outside workspace

## 📊 Policy Output Formats

### **Human-Readable**
```bash
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --load
```

### **JSON Output**
```bash
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --load --json
```

### **Rule Categories**
```bash
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --rules
```

### **Compliance Check**
```bash
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --check security
```

## 🚨 Error Handling

### **Missing AI_AGENTS Directory**
```python
try:
    from agent_integration import load_policies_for_agent
    policies = load_policies_for_agent()
except Exception as e:
    print(f"Policy loading failed: {e}")
    # Fallback to standard behavior
```

### **Policy Validation Failures**
```python
policies = load_policies_for_agent()
if policies["status"] == "partial":
    print("Warning: Some policies failed to load")
    # Continue with available policies
```

### **Context Detection Issues**
```python
loader = PolicyLoader()
loader.detect_context()

if loader.repo_name == "no-repo":
    print("Not in a git repository, using global policies only")
```

## 🔄 Version Compatibility

### **Version 2.0.0 Features**
- ✅ Automatic context detection
- ✅ Intelligent caching
- ✅ Priority-based policy loading
- ✅ Multi-format output (human/JSON)
- ✅ Compliance checking
- ✅ Domain-specific rules
- ✅ Context overrides

### **Migration from Version 1.0**
- Old manual loading → New automatic detection
- Static policy lists → Dynamic context-aware loading
- Single format → Multiple output formats
- Manual priority → Automatic hierarchy

## 📝 Best Practices

### **For AI Agents**
1. **Always load policies** before making decisions
2. **Check compliance** before generating code or infrastructure
3. **Respect policy priority** (context > domain > global)
4. **Handle partial loads** gracefully
5. **Use caching** for performance in repeated operations

### **For Policy Authors**
1. **Use clear naming** for policy files
2. **Structure policies** with clear sections
3. **Include examples** in policy documents
4. **Keep policies** concise and actionable
5. **Version policy changes** for tracking

### **For System Integration**
1. **Cache policies** to improve performance
2. **Validate policies** before loading
3. **Log policy loading** for debugging
4. **Monitor cache hits** for optimization
5. **Handle errors** gracefully

## 🔧 Troubleshooting

### **Policies Not Loading**
```bash
# Check AI_AGENTS directory exists
ls -la /home/cortex/workspace/AI_AGENTS

# Validate policy integrity
python3 /home/cortex/workspace/AI_AGENTS/load_policies.py --validate

# Check cache
ls -la /tmp/ai_agents_cache/
```

### **Wrong Context Detected**
```python
# Force specific context
loader = PolicyLoader()
loader.repo_name = "specific-repo"
loader.tech_stack = ["python", "docker"]
```

### **Cache Issues**
```bash
# Clear cache
rm -rf /tmp/ai_agents_cache/

# Disable caching
loader.cache_ttl = timedelta(seconds=0)
```

## 🎯 Integration Examples

### **Example 1: Devin Integration**
```python
# At start of Devin session
from agent_integration import load_policies_for_agent

policies = load_policies_for_agent()
print(f"Loaded {policies['policy_summary']['total_policies']} policies")

# Before making changes
compliance = check_compliance("infrastructure")
if compliance["compliant"]:
    # Proceed with changes
    pass
```

### **Example 2: CI/CD Integration**
```bash
# In CI/CD pipeline
python3 /home/cortex/workspace/AI_AGENTS/agent_integration.py --check all --json > compliance_report.json

# Check exit code
if [ $? -ne 0 ]; then
    echo "Compliance check failed"
    exit 1
fi
```

### **Example 3: Development Environment**
```python
# In development tools
from agent_integration import get_active_rules

def pre_commit_check(files_changed):
    rules = get_active_rules()
    security_rules = rules["security"]
    
    for file in files_changed:
        if not check_file_against_rules(file, security_rules):
            return False
    
    return True
```

## 📚 Additional Resources

- **AI_AGENTS Repository**: `/home/cortex/workspace/AI_AGENTS`
- **Policy Documentation**: Individual policy files in AI_AGENTS directory
- **Migration Guide**: `AI_AGENTS/MIGRATION_GUIDE.md`
- **Architecture Decisions**: `AI_AGENTS/global/adr/`

---

**Version**: 2.0.0  
**Last Updated**: 2026-07-27  
**Maintained by**: AI Governance Team