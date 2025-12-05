# Claude Code Setup for LSP Bridge

This guide shows how to configure Claude Code to automatically use LSP for compilation diagnostics instead of slow build tools like `sbt compile`.

## Overview

With this setup:
- ✅ **Auto-diagnostics**: Compilation runs automatically after every Scala file edit
- ✅ **No tool calls needed**: Just read `.lsp-bridge/diagnostics.json` after edits
- ✅ Real-time compilation feedback (~3 seconds vs 30+ seconds for sbt)
- ✅ No manual permission prompts for common operations

## Prerequisites

1. **Metals on your PATH** (for Scala projects):
   ```bash
   # Install via Coursier
   coursier install metals

   # Verify it's on your PATH
   metals --version
   ```
   If `metals --version` doesn't work, add Coursier's bin directory to your PATH:
   ```bash
   # Add to ~/.bashrc, ~/.zshrc, or ~/.profile
   export PATH="$PATH:$HOME/Library/Application Support/Coursier/bin"  # macOS
   export PATH="$PATH:$HOME/.local/share/coursier/bin"                 # Linux
   ```
   **Important:** After updating your PATH, restart your terminal or run `source ~/.bashrc` (or equivalent) before starting Claude Code.

2. Install lsp-bridge-mcp (see main README.md)
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

**Note:** After adding this, restart Claude Code for the MCP server to load.

## Step 2: Configure Permissions

Auto-approve lsp-bridge tools so Claude can check compilation errors without prompting.

**File: `~/.claude/settings.json`**

Add to the `permissions.allow` array:

```json
{
  "permissions": {
    "allow": [
      "mcp__lsp-bridge"
    ]
  }
}
```

## Step 3: Configure PostToolUse Hook (Required for Auto-Diagnostics)

This is the key to auto-diagnostics. The hook triggers compilation automatically after every Scala file edit.

**File: `~/.claude/settings.json`**

Add to the `hooks` section:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/notify-metals.sh"
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
# Read JSON from stdin and notify lsp-bridge for Scala files
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -n "$FILE_PATH" && "$FILE_PATH" == *.scala ]]; then
    sleep 0.3
    echo "$FILE_PATH" > /tmp/lsp-bridge-notify.txt
fi
```

Make it executable:
```bash
mkdir -p ~/.claude/hooks
chmod +x ~/.claude/hooks/notify-metals.sh
```

**How it works:**
1. Claude edits a `.scala` file
2. Hook writes file path to `/tmp/lsp-bridge-notify.txt`
3. MCP server watcher detects the change, sends `didChange` to Metals
4. Metals compiles and publishes diagnostics
5. Diagnostics written to `<project>/.lsp-bridge/diagnostics.json`
6. Claude reads the diagnostics file (no permission prompt needed)

## Step 4: Configure CLAUDE.md

Add instructions to your global `~/.claude/CLAUDE.md` to make Claude use the auto-diagnostics flow.

**File: `~/.claude/CLAUDE.md`**

```markdown
# Scala/LSP Development Workflow

**CRITICAL**: When working on Scala projects, ALWAYS use LSP (Language Server Protocol) via the lsp-bridge MCP server instead of sbt compile.

## TL;DR - READ THIS FIRST

**NEVER run `sbt compile` or `sbt test:compile` to check for errors.**

**After editing a Scala file, just wait 3 seconds and read the diagnostics file:**
```bash
sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
```
A PostToolUse hook automatically triggers compilation - you do NOT need to call `trigger_compilation` manually.

**To look up type info, method signatures, or documentation:**
```
get_hover(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```

**To jump to a symbol's definition (instead of searching/grepping):**
```
get_definition(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```
These are MUCH faster than searching through code or reading library source files.

**Only use manual LSP tools if the diagnostics file doesn't exist:**
```
1. list_workspaces
2. trigger_compilation workspace="metals"
3. get_diagnostics workspace="metals"
```

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
- Run `sbt compile` to check for compilation errors
- Run `sbt test:compile` to check test compilation
- Skip calling list_workspaces first
- Do automated retries if list_workspaces fails (they will always fail - need a new user message)
- Immediately fall back to sbt on first failure (ask user to retry first)

## Bloop Setup Check (BEFORE Using LSP)

**CRITICAL**: Before using LSP diagnostics in a Scala project, ALWAYS check if Bloop is configured:

```bash
# 1. Check if .bloop exists
if [ ! -d .bloop ]; then
  # 2. Ensure sbt-bloop plugin is configured
  if ! grep -q "sbt-bloop" project/plugins.sbt 2>/dev/null; then
    echo 'addSbtPlugin("ch.epfl.scala" % "sbt-bloop" % "1.5.11")' >> project/plugins.sbt
  fi

  # 3. Generate Bloop configuration
  sbt bloopInstall

  # 4. Wait for Metals to detect Bloop
  sleep 3
fi
```

**Why this matters:**
- Without Bloop, LSP will show 0 errors even when errors exist
- Metals requires Bloop (Build Server Protocol) for compilation diagnostics

## After EVERY File Edit (Auto-Diagnostics)

**A PostToolUse hook automatically triggers Metals compilation after every Scala file edit.**

**You do NOT need to call `trigger_compilation` or `get_diagnostics` manually!** Just read the file:

```bash
sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
```

**Workflow:**
```
1. Edit a .scala file
2. Wait ~3 seconds (hook triggers compilation automatically)
3. Read diagnostics file: cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
4. If errors found → Fix them immediately
5. Repeat until 0 errors
```

**IMPORTANT:** Do NOT use `trigger_compilation` after edits - the hook already did it. Just read the diagnostics file.

**Only fall back to manual LSP tools if the diagnostics file doesn't exist:**
```
1. list_workspaces
2. trigger_compilation workspace="metals"
3. get_diagnostics workspace="metals"
```

**Never proceed to the next edit without confirming the current edit has no errors (unless the error is expected because you're writing code in stages).**

## Proactive LSP Usage

**IMPORTANT: Use LSP tools proactively, not just when stuck.** These tools are faster and more accurate than searching/reading files:

| Instead of... | Use LSP... |
|---------------|------------|
| Reading a file to find a method's return type | `get_hover` on the method call |
| Grepping/searching to find where something is defined | `get_definition` on the symbol |
| Reading library source files to understand an API | `get_hover` for signature + docs |
| Guessing at type signatures | `get_hover` to confirm |

**When you see a method call and need to understand its signature or return type, use `get_hover` BEFORE reading the source file.** It's faster and gives you exactly what you need.

**When you need to navigate to a definition, use `get_definition` BEFORE using search/grep.** It jumps directly to the right location.

## Using Hover for Type Information

**Use `get_hover` to instantly look up type signatures, documentation, and scaladoc** instead of searching through code or reading library source files.

```
get_hover(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```

**Parameters:**
- `workspace`: Always "metals" for Scala
- `file_path`: **Absolute path** to the file (not relative)
- `line`: 1-indexed line number (as shown in editors)
- `character`: 0-indexed column position

**Use cases:**
- Look up method signatures: `def foo(x: Int, y: String): Option[Result]`
- Get case class field definitions
- View scaladoc/documentation for standard library or third-party functions
- Check type inference results for `val` or `var`
- Understand what a symbol is without reading its source file

**When to use hover vs reading files:**
- ✅ Use hover: Quick type lookups, method signatures, library docs
- ✅ Use hover: Understanding what a symbol is at a specific location
- ❌ Don't use hover: Understanding control flow or reading full implementations

## Using Go to Definition

**Use `get_definition` to jump directly to where a symbol is defined** instead of searching/grepping through code.

```
get_definition(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```

**Parameters:** Same as `get_hover` (workspace, file_path, line, character)

**Use cases:**
- Navigate to method implementations
- Find class/trait/object definitions
- Jump to where a variable is declared
- Explore library source code (Metals extracts sources from JARs)

## Why LSP Instead of sbt

- **Faster**: LSP is real-time (~3s), sbt is slow (30-60s)
- **Automatic**: Hook triggers compilation, no manual tool calls
- **Always running**: LSP is already monitoring
- **Precise**: LSP shows exact locations
- **No prompts**: Reading .lsp-bridge/ doesn't need permission
- **Hover info**: Instantly get type signatures and documentation
- **Go to definition**: Jump directly to symbol definitions

## When to Use sbt

Use sbt ONLY for:
- Running tests: `sbt test`
- Running application: `sbt run`
- Publishing: `sbt publish`
- Packaging: `sbt assembly`
- Initial project setup

**For compilation checking: ALWAYS use LSP via auto-diagnostics.**
```

## Step 5: Test the Setup

1. **Restart Claude Code** to pick up all configuration changes
2. **Navigate to a Scala project** with Bloop configured
3. **Ask Claude**: "introduce an error in Main.scala and then fix it"
4. **Expected behavior**:
   - Claude edits the file
   - Hook triggers automatically
   - Claude reads `.lsp-bridge/diagnostics.json`
   - Claude sees the error and fixes it
   - Claude verifies 0 errors

## Troubleshooting

### Diagnostics file doesn't exist

**Symptom:** `<project>/.lsp-bridge/diagnostics.json` doesn't exist after edits.

**Solution:**
1. Check if Metals is running: `tail /tmp/lsp-bridge-mcp.log`
2. Manually trigger: Use `list_workspaces`, then `trigger_compilation`
3. Check Bloop is configured: `ls .bloop/`

### Hook doesn't trigger

**Symptom:** `/tmp/lsp-bridge-notify.txt` isn't updated after edits.

**Solution:**
1. Check hook is configured in `~/.claude/settings.json`
2. Check hook script exists and is executable: `ls -la ~/.claude/hooks/notify-metals.sh`
3. Test hook manually: `echo '{"tool_input":{"file_path":"test.scala"}}' | ~/.claude/hooks/notify-metals.sh`

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

### Diagnostics are stale

**Symptom:** Diagnostics file shows old errors.

**Solution:**
1. Check hook is triggering: `stat /tmp/lsp-bridge-notify.txt`
2. Check MCP logs: `tail /tmp/lsp-bridge-mcp.log`
3. Manually trigger compilation with LSP tools

### MCP tools not available

**Symptom:** "No such tool available" when trying manual LSP commands.

**Solution:**
1. MCP tools register between requests - send any message and retry
2. Check MCP server is configured in `~/.claude.json`
3. Restart Claude Code

## Summary

After this setup:
1. ✅ Automatic compilation after every Scala edit
2. ✅ Just read `.lsp-bridge/diagnostics.json` for errors
3. ✅ No manual tool calls needed
4. ✅ No permission prompts
5. ✅ ~3 second feedback loop
6. ✅ Instant type lookups with `get_hover`
7. ✅ Jump to definitions with `get_definition`

The key insights:
- **PostToolUse hooks enable automatic compilation**, so Claude just needs to read a file to get diagnostics
- **Hover provides instant type information**, so Claude doesn't need to search through code or libraries
- **Go to definition navigates directly to symbols**, eliminating the need to search/grep for implementations
