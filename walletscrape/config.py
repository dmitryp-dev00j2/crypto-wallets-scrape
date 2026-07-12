import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_RPCS = {
    "eth": "https://eth.llamarpc.com",
    "arb": "https://arb1.arbitrum.io/rpc",
    "polygon": "https://polygon-rpc.com",
    "bsc": "https://binance.llamarpc.com",
    "solana": "https://api.mainnet-beta.solana.com",
}

EVM_CHAINS = {"eth", "arb", "polygon", "bsc", "optimism", "base"}
_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")

def _expand_env_vars(text: str) -> str:
    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default)
    return _ENV_VAR_RE.sub(replace, text)

@dataclass
class WalletTarget:
    address: str
    chain: str
    label: Optional[str] = None
    tokens: List[str] = field(default_factory=list)

    def normalized_address(self) -> str:
        if self.chain in EVM_CHAINS:
            # EVM RPCs expect standard lowercase or eip55, lowercase avoids set collision
            return self.address.lower()
        return self.address  # solana addresses are base58 and case-sensitive

@dataclass
class AppConfig:
    wallets: List[WalletTarget] = field(default_factory=list)
    rpc_endpoints: Dict[str, str] = field(default_factory=dict)
    explorer_keys: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 20.0
    retry_attempts: int = 3

    def get_rpc(self, chain: str) -> str:
        c = chain.lower()
        if c in self.rpc_endpoints:
            return self.rpc_endpoints[c]
        if c in DEFAULT_RPCS:
            return DEFAULT_RPCS[c]
        raise ValueError(f"No RPC endpoint configured or known for chain '{chain}'")

def _validate_target(addr: str, chain: str) -> None:
    if chain in EVM_CHAINS:
        if not re.match(r"^0x[a-fA-F0-9]{40}$", addr):
            raise ValueError(f"Invalid EVM address '{addr}' for chain '{chain}'")
    elif chain == "solana":
        if not (32 <= len(addr) <= 44):
            # crude length check for base58 solana pubkey
            raise ValueError(f"Suspicious Solana address length '{addr}'")

def load_config(path: Path) -> AppConfig:
    """Reads TOML config, expands ${VAR:default} env patterns, and validates targets."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")

    raw_content = path.read_text(encoding="utf-8")
    expanded = _expand_env_vars(raw_content)
    data = tomllib.loads(expanded)

    rpc_map = dict(DEFAULT_RPCS)
    for chain_key, url in data.get("rpcs", {}).items():
        if url and isinstance(url, str):
            rpc_map[chain_key.lower()] = url.strip()

    seen = set()
    targets = []
    for raw_target in data.get("wallets", []):
        addr = raw_target["address"].strip()
        chain = raw_target.get("chain", "eth").lower()
        _validate_target(addr, chain)

        # print(f"debug: parsing target {addr} on {chain}")
        target = WalletTarget(
            address=addr,
            chain=chain,
            label=raw_target.get("label"),
            tokens=[t.strip() for t in raw_target.get("tokens", [])],
        )
        unique_key = (target.chain, target.normalized_address())
        if unique_key not in seen:
            seen.add(unique_key)
            targets.append(target)

    general = data.get("general", {})
    return AppConfig(
        wallets=targets,
        rpc_endpoints=rpc_map,
        explorer_keys=data.get("keys", {}),
        timeout_seconds=float(general.get("timeout", 20.0)),
        retry_attempts=int(general.get("retries", 3)),
    )
