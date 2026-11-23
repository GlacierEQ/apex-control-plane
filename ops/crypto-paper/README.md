# $59 Coinbase-sized paper run (Hummingbot + Condor preparation)

## Operator acceptance correction — unfunded but actually running

Passing a Hummingbot strategy simulation and Condor unit tests **does not**
make a working Hummingbot + Condor system. The separate
`crypto-empty-stack-e2e.yml` workflow is the end-to-end gate for the next stage.
It starts the real authenticated Hummingbot API, PostgreSQL, MQTT broker,
Condor local dashboard, and a keyless local Ollama model at fixed upstream
commits, then requires all of the following at the same time:

- Hummingbot API doctor succeeds, the broker connects, and API authentication
  works against the live stack.
- Condor starts, local login works, its own API server selector reports
  `online`, and the official Condor doctor reports no failures.
- The local LLM generates an actual response rather than only reporting that
  a model name is configured.
- Every Hummingbot account has **zero exchange credentials** and there are
  **zero cached asset balances and zero running trading bots**. No deposit,
  payment, or Coinbase connection.

The verification script `verify-empty-stack.py` fails closed on any missing
stage. A GitHub-hosted successful run proves an **ephemeral unfunded stack**,
not a persistent deployment on the Hermes Mac. Operational deployment must
repeat the same proof on its actual host before it can be called ready.

The November 23, 2026 ephemeral readback first reached `EMPTY_STACK_READY`
in GitHub Actions run `45170418663`: the API doctor showed 22 passes and zero
failures, and Condor doctor showed 12 passes and zero failures. The source
remains gated on the current PR head and on re-running after any modification.
The Mac's existing DeepSeek-R1 model is now serving locally through Ollama,
but its Docker daemon is still stopped; the external NTFS volume cannot
host Colima's required Unix sockets. No persistent API/Condor installation
has been claimed.

This is a **native Hummingbot paper run**, not a home-built trading simulator.
The $59 is the simulated USD balance, **not a connection to the user's Coinbase funds**.
No Coinbase credentials, API keys, deposits, withdrawals, orders, or real assets are accessed.

## Verified upstream boundary

- Hummingbot: https://github.com/hummingbot/hummingbot (release `v2.18.0`).
- Condor: https://github.com/hummingbot/condor (AI agent orchestration built on Hummingbot API).
- Condor upstream commit used for isolated tests: `97d9261afcbad6977e92c4eb520a09c8da84ad32`.
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
upstream image. That workflow also installs Condor from its locked upstream
dependencies and runs five focused upstream test modules (87 assertions/tests
at the pinned commit) covering leverage and risk gates, pinned-server refusals,
write scope, and session readiness. Both checks must pass before Mac deployment.

The Mac's Hermes stack remains untouched. On November 23, 2026, its container
daemon was stopped, its internal disk had approximately 1.6 GiB available,
and its system load was elevated. Its external `My Passport` volume had ample
space, but no container runtime has been relocated or started there. Mac
installation is **not** verified and must not be inferred from the CI run.

## Exact safety properties

- Starting simulated cash: **$59 USD**; starting simulated BTC: **0**.
- Connector: `kraken_paper_trade` only. This is public-data paper mode, not Coinbase.
- Market: BTC-USD; maximum *configured base order size* `0.0001 BTC`.
- Bid/ask spread: 0.5% each side; refresh every 120 seconds.
- No leverage, Coinbase trade keys, transfers, or LLM inference.
- No claim of fee-adjusted edge: paper fills and actual execution quality differ.

## Integration boundary

Condor is **not** configured to place trades here. Its upstream risk tests
do not establish end-to-end Condor-to-Hummingbot API behavior. After both CI
checks pass and the Mac has capacity, install its official harness, run
`make doctor`, and connect its Hummingbot API to a dedicated paper-only bot
before introducing any LLM model.
Do not give an autonomous agent a wallet, Coinbase trading permission, or
live exchange route during this simulation stage.
