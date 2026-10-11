# FreeCAD MCP (hardened fork)

> **This is a security-hardened fork of [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) v0.1.26.**
> Differences from upstream:
>
> - **Mandatory auth token** on both the FreeCAD addon and the MCP server.
> - **`execute_code_headless` removed** (it bypassed the token).
> - **RPC limits**: 2 MiB request bodies, at most 8 concurrent requests.
> - **Code filter** for `execute_code`: allowed imports only, no `open`/`eval`/dunder access (defense in depth, not a sandbox).
>
> Read [SECURITY.md](SECURITY.md) for the audit and recommended deployment, and
> [CHANGELOG.md](CHANGELOG.md) for the full list. Install from this repository,
> not from the `freecad-mcp` PyPI package (see [Quick start](#quick-start)).
> All credit for the original project goes to its authors.

<p align="left">
 <a href="https://www.star-history.com/neka-nat/freecad-mcp">
  <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/badge?repo=neka-nat/freecad-mcp&type=trending&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/badge?repo=neka-nat/freecad-mcp&type=trending" />
   <img alt="GitHub Trending Repository of the Day" src="https://api.star-history.com/badge?repo=neka-nat/freecad-mcp&type=trending" />
  </picture>
 </a>
</p>

[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/neka-nat-freecad-mcp-badge.png)](https://mseep.ai/app/neka-nat-freecad-mcp)

Control FreeCAD from Claude Desktop and other MCP clients. Create and edit models,
run Python scripts, inspect documents, and run FEM analyses.

## Demo

Design a flange:

![Designing a flange in FreeCAD](./assets/freecad_mcp4.gif)

See [more demos and examples](docs/examples.md) for a toy car, modelling from a
2D drawing, and agent integrations.

## Quick start

You need FreeCAD and [uv / uvx](https://docs.astral.sh/uv/guides/tools/).
FreeCAD MCP has two components: an addon running inside FreeCAD and an MCP server
launched by your client.

### 1. Install and start the FreeCAD addon

```bash
git clone --branch hardened https://github.com/jesuslayer/freecad-mcp.git
cd freecad-mcp
```

Copy `addon/FreeCADMCP` into your [FreeCAD addon directory](docs/installation.md#addon-directory),
then restart FreeCAD. Select the **MCP Addon** workbench, click **Set Auth Token**
in the **FreeCAD MCP** toolbar and leave the field blank to generate a token
(it is copied to the clipboard). Then click **Start RPC Server**.

See the [installation guide](docs/installation.md) for platform-specific commands
and screenshots.

### 2. Connect Claude Desktop

Add the following entry to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/jesuslayer/freecad-mcp@hardened", "freecad-mcp"],
      "env": { "FREECAD_MCP_TOKEN": "<the token generated in FreeCAD>" }
    }
  }
}
```

For Claude Code:

```bash
claude mcp add freecad -e FREECAD_MCP_TOKEN=<token> -- uvx --from git+https://github.com/jesuslayer/freecad-mcp@hardened freecad-mcp
```

Restart Claude Desktop to load the configuration, keep FreeCAD open with its RPC
server running, and ask Claude to create a model. Connections use `localhost` by
default.

## Documentation

| Guide | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Addon directories, setup screenshots, running from source |
| [Configuration](docs/configuration.md) | Auto-start, text feedback, remote connections |
| [Tools](docs/tools.md) | Available tools, screenshots, FEM analysis |
| [Code execution](docs/execution.md) | GUI execution, background jobs, timeout troubleshooting |
| [Demos and examples](docs/examples.md) | Design demos, FEM example, ADK and LangChain integrations |

## Contributors

<a href="https://github.com/neka-nat/freecad-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=neka-nat/freecad-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
