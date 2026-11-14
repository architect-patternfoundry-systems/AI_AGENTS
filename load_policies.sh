#!/bin/bash

# AI_AGENTS Policy Loader
# Automatically loads and applies AI agent governance policies based on context
# Version: 2.0.0

set -euo pipefail

# --- CONFIGURATION ---
AI_AGENTS_ROOT="/home/cortex/workspace/AI_AGENTS"
WORKSPACE_ROOT="/home/cortex/workspace"
CURRENT_DIR="$(pwd)"
CACHE_DIR="/tmp/ai_agents_cache"
CACHE_TTL=3600  # 1 hour cache

# --- COLORS ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- CONTEXT DETECTION ---
detect_context() {
    log_info "Detecting operational context..."
    
    # Detect repository
    if git rev-parse --git-dir > /dev/null 2>&1; then
        REPO_ROOT=$(git rev-parse --show-toplevel)
        REPO_NAME=$(basename "$REPO_ROOT")
        log_debug "Repository detected: $REPO_NAME"
    else
        REPO_ROOT=""
        REPO_NAME="no-repo"
        log_debug "No git repository detected"
    fi
    
    # Detect technology stack
    TECH_STACK=()
    if [ -f "package.json" ]; then
        TECH_STACK+=("nodejs")
        if grep -q '"next"' package.json 2>/dev/null; then
            TECH_STACK+=("nextjs")
        fi
    fi
    if [ -f "go.mod" ]; then
        TECH_STACK+=("golang")
        if [ -f "Project.mk" ] || grep -q "kubebuilder" go.mod 2>/dev/null; then
            TECH_STACK+=("kubebuilder")
        fi
    fi
    if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
        TECH_STACK+=("python")
    fi
    if [ -f "Chart.yaml" ] || [ -f "flux-system" ]; then
        TECH_STACK+=("kubernetes")
        TECH_STACK+=("flux")
    fi
    if [ -f "Dockerfile" ] || [ -f "docker-compose.yml" ]; then
        TECH_STACK+=("docker")
    fi
    
    log_debug "Technology stack detected: ${TECH_STACK[*]:-none}"
    
    # Detect workspace context
    if [[ "$CURRENT_DIR" == "$WORKSPACE_ROOT"* ]]; then
        WORKSPACE_CONTEXT="workspace"
        log_debug "Workspace context detected"
    else
        WORKSPACE_CONTEXT="external"
        log_debug "External context detected"
    fi
}

# --- POLICY LOADING ---
load_global_policies() {
    log_info "Loading global governance policies..."
    
    local global_policies=()
    
    # Infrastructure standards
    if [ -f "$AI_AGENTS_ROOT/global/infrastructure.md" ]; then
        global_policies+=("$AI_AGENTS_ROOT/global/infrastructure.md")
        log_debug "  + Infrastructure standards"
    fi
    
    # Operations standards
    if [ -f "$AI_AGENTS_ROOT/global/operations.md" ]; then
        global_policies+=("$AI_AGENTS_ROOT/global/operations.md")
        log_debug "  + Operations standards"
    fi
    
    # Security standards
    if [ -f "$AI_AGENTS_ROOT/global/security.md" ]; then
        global_policies+=("$AI_AGENTS_ROOT/global/security.md")
        log_debug "  + Security standards"
    fi
    
    # ADRs
    if [ -d "$AI_AGENTS_ROOT/global/adr" ]; then
        for adr in "$AI_AGENTS_ROOT/global/adr"/*.md; do
            if [ -f "$adr" ]; then
                global_policies+=("$adr")
            fi
        done
        log_debug "  + Architectural decisions (ADRs)"
    fi
    
    echo "${global_policies[@]}"
}

load_domain_policies() {
    log_info "Loading domain-specific policies..."
    
    local domain_policies=()
    
    for tech in "${TECH_STACK[@]}"; do
        case "$tech" in
            nextjs)
                if [ -f "$AI_AGENTS_ROOT/domains/nextjs/rules.md" ]; then
                    domain_policies+=("$AI_AGENTS_ROOT/domains/nextjs/rules.md")
                    log_debug "  + Next.js rules"
                fi
                ;;
            kubebuilder)
                if [ -f "$AI_AGENTS_ROOT/domains/kubernetes/kubebuilder.md" ]; then
                    domain_policies+=("$AI_AGENTS_ROOT/domains/kubernetes/kubebuilder.md")
                    log_debug "  + Kubebuilder rules"
                fi
                ;;
            python)
                if [ -f "$AI_AGENTS_ROOT/domains/python/rules.md" ]; then
                    domain_policies+=("$AI_AGENTS_ROOT/domains/python/rules.md")
                    log_debug "  + Python rules"
                fi
                ;;
            flux)
                if [ -f "$AI_AGENTS_ROOT/domains/infrastructure/flux.md" ]; then
                    domain_policies+=("$AI_AGENTS_ROOT/domains/infrastructure/flux.md")
                    log_debug "  + Flux rules"
                fi
                ;;
            kubernetes)
                if [ -f "$AI_AGENTS_ROOT/domains/kubernetes/general.md" ]; then
                    domain_policies+=("$AI_AGENTS_ROOT/domains/kubernetes/general.md")
                    log_debug "  + Kubernetes general rules"
                fi
                ;;
        esac
    done
    
    echo "${domain_policies[@]}"
}

load_context_policies() {
    log_info "Loading context-specific policies..."
    
    local context_policies=()
    
    # Workspace overrides
    if [ -f "$AI_AGENTS_ROOT/context/workspace/overrides.md" ]; then
        context_policies+=("$AI_AGENTS_ROOT/context/workspace/overrides.md")
        log_debug "  + Workspace overrides"
    fi
    
    # Repository-specific overrides
    if [ -n "$REPO_NAME" ] && [ -d "$AI_AGENTS_ROOT/context/repositories/$REPO_NAME" ]; then
        for policy in "$AI_AGENTS_ROOT/context/repositories/$REPO_NAME"/*.md; do
            if [ -f "$policy" ]; then
                context_policies+=("$policy")
            fi
        done
        log_debug "  + Repository-specific overrides ($REPO_NAME)"
    fi
    
    # Local AGENTS.md
    if [ -f "$REPO_ROOT/AGENTS.md" ]; then
        context_policies+=("$REPO_ROOT/AGENTS.md")
        log_debug "  + Local AGENTS.md"
    fi
    
    echo "${context_policies[@]}"
}

# --- POLICY COMPILATION ---
compile_policies() {
    log_info "Compiling policy hierarchy..."
    
    local cache_key="$REPO_NAME-${TECH_STACK[*]:-none}-$WORKSPACE_CONTEXT"
    local cache_file="$CACHE_DIR/$cache_key.json"
    
    # Check cache
    if [ -f "$cache_file" ]; then
        local cache_age=$(($(date +%s) - $(stat -c %Y "$cache_file")))
        if [ $cache_age -lt $CACHE_TTL ]; then
            log_info "Using cached policies (age: ${cache_age}s)"
            cat "$cache_file"
            return 0
        fi
    fi
    
    # Load policies in priority order
    local policies=()
    
    # 1. Global governance (lowest priority)
    policies+=("GLOBAL:$(load_global_policies)")
    
    # 2. Domain-specific rules
    policies+=("DOMAIN:$(load_domain_policies)")
    
    # 3. Context overrides
    policies+=("CONTEXT:$(load_context_policies)")
    
    # Create cache directory
    mkdir -p "$CACHE_DIR"
    
    # Compile to JSON
    echo "{"
    echo "  \"context\": {"
    echo "    \"repo_name\": \"$REPO_NAME\","
    echo "    \"repo_root\": \"$REPO_ROOT\","
    echo "    \"tech_stack\": [$(printf '"%s",' "${TECH_STACK[@]}" | sed 's/,$//')],"
    echo "    \"workspace_context\": \"$WORKSPACE_CONTEXT\","
    echo "    \"current_dir\": \"$CURRENT_DIR\""
    echo "  },"
    echo "  \"policies\": {"
    echo "    \"global\": [$(printf '"%s",' $(load_global_policies) | sed 's/,$//')],"
    echo "    \"domain\": [$(printf '"%s",' $(load_domain_policies) | sed 's/,$//')],"
    echo "    \"context\": [$(printf '"%s",' $(load_context_policies) | sed 's/,$//')]"
    echo "  },"
    echo "  \"priority_order\": [\"context\", \"domain\", \"global\"],"
    echo "  \"cache_timestamp\": $(date +%s)"
    echo "}" > "$cache_file"
    
    log_info "Policies compiled and cached"
    cat "$cache_file"
}

# --- POLICY VALIDATION ---
validate_policies() {
    log_info "Validating policy integrity..."
    
    local policy_count=0
    local missing_count=0
    
    # Check if AI_AGENTS root exists
    if [ ! -d "$AI_AGENTS_ROOT" ]; then
        log_error "AI_AGENTS root not found: $AI_AGENTS_ROOT"
        return 1
    fi
    
    # Check global policies
    if [ ! -f "$AI_AGENTS_ROOT/global/infrastructure.md" ]; then
        log_warn "Missing global infrastructure policy"
        missing_count=$((missing_count + 1))
    else
        policy_count=$((policy_count + 1))
    fi
    
    if [ ! -f "$AI_AGENTS_ROOT/global/operations.md" ]; then
        log_warn "Missing global operations policy"
        missing_count=$((missing_count + 1))
    else
        policy_count=$((policy_count + 1))
    fi
    
    if [ ! -f "$AI_AGENTS_ROOT/global/security.md" ]; then
        log_warn "Missing global security policy"
        missing_count=$((missing_count + 1))
    else
        policy_count=$((policy_count + 1))
    fi
    
    log_info "Policy validation complete: $policy_count policies loaded, $missing_count missing"
    
    return 0
}

# --- POLICY EXPORT ---
export_for_agent() {
    log_info "Exporting policies for agent consumption..."
    
    local policy_file
    policy_file=$(compile_policies)
    
    # Set environment variables for agent
    export AI_AGENTS_POLICIES_LOADED="true"
    export AI_AGENTS_POLICY_FILE="$policy_file"
    export AI_AGENTS_CONTEXT="$WORKSPACE_CONTEXT"
    export AI_AGENTS_REPO="$REPO_NAME"
    export AI_AGENTS_TECH_STACK="${TECH_STACK[*]:-none}"
    
    log_info "Policies exported to environment variables"
    log_debug "  AI_AGENTS_POLICIES_LOADED=$AI_AGENTS_POLICIES_LOADED"
    log_debug "  AI_AGENTS_POLICY_FILE=$AI_AGENTS_POLICY_FILE"
    log_debug "  AI_AGENTS_CONTEXT=$AI_AGENTS_CONTEXT"
    log_debug "  AI_AGENTS_REPO=$AI_AGENTS_REPO"
    log_debug "  AI_AGENTS_TECH_STACK=$AI_AGENTS_TECH_STACK"
}

# --- MAIN ---
main() {
    echo "🤖 AI_AGENTS Policy Loader v2.0.0"
    echo "=================================="
    echo ""
    
    # Detect context
    detect_context
    echo ""
    
    # Validate policies
    validate_policies
    echo ""
    
    # Compile and export
    export_for_agent
    echo ""
    
    log_info "Policy loading complete"
    echo ""
    echo "Active policy hierarchy (highest to lowest priority):"
    echo "  1. Repository-specific AGENTS.md"
    echo "  2. Repository-specific context override"
    echo "  3. Workspace context override"
    echo "  4. Domain-specific rules"
    echo "  5. Global governance"
    echo ""
    
    # Output policy file path for agent parsing
    local policy_file
    policy_file=$(compile_policies)
    echo "Policy file: $policy_file"
}

# Run main function
main "$@"