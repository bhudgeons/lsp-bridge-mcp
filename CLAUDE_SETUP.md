# Claude Code Setup for LSP Bridge

This guide shows how to configure Claude Code to automatically use LSP for compilation diagnostics instead of slow build tools like `sbt compile`.

## Overview

With this setup:
- ✅ Claude automatically checks LSP for errors after every file edit
- ✅ Real-time compilation feedback (1-2 seconds vs 30+ seconds for sbt)
- ✅ No manual permission prompts for common operations
- ✅ Automatic Metals notification when files change

## Prerequisites

1. Install lsp-bridge-mcp (see main README.md)
2. Configure lsp-bridge for your project (see SETUP.md)
3. Have Claude Code installed

## Step 1: Configure MCP Server

Add lsp-bridge to your Claude MCP configuration.

### Installation Options

**Option A: Global Installation (Recommended)**

If you installed lsp-bridge globally with `pip install -e .`:

**File: `~/.claude.json`**

```json
{
  "mcpServers": {
    "lsp-bridge": {
      "command": "python",
      "args": ["-m", "lsp_bridge"]
    }
  }
}
```

**Option B: Virtual Environment Installation**

If you installed lsp-bridge in a venv, use the full path to the venv's Python:

**File: `~/.claude.json`**

```json
{
  "mcpServers": {
    "lsp-bridge": {
      "command": "/absolute/path/to/lsp-bridge-mcp/venv/bin/python",
      "args": ["-m", "lsp_bridge"]
    }
  }
}
```

Replace `/absolute/path/to/lsp-bridge-mcp` with your actual installation path.

**Why this matters:** Using the full path ensures the MCP server starts correctly after reboots without needing to activate the virtual environment.

**Note:** After adding this, restart Claude Code for the MCP server to load.

## Step 2: Configure Permissions

Auto-approve lsp-bridge tools so Claude can check compilation errors without prompting.

**File: `~/.claude/settings.json`**

Add to the `permissions.allow` array:

```json
{
  "permissions": {
    "allow": [
      "mcp__lsp-bridge",
      "mcp__lsp-bridge__list_workspaces",
      "mcp__lsp-bridge__get_diagnostics",
      "mcp__lsp-bridge__trigger_compilation",
      "mcp__lsp-bridge__get_status"
    ]
  }
}
```

## Step 3: Configure LSP-First Workflow

Add instructions to your global `~/.claude/CLAUDE.md` to make Claude use LSP instead of build tools.

**File: `~/.claude/CLAUDE.md`**

Add this section (customize for your language - example shows Scala/Metals):

```markdown
# Scala/LSP Development Workflow

**CRITICAL**: When working on Scala projects, ALWAYS use LSP (Language Server Protocol) via the lsp-bridge MCP server instead of sbt compile.

## FIRST STEP: When asked to check/fix errors

**BEFORE doing anything else, ALWAYS run these commands IN ORDER:**

1. `list_workspaces` - Initializes LSP workspace (may fail on first attempt in fresh session)
   - If fails with "No such tool available": **Tell the user to send any message to retry**
   - MCP tools become available between requests, not during a request
   - Automated retries within the same response will always fail
   - Once user sends a new message, the retry will succeed immediately
   - Example message: "MCP server is still initializing. Please type 'continue' or any message, and I'll retry immediately."
2. `trigger_compilation workspace="metals"` - Ensures Metals compiles the code
3. `get_diagnostics workspace="metals"` - Retrieves compilation errors

**NEVER:**
- Skip calling list_workspaces first
- Do automated retries if list_workspaces fails (they will always fail - need a new user message)
- Immediately fall back to sbt on first failure (ask user to retry first)
- Assume LSP tools aren't available without asking user to retry
- Use `sbt compile` before asking user to retry LSP
- Read files manually to find errors before checking LSP

## After EVERY File Edit

**MANDATORY**: After editing ANY Scala file, check LSP diagnostics:

1. Make an edit to a .scala file
2. Wait 1-2 seconds for Metals to process the change
3. Use trigger_compilation tool with workspace="metals" to ensure compilation
4. Use get_diagnostics tool with workspace="metals" to check for errors
5. If errors found → Fix them immediately
6. Repeat until LSP shows 0 errors

**Never proceed to the next edit without confirming the current edit has no errors (unless the error is expected because you're writing code in stages).**

## LSP Initialization Pattern

**First LSP operation in a session:**
1. **Call list_workspaces first** - may fail with "No such tool available"
2. **If it fails, ask user to send any message** - tools register between requests
3. **Retry after user message** - will succeed immediately
4. **Then call get_diagnostics** or other tools - these will work instantly

**Example:**
```
1. Call list_workspaces → "No such tool available"
2. Tell user: "MCP server initializing. Please type 'continue' and I'll retry."
3. User sends message → New request starts
4. Call list_workspaces → Works immediately
5. Call get_diagnostics workspace="metals" → Works instantly
6. All subsequent LSP calls work instantly
```

**If LSP tools fail with "No such tool available":**
1. **This means MCP server is still initializing** (tools register between requests, not during requests)
2. **Do NOT do automated retries - they will all fail**
3. **Instead, ask the user to send any message to retry**
4. When user sends a new message, retry list_workspaces - it will succeed immediately
5. Only fall back to `sbt compile` if the second attempt (after user message) also fails

**CRITICAL: MCP tools become available between requests. Automated retries within the same response will ALWAYS fail. You MUST wait for a new user message to start a new request.**

## Why LSP Instead of sbt

- **Faster**: LSP is real-time (1-2s), sbt is slow (30-60s)
- **Always running**: LSP is already monitoring
- **Integrated**: LSP is part of the editor workflow
- **Precise**: LSP shows exact locations
- **Auto-approved**: No permission popups

## When to Use sbt

Use sbt ONLY for:
- Running tests: `sbt test`
- Running application: `sbt run`
- Publishing: `sbt publish`
- Packaging: `sbt assembly`
- Initial project setup

**For compilation checking: ALWAYS use LSP.**
```

## Step 4: Configure Post-Edit Hooks (Optional but Recommended)

Automatically notify Metals when files change so diagnostics update immediately.

**File: `~/.claude/settings.json`**

Add to the `hooks` section:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/notify-metals.sh",
            "statusMessage": "Syncing with Metals..."
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/notify-metals.sh",
            "statusMessage": "Syncing with Metals..."
          }
        ]
      }
    ]
  }
}
```

**File: `~/.claude/hooks/notify-metals.sh`**

```bash
#!/bin/bash
# Touch the edited file to trigger Metals file watcher
if [ -n "$CLAUDE_TOOL_RESULT" ]; then
  # Extract file path from Edit/Write tool result
  FILE_PATH=$(echo "$CLAUDE_TOOL_RESULT" | grep -o '/[^"]*\.scala' | head -1)
  if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
    touch "$FILE_PATH"
  fi
fi
```

Make it executable:
```bash
chmod +x ~/.claude/hooks/notify-metals.sh
```

## Step 5: Test the Setup

1. **Start a fresh Claude Code session**
2. **Navigate to a Scala project** with Bloop configured
3. **Ask Claude**: "fix errors"
4. **Expected behavior**:
   - Claude tries `list_workspaces`
   - If it's the first attempt in a fresh session, it may fail with "No such tool available"
   - Claude says: "MCP server is initializing. Please type 'continue' or any message, and I'll retry immediately."
   - You type: "continue" (or any message)
   - Claude retries `list_workspaces` → Works immediately
   - Claude calls `trigger_compilation` and `get_diagnostics`
   - Claude shows you the errors

## Troubleshooting

### "No such tool available" - even after retry

**Symptom:** Even after sending a message to retry, tools still aren't available.

**Solution:** Check if lsp-bridge MCP server is running:
```bash
# Check Claude's MCP server list
claude mcp list

# Should show lsp-bridge with status "running"
```

If not running, check `~/.claude.json` configuration and restart Claude Code.

### LSP shows 0 errors but sbt compile shows errors

**Symptom:** LSP reports no errors, but sbt compile finds errors.

**Solution:** Check if Bloop is configured:
```bash
# Check if .bloop directory exists
ls .bloop/

# If not, generate Bloop configuration
sbt bloopInstall

# Wait for Metals to detect Bloop
sleep 3
```

Metals requires Bloop (Build Server Protocol) for compilation diagnostics.

### Diagnostics are stale after editing

**Symptom:** LSP doesn't show new errors after editing files.

**Solution:**
1. Ensure post-edit hooks are configured (Step 4)
2. Manually call `trigger_compilation` after edits
3. Wait 1-2 seconds for Metals to process changes

### Permission prompts every time

**Symptom:** Claude asks for permission to use LSP tools.

**Solution:** Check `~/.claude/settings.json` has lsp-bridge tools in `permissions.allow` (Step 2).

## Language-Specific Notes

### Scala with Metals

- Requires Bloop: `sbt bloopInstall`
- First compilation takes 10-15 seconds
- Subsequent checks are near-instant
- Workspace name: usually "metals"

### Rust with rust-analyzer

- No additional setup required
- Workspace name: usually "rust"
- Very fast compilation checks

### TypeScript with typescript-language-server

- Requires tsconfig.json
- Workspace name: usually "typescript"
- Incremental compilation is fast

## Advanced Configuration

### Multiple Projects

If you work on multiple projects, use project-specific `.mcp.json`:

**File: `/path/to/project/.mcp.json`**

```json
{
  "mcpServers": {
    "lsp-bridge": {
      "command": "python",
      "args": [
        "-m",
        "lsp_bridge",
        "${projectDir}/lsp-bridge-config.json"
      ]
    }
  }
}
```

### Custom Workspace Names

In your CLAUDE.md, replace "metals" with your workspace name:
- Scala → "metals"
- Rust → "rust"
- TypeScript → "typescript"
- Custom → whatever you named it in config.json

## Summary

After this setup:
1. ✅ Claude uses LSP instead of slow build tools
2. ✅ Real-time error checking after every edit
3. ✅ No permission prompts
4. ✅ Automatic Metals synchronization
5. ✅ First-class LSP integration

The key insight: **MCP tools register between requests**, so if the first attempt fails, just send any message and retry - it will work immediately.
