from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any


@dataclass
class WalletTarget:
    """Wallet to monitor across configured networks."""
    address: str
    label: str = ""
    chains: list[str] = field(default_factory=lambda: ["ethereum"])
    tags: list[str] = field(default_factory=list)


@dataclass
class NativeBalance:
    chain: str
    wallet: str
    raw_amount: int
    decimals: int
    timestamp: datetime
    amount: Decimal = Decimal(0)

    def __post_init__(self):
        if self.amount == Decimal(0) and self.decimals >= 0:
            self.amount = Decimal(self.raw_amount) / Decimal(10 ** self.decimals)


@dataclass
class TokenHolding:
    chain: str
    wallet: str
    token_address: str
    symbol: str
    name: str
    raw_balance: int
    decimals: int
    timestamp: datetime
    balance: Decimal = Decimal(0)
    usd_price: Optional[Decimal] = None

    def __post_init__(self):
        if self.balance == Decimal(0) and self.decimals >= 0:
            self.balance = Decimal(self.raw_balance) / Decimal(10 ** self.decimals)

    @property
    def usd_value(self) -> Optional[Decimal]:
        if self.usd_price is not None:
            return (self.balance * self.usd_price).quantize(Decimal("0.01"))
        return None


@dataclass
class TransferEvent:
    chain: str
    tx_hash: str
    block_number: int  # stores solana slot number when chain is solana
    timestamp: datetime
    from_addr: str
    to_addr: str
    token_address: Optional[str]
    symbol: str
    raw_amount: int
    decimals: int
    amount: Decimal = Decimal(0)
    # FIXME: solana sigs don't have log_index, using inner instruction idx instead
    log_index: int = 0
    usd_value: Optional[Decimal] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.amount == Decimal(0) and self.decimals >= 0:
            self.amount = Decimal(self.raw_amount) / Decimal(10 ** self.decimals)
