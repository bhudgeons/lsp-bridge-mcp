# Claude Code Setup for LSP Bridge

This guide shows how to configure Claude Code to automatically use LSP for compilation diagnostics instead of slow build tools like `sbt compile`.

## Overview

With this setup:
- ✅ **Auto-diagnostics**: Compilation runs automatically after every Scala file edit
- ✅ **No tool calls needed**: Just read `.lsp-bridge/diagnostics.json` after edits
- ✅ Real-time compilation feedback (~3 seconds vs 30+ seconds for sbt)
- ✅ No manual permission prompts for common operations

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

**After editing a Scala file, diagnostics are automatically updated.** Just read the diagnostics file:
```bash
sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
```

**If you need to manually trigger compilation or the diagnostics file doesn't exist:**
```
1. list_workspaces
2. trigger_compilation workspace="metals"
3. get_diagnostics workspace="metals"
```

**To look up type info, method signatures, or documentation:**
```
get_hover(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```

**To jump to a symbol's definition (instead of searching/grepping):**
```
get_definition(workspace="metals", file_path="/absolute/path/File.scala", line=10, character=15)
```
These are MUCH faster than searching through code or reading library source files.

## After EVERY File Edit (Auto-Diagnostics)

**A PostToolUse hook automatically triggers Metals compilation after every Scala file edit.**

Diagnostics are written to `<project>/.lsp-bridge/diagnostics.json`. To check:

```bash
sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq .
```

**Workflow:**
```
1. Edit a .scala file
2. Wait ~3 seconds (hook triggers compilation automatically)
3. Read diagnostics: cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
4. If errors found → Fix them immediately
5. Repeat until 0 errors
```

**If diagnostics file doesn't exist or seems stale**, fall back to manual LSP:
```
1. list_workspaces
2. trigger_compilation workspace="metals"
3. get_diagnostics workspace="metals"
```

## Example Workflow

```
User: "Fix the type error in Main.scala"

1. Read Main.scala to see the code
2. Check current errors: cat <project>/.lsp-bridge/diagnostics.json | jq .
3. Edit Main.scala to fix the error
4. Wait and check: sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
5. If errors remain: Fix them immediately
6. If no errors: Proceed or report success

NEVER skip step 4. NEVER assume the edit was correct.
NEVER use sbt compile - ALWAYS use LSP.
```

## Multiple Edits

When making multiple changes:

```
1. Edit File1.scala
2. sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
3. Fix any errors
4. Edit File2.scala
5. sleep 3 && cat <project>/.lsp-bridge/diagnostics.json | jq -c '{errors: .error_count}'
6. Fix any errors
```

**Check diagnostics after EACH edit, not just at the end.**

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

**Example:**
```
# To check what `println` does at line 5, column 4:
get_hover(workspace="metals", file_path="/Users/you/project/Main.scala", line=5, character=4)

# Returns:
# def println(x: Any): Unit
# Prints out an object to the default output, followed by a newline character.
# Parameters: x - the object to print.
```

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

**Example:**
```
# To find where `greet` is defined at line 18, column 18:
get_definition(workspace="metals", file_path="/Users/you/project/Main.scala", line=18, character=18)

# Returns:
# Definition found:
# 📍 /Users/you/project/Main.scala:21
# Use `Read` tool to view this file at line 21.
```

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
