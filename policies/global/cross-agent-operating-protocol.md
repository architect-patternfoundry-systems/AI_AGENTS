---
policy_id: cross-agent-operating-protocol
version: 1.0.0
status: active
applies_to: [devin, antigravity-cli, cursor, claude-code, subagents]
precedence: 4
---

# Cross-Agent Operating Protocol

You are working in a shared, multi-agent engineering workspace. Other agents
may be modifying this repository, related repositories, infrastructure, or
live development environments concurrently.

Your objective is to make assigned work recoverable, reviewable, isolated,
and verifiable. Do not expand the task beyond the user's explicit request.

## 1. Instruction precedence

Follow instructions in this order:

1. The user's current explicit request and approval boundaries.
2. Repository-local instructions closest to the files you touch
   (`AGENTS.md`, nested `AGENTS.md`, `README`, `CONTRIBUTING`, runbooks).
3. Approved ADRs, security policies, and operational runbooks.
4. This protocol.

If instructions conflict, required policy files are missing, or ownership is
unclear, stop and report the conflict before making changes.

A user request may define task scope and approve operations, but it does not
override security requirements, access controls, protected-branch rules, or
repository-local constraints unless the user is authorized to change those
controls and explicitly requests that policy change.

## 2. Start-of-task checklist

Before editing:

1. Read applicable repository instructions.
2. Run and report:
   ```bash
   git status --short
   git branch --show-current
   git rev-parse --short HEAD
   git remote -v
   ```
3. Identify active branches/PRs and any concurrent agent ownership affecting
   your target files.
4. State:
   - repository and worktree path,
   - branch and base SHA,
   - target files/directories,
   - intended outcome,
   - validation commands,
   - whether the work touches shared or live state.

## 3. Worktree isolation and ownership

- Use a dedicated feature/fix branch and, when concurrent editing is possible,
  a dedicated Git worktree. Do not share a working tree with another agent.
- Do not edit files or branches owned by another active agent.
- If your task overlaps another agent's scope, remain read-only and ask the
  user to resolve ownership.
- Do not create duplicate sources of truth. Find and preserve the canonical
  source before adding data, generated output, configuration, or artifacts.

## 4. Git safety, persistence, and recovery

- Before switching branches, rebasing, resetting, stashing, cleaning, or
  changing worktrees, ensure your in-scope work is recoverable in a commit,
  patch, or named stash. Do not commit another agent's work merely to make
  the tree clean. If unrelated changes block safe isolation, stop and ask the
  user to resolve ownership.
- Use explicit staging: `git add <paths>`. Do not use `git add .` unless the
  user explicitly authorizes it and you have reviewed `git status`.
- A clean checkout must build: commit all source files, imports, data files,
  manifests, migrations, and generated artifacts required by committed code.
- Before a PR, inspect `git status --short` and verify that no required files
  remain untracked.
- Never use `git clean`, `git reset --hard`, `git stash drop`, `git stash
  clear`, branch deletion, or rebase on shared work without explicit approval.
- Never force-push a shared, protected, base, or another agent's branch. On
  your own unmerged feature branch, use `git push --force-with-lease` only
  after recording the old and intended new HEAD SHAs and receiving explicit
  approval for a history rewrite that removes or replaces published commits.
- Never commit secrets, tokens, credentials, private keys, or `.env` files.
  Run the repository-required secret scan before push. If no
  repository-specific scanner exists and the change touches configuration,
  credentials, deployment files, or integrations, run the approved workspace
  secret scan or report that no scanner is available.

If work appears lost, stop destructive cleanup and preserve the repository
state. Before concluding that work is unrecoverable, inspect recoverable Git
objects using `git reflog`, `git fsck --lost-found`, and any relevant stashes.
Do not prune, garbage-collect, clear stashes, or run further cleanup commands
until recovery has been assessed.

## 5. Change discipline and source-of-truth rules

- Keep each commit focused on one review question.
- Use conventional commit messages when the repository requires them.
- Do not mix unrelated UI, infrastructure, dependency, policy, and feature
  changes in one PR.
- Do not add a dependency exception for a third-party package required by CI.
  Add the dependency to the appropriate versioned dependency definition.
- Use time-bounded, tracked exceptions only for confirmed missing internal
  modules or explicitly optional integrations.
- Do not make silent incidental changes. If a formatter, generator,
  pre-commit hook, dependency resolver, or tool changes files outside the
  assigned scope, inspect the diff. Revert unrelated changes or report them
  explicitly before committing.

Before editing or creating generated data, identify:
- the authoritative source,
- the generator command,
- the generated output,
- and the repository's policy for committing generated output.

Do not hand-edit generated files unless the task explicitly requires it. When
generated output is committed, regenerate it from the authoritative source
and verify the working tree is deterministic after regeneration.

## 6. Dependency and exception policy

Do not use an exception to hide a dependency required by the verification
path.

- Missing third-party package: add a pinned or governed dependency to the
  appropriate CI/test dependency file.
- Missing repository-owned module: use a narrow, time-bounded exception only
  if a tracking issue and remediation owner exist.
- Optional runtime integration: represent it explicitly in manifest/test
  metadata and verify the fallback behavior.

If you must add an exception, record the kind, modules, reason, remediation,
and expiry. Create a tracking issue. Retire the exception once the root cause
is fixed.

## 7. Validation and clean-checkout requirements

Run the narrowest relevant validation first, then the required regression
validation from repository instructions.

Before declaring completion, report:
- exact commands run,
- pass/fail/skipped outcome,
- anything not run and why,
- clean-checkout risks,
- remaining assumptions.

CI and a clean checkout are authoritative over a locally dirty environment.

If a required test cannot pass yet, create a clearly labeled `wip:` recovery
commit rather than leaving critical work uncommitted. Do not present WIP as
ready for merge.

## 8. Artifact governance

For durable governance or user-facing artifacts — ADR, proposal,
specification, runbook, report, checklist, or postmortem — follow the
repository-local artifact policy. Do not assume another repository uses the
same taxonomy, mirror path, or index.

If applicable:
1. Classify using the repository taxonomy.
2. Mirror it to the required artifact location.
3. Add it to the artifact index.
4. Verify the mirrored artifact is accessible from a clean checkout.

Do not apply artifact registration rules to ordinary source edits or
temporary notes unless repository instructions require it.

## 9. Shared and live-system approval gates

Read-only inspection is allowed within the current task scope, provided it
does not expose secrets, private user content, credentials, or regulated data
in chat, logs, screenshots, commits, or artifacts.

Ask for explicit confirmation before destructive or disruptive operations,
including:
- deleting or scaling Kubernetes resources,
- changing live deployment images,
- modifying DNS, Cloudflare, Tailscale, ingress, credentials, or firewall
  policy,
- restarting controllers or shared services,
- modifying production data,
- changing shared GPU/capacity policy.

For Tilt-managed services, do not use raw `kubectl apply` against
image-bearing manifests unless the task explicitly authorizes replacing
Tilt-managed image references.

## 10. Out-of-scope guardrails

Do not create or deploy new services, ports, public domains, Slack
integrations, authentication flows, or infrastructure topology changes
unless the current task explicitly authorizes them.

Do not begin the next project phase merely because a status report says the
system is "ready." Wait for an explicit task assignment.

## 11. Required final report

Do not report a change as deployed, merged, passing, or complete unless you
personally verified the relevant state in the authoritative system.
Distinguish between:
- implemented locally,
- committed and pushed,
- CI verified,
- deployed,
- runtime verified.

Use concise checkpoint updates during multi-step work. Provide the complete
final-report template when pausing, handing off, requesting approval, or
declaring a substantive milestone complete.

Use this format after each substantive task:

```markdown
## Status
- Outcome: complete / blocked / needs approval
- Repository / worktree:
- Branch:
- Base SHA -> current SHA:
- Files changed:
- Commits created:
- Validation:
- CI status:
- Shared/live-state changes:
- Risks, assumptions, or follow-ups:
- Next action or exact approval needed:
```
