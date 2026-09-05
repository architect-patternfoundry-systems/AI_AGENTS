#!/usr/bin/env python3
"""
agent-invoke: Agent Invocation Control Plane CLI

Composes deterministic agent invocation prompts from versioned policy manifests.
Read-only context compiler — does not mutate Git, deploy, or contact live systems.

Usage:
    agent-invoke discover --repo /path/to/repo
    agent-invoke validate --repo neural_mesh_canvas
    agent-invoke compose --repo neural_mesh_canvas --agent antigravity-cli --task-file tasks/foo.yaml
    agent-invoke explain --repo neural_mesh_canvas
    agent-invoke doctor
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Constants───────────────────────────────────────────────────────────────

AI_AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = AI_AGENTS_ROOT / "policies"
PROFILES_DIR = AI_AGENTS_ROOT / "agent_profiles"
SCHEMAS_DIR = AI_AGENTS_ROOT / "schemas"
TEMPLATES_DIR = AI_AGENTS_ROOT / "templates"
TASKS_DIR = AI_AGENTS_ROOT / "tasks"
REPO_POLICIES_DIR = POLICIES_DIR / "repositories"

# ─── YAML loading (graceful fallback) ─────────────────────────────────────────

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Error: Jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    """Load a YAML file and return a dict."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def sha256_file(path: Path) -> str:
    """Compute SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def find_repo_context(repo_identifier: str) -> Path:
    """Find a repository context manifest by name or path."""
    # Try as a filename in the repo policies directory
    candidate = REPO_POLICIES_DIR / f"{repo_identifier}.yaml"
    if candidate.exists():
        return candidate
    # Try as a path
    candidate = Path(repo_identifier)
    if candidate.exists():
        return candidate
    return None


def load_global_policies() -> list:
    """Load all global policy manifests."""
    policies = []
    global_dir = POLICIES_DIR / "global"
    if not global_dir.exists():
        return policies
    for md_file in sorted(global_dir.glob("*.md")):
        # Extract frontmatter
        content = md_file.read_text()
        if content.startswith("---"):
            end = content.index("---", 3)
            frontmatter = yaml.safe_load(content[3:end])
            if frontmatter:
                frontmatter["_path"] = str(md_file)
                frontmatter["_digest"] = sha256_file(md_file)
                policies.append(frontmatter)
    return policies


def load_agent_profile(profile_id: str) -> dict:
    """Load an agent profile by ID."""
    path = PROFILES_DIR / f"{profile_id}.yaml"
    if not path.exists():
        return None
    return load_yaml(path)


def load_task_spec(task_file: str) -> dict:
    """Load a task specification from a file path or task name."""
    path = Path(task_file)
    if not path.is_absolute():
        # Try as a filename in the tasks directory
        candidate = TASKS_DIR / task_file
        if candidate.exists():
            path = candidate
        elif path.exists():
            pass  # relative to cwd
    if not path.exists():
        print(f"Error: task file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return load_yaml(path)


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_discover(args):
    """Discover context: repo, policy roots, ADRs, local context."""
    repo_path = Path(args.repo)
    if not repo_path.exists():
        print(f"Error: repository path not found: {repo_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Repository: {repo_path.name}")
    print(f"Path: {repo_path}")
    print()

    # Check for AGENTS.md
    agents_md = repo_path / "AGENTS.md"
    if agents_md.exists():
        print(f"  [FOUND] AGENTS.md ({agents_md.stat().st_size} bytes)")
    else:
        print(f"  [MISSING] AGENTS.md")

    # Check for .devin/instructions.md
    devin_instructions = repo_path / ".devin" / "instructions.md"
    if devin_instructions.exists():
        print(f"  [FOUND] .devin/instructions.md ({devin_instructions.stat().st_size} bytes)")

    # Check for .agents/ directory
    agents_dir = repo_path / ".agents"
    if agents_dir.exists():
        print(f"  [FOUND] .agents/ directory")

    # Check for repo context manifest in AI_AGENTS
    repo_manifest = REPO_POLICIES_DIR / f"{repo_path.name}.yaml"
    if repo_manifest.exists():
        print(f"  [FOUND] AI_AGENTS repo context: {repo_manifest}")
        ctx = load_yaml(repo_manifest)
        if ctx.get("sensitive_paths"):
            print(f"    Sensitive paths: {len(ctx['sensitive_paths'])}")
        if ctx.get("verification_profiles"):
            print(f"    Verification profiles: {', '.join(ctx['verification_profiles'].keys())}")
        if ctx.get("known_services"):
            print(f"    Known services: {len(ctx['known_services'])}")
    else:
        print(f"  [MISSING] AI_AGENTS repo context for '{repo_path.name}'")

    # Check for global policies
    global_policies = load_global_policies()
    if global_policies:
        print()
        print(f"  Global policies ({len(global_policies)}):")
        for p in global_policies:
            print(f"    - {p.get('policy_id', 'unknown')} v{p.get('version', '?')} [{p.get('status', '?')}]")

    # Check for agent profiles
    profiles = sorted(PROFILES_DIR.glob("*.yaml"))
    if profiles:
        print()
        print(f"  Agent profiles ({len(profiles)}):")
        for p in profiles:
            data = load_yaml(p)
            print(f"    - {data.get('profile_id', p.stem)}: {data.get('display_name', '?')}")

    # Git state
    git_dir = repo_path / ".git"
    if git_dir.exists():
        print()
        print("  Git state:")
        import subprocess
        for cmd_str in ["git status --short", "git branch --show-current", "git rev-parse --short HEAD"]:
            result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, cwd=repo_path)
            print(f"    {cmd_str}: {result.stdout.strip() or '(clean)'}")


def cmd_validate(args):
    """Validate repository context configuration."""
    repo_manifest = find_repo_context(args.repo)
    if not repo_manifest:
        print(f"Error: no repo context found for '{args.repo}'", file=sys.stderr)
        sys.exit(1)

    ctx = load_yaml(repo_manifest)
    errors = []
    warnings = []

    # Check required fields
    if not ctx.get("repository"):
        errors.append("Missing 'repository' field")
    if not ctx.get("policy_roots"):
        errors.append("Missing 'policy_roots' field")

    # Check policy roots exist
    repo_path = Path(ctx.get("path", "."))
    if repo_path.exists():
        for root in ctx.get("policy_roots", []):
            root_path = repo_path / root
            if not root_path.exists():
                warnings.append(f"Policy root not found on disk: {root}")

    # Check artifact governance
    ag = ctx.get("artifact_governance")
    if ag and ag.get("enabled"):
        if not ag.get("taxonomy"):
            warnings.append("Artifact governance enabled but no taxonomy defined")
        if not ag.get("mirror_directory"):
            warnings.append("Artifact governance enabled but no mirror_directory defined")
        if not ag.get("index_file"):
            warnings.append("Artifact governance enabled but no index_file defined")

    # Check verification profiles
    profiles = ctx.get("verification_profiles", {})
    for name, profile in profiles.items():
        if not profile.get("commands"):
            warnings.append(f"Verification profile '{name}' has no commands")

    # Check sensitive paths
    for item in ctx.get("sensitive_paths", []):
        if not item.get("path"):
            errors.append(f"Sensitive path entry missing 'path': {item}")
        if not item.get("classification"):
            warnings.append(f"Sensitive path '{item.get('path')}' missing classification")

    # Report
    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors:
            print(f"  [ERROR] {e}")
    else:
        print("OK: No errors")

    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  [WARN] {w}")

    if errors:
        sys.exit(1)


def cmd_compose(args):
    """Compose an invocation prompt from policy + task spec."""
    # Load repo context
    repo_manifest = find_repo_context(args.repo)
    if not repo_manifest:
        print(f"Error: no repo context found for '{args.repo}'", file=sys.stderr)
        sys.exit(1)
    repo_context = load_yaml(repo_manifest)

    # Load task spec
    task_spec = load_task_spec(args.task_file)

    # Load agent profile
    profile_id = args.agent or task_spec.get("agent_profile", "devin")
    agent_profile = load_agent_profile(profile_id)
    if not agent_profile:
        print(f"Error: agent profile not found: {profile_id}", file=sys.stderr)
        sys.exit(1)

    # Load global policies
    global_policies = load_global_policies()

    # Build invocation envelope
    invocation_id = f"inv_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Determine capabilities from task scope
    permitted = set(task_spec.get("scope", {}).get("permitted_operations", []))
    prohibited = set(task_spec.get("scope", {}).get("prohibited_operations", []))

    # Default capability sets by mode
    mode = task_spec.get("mode", "implement")
    if mode == "assess":
        default_allowed = ["read", "git-status", "git-diff", "git-log", "local-tests"]
        default_forbidden = ["modify-source", "deploy", "git-push", "git-force-push"]
    elif mode == "implement":
        default_allowed = ["read", "git-status", "git-diff", "git-log", "local-tests", "edit-files", "git-commit"]
        default_forbidden = ["git-force-push", "deploy", "network-policy-change"]
    elif mode == "infra":
        default_allowed = ["read", "git-status", "git-diff", "git-log", "edit-files", "git-commit", "tofu-plan"]
        default_forbidden = ["git-force-push", "deploy", "kubectl-apply"]
    else:
        default_allowed = ["read", "git-status", "git-diff", "git-log"]
        default_forbidden = ["git-force-push", "deploy"]

    allowed = list(set(default_allowed) | permitted) if permitted else default_allowed
    forbidden = list(set(default_forbidden) | prohibited) if prohibited else default_forbidden
    requires_confirmation = ["git-push", "create-pull-request", "kubernetes-scale", "kubernetes-apply"]

    envelope = {
        "schema_version": "v1",
        "invocation_id": invocation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": {
            "title": task_spec.get("title", "Untitled"),
            "mode": mode,
            "requested_by": "human",
            "scope": task_spec.get("scope", {}),
            "acceptance_criteria": task_spec.get("acceptance_criteria", []),
        },
        "identity": {
            "agent": {
                "provider": agent_profile.get("provider", profile_id),
                "profile": profile_id,
            },
        },
        "policy": {
            "global": [
                {"id": p.get("policy_id", "unknown"), "version": str(p.get("version", "0")), "digest": p.get("_digest", "")}
                for p in global_policies
            ],
            "domain": [],
            "repository": [{"id": repo_context.get("repository", "unknown"), "version": "1"}],
            "task_overrides": [],
        },
        "capabilities": {
            "allowed": sorted(allowed),
            "requires_confirmation": requires_confirmation,
            "forbidden": sorted(forbidden),
        },
        "evidence": {
            "required": ["git_status", "current_branch", "base_sha", "validation_results", "final_report"],
            "classification": ["observed", "inferred", "unverified"],
        },
        "rendering": {
            "format": args.format,
            "include": ["protocol", "repository_context", "task_appendix", "acceptance_criteria", "final_report_template"],
        },
    }

    # Output
    if args.format == "json":
        output = json.dumps(envelope, indent=2)
    else:
        # Render markdown using Jinja2
        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), keep_trailing_newline=True)
        template = env.get_template("invocation.md.j2")
        output = template.render(
            repo_context=repo_context,
            task_spec=task_spec,
            agent_profile=agent_profile,
            envelope=envelope,
        )

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written {len(output)} bytes to {args.output}")
        # Also write the envelope JSON alongside
        if args.format != "json":
            envelope_path = Path(args.output).with_suffix(".envelope.json")
            envelope_path.write_text(json.dumps(envelope, indent=2))
            print(f"Written envelope to {envelope_path}")
    else:
        print(output)


def cmd_explain(args):
    """Show why each rule was included, its source, and precedence."""
    repo_manifest = find_repo_context(args.repo)
    if not repo_manifest:
        print(f"Error: no repo context found for '{args.repo}'", file=sys.stderr)
        sys.exit(1)
    repo_context = load_yaml(repo_manifest)

    print(f"Repository: {repo_context.get('repository')}")
    print(f"Context manifest: {repo_manifest}")
    print()

    # Policy roots
    print("Policy roots (in precedence order):")
    for i, root in enumerate(repo_context.get("policy_roots", []), 1):
        print(f"  {i}. {root}")
    print()

    # Global policies
    global_policies = load_global_policies()
    if global_policies:
        print("Global policies:")
        for p in global_policies:
            print(f"  - {p.get('policy_id')}: v{p.get('version')} [{p.get('status')}]")
            print(f"    Path: {p.get('_path')}")
            print(f"    Digest: {p.get('_digest')}")
            print(f"    Applies to: {p.get('applies_to', 'all')}")
            print(f"    Precedence level: {p.get('precedence', 'unspecified')}")
        print()

    # Sensitive paths
    if repo_context.get("sensitive_paths"):
        print("Sensitive paths:")
        for item in repo_context["sensitive_paths"]:
            print(f"  - {item['path']}: {item['classification']}")
            if item.get("required_approval"):
                print(f"    Approval: {item['required_approval']}")
            if item.get("validation"):
                print(f"    Validation: {', '.join(item['validation'])}")
        print()

    # Verification profiles
    if repo_context.get("verification_profiles"):
        print("Verification profiles:")
        for name, profile in repo_context["verification_profiles"].items():
            cmds = profile.get("commands", [])
            print(f"  - {name} ({len(cmds)} commands)")
            if profile.get("working_directory"):
                print(f"    Working dir: {profile['working_directory']}")
        print()

    # Agent profiles
    profiles = sorted(PROFILES_DIR.glob("*.yaml"))
    if profiles:
        print("Available agent profiles:")
        for p in profiles:
            data = load_yaml(p)
            print(f"  - {data.get('profile_id')}: {data.get('display_name')}")
            caps = data.get("capabilities", {})
            enabled = [k for k, v in caps.items() if v and k.startswith("can_")]
            print(f"    Capabilities: {', '.join(enabled)}")


def cmd_doctor(args):
    """Verify installation, config, schemas, and agent profile availability."""
    print("agent-invoke doctor")
    print("=" * 50)

    checks = []

    # Check directories
    for name, path in [("policies", POLICIES_DIR), ("profiles", PROFILES_DIR),
                       ("schemas", SCHEMAS_DIR), ("templates", TEMPLATES_DIR),
                       ("tasks", TASKS_DIR)]:
        exists = path.exists()
        checks.append((name, str(path), exists))
        status = "OK" if exists else "MISSING"
        print(f"  [{status}] {name}: {path}")

    # Check global policies
    global_dir = POLICIES_DIR / "global"
    md_files = list(global_dir.glob("*.md")) if global_dir.exists() else []
    checks.append(("global_policies", str(global_dir), len(md_files) > 0))
    print(f"  [{'OK' if md_files else 'MISSING'}] global policies: {len(md_files)} file(s)")

    # Check repo contexts
    repo_files = list(REPO_POLICIES_DIR.glob("*.yaml")) if REPO_POLICIES_DIR.exists() else []
    checks.append(("repo_contexts", str(REPO_POLICIES_DIR), len(repo_files) > 0))
    print(f"  [{'OK' if repo_files else 'MISSING'}] repo contexts: {len(repo_files)} file(s)")
    for f in repo_files:
        print(f"    - {f.stem}")

    # Check agent profiles
    profile_files = list(PROFILES_DIR.glob("*.yaml")) if PROFILES_DIR.exists() else []
    checks.append(("agent_profiles", str(PROFILES_DIR), len(profile_files) > 0))
    print(f"  [{'OK' if profile_files else 'MISSING'}] agent profiles: {len(profile_files)} file(s)")
    for f in profile_files:
        print(f"    - {f.stem}")

    # Check templates
    template_files = list(TEMPLATES_DIR.glob("*.j2")) if TEMPLATES_DIR.exists() else []
    checks.append(("templates", str(TEMPLATES_DIR), len(template_files) > 0))
    print(f"  [{'OK' if template_files else 'MISSING'}] templates: {len(template_files)} file(s)")

    # Check Python deps
    print()
    print("  Python dependencies:")
    for mod in ["yaml", "jinja2"]:
        try:
            __import__(mod)
            print(f"    [OK] {mod}")
        except ImportError:
            print(f"    [MISSING] {mod}")
            checks.append((f"dep_{mod}", mod, False))

    # Summary
    print()
    failed = [c for c in checks if not c[2]]
    if failed:
        print(f"FAIL: {len(failed)} check(s) failed")
        for name, path, _ in failed:
            print(f"  - {name}: {path}")
        sys.exit(1)
    else:
        print(f"OK: All {len(checks)} checks passed")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="agent-invoke",
        description="Agent Invocation Control Plane — compose deterministic agent prompts from versioned policy.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p = sub.add_parser("discover", help="Find repository, policy roots, and local context")
    p.add_argument("--repo", required=True, help="Repository path or name")

    # validate
    p = sub.add_parser("validate", help="Validate repository context configuration")
    p.add_argument("--repo", required=True, help="Repository name or path to context manifest")

    # compose
    p = sub.add_parser("compose", help="Compose an invocation prompt from policy + task spec")
    p.add_argument("--repo", required=True, help="Repository name or path to context manifest")
    p.add_argument("--agent", help="Agent profile ID (default: from task spec or 'devin')")
    p.add_argument("--task-file", required=True, help="Path to task spec YAML")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # explain
    p = sub.add_parser("explain", help="Show policy sources, precedence, and composition")
    p.add_argument("--repo", required=True, help="Repository name or path to context manifest")

    # doctor
    sub.add_parser("doctor", help="Verify installation and configuration")

    args = parser.parse_args()

    if args.command == "discover":
        cmd_discover(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "compose":
        cmd_compose(args)
    elif args.command == "explain":
        cmd_explain(args)
    elif args.command == "doctor":
        cmd_doctor(args)


if __name__ == "__main__":
    main()
