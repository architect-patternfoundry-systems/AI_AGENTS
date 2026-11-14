#!/usr/bin/env python3
"""
AI_AGENTS Policy Loader (Python Version)
Automatically loads and applies AI agent governance policies based on context
Version: 2.0.0
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import subprocess

class PolicyLoader:
    """Loads and manages AI agent governance policies"""
    
    def __init__(self, ai_agents_root: str = "/home/cortex/workspace/AI_AGENTS",
                 workspace_root: str = "/home/cortex/workspace"):
        self.ai_agents_root = Path(ai_agents_root)
        self.workspace_root = Path(workspace_root)
        self.current_dir = Path.cwd()
        self.cache_dir = Path("/tmp/ai_agents_cache")
        self.cache_ttl = timedelta(hours=1)
        
        # Context information
        self.repo_root: Optional[Path] = None
        self.repo_name: str = "no-repo"
        self.tech_stack: List[str] = []
        self.workspace_context: str = "external"
        
        # Loaded policies
        self.policies: Dict = {
            "global": [],
            "domain": [],
            "context": []
        }
        
    def detect_context(self) -> None:
        """Detect operational context"""
        print("🤖 Detecting operational context...")
        
        # Detect repository
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True
            )
            self.repo_root = Path(result.stdout.strip())
            self.repo_name = self.repo_root.name
            print(f"  📂 Repository detected: {self.repo_name}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.repo_root = None
            self.repo_name = "no-repo"
            print("  📂 No git repository detected")
        
        # Detect technology stack
        self.tech_stack = self._detect_tech_stack()
        print(f"  🔧 Technology stack: {', '.join(self.tech_stack) if self.tech_stack else 'none'}")
        
        # Detect workspace context
        if str(self.current_dir).startswith(str(self.workspace_root)):
            self.workspace_context = "workspace"
            print("  🏢 Workspace context detected")
        else:
            self.workspace_context = "external"
            print("  🌍 External context detected")
    
    def _detect_tech_stack(self) -> List[str]:
        """Detect technology stack from current directory"""
        stack = []
        
        # Check for Node.js/Next.js
        if (self.current_dir / "package.json").exists():
            stack.append("nodejs")
            try:
                with open(self.current_dir / "package.json") as f:
                    if "next" in f.read():
                        stack.append("nextjs")
            except:
                pass
        
        # Check for Go/Kubebuilder
        if (self.current_dir / "go.mod").exists():
            stack.append("golang")
            if (self.current_dir / "Project.mk").exists():
                stack.append("kubebuilder")
        
        # Check for Python
        for py_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
            if (self.current_dir / py_file).exists():
                stack.append("python")
                break
        
        # Check for Kubernetes/Flux
        if (self.current_dir / "Chart.yaml").exists() or (self.current_dir / "flux-system").exists():
            stack.extend(["kubernetes", "flux"])
        
        # Check for Docker
        for docker_file in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
            if (self.current_dir / docker_file).exists():
                stack.append("docker")
                break
        
        # Check for Cloudflare
        if (self.current_dir / "cloudflare_config.yml").exists() or \
           (self.current_dir / "cloudflare_config_dev.yml").exists() or \
           (self.current_dir / "tunnel_identity_separation.tf").exists():
            stack.append("cloudflare")
        
        return stack
    
    def load_global_policies(self) -> List[Path]:
        """Load global governance policies"""
        print("📜 Loading global governance policies...")
        policies = []
        
        # Infrastructure standards
        infra_policy = self.ai_agents_root / "global" / "infrastructure.md"
        if infra_policy.exists():
            policies.append(infra_policy)
            print("  ✅ Infrastructure standards")
        
        # Operations standards
        ops_policy = self.ai_agents_root / "global" / "operations.md"
        if ops_policy.exists():
            policies.append(ops_policy)
            print("  ✅ Operations standards")
        
        # Security standards
        sec_policy = self.ai_agents_root / "global" / "security.md"
        if sec_policy.exists():
            policies.append(sec_policy)
            print("  ✅ Security standards")
        
        # ADRs
        adr_dir = self.ai_agents_root / "global" / "adr"
        if adr_dir.exists():
            for adr in adr_dir.glob("*.md"):
                policies.append(adr)
            print(f"  ✅ Architectural decisions ({len(list(adr_dir.glob('*.md')))} ADRs)")
        
        return policies
    
    def load_domain_policies(self) -> List[Path]:
        """Load domain-specific policies"""
        print("📚 Loading domain-specific policies...")
        policies = []
        
        domain_mappings = {
            "nextjs": "domains/nextjs/rules.md",
            "kubebuilder": "domains/kubernetes/kubebuilder.md",
            "python": "domains/python/rules.md",
            "flux": "domains/infrastructure/flux.md",
            "kubernetes": "domains/kubernetes/general.md",
            "cloudflare": "domains/cloudflare/acl_governance.md"
        }
        
        for tech in self.tech_stack:
            if tech in domain_mappings:
                policy_path = self.ai_agents_root / domain_mappings[tech]
                if policy_path.exists():
                    policies.append(policy_path)
                    print(f"  ✅ {tech.capitalize()} rules")
        
        return policies
    
    def load_context_policies(self) -> List[Path]:
        """Load context-specific policies"""
        print("🎯 Loading context-specific policies...")
        policies = []
        
        # Workspace overrides
        workspace_override = self.ai_agents_root / "context" / "workspace" / "overrides.md"
        if workspace_override.exists():
            policies.append(workspace_override)
            print("  ✅ Workspace overrides")
        
        # Repository-specific overrides
        if self.repo_root:
            repo_override_dir = self.ai_agents_root / "context" / "repositories" / self.repo_name
            if repo_override_dir.exists():
                for policy in repo_override_dir.glob("*.md"):
                    policies.append(policy)
                print(f"  ✅ Repository-specific overrides ({self.repo_name})")
            
            # Local AGENTS.md
            local_agents = self.repo_root / "AGENTS.md"
            if local_agents.exists():
                policies.append(local_agents)
                print("  ✅ Local AGENTS.md")
        
        return policies
    
    def compile_policies(self) -> Dict:
        """Compile policy hierarchy"""
        print("🔨 Compiling policy hierarchy...")
        
        # Create cache key
        cache_key = f"{self.repo_name}-{'-'.join(self.tech_stack)}-{self.workspace_context}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < self.cache_ttl:
                print(f"⚡ Using cached policies (age: {cache_age.total_seconds():.0f}s)")
                with open(cache_file) as f:
                    return json.load(f)
        
        # Load policies
        self.policies["global"] = [str(p) for p in self.load_global_policies()]
        self.policies["domain"] = [str(p) for p in self.load_domain_policies()]
        self.policies["context"] = [str(p) for p in self.load_context_policies()]
        
        # Compile policy document
        policy_doc = {
            "context": {
                "repo_name": self.repo_name,
                "repo_root": str(self.repo_root) if self.repo_root else None,
                "tech_stack": self.tech_stack,
                "workspace_context": self.workspace_context,
                "current_dir": str(self.current_dir)
            },
            "policies": self.policies,
            "priority_order": ["context", "domain", "global"],
            "metadata": {
                "version": "2.0.0",
                "cache_timestamp": datetime.now().isoformat(),
                "ai_agents_root": str(self.ai_agents_root)
            }
        }
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to cache
        with open(cache_file, 'w') as f:
            json.dump(policy_doc, f, indent=2)
        
        print("✅ Policies compiled and cached")
        return policy_doc
    
    def validate_policies(self) -> Tuple[bool, List[str]]:
        """Validate policy integrity"""
        print("🔍 Validating policy integrity...")
        
        issues = []
        
        # Check AI_AGENTS root
        if not self.ai_agents_root.exists():
            issues.append(f"AI_AGENTS root not found: {self.ai_agents_root}")
            return False, issues
        
        # Check required global policies
        required_policies = [
            ("infrastructure.md", "global/infrastructure.md"),
            ("operations.md", "global/operations.md"),
            ("security.md", "global/security.md")
        ]
        
        for name, path in required_policies:
            policy_file = self.ai_agents_root / path
            if not policy_file.exists():
                issues.append(f"Missing required policy: {path}")
        
        policy_count = len(required_policies) - len(issues)
        print(f"✅ Policy validation: {policy_count}/{len(required_policies)} policies loaded")
        
        if issues:
            print(f"⚠️  Issues found: {len(issues)}")
            for issue in issues:
                print(f"  - {issue}")
        
        return len(issues) == 0, issues
    
    def export_for_agent(self) -> Dict:
        """Export policies for agent consumption"""
        print("📤 Exporting policies for agent consumption...")
        
        policy_doc = self.compile_policies()
        
        # Set environment variables
        os.environ["AI_AGENTS_POLICIES_LOADED"] = "true"
        os.environ["AI_AGENTS_CONTEXT"] = self.workspace_context
        os.environ["AI_AGENTS_REPO"] = self.repo_name
        os.environ["AI_AGENTS_TECH_STACK"] = ",".join(self.tech_stack)
        
        print("✅ Policies exported to environment variables")
        return policy_doc
    
    def get_applicable_policies(self) -> List[str]:
        """Get list of applicable policy files in priority order"""
        policy_doc = self.compile_policies()
        
        # Return in priority order (highest first)
        applicable = []
        for level in policy_doc["priority_order"]:
            applicable.extend(policy_doc["policies"][level])
        
        return applicable
    
    def load_policy_content(self, policy_path: str) -> str:
        """Load content of a specific policy file"""
        path = Path(policy_path)
        if path.exists():
            with open(path) as f:
                return f.read()
        return ""
    
    def get_policy_summary(self) -> Dict:
        """Get summary of loaded policies"""
        policy_doc = self.compile_policies()
        
        return {
            "total_policies": sum(len(policies) for policies in policy_doc["policies"].values()),
            "by_level": {
                level: len(policies) 
                for level, policies in policy_doc["policies"].items()
            },
            "context": policy_doc["context"],
            "priority_order": policy_doc["priority_order"]
        }


def main():
    """Main function for CLI usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI_AGENTS Policy Loader")
    parser.add_argument("--export", action="store_true", help="Export policies for agent")
    parser.add_argument("--validate", action="store_true", help="Validate policy integrity")
    parser.add_argument("--summary", action="store_true", help="Show policy summary")
    parser.add_argument("--list", action="store_true", help="List applicable policies")
    parser.add_argument("--content", type=str, help="Show content of specific policy")
    
    args = parser.parse_args()
    
    loader = PolicyLoader()
    loader.detect_context()
    
    if args.validate:
        valid, issues = loader.validate_policies()
        if not valid:
            print("❌ Policy validation failed")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
        else:
            print("✅ Policy validation passed")
    
    if args.summary:
        summary = loader.get_policy_summary()
        print("\n📊 Policy Summary:")
        print(f"  Total policies: {summary['total_policies']}")
        print(f"  By level:")
        for level, count in summary['by_level'].items():
            print(f"    {level}: {count}")
        print(f"  Context: {summary['context']}")
    
    if args.list:
        policies = loader.get_applicable_policies()
        print("\n📋 Applicable Policies (priority order):")
        for i, policy in enumerate(policies, 1):
            print(f"  {i}. {policy}")
    
    if args.content:
        content = loader.load_policy_content(args.content)
        if content:
            print(f"\n📄 Content of {args.content}:")
            print(content)
        else:
            print(f"❌ Policy not found: {args.content}")
    
    if args.export or not any([args.validate, args.summary, args.list, args.content]):
        policy_doc = loader.export_for_agent()
        print("\n✅ Policy loading complete")
        print("📋 Policy hierarchy (highest to lowest priority):")
        print("  1. Repository-specific AGENTS.md")
        print("  2. Repository-specific context override")
        print("  3. Workspace context override")
        print("  4. Domain-specific rules")
        print("  5. Global governance")


if __name__ == "__main__":
    main()