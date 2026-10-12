# Contributing to heavymetalagent

Thanks for helping. This project signs real transactions, so correctness and safety matter more than features.

## Development setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/opensourcenjoyer/heavymetalnotfunagent && cd heavymetalnotfunagent
uv sync --extra dev
uv run heavymetal --help
```

Use a throwaway data directory while developing so you never touch your real wallet:

```bash
export HEAVYMETAL_HOME=$(mktemp -d)
uv run heavymetal --devnet
```

## Checks

Run these before pushing:

```bash
uv run ruff check .
uv run ruff format --check .     # `uv run ruff format .` to fix
uv run pytest -q
```

## Ground rules

- **Tests must be offline.** No network, no mainnet, no real keys. Use the fakes in `tests/conftest.py` (`FakeRPC`, `FakeDex`, `FakeDecider`) or `httpx.MockTransport`.
- **Never commit secrets.** API keys, RPC URLs with embedded keys, `wallet.json` and `config.toml` stay out of the repo, including in tests, fixtures and screenshots.
- **External text is untrusted.** Token names, descriptions, memos and web content must stay marked as untrusted in tool results. Don't let them reach anything that can move funds without going through the review.
- **Don't weaken the swap review** (`review.py`, `decide.py`, the registry gate) without an explicit discussion in an issue first. Changes there need tests covering the new verdict paths.
- **Keep it lightweight.** New dependencies need a good reason.
- Mainnet-only behavior (Jupiter, PumpPortal, launches) can't be tested in CI. If you change it, say in the PR how you verified it (e.g. tiny amounts on mainnet, `solana-test-validator`).

## Pull requests

1. For anything non-trivial, open an issue first to agree on the approach.
2. Keep PRs focused; one change per PR.
3. Add or update tests and add an entry under `## [Unreleased]` in `CHANGELOG.md`.
4. Describe what changed and how you verified it.
