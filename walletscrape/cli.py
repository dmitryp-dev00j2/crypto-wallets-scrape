import argparse
import sys
from pathlib import Path
from walletscrape.config import load_config
from walletscrape.client import MultiChainClient
from walletscrape.storage import SQLiteStorage, JSONLStorage

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="walletscrape",
        description="Scrape balances and token transfers for whale wallets.",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("wallets.toml"),
        help="Path to config file (default: wallets.toml)",
    )
    parser.add_argument("--chain", choices=["eth", "arb", "polygon", "bsc", "solana"], help="Filter run to single chain")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = subparsers.add_parser("run", help="Fetch current balances and write snapshot")
    run_p.add_argument("--out-db", type=Path, default=Path("snapshots.db"), help="SQLite output path")
    run_p.add_argument("--jsonl", type=Path, default=None, help="Optional JSONL export path")
    run_p.add_argument("--dry-run", action="store_true", help="Print output without saving")
    run_p.add_argument("-v", "--verbose", action="store_true", help="Print token zero balances too")

    # history / transfers
    hist_p = subparsers.add_parser("transfers", help="Fetch recent token transfer logs")
    hist_p.add_argument("--limit", type=int, default=50, help="Max transfer events per wallet (default 50)")
    hist_p.add_argument("--out-db", type=Path, default=Path("snapshots.db"))
    hist_p.add_argument("--jsonl", type=Path, default=None)

    # list
    subparsers.add_parser("list", help="Show configured wallets and endpoints")
    return parser

def run_cmd(args) -> int:
    cfg = load_config(args.config)
    if args.chain:
        cfg.wallets = [w for w in cfg.wallets if w.chain == args.chain]
        if not cfg.wallets:
            print(f"No wallets configured for chain '{args.chain}'", file=sys.stderr)
            return 1

    client = MultiChainClient(cfg)
    print(f"Fetching balances for {len(cfg.wallets)} target(s)...")
    snapshots = client.fetch_all_snapshots()

    if args.dry_run:
        for snap in snapshots:
            print(f"\n[{snap.chain.upper()}] {snap.label or snap.address}")
            print(f"  Native: {snap.native_balance:.6f} {snap.native_symbol}")
            for tok in snap.tokens:
                if tok.amount <= 0.0 and not args.verbose:
                    continue
                usd_txt = f" (~${tok.usd_value:.2f})" if tok.usd_value is not None else ""
                print(f"  - {tok.symbol:<8} {tok.amount:>14.4f}{usd_txt}")
        return 0

    db = SQLiteStorage(args.out_db)
    db.init_tables()
    db.save_snapshots(snapshots)
    print(f"Saved {len(snapshots)} snapshot(s) to {args.out_db}")

    if args.jsonl:
        jstore = JSONLStorage(args.jsonl)
        jstore.append_snapshots(snapshots)
        print(f"Appended records to {args.jsonl}")

    return 0

def transfers_cmd(args) -> int:
    cfg = load_config(args.config)
    if args.chain:
        cfg.wallets = [w for w in cfg.wallets if w.chain == args.chain]
    
    client = MultiChainClient(cfg)
    events = client.fetch_recent_transfers(limit_per_wallet=args.limit)
    print(f"Found {len(events)} recent transfer events")

    db = SQLiteStorage(args.out_db)
    db.init_tables()
    saved_count = db.save_transfers(events)
    print(f"Stored {saved_count} new events in {args.out_db}")

    if args.jsonl:
        JSONLStorage(args.jsonl).append_transfers(events)
    return 0

def list_cmd(args) -> int:
    cfg = load_config(args.config)
    print(f"Config: {args.config}")
    print(f"Wallets ({len(cfg.wallets)} total):")
    for w in cfg.wallets:
        lbl = f" ({w.label})" if w.label else ""
        custom_toks = f" [{len(w.tokens)} tracked tokens]" if w.tokens else ""
        print(f"  [{w.chain:<8}] {w.address}{lbl}{custom_toks}")
    return 0

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return run_cmd(args)
    elif args.command == "transfers":
        return transfers_cmd(args)
    elif args.command == "list":
        return list_cmd(args)
    return 1
