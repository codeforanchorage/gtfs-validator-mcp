# GTFS Validator MCP Server

MCP server that validates GTFS transit feeds using multiple validators and city-specific rules.

## Tools

| Tool | Description |
|------|-------------|
| `list_cities` | List all cities with validation configs |
| `get_config` | Get a city's validation rules |
| `validate` | Run MobilityData + Etalab validators on a feed |
| `diff` | Compare current vs incoming GTFS feed |
| `validate_and_diff` | Full validation + diff in one call |

## Setup on Replit

1. Create a new Replit from this directory
2. It will auto-run `setup.sh` to download validators
3. The server starts on stdio for MCP connections

## Adding a New City

Create a JSON file in `cities/` — see `cities/anchorage.json` for the format.

## Connecting to Claude Code

```json
{
  "mcpServers": {
    "gtfs-validator": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/replit-mcp-server"
    }
  }
}
```
