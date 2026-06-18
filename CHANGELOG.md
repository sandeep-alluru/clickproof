# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-18

### Added
- Content-addressed `UIFact` and `FactObservation` data model backed by SQLite
- `FactStore` — SQLite-backed persistence for UIFacts and observations
- `FactScorer` — confidence scoring with staleness decay and count boost
- `FactRetriever` — query by app/version/element with min_score threshold
- `bootstrap_context()` — text summary for agent system prompt injection
- Rich terminal output, JSON, and Markdown formatters
- Click CLI: `add`, `observe`, `query`, `log`, `status` subcommands
- FastAPI REST server: `/fact`, `/observe`, `/query`, `/facts`, `/bootstrap`, `/health`
- MCP server (`clickproof-mcp`) with `add_ui_fact`, `query_facts`, `bootstrap_context` tools
- 109 unit tests across all layers with 87%+ branch coverage

[Unreleased]: https://github.com/sandeep-alluru/clickproof/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/clickproof/releases/tag/v0.1.0
