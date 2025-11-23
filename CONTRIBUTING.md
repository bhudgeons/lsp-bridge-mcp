# Contributing to LSP Bridge MCP

Thank you for your interest in contributing! This project bridges Claude Code to Language Server Protocol (LSP) servers, enabling real-time compilation diagnostics.

## Getting Started

### Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lsp-bridge-mcp
   ```

2. **Install dependencies**
   ```bash
   pip install -e .
   ```

3. **Create a configuration**
   ```bash
   cp config.example.json config.json
   # Edit config.json with your LSP server details
   ```

4. **Run tests**
   ```bash
   python test_manual.py
   ```

## Project Structure

```
lsp-bridge-mcp/
├── src/lsp_bridge/
│   ├── lsp_client.py    # LSP protocol client implementation
│   └── server.py        # MCP server implementation
├── test_manual.py       # Manual testing script
└── config.json          # LSP server configuration
```

## Architecture Overview

### LSP Client (`lsp_client.py`)
- Handles communication with LSP servers via stdio
- Implements JSON-RPC 2.0 protocol
- Manages LSP lifecycle (initialize, shutdown)
- Subscribes to diagnostic notifications

### MCP Server (`server.py`)
- Exposes LSP data as MCP resources, tools, and prompts
- Manages multiple LSP workspace connections
- Formats diagnostics for Claude Code

## Adding Support for New LSP Servers

To add support for a new language:

1. **Test the LSP server manually**
   ```json
   {
     "servers": [
       {
         "name": "your-language",
         "workspace_root": "/path/to/project",
         "command": ["your-lsp-server", "--stdio"]
       }
     ]
   }
   ```

2. **Verify it works**
   ```bash
   python test_manual.py
   ```

3. **Add example to README.md**
   - Add configuration example
   - Document any special setup requirements

## Development Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings for public functions
- Keep functions focused and small

### Logging
- Use the existing logger: `logging.getLogger("lsp-bridge")`
- Log important events at INFO level
- Log errors and exceptions at ERROR level
- Use DEBUG for detailed protocol messages

### Error Handling
- Catch and log exceptions gracefully
- Return meaningful error messages in MCP responses
- Don't let LSP errors crash the MCP server

## Testing

### Manual Testing
```bash
python test_manual.py
```

This connects to your configured LSP server and verifies:
- Connection establishment
- Initialization handshake
- Diagnostic reception

### Testing with Claude Code

1. Configure MCP server in `~/.claude.json`
2. Start Claude Code
3. Use MCP tools:
   - `list_workspaces`
   - `get_diagnostics`
   - `trigger_compilation`

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clear, focused commits
   - Update documentation as needed
   - Test thoroughly

3. **Submit PR**
   - Describe what you changed and why
   - Reference any related issues
   - Ensure tests pass

4. **Code review**
   - Address review feedback
   - Keep discussion focused and respectful

## Common Contributions

### Adding Language Support
Most valuable contribution! Follow "Adding Support for New LSP Servers" above.

### Improving Documentation
- Fix typos or unclear explanations
- Add examples
- Improve setup instructions

### Bug Fixes
- Report bugs in GitHub issues
- Include reproduction steps
- Submit fix with test case

### Feature Requests
- Open an issue first to discuss
- Explain the use case
- Consider implementation complexity

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers get started
- Keep discussions on-topic

## Questions?

- Check the [README.md](README.md) for basic setup
- Check [CLAUDE_SETUP.md](CLAUDE_SETUP.md) for Claude Code integration
- Open a GitHub issue for bugs or feature requests
- Start a discussion for general questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
