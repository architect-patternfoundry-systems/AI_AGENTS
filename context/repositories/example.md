# Repository-Specific Overrides Example

This file demonstrates how repository-specific overrides should be structured.

## Repository: example-repo

### Override Global Rules
- **NFS Path Override**: Use `/mnt/data_lake/example-repo/` instead of standard path
- **Prometheus Port**: Use port 9105 instead of default 9101
- **Memory Limit**: Increase to 2Gi for this specific service

### Additional Repository-Specific Rules
- Use specific Python version: 3.11
- Require code review from team lead
- Integration tests must pass before merge

### Repository-Specific ADRs
- Link to repository-specific ADRs if any

## Usage
Copy this file and rename it to match your repository name. Add repository-specific overrides and additional rules as needed.