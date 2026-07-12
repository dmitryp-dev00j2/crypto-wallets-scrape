from typing import Dict, Type, Any

_PARSERS: Dict[str, Type] = {}

# Map common chain identifiers to their parser family
_CHAIN_ALIASES = {
    "ethereum": "evm",
    "eth": "evm",
    "arbitrum": "evm",
    "optimism": "evm",
    "polygon": "evm",
    "base": "evm",
    "bsc": "evm",
    "avalanche": "evm",
    "solana": "solana",
    "sol": "solana",
}

def register_parser(chain_type: str, parser_cls: Type) -> None:
    _PARSERS[chain_type.lower()] = parser_cls

def get_parser(chain_name: str) -> Any:
    key = chain_name.lower()
    family = _CHAIN_ALIASES.get(key, key)
    
    cls = _PARSERS.get(family)
    if not cls:
        # Lazy load to avoid circular imports
        if family == "evm":
            from walletscrape.parsers.evm import EvmParser
            register_parser("evm", EvmParser)
            cls = EvmParser
        elif family == "solana":
            from walletscrape.parsers.solana import SolanaParser
            register_parser("solana", SolanaParser)
            cls = SolanaParser
        else:
            raise ValueError(f"unsupported chain or parser family: {chain_name}")
    
    return cls()
