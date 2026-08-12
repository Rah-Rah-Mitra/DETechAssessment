# Prompt Logger

If you use any AI coding assistant while working on this assessment (Claude Code, Codex, GitHub Copilot, Cline, etc.), your prompts must be submitted alongside your code.

There are two ways to get your prompts into this folder. [Option A](#option-a-automatic-sync-via-the-pre-commit-hook-recommended) is a pre-commit hook that copies sessions automatically on every commit (recommended). [Option B](#option-b-manual-export-for-everything-else) is to export from your tool and drop the files in yourself.

## Before you start

**Capturing your prompts is your responsibility.** [Option A](#option-a-automatic-sync-via-the-pre-commit-hook-recommended) handles common tools but can't account for everything. If it doesn't work for you, capture your prompts another way. The hook never blocks a commit, so a missed capture won't announce itself. After committing, check that `prompt-logger/` actually contains your sessions.

## Option A. Automatic sync via the pre-commit hook (recommended)

A git hook runs on every commit, finds sessions that belong to this repo, copies them into `prompt-logger/<tool>/`, and stages them into the same commit.

### Activate the hook

```bash
git config core.hooksPath .githooks
```

On macOS/Linux you may also need:

```bash
chmod +x .githooks/pre-commit
```

### What it captures

| Tool                     | Source on disk                                                                                     |
| ------------------------ | -------------------------------------------------------------------------------------------------- |
| Claude Code              | `~/.claude/projects/<repo-path-slug>/*.jsonl`                                                       |
| Codex CLI                | `~/.codex/sessions/**/rollout-*.jsonl` (matched to this repo by the path recorded inside the file) |
| Cline (VS Code)          | `globalStorage/saoudrizwan.claude-dev/tasks/<id>/ui_messages.json`                                 |
| GitHub Copilot (VS Code) | `workspaceStorage/<hash>/chatSessions/*.json` (matched to this repo via `workspace.json`)          |

The hook matches sessions to this repo using the full repo path or the `<parent-folder>/<repo-name>` tail, so same-named projects elsewhere won't be swept in.

### Verify it worked

After committing, run:

```bash
git show --stat HEAD
```

You should see `prompt-logger/` entries in the output. If not, fall back to Option B.

### If the hook doesn't fire

- `git config --get core.hooksPath` should print `.githooks`.
- Don't use `git commit --no-verify` (skips all hooks).
- Some GUI git clients bypass `core.hooksPath`. Commit from the terminal, or use Option B.

## Option B. Manual export (for everything else)

If your tool isn't in the table above, or you'd rather export by hand, drop the files into `prompt-logger/<tool>/` yourself and commit them.

### Claude Code

Copy `.jsonl` files from `~/.claude/projects/<repo-path-slug>/` into `prompt-logger/claude-code/`. The slug is this repo's absolute path with every non-alphanumeric character replaced by `-`.

### Codex

Copy the relevant `rollout-*.jsonl` files from `~/.codex/sessions/YYYY/MM/DD/` into `prompt-logger/codex/`.

### GitHub Copilot (VS Code)

1. Open the Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`).
2. Run **Chat: Export Chat**.
3. Save the `.json` into `prompt-logger/copilot/`.

### Cline (VS Code)

Copy `ui_messages.json` from the relevant task folder into `prompt-logger/cline/`. Task folders live at:

- macOS: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/`
- Windows: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\tasks\`
- Linux: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/`

### Any other tool

Find where your assistant stores its chat history, or use its export command, then commit the files under `prompt-logger/<your-tool-name>/`.