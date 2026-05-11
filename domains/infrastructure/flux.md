# Flux/Infrastructure Domain Rules

Rules and patterns for GitOps and infrastructure as code using Flux.

## Repository Structure
- `apps/` - Application deployments
- `clusters/` - Cluster configurations
- `globals/` - Global configurations
- `namespaces/` - Namespace definitions
- `kustomization.yaml` - Root Kustomization

## Flux Patterns
- Use Kustomize for resource composition
- Use HelmRelease for Helm charts
- Use ImageRepository for image sources
- Use ImagePolicy for image updates
- Use ImageUpdateAutomation for automatic updates

## Commit Conventions
- Use conventional commits
- Include Jira tickets in commit messages
- Sign commits for verification
- Write clear commit messages

## Branch Strategy
- `main` - Production-ready code
- `develop` - Integration branch
- Feature branches from `develop`
- Release branches for production preparation

## Deployment Workflow
1. Create feature branch
2. Make changes and test locally
3. Create pull request
4. Review and approve
5. Merge to develop
6. Flux automatically deploys to dev
7. Create release branch from develop
8. Deploy to staging for testing
9. Merge release to main
10. Flux deploys to production

## Rollback Strategy
- Keep deployment history in git
- Use git revert for rollbacks
- Test rollbacks in staging first
- Document rollback procedures