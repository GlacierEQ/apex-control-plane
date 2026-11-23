#!/usr/bin/env bash
# Execute Hummingbot's native paper-trading engine. This script has no live-trade path.
set -euo pipefail

if ! command -v hbot >/dev/null 2>&1; then
  echo 'Hummingbot hbot CLI is required; see ops/crypto-paper/README.md' >&2
  exit 1
fi

# No Coinbase connection or exchange-trading credentials are needed.
# A fresh Hummingbot profile is required: do not overwrite another paper
# account's balances or attempt to restart an already-loaded strategy.
config_name='glaciereq_59_paper.yml'
if hbot config --json 2>/dev/null | grep -Fq "$config_name"; then
  echo "A config named $config_name is already loaded; refusing to overwrite it" >&2
  exit 1
fi

hbot config paper_trade.paper_trade_account_balance '{"USD":59,"BTC":0}'
hbot create simple_pmm --name "$config_name" \
  --set exchange=kraken_paper_trade \
  --set trading_pair=BTC-USD \
  --set order_amount=0.0001 \
  --set bid_spread=0.005 \
  --set ask_spread=0.005 \
  --set order_refresh_time=120

# Verify the loaded native Hummingbot strategy is the paper connector.
exchange_config="$(hbot config exchange --json)"
if ! printf '%s' "$exchange_config" | grep -Fq 'kraken_paper_trade'; then
  echo 'Refusing to start: native strategy is not on kraken_paper_trade' >&2
  exit 1
fi

hbot start "$config_name"
hbot status --json
