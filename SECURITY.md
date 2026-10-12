# Security Policy

heavymetalagent holds a private key and signs transactions autonomously. Security bugs here can lose people money, so please report them privately.

## Reporting a vulnerability

**Do not open a public issue, PR or discussion.**

Report privately via GitHub: go to the repository's **Security** tab, then **Report a vulnerability** ([direct link](https://github.com/opensourcenjoyer/heavymetalnotfunagent/security/advisories/new)).

Please include:
- what an attacker can do and what they need (e.g. "a token description can make the agent send SOL")
- steps or a proof of concept, ideally on devnet or with mocked data
- affected version or commit

We aim to acknowledge reports within 72 hours and to agree on a disclosure timeline with you. Credit is given in the advisory unless you prefer otherwise.

## In scope

- **Key handling:** leaking the wallet key or API keys (logs, tool results, model prompts, file permissions).
- **Swap review bypass:** getting a swap or trade signed that the review gate should block, or a fail-open path when the reviewer errors.
- **Prompt injection that moves funds:** untrusted text (token metadata, memos, web content, RPC responses) causing a transfer, trade, launch or RPC switch the user did not ask for.
- **RPC redirection:** making the agent use an RPC node the user did not save.
- **Transaction integrity:** signing transactions whose contents differ from what was quoted or reviewed (e.g. a malicious Jupiter/PumpPortal response).
- **Web mode (`--web`)** exposing the agent to other machines or users without the operator's intent.

## Out of scope

- Losses from trading decisions the user asked for, or from tokens that are simply bad investments.
- The model making a wrong call within its documented limits (see "Risks" in the README). A reliable, reproducible way to make it wrong *is* in scope.
- Vulnerabilities in third-party services (Jupiter, PumpPortal, Dexscreener, RugCheck, LLM providers). Report those to the vendor.
- Attacks that need prior access to the user's machine or `~/.heavymetal`.

## Supported versions

| Version | Supported |
|---|---|
| 0.0.x (latest) | yes |

Only the latest release gets security fixes during 0.x.
