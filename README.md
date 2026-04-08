# GTFS Validator MCP Server

An [MCP](https://modelcontextprotocol.io/) server that validates GTFS transit feeds using multiple validation passes and city-specific rules. Designed to be called by Claude Code (or any MCP client) to automate feed review, diffing, and PR generation for transit data updates.

Hosted on [Replit](https://replit.com/) and currently configured for [Anchorage People Mover](https://www.muni.org/Departments/transit/PeopleMover/).

## How it works

The server pulls GTFS feeds directly from GitHub repos, runs them through two independent validators, applies configurable city-specific rules, and returns structured JSON results. This lets an AI assistant validate and compare feeds without needing local tooling installed.

```
GitHub repo (GTFS feeds)
        |
        v
  +-----------------+
  | MCP Server      |
  |  1. MobilityData|  <-- spec compliance (Java)
  |  2. Etalab      |  <-- practical checks (Rust)
  |  3. City rules  |  <-- custom thresholds
  |  4. Diff engine |  <-- current vs incoming
  +-----------------+
        |
        v
  Structured JSON results --> Claude Code --> PRs
```

## Tools

| Tool | Description |
|------|-------------|
| `list_cities` | List all configured cities and their agencies |
| `get_config` | Get a city's full validation config and rules |
| `validate` | Run MobilityData + Etalab validators on a feed (`current` or `incoming`) |
| `validate_url` | Validate a GTFS zip from any URL (useful for checking agency feeds before import) |
| `diff` | Compare current vs incoming feed: routes, stops, trips, calendars, fares, with geographic drift detection |
| `validate_and_diff` | All-in-one: validate incoming + diff against current |

## Validation passes

### Pass 1: MobilityData canonical validator
The [MobilityData GTFS Validator](https://github.com/MobilityData/gtfs-validator) (v7.1.0) checks spec compliance — required fields, valid references, format rules. Runs as a Java JAR.

### Pass 2: Etalab transport-validator
The [Etalab transport-validator](https://github.com/etalab/transport-validator) runs practical quality checks that go beyond spec compliance. Built from source (Rust).

### Pass 3: City-specific rules
Custom rules defined per city in `cities/*.json`. These catch agency-specific issues:

- **Expected counts** — agency count, fare count
- **Required files** — which GTFS files must be present
- **Change thresholds** — warn if trip/stop/route counts change by more than N%
- **Geographic drift** — flag stops that moved more than N meters between feeds
- **Fare validation** — fares must not be empty

## Diff engine

The `diff` tool compares current and incoming feeds with:

- **File-level summary** — row counts, deltas, percentage changes for all GTFS files
- **Route diff** — added, removed, and modified routes (field-level changes)
- **Stop diff** — added/removed stops plus **geographic drift detection** using haversine distance
- **Trip diff** — added/removed/modified trips with field-level change detail
- **Calendar diff** — service ID changes and date range modifications
- **Fare diff** — fare attribute changes
- **City rule checks** — threshold violations flagged as warnings or errors

## City configuration

Each city has a JSON config file in `cities/`. Example (`cities/anchorage.json`):

```json
{
  "city": "Anchorage",
  "state": "AK",
  "agency": "Municipality of Anchorage People Mover",
  "agency_id": "0",
  "repo": "codeforanchorage/gtfs_update",
  "current_path": "People_Mover_2025",
  "incoming_path": "New_People_Mover_2025",
  "feed_source_url": "https://prior-url-for-gtfs-download",
  "timezone": "America/Anchorage",
  "rules": {
    "expected_agency_count": 1,
    "expected_fare_count": 1,
    "required_files": ["agency.txt", "calendar.txt", "..."],
    "max_stop_location_drift_meters": 50,
    "trip_count_change_warning_pct": 30,
    "stop_count_change_warning_pct": 20,
    "route_count_change_warning_pct": 25,
    "require_shapes": true,
    "require_feed_info": true,
    "fare_must_not_be_empty": true
  }
}
```

To add a new city, create a new JSON file in `cities/` following this structure. The `repo` field points to the GitHub repo containing the GTFS feeds, and `current_path`/`incoming_path` specify the directories within that repo.

## Deployment on Replit

The server is designed to run on Replit. The `.replit` config handles the full setup:

1. `setup.sh` downloads the MobilityData JAR and builds the Etalab validator from source
2. Python dependencies are installed from `requirements.txt`
3. The server starts on port 8080 with SSE transport

### System dependencies (via `replit.nix`)
- Python 3.11
- JDK 17 (for MobilityData validator)
- Rust/Cargo (for building Etalab validator)
- curl, gcc, OpenSSL, pkg-config

### Python dependencies
- `mcp` — Model Context Protocol SDK
- `httpx` — HTTP client for GitHub API calls
- `uvicorn` + `starlette` — ASGI server for SSE transport

## Connecting to Claude Code

Add to your Claude Code MCP settings (`~/.claude/settings.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "gtfs-validator": {
      "type": "sse",
      "url": "https://your-replit-url.replit.app/sse"
    }
  }
}
```

For local development, you can run the server directly:

```json
{
  "mcpServers": {
    "gtfs-validator": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/gtfs-validator-mcp"
    }
  }
}
```

## Project structure

```
├── server.py              # MCP server with all tool definitions
├── gtfs_diff.py           # Feed diff engine (routes, stops, trips, calendars, fares)
├── validators/
│   ├── mobilitydata.py    # MobilityData JAR wrapper
│   └── etalab.py          # Etalab binary wrapper
├── cities/
│   └── anchorage.json     # City-specific validation config
├── setup.sh               # Downloads/builds validator binaries
├── replit.nix             # Nix dependencies for Replit
├── requirements.txt       # Python dependencies
└── .replit                # Replit run configuration
```

## Typical workflow

1. A transit agency publishes a new GTFS feed
2. The feed is placed in the `incoming_path` directory of the GitHub repo
3. Claude Code calls `validate` to check the incoming feed for errors
4. Claude Code calls `diff` to compare incoming against current
5. Based on results, Claude Code creates targeted PRs for each logical change group (fares, calendar, trips, shapes, etc.)
6. After review and merge, the incoming feed becomes the current feed

## License

MIT
