#!/usr/bin/env python3
"""
AI_AGENTS Policy Integration Helper
Simple interface for AI agents to load and apply governance policies
"""

import os
import sys
import json
from pathlib import Path

# Add AI_AGENTS to path
ai_agents_path = Path("/home/cortex/workspace/AI_AGENTS")
sys.path.insert(0, str(ai_agents_path))

try:
    from load_policies import PolicyLoader
except ImportError:
    print("❌ Failed to import PolicyLoader")
    sys.exit(1)


def load_policies_for_agent():
    """
    Load policies for AI agent consumption
    Returns a dictionary with policy information and applicable rules
    """
    loader = PolicyLoader()
    loader.detect_context()
    
    # Validate policies
    valid, issues = loader.validate_policies()
    if not valid:
        print("⚠️  Policy validation warnings:")
        for issue in issues:
            print(f"  - {issue}")
    
    # Get policy summary
    summary = loader.get_policy_summary()
    
    # Get applicable policies in priority order
    applicable_policies = loader.get_applicable_policies()
    
    # Load content of high-priority policies
    policy_contents = {}
    for policy_path in applicable_policies[:3]:  # Load top 3 priority policies
        content = loader.load_policy_content(policy_path)
        if content:
            policy_contents[policy_path] = content
    
    return {
        "status": "loaded" if valid else "partial",
        "context": loader.current_dir,
        "repository": loader.repo_name,
        "tech_stack": loader.tech_stack,
        "workspace_context": loader.workspace_context,
        "policy_summary": summary,
        "applicable_policies": applicable_policies,
        "high_priority_content": policy_contents,
        "environment_variables": {
            "AI_AGENTS_POLICIES_LOADED": os.environ.get("AI_AGENTS_POLICIES_LOADED", "false"),
            "AI_AGENTS_CONTEXT": os.environ.get("AI_AGENTS_CONTEXT", ""),
            "AI_AGENTS_REPO": os.environ.get("AI_AGENTS_REPO", ""),
            "AI_AGENTS_TECH_STACK": os.environ.get("AI_AGENTS_TECH_STACK", "")
        }
    }


def get_active_rules():
    """
    Get active rules that should be applied
    Returns a simplified list of rules based on loaded policies
    """
    policy_data = load_policies_for_agent()
    
    active_rules = {
        "infrastructure": [],
        "operations": [],
        "security": [],
        "domain_specific": [],
        "context_overrides": []
    }
    
    # Parse policy contents to extract rules
    for policy_path, content in policy_data["high_priority_content"].items():
        if "infrastructure" in policy_path.lower():
            active_rules["infrastructure"].append({
                "source": policy_path,
                "content": content[:500] + "..." if len(content) > 500 else content
            })
        elif "operations" in policy_path.lower():
            active_rules["operations"].append({
                "source": policy_path,
                "content": content[:500] + "..." if len(content) > 500 else content
            })
        elif "security" in policy_path.lower():
            active_rules["security"].append({
                "source": policy_path,
                "content": content[:500] + "..." if len(content) > 500 else content
            })
        elif "context" in policy_path.lower() or "override" in policy_path.lower():
            active_rules["context_overrides"].append({
                "source": policy_path,
                "content": content[:500] + "..." if len(content) > 500 else content
            })
    
    return active_rules


def check_compliance(rule_type: str = "all"):
    """
    Check compliance with specific rule type
    Options: 'infrastructure', 'operations', 'security', 'domain', 'context', 'all'
    """
    rules = get_active_rules()
    
    if rule_type == "all":
        return {
            "compliant": True,
            "active_rules": rules,
            "recommendations": "Review all applicable policies before proceeding"
        }
    elif rule_type in rules:
        return {
            "compliant": True,
            "active_rules": rules[rule_type],
            "recommendations": f"Follow {rule_type} guidelines from loaded policies"
        }
    else:
        return {
            "compliant": False,
            "error": f"Unknown rule type: {rule_type}",
            "available_types": list(rules.keys())
        }


def main():
    """Main function for direct agent usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI_AGENTS Policy Integration")
    parser.add_argument("--load", action="store_true", help="Load policies for agent")
    parser.add_argument("--rules", action="store_true", help="Get active rules")
    parser.add_argument("--check", type=str, default="all", help="Check compliance (infrastructure, operations, security, domain, context, all)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if args.load:
        data = load_policies_for_agent()
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            print("🤖 AI_AGENTS Policy Integration")
            print("=" * 40)
            print(f"Status: {data['status']}")
            print(f"Repository: {data['repository']}")
            print(f"Tech Stack: {', '.join(data['tech_stack'])}")
            print(f"Context: {data['workspace_context']}")
            print(f"Total Policies: {data['policy_summary']['total_policies']}")
            print(f"\nApplicable Policies: {len(data['applicable_policies'])}")
            for i, policy in enumerate(data['applicable_policies'][:5], 1):
                print(f"  {i}. {policy}")
    
    elif args.rules:
        rules = get_active_rules()
        if args.json:
            print(json.dumps(rules, indent=2, default=str))
        else:
            print("📋 Active Rules")
            print("=" * 40)
            for category, rule_list in rules.items():
                if rule_list:
                    print(f"\n{category.upper()}:")
                    for rule in rule_list:
                        print(f"  - {rule['source']}")
    
    elif args.check:
        compliance = check_compliance(args.check)
        if args.json:
            print(json.dumps(compliance, indent=2, default=str))
        else:
            print("✅ Compliance Check")
            print("=" * 40)
            print(f"Compliant: {compliance['compliant']}")
            if 'recommendations' in compliance:
                print(f"Recommendations: {compliance['recommendations']}")
    
    else:
        # Default: Load and show summary
        data = load_policies_for_agent()
        print("🤖 AI_AGENTS Policy Integration Ready")
        print("=" * 40)
        print(f"Repository: {data['repository']}")
        print(f"Tech Stack: {', '.join(data['tech_stack'])}")
        print(f"Policies Loaded: {data['policy_summary']['total_policies']}")
        print(f"Status: {data['status']}")
        print("\nUse --help for more options")


if __name__ == "__main__":
    main()