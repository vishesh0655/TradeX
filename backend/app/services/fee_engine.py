"""Configurable simulated fees for paper executions."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import os


CENT = Decimal("0.01")
BPS = Decimal("10000")


@dataclass(frozen=True)
class FeeConfig:
    brokerage_bps: Decimal = Decimal("0")
    platform_bps: Decimal = Decimal("0")
    tax_bps: Decimal = Decimal("0")

    def __post_init__(self):
        names = ("brokerage_bps", "platform_bps", "tax_bps")
        rates = tuple(Decimal(str(getattr(self, name))) for name in names)
        if any(not value.is_finite() or value < 0 for value in rates):
            raise ValueError("Fee rates must be finite and non-negative")
        for name, value in zip(names, rates):
            object.__setattr__(self, name, value)
        if sum(rates, Decimal("0")) > BPS:
            raise ValueError("Total simulated fee rate cannot exceed 100%")

    @classmethod
    def from_environment(cls):
        """Read optional simulated fee rates in basis points (zero by default)."""
        return cls(
            brokerage_bps=Decimal(os.getenv("TRADEX_BROKERAGE_BPS", "0")),
            platform_bps=Decimal(os.getenv("TRADEX_PLATFORM_FEE_BPS", "0")),
            tax_bps=Decimal(os.getenv("TRADEX_SIMULATED_TAX_BPS", "0")),
        )


@dataclass(frozen=True)
class FeeBreakdown:
    brokerage: Decimal
    platform: Decimal
    taxes: Decimal
    total: Decimal


class FeeEngine:
    """Calculates configured paper fees without any payment integration."""

    def __init__(self, config: FeeConfig | None = None):
        self.config = config or FeeConfig.from_environment()

    def calculate(self, gross_notional: Decimal) -> FeeBreakdown:
        gross = Decimal(gross_notional)
        if not gross.is_finite() or gross < 0:
            raise ValueError("Gross notional must be a finite non-negative amount")
        brokerage = (gross * self.config.brokerage_bps / BPS).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        platform = (gross * self.config.platform_bps / BPS).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        taxes = (gross * self.config.tax_bps / BPS).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        return FeeBreakdown(
            brokerage=brokerage,
            platform=platform,
            taxes=taxes,
            total=brokerage + platform + taxes,
        )

    def estimate_order(self, *, side: str, gross_notional: Decimal) -> dict:
        """Return the configured simulated charges and signed cash impact."""
        normalized_side = str(side).upper()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("Side must be BUY or SELL")
        gross = Decimal(gross_notional)
        breakdown = self.calculate(gross)
        net_cash_effect = (
            -(gross + breakdown.total)
            if normalized_side == "BUY"
            else gross - breakdown.total
        )
        return {
            "side": normalized_side,
            "gross_notional": gross,
            "brokerage": breakdown.brokerage,
            "platform": breakdown.platform,
            "taxes": breakdown.taxes,
            "total_fees": breakdown.total,
            "net_cash_effect": net_cash_effect,
        }


fee_engine = FeeEngine()
