from decimal import Decimal
from typing import Dict, Any, List, Optional
from walletscrape.models import BalanceSnapshot, TokenTransfer

ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

class EvmParser:
    """Parses raw JSON-RPC responses from EVM-compatible nodes."""

    def parse_native_balance(self, raw_hex: str, decimals: int = 18) -> Decimal:
        if not raw_hex or raw_hex == "0x":
            return Decimal(0)
        wei = int(raw_hex, 16)
        return Decimal(wei) / Decimal(10 ** decimals)

    def parse_token_balance(self, raw_hex: str, decimals: int = 18) -> Decimal:
        if not raw_hex or raw_hex == "0x":
            return Decimal(0)
        val = int(raw_hex, 16)
        return Decimal(val) / Decimal(10 ** decimals)

    def build_balance_payload(self, address: str, req_id: int = 1) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "eth_getBalance",
            "params": [address, "latest"],
        }

    def build_token_balance_payload(self, contract: str, wallet: str, req_id: int = 1) -> Dict[str, Any]:
        # balanceOf(address) selector is 0x70a08231
        clean_addr = wallet.lower().replace("0x", "").zfill(64)
        data = f"0x70a08231{clean_addr}"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "eth_call",
            "params": [{"to": contract, "data": data}, "latest"],
        }

    def build_logs_filter(
        self,
        wallet: str,
        from_block: int,
        to_block: int,
        token_contracts: Optional[List[str]] = None,
        req_id: int = 1,
    ) -> List[Dict[str, Any]]:
        # EVM logs don't support OR between topic positions in standard RPC without multiple queries,
        # so we build two filters: one for incoming and one for outgoing transfers.
        wallet_padded = "0x" + wallet.lower().replace("0x", "").zfill(64)
        
        base_params: Dict[str, Any] = {
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        if token_contracts:
            base_params["address"] = token_contracts if len(token_contracts) > 1 else token_contracts[0]

        # incoming: Transfer(?, wallet)
        incoming_params = dict(base_params)
        incoming_params["topics"] = [ERC20_TRANSFER_TOPIC, None, wallet_padded]

        # outgoing: Transfer(wallet, ?)
        outgoing_params = dict(base_params)
        outgoing_params["topics"] = [ERC20_TRANSFER_TOPIC, wallet_padded]

        return [
            {"jsonrpc": "2.0", "id": req_id, "method": "eth_getLogs", "params": [incoming_params]},
            {"jsonrpc": "2.0", "id": req_id + 1, "method": "eth_getLogs", "params": [outgoing_params]},
        ]

    def parse_transfer_log(self, log: Dict[str, Any], target_address: str) -> Optional[TokenTransfer]:
        topics = log.get("topics", [])
        if not topics or topics[0].lower() != ERC20_TRANSFER_TOPIC:
            return None

        if len(topics) < 3:
            return None

        from_addr = "0x" + topics[1][-40:].lower()
        to_addr = "0x" + topics[2][-40:].lower()
        target = target_address.lower()

        if from_addr != target and to_addr != target:
            return None

        raw_data = log.get("data", "0x")
        # print(f"DEBUG raw_data: {raw_data}")
        if raw_data == "0x" and len(topics) == 4:
            # NFT or weird non-compliant ERC20 log
            amount_raw = int(topics[3], 16)
        else:
            # Normal ERC20 transfer amount is in data
            try:
                amount_raw = int(raw_data, 16) if raw_data != "0x" else 0
            except ValueError:
                amount_raw = 0

        # FIXME: Some contracts don't return bool on transfer/approve (looking at you USDT)
        block_num = int(log.get("blockNumber", "0x0"), 16)
        tx_hash = log.get("transactionHash", "")
        log_index = int(log.get("logIndex", "0x0"), 16)
        token_contract = log.get("address", "").lower()

        return TokenTransfer(
            chain="evm",
            tx_hash=tx_hash,
            block_number=block_num,
            log_index=log_index,
            token_address=token_contract,
            from_address=from_addr,
            to_address=to_addr,
            raw_amount=str(amount_raw),
            decimals=18,
        )

    def parse_batch_logs(self, responses: List[Dict[str, Any]], target_address: str) -> List[TokenTransfer]:
        transfers = []
        seen = set()

        for resp in responses:
            logs = resp.get("result", [])
            if not isinstance(logs, list):
                continue
            for log in logs:
                tx_transfer = self.parse_transfer_log(log, target_address)
                if not tx_transfer:
                    continue
                # deduplicate since log might match both filters if sender == receiver
                key = (tx_transfer.tx_hash, tx_transfer.log_index)
                if key in seen:
                    continue
                seen.add(key)
                transfers.append(tx_transfer)

        return sorted(transfers, key=lambda t: (t.block_number, t.log_index))
