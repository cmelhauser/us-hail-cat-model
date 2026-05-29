# Git remotes policy

This repository uses two remotes with **different roles**. All day-to-day work
targets **`origin` only**.

| Remote | URL | Fetch | Push | PRs |
|--------|-----|-------|------|-----|
| **`origin`** | `https://github.com/cmelhauser/us-hail-cat-model.git` | Yes | **Yes** | **Yes** — base `main` on this repo |
| **`upstream`** | `https://github.com/theonlymuffinbot/us-hail-cat-model.git` | Optional (read-only sync) | **No** | **No** |

## Required local setup (once per clone)

From the repo root:

```bash
./scripts/setup_git_remotes.sh
```

Or manually:

```bash
git config remote.pushDefault origin
git remote set-url --push upstream no_push   # fails loudly if someone runs git push upstream
```

## Commands to use

```bash
# Push current branch
git push -u origin HEAD

# Open a PR (always this repo, never upstream)
gh pr create --repo cmelhauser/us-hail-cat-model --base main --head "$(git branch --show-current)"
```

## Do not

- `git push upstream …`
- `gh pr create` without `--repo cmelhauser/us-hail-cat-model` (defaults can target the wrong fork)
- Merge or commit directly to `upstream` on GitHub

AI agents and contributors must treat **`origin`** as the sole write remote.
