from decimal import Decimal
from typing import Any, Dict, List, Optional

LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def parse_sol_balance(wallet: str, rpc_result: Dict[str, Any], timestamp: int) -> Dict[str, Any]:
    val = rpc_result.get("value", rpc_result) if isinstance(rpc_result, dict) else rpc_result
    lamports = int(val)
    amount = Decimal(lamports) / Decimal(LAMPORTS_PER_SOL)
    return {
        "chain": "solana",
        "wallet": wallet,
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "SOL",
        "raw_amount": str(lamports),
        "amount": float(amount),
        "decimals": 9,
        "timestamp": timestamp,
    }


def parse_spl_token_accounts(wallet: str, rpc_result: Dict[str, Any], timestamp: int) -> List[Dict[str, Any]]:
    items = []
    value_list = rpc_result.get("value", [])
    if not isinstance(value_list, list):
        return items

    for entry in value_list:
        # print(f"DEBUG raw solana acc: {entry}")
        account_data = entry.get("account", {}).get("data", {})
        if not isinstance(account_data, dict):
            continue

        parsed = account_data.get("parsed", {})
        info = parsed.get("info", {})
        token_amount = info.get("tokenAmount", {})

        mint = info.get("mint")
        if not mint:
            continue

        raw_amt = token_amount.get("amount", "0")
        decimals = token_amount.get("decimals", 0)
        ui_amt = token_amount.get("uiAmount")

        if ui_amt is None:
            try:
                amt = float(Decimal(raw_amt) / Decimal(10 ** int(decimals)))
            except (ArithmeticError, ValueError):
                amt = 0.0
        else:
            amt = float(ui_amt)

        if raw_amt == "0" or amt == 0.0:
            continue

        items.append({
            "chain": "solana",
            "wallet": wallet,
            "token_address": mint,
            "symbol": None,
            "raw_amount": str(raw_amt),
            "amount": amt,
            "decimals": int(decimals),
            "timestamp": timestamp,
        })

    return items


def parse_transaction_transfers(tx_response: Dict[str, Any], target_wallet: str) -> List[Dict[str, Any]]:
    """Extract token movements from parsed Solana transaction json."""
    transfers = []
    if not tx_response:
        return transfers

    meta = tx_response.get("meta", {})
    if meta.get("err") is not None:
        return transfers

    tx = tx_response.get("transaction", {})
    message = tx.get("message", {})
    instructions = list(message.get("instructions", []))
    
    # inner instructions from CPI calls (DEX swaps, wrappers)
    for inner_wrap in meta.get("innerInstructions", []):
        instructions.extend(inner_wrap.get("instructions", []))

    sig = tx.get("signatures", [""])[0] if tx.get("signatures") else ""
    block_time = tx_response.get("blockTime", 0)
    slot = tx_response.get("slot", 0)

    for ix in instructions:
        if not isinstance(ix, dict):
            continue
        program = ix.get("program")
        program_id = ix.get("programId")
        
        is_spl = program in ("spl-token", "spl-token-2022") or program_id in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID)
        if not is_spl:
            continue

        parsed = ix.get("parsed", {})
        if not isinstance(parsed, dict):
            continue
            
        ix_type = parsed.get("type")
        info = parsed.get("info", {})

        if ix_type in ("transfer", "transferChecked"):
            source = info.get("source")
            dest = info.get("destination")
            authority = info.get("authority", info.get("owner"))
            raw_amt = info.get("amount") or info.get("tokenAmount", {}).get("amount", "0")
            mint = info.get("mint", "")
            decimals = info.get("tokenAmount", {}).get("decimals", 0)

            transfers.append({
                "tx_hash": sig,
                "chain": "solana",
                "wallet": target_wallet,
                "from_addr": authority or source,
                "to_addr": dest,
                "token_address": mint,
                "raw_amount": str(raw_amt),
                "decimals": int(decimals) if decimals else 0,
                "slot": slot,
                "timestamp": block_time,
            })

    return transfers
