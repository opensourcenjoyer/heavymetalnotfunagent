# heavymetalagent: Architecture

## Problem
Memecoin trading is spread across charts, safety checkers, wallet explorers, social platforms and swap UIs. Rookies miss red flags and get rugged. Existing agent kits have no memory, ledger or research workflow, and general agent frameworks are heavy.

## Solution
One lightweight Python agent: natural language in, research and execution out, from its own wallet.

**In one line:** a single async agent loop (DeepSeek V4 Flash or Claude) sends tool calls through a typed registry to thin Solana adapters. Every swap is first reviewed by a decisions model (TypeSafe Jev 1.13), then signed locally with the agent's own wallet. Sessions, trades and reviews live in SQLite. OpenRouter traffic is Zero Data Retention by default.

## Component view

```mermaid
flowchart TB
    User((User))

    subgraph UI["UI layer"]
        REPL["REPL<br/>prompt_toolkit + rich<br/>(default)"]
        TUI["Textual TUI (--tui)<br/>Browser via textual-serve (--web)"]
    end

    subgraph Core["Agent core"]
        LOOP["Agent loop<br/>agent.run_turn()"]
        PROMPT["Prompt builder<br/>system.md + wallet context"]
        PRUNE["Context builder<br/>sanitize + clip old results"]
        EXEC["Tool executor<br/>registry.execute()"]
        ENV["AgentEnv<br/>wallet, rpc, http, db"]
        REV["Swap review<br/>review.py: facts → stops → holds → release"]
    end

    subgraph Providers
        ANT["AnthropicProvider<br/>native Claude"]
        OAI["OpenAICompatProvider<br/>OpenRouter / Ollama / vLLM, ZDR"]
        JEV["DecisionsDecider<br/>Jev 1.x /alpha/decisions"]
        CHD["ChatDecider<br/>any chat model"]
    end

    subgraph Tools["Tool registry (async, JSON)"]
        T_WAL["wallet<br/>wallet_info, send, receive"]
        T_MKT["analyze<br/>token_audit, pool_info, rug_check,<br/>holders, trending, new_launches"]
        T_TRD["trade<br/>quote, swap, pump_trade,<br/>buy_with_tpsl, close_position"]
        T_LCH["launch<br/>launch_token, claim_creator_fees"]
        T_SCN["scan<br/>scan_wallet"]
        T_MEM["memory<br/>remember, recall, trade_history"]
    end

    subgraph Adapters
        A_RPC["rpc / nodes / tx<br/>sign, send, confirm, failover"]
        A_JUP[jupiter]
        A_PP[pumpportal]
        A_DS[dexscreener]
        A_RC[rugcheck]
        A_IPFS[ipfs]
        A_FC["fake_check / resolver"]
    end

    subgraph Store["Local state (~/.heavymetal)"]
        DB_S[("sessions<br/>messages")]
        DB_T[("trades ledger<br/>positions")]
        DB_R[("reviews<br/>usage")]
        DB_K[("knowledge<br/>FTS5")]
        KEY[/"wallet.json<br/>chmod 600"/]
    end

    subgraph External
        X_LLM[LLM APIs]
        X_RPC[Solana RPC]
        X_API["Jupiter / PumpPortal /<br/>Dexscreener / RugCheck"]
        X_IPFS[IPFS / Pinata]
    end

    User --> REPL & TUI
    REPL & TUI --> LOOP
    LOOP --> PROMPT & PRUNE
    LOOP --> ANT & OAI
    ANT & OAI --> X_LLM
    LOOP --> EXEC
    EXEC --> ENV
    EXEC -- "swap / pump_trade /<br/>buy_with_tpsl / close_position" --> REV
    REV --> JEV
    REV -. fallback .-> CHD
    REV --> DB_R
    JEV & CHD --> X_LLM
    EXEC --> T_WAL & T_MKT & T_TRD & T_LCH & T_SCN & T_MEM
    T_WAL & T_SCN --> A_RPC
    T_TRD --> A_JUP & A_PP
    T_TRD --> DB_T
    T_LCH --> A_PP & A_IPFS
    T_MKT --> A_DS & A_RC & A_FC
    A_JUP & A_PP --> A_RPC
    A_RPC --> KEY
    A_RPC --> X_RPC
    A_JUP & A_PP & A_DS & A_RC --> X_API
    A_IPFS --> X_IPFS
    T_MEM --> DB_K & DB_T
    LOOP --> DB_S
```

The loop runs LLM → tool_calls → [review] → execute → results → LLM … until `[DONE]` or `llm.max_iterations`. Ctrl+C interrupts the turn without quitting.

## Tool-call sequence

```mermaid
sequenceDiagram
    actor User
    participant L as Agent loop
    participant P as LLM provider
    participant E as Tool executor
    participant R as Swap review
    participant A as Adapters
    participant D as SQLite
    participant S as Solana RPC

    User->>L: "check $FROG, buy 0.1 SOL if safe"
    L->>D: load session + memory
    L->>P: messages + tool schemas
    P-->>L: tool_calls: token_audit, rug_check
    L->>E: execute
    E->>A: Dexscreener / RugCheck / RPC
    A-->>E: JSON (untrusted, wrapped)
    E-->>L: tool results
    L->>P: messages + results
    Note right of P: reasons on liquidity,<br/>authorities, holders
    P-->>L: tool_call: swap(SOL→FROG, 0.1)
    L->>E: execute swap
    E->>R: code facts + yes/no questions
    R-->>E: EXECUTE (or blocked verdict + hint)
    E->>A: Jupiter /order (or PumpPortal)
    A->>S: sign locally, send, confirm
    S-->>A: signature
    A->>D: write trades ledger
    E-->>L: {status, signature}
    L->>P: messages + result
    P-->>L: final answer [DONE]
    L->>D: persist turn
    L-->>User: summary + explorer link
```

## Why not existing agents
- General frameworks (e.g. Hermes Agent): heavy, no wallet model or tx pipeline.
- Chain toolkits (Solana Agent Kit, agentipy, Coinbase AgentKit): action libraries without memory, ledger or research loop.
- Telegram trading bots: closed source, ~1% fee per trade, no reasoning.

## Why Solana (vs Ethereum L1)
- **Speed:** ~0.4 s slots vs ~12 s blocks, and confirmation in seconds vs ~13 min finality.
- **Fees:** a 5,000-lamport base fee per signature vs a congestion-priced gas auction.
- **Simpler flow:** no approve step before swaps, and bonding-curve launches take one transaction.

Ethereum L2s narrow the gap, and the core is chain-agnostic, but most memecoin activity is on Solana.

## Layers
1. **UI**: prompt_toolkit/rich REPL (default, `heavymetal`), fullscreen Textual TUI (`heavymetal --tui`), browser mode via textual-serve (`heavymetal --web`). The core is UI-agnostic via `on_delta` / `on_tool` callbacks.
2. **Agent loop**: LLM call, parse tool calls, execute, feed results back; max iterations; Ctrl+C interrupt; context pruning.
3. **Provider layer**: native Anthropic provider (any `claude-*` model) + OpenAI-compatible provider (OpenRouter, Ollama, vLLM), streaming, `provider.zdr=true` + `data_collection=deny` on OpenRouter calls.
4. **Swap review** (`review.py` + `decide.py`): code facts → narrow yes/no questions (`user_requested`, `params_ok`, `manipulation`, `intended_repeat`, `fake_or_copycat`) → code holds → fixed-priority release. Jev 1.x answers all questions in one `/api/alpha/decisions` call with probabilities; any other model answers via chat prompts. Fails closed.
5. **Tool registry**: async functions returning JSON strings, with hand-written schemas.
6. **Adapters**: RPC with multi-node failover, Jupiter, PumpPortal, Dexscreener, RugCheck, IPFS, fake-token/homoglyph checks, link resolver.
7. **Storage**: SQLite (sessions, messages, trades, positions, reviews, usage, knowledge) under `~/.heavymetal/` (override with `HEAVYMETAL_HOME`).

## Transaction pipeline
[review for swaps] → build or fetch tx → sign locally (partial signing for co-signed Jupiter RFQ txs) → send via RPC → re-broadcast until confirmed / failed / blockhash expired → trades ledger.

## Risk model
- **No confirmations:** execution is autonomous.
- **Prompt injection:** untrusted inputs (token metadata, memos, web content) can carry it.
- **Key on disk:** the wallet key is stored locally.
- **Spending limit:** the wallet balance is the only cap, so fund it with small amounts.
- **TP/SL:** targets are tracked but not executed automatically.
