# walletscrape

CLI tool I put together to track balances and token transfers across EVM chains (Ethereum, Arbitrum, Optimism, Base, Polygon, BSC) and Solana without paying for indexed API tiers when direct node RPCs and explorer endpoints work fine.

Saves structured snapshots into SQLite or append-only JSONL files so you can query them with duckdb or standard SQL.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy the example env if you want explorer API keys for fallback history:

```bash
cp .env.example .env
```

## Config format

`wallets.json` supports both EVM hex addresses and Solana base58 keys:

```json
{
  "rpc_endpoints": {
    "ethereum": "https://eth.llamarpc.com",
    "base": "https://mainnet.base.org",
    "solana": "https://api.mainnet-beta.solana.com"
  },
  "explorer_keys": {
    "etherscan": "YOUR_ETHERSCAN_KEY"
  },
  "tokens": {
    "ethereum": [
      "0xdac17f958d2ee523a2206206994597c13d831ec7",
      "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    ],
    "solana": [
      "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    ]
  },
  "wallets": [
    {
      "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
      "chain": "ethereum",
      "label": "vitalik.eth"
    },
    {
      "address": "52C9T2TqcsMzhDaZCsoKUPhuZd84eStWzTLddTdBJUpm",
      "chain": "solana",
      "label": "sol-whale-1"
    }
  ]
}
```

## Usage

Fetch current native + token balances:

```bash
walletscrape balances -c wallets.json --db data/snapshots.db
```

Stream recent token transfers into JSONL:

```bash
walletscrape transfers -c wallets.json --format jsonl --out data/transfers.jsonl --days 7
```

Run both in one pass with live terminal summary:

```bash
walletscrape sync -c wallets.json --db data/snapshots.db
```

## Running tests

```bash
pytest
```

<!-- last-sync: 2026-09-11 -->
