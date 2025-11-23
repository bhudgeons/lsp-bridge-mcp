# LSP Bridge MCP Server

Connect Claude Code to Language Server Protocol (LSP) servers for real-time compilation diagnostics, errors, warnings, and more.

## 🎯 Features

- **Real-time Diagnostics**: See compilation errors and warnings as they happen
- **Multi-Language Support**: Works with any LSP server (Metals, rust-analyzer, typescript-language-server, etc.)
- **MCP Resources**: Diagnostics exposed as readable resources
- **MCP Tools**: Query diagnostics, trigger compilation, check status
- **Zero Configuration**: Works out of the box with sensible defaults

## 🚀 Quick Start

**For detailed Claude Code setup including CLAUDE.md configuration, see [CLAUDE_SETUP.md](CLAUDE_SETUP.md)**

### 1. Install

**Option A: Global Installation (Recommended)**

Install globally so it's always available:

```bash
cd lsp-bridge-mcp
pip install -e .
```

**Option B: Virtual Environment Installation**

If you prefer using a virtual environment:

```bash
cd lsp-bridge-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

Note: If using a venv, you'll need to specify the full path to the venv's Python in your MCP config (see Step 3 below).

### 2. Create Configuration

Create `config.json` in your project or home directory:

```json
{
  "servers": [
    {
      "name": "metals",
      "workspace_root": "/path/to/your-scala-project",
      "command": ["metals"]
    }
  ]
}
```

### 3. Configure Claude Code

Add to `~/.claude.json`:

**If installed globally (Option A):**

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

**If installed in a venv (Option B):**

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

Or for a specific project, create `.mcp.json` in your project directory:

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

**⚠️ Important: First Use in Fresh Sessions**

MCP tools register between requests, not during requests. In a fresh Claude session:
1. First `list_workspaces` call may fail with "No such tool available"
2. Send any message to Claude (e.g., "continue")
3. Retry immediately - it will work

See [CLAUDE_SETUP.md](CLAUDE_SETUP.md) for instructions on configuring Claude to handle this automatically.

### 4. Use in Claude Code

Once configured, Claude can:

#### View Resources
```
Claude can see resources like:
- lsp://metals/diagnostics/all
- lsp://metals/diagnostics/src/main/scala/YourFile.scala
```

#### Use Tools
```
- get_diagnostics(workspace: "metals")
- get_diagnostics(workspace: "metals", file_path: "src/main/scala/File.scala")
- trigger_compilation(workspace: "metals")
- get_status(workspace: "metals")
- list_workspaces()
```

#### Use Prompts
```
Claude can use the "analyze_diagnostics" prompt to get AI-powered analysis of compilation errors
```

## 📖 Usage Examples

### Example 1: Check All Diagnostics

In Claude Code:
```
Read the resource lsp://metals/diagnostics/all
```

Claude will see all compilation errors and warnings.

### Example 2: Analyze Specific File

```
Use get_diagnostics tool with workspace="metals" and file_path="src/main/scala/MyFile.scala"
```

### Example 3: Trigger Compilation

```
Use trigger_compilation tool with workspace="metals"
```

Claude will trigger a full compilation and report results.

### Example 4: Auto-Analysis

```
Use the analyze_diagnostics prompt for workspace="metals"
```

Claude will analyze all errors, suggest fixes, and prioritize them.

## 📚 Documentation

- **[CLAUDE_SETUP.md](CLAUDE_SETUP.md)** - Complete setup for Claude Code including CLAUDE.md workflow
- **[SETUP.md](SETUP.md)** - General installation and configuration
- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide
- **[WORKFLOW.md](WORKFLOW.md)** - Example workflows
- **[PERMISSIONS.md](PERMISSIONS.md)** - Permission configuration
- **[HOOKS_SETUP.md](HOOKS_SETUP.md)** - Post-edit hooks for auto-sync

## 🔧 Configuration

### Metals (Scala)

```json
{
  "servers": [
    {
      "name": "metals",
      "workspace_root": "/path/to/scala/project",
      "command": ["metals"]
    }
  ]
}
```

### rust-analyzer (Rust)

```json
{
  "servers": [
    {
      "name": "rust",
      "workspace_root": "/path/to/rust/project",
      "command": ["rust-analyzer"]
    }
  ]
}
```

### typescript-language-server (TypeScript)

```json
{
  "servers": [
    {
      "name": "typescript",
      "workspace_root": "/path/to/ts/project",
      "command": ["typescript-language-server", "--stdio"]
    }
  ]
}
```

### Multiple Workspaces

```json
{
  "servers": [
    {
      "name": "backend",
      "workspace_root": "/path/to/backend",
      "command": ["metals"]
    },
    {
      "name": "frontend",
      "workspace_root": "/path/to/frontend",
      "command": ["typescript-language-server", "--stdio"]
    }
  ]
}
```

## 🛠️ Available Tools

### `get_diagnostics`
Get compilation errors and warnings.

**Parameters:**
- `workspace` (required): Workspace name (e.g., "metals")
- `file_path` (optional): Specific file to get diagnostics for

**Returns:** JSON with errors, warnings, and their locations

### `trigger_compilation`
Trigger compilation in the LSP server (if supported).

**Parameters:**
- `workspace` (required): Workspace name

**Returns:** Compilation result

### `get_status`
Get the current status of LSP servers.

**Parameters:**
- `workspace` (optional): Specific workspace to check

**Returns:** Status including error/warning counts

### `list_workspaces`
List all connected LSP server workspaces.

**Returns:** Array of workspace names

## 📊 Diagnostic Format

Diagnostics are returned in this format:

```json
{
  "summary": {
    "total_files": 5,
    "total_diagnostics": 12,
    "errors": 3,
    "warnings": 9,
    "info": 0
  },
  "by_file": {
    "/path/to/File.scala": [
      {
        "severity": "ERROR",
        "line": 42,
        "character": 10,
        "message": "type mismatch",
        "source": "metals",
        "code": "type-mismatch"
      }
    ]
  }
}
```

## 🐛 Debugging

Logs are written to `/tmp/lsp-bridge-mcp.log`:

```bash
tail -f /tmp/lsp-bridge-mcp.log
```

## 🔍 How It Works

1. **LSP Client**: Connects to language servers via stdio
2. **Message Handling**: Subscribes to `textDocument/publishDiagnostics` notifications
3. **State Management**: Maintains current diagnostics for all files
4. **MCP Exposure**: Exposes diagnostics as MCP resources and tools
5. **Real-time Updates**: Diagnostics update automatically as you code

## 🎨 Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│ Claude Code │ ◄─MCP──►│ LSP Bridge   │ ◄─LSP──►│   Metals    │
│             │         │ MCP Server   │         │   Server    │
└─────────────┘         └──────────────┘         └─────────────┘
                              │
                              ├─ Resources (diagnostics)
                              ├─ Tools (get_diagnostics, etc.)
                              └─ Prompts (analyze_diagnostics)
```

## 📝 License

MIT

## 🤝 Contributing

Contributions welcome! This is a community project.

## 🚀 Roadmap

- [ ] Code actions support
- [ ] Hover information
- [ ] Go to definition
- [ ] Find references
- [ ] Rename support
- [ ] Auto-format on save
- [ ] Incremental document sync
- [ ] Multi-root workspace support
- [ ] LSP server auto-discovery
- [ ] Hot reload configuration
