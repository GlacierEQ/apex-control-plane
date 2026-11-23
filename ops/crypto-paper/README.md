# $59 Coinbase-sized paper run (Hummingbot + Condor preparation)

This is a **native Hummingbot paper run**, not a home-built trading simulator.
The $59 is the simulated USD balance, **not a connection to the user's Coinbase funds**.
No Coinbase credentials, API keys, deposits, withdrawals, orders, or real assets are accessed.

## Verified upstream boundary

- Hummingbot: https://github.com/hummingbot/hummingbot (release `v2.18.0`).
- Condor: https://github.com/hummingbot/condor (AI agent orchestration built on Hummingbot API).
- The Coinbase Advanced Hummingbot connector supports live spot orders **but does not provide paper trading** as of the September 2026 connector documentation: https://hummingbot.org/exchanges/coinbase/.
- Hummingbot **does** support native paper trading for Kraken: https://hummingbot.org/client/global-configs/paper-trade/.
- Official setup: https://hummingbot.org/installation/hummingbot-client/.

This setup exercises Hummingbot's real strategy engine and paper-order flow against
Kraken's public BTC-USD order book. It does **not** claim to validate Coinbase order
execution, Coinbase pricing, profitability, or the Condor LLM control plane.
Those are separate follow-on validations before any live-money proposal.

## On the Mac (when the Mac bridge is available)

1. Check free disk space, Docker Desktop, and existing Hummingbot/Hermes workers;
   do not replace an active install or reuse an account's live profile.
2. Clone and inspect the Hummingbot `v2.18.0` release into an isolated workspace.
3. In that Hummingbot checkout, run `make setup` (answer **No** to Gateway),
   `make deploy`, and `make link-cli`. To use the `hbot` CLI reliably in Docker,
   set the documented `command: tail -f /dev/null` for the Hummingbot service
   before deploying the container.
4. Use a **fresh isolated** `conf/` directory/profile. Set a local keystore
   password through Hummingbot's secure input mechanism; never commit it.
5. Run `bash /path/to/apex-control-plane/ops/crypto-paper/start-hummingbot-paper.sh`
   from within the Hummingbot setup where `hbot` is available.
6. Observe `hbot status --json`, `hbot logs`, and `hbot history`. Stop with
   `hbot stop` when the observation window is complete.

The same script is exercised by the repository's GitHub Actions paper smoke
workflow, which uses an isolated ephemeral Docker runner and Hummingbot's
upstream image. It must pass before treating this as runnable on the Mac.

## Exact safety properties

- Starting simulated cash: **$59 USD**; starting simulated BTC: **0**.
- Connector: `kraken_paper_trade` only. This is public-data paper mode, not Coinbase.
- Market: BTC-USD; maximum *configured base order size* `0.0001 BTC`.
- Bid/ask spread: 0.5% each side; refresh every 120 seconds.
- No leverage, Coinbase trade keys, transfers, or LLM inference.
- No claim of fee-adjusted edge: paper fills and actual execution quality differ.

## Integration boundary

Condor is **not** configured to place trades here. After native paper execution
passes, install its official harness, run `make doctor`, and connect its
Hummingbot API to a dedicated paper-only bot before introducing any LLM model.
Do not give an autonomous agent a wallet, Coinbase trading permission, or
live exchange route during this simulation stage.
