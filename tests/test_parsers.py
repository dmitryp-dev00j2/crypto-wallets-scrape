from decimal import Decimal
import pytest

from walletscrape.parsers.evm import (
    parse_hex_int,
    decode_log_address,
    parse_erc20_transfer,
    format_units,
)
from walletscrape.parsers.solana import (
    lamports_to_sol,
    parse_token_balance,
    parse_spl_transfer_instruction,
)


TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def test_parse_hex_int():
    assert parse_hex_int("0x0") == 0
    assert parse_hex_int("0x1") == 1
    assert parse_hex_int("0x10") == 16
    assert parse_hex_int("0xde0b6b3a7640000") == 1000000000000000000
    assert parse_hex_int(None) == 0
    assert parse_hex_int("") == 0


def test_decode_log_address():
    padded = "0x000000000000000000000000dac17f958d2ee523a2206206994597c13d831ec7"
    assert decode_log_address(padded) == "0xdac17f958d2ee523a2206206994597c13d831ec7"

    short = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    assert decode_log_address(short) == "0xdac17f958d2ee523a2206206994597c13d831ec7"


def test_format_units():
    assert format_units(1000000000000000000, 18) == Decimal("1.0")
    assert format_units(500000, 6) == Decimal("0.5")
    assert format_units(0, 18) == Decimal("0")
    assert format_units(12345, 0) == Decimal("12345")


def test_parse_erc20_transfer_valid():
    raw_log = {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "topics": [
            TRANSFER_TOPIC,
            "0x00000000000000000000000028c6c06298d514db089934071355e5743bf21d60",
            "0x000000000000000000000000503828976d22510aad0201ac7ec88293211d23dc",
        ],
        "data": "0x0000000000000000000000000000000000000000000000000000000005f5e100",
        "blockNumber": "0x112a880",
        "transactionHash": "0xabc123",
        "logIndex": "0x14",
    }

    tx = parse_erc20_transfer(raw_log, decimals=6, symbol="USDC")
    assert tx is not None
    assert tx["from_addr"] == "0x28c6c06298d514db089934071355e5743bf21d60"
    assert tx["to_addr"] == "0x503828976d22510aad0201ac7ec88293211d23dc"
    assert tx["amount"] == Decimal("100.0")
    assert tx["symbol"] == "USDC"
    assert tx["block_number"] == 18000000


def test_parse_erc20_transfer_insufficient_topics():
    # missing 'to' topic or transfer with non-standard indexed params
    raw_log = {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "topics": [TRANSFER_TOPIC, "0x00000000000000000000000028c6c06298d514db089934071355e5743bf21d60"],
        "data": "0x05f5e100",
        "blockNumber": "0x1",
    }
    assert parse_erc20_transfer(raw_log) is None


def test_solana_lamports_to_sol():
    assert lamports_to_sol(1000000000) == Decimal("1.0")
    assert lamports_to_sol(500000000) == Decimal("0.5")
    assert lamports_to_sol(0) == Decimal("0")


def test_solana_parse_token_balance():
    item = {
        "accountIndex": 1,
        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "owner": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
        "uiTokenAmount": {
            "amount": "150000000",
            "decimals": 6,
            "uiAmount": 150.0,
            "uiAmountString": "150",
        },
    }
    res = parse_token_balance(item)
    assert res["mint"] == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert res["owner"] == "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
    assert res["amount"] == Decimal("150")
    assert res["decimals"] == 6


def test_solana_parse_token_balance_missing_ui_amount():
    # RPC nodes sometimes omit uiAmount float when balance is too large
    item = {
        "mint": "So11111111111111111111111111111111111111112",
        "owner": "4fYNw3dojWmQ4dXtSGE9epjRGy9pFSx62YypT7qn4o79",
        "uiTokenAmount": {
            "amount": "2500000000",
            "decimals": 9,
            "uiAmount": None,
            "uiAmountString": "2.5",
        },
    }
    res = parse_token_balance(item)
    assert res["amount"] == Decimal("2.5")


def test_solana_spl_transfer_instruction():
    parsed_ix = {
        "parsed": {
            "info": {
                "amount": "1000000",
                "authority": "6i38bTssL4C4mY6xVjX2vTjZ7K6vM7z8pB8wE",
                "destination": "8bTssL4C4mY6xVjX2vTjZ7K6vM7z8pB8wE6i3",
                "source": "4mY6xVjX2vTjZ7K6vM7z8pB8wE6i38bTssL4C",
            },
            "type": "transfer",
        },
        "program": "spl-token",
    }
    res = parse_spl_transfer_instruction(parsed_ix, decimals=6)
    assert res is not None
    assert res["amount"] == Decimal("1.0")
    assert res["source"] == "4mY6xVjX2vTjZ7K6vM7z8pB8wE6i38bTssL4C"
