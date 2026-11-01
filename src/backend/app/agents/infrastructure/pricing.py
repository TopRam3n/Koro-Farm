"""Versioned, model-specific list prices for estimating model cost (USD per million tokens).

These are estimates from published standard pay-as-you-go list prices, not the charges on any account (trial
credits, discounts and taxes are not reflected). Every estimate records the price version it used.

Sources, read on 31 October 2026:
* MiniMax: https://platform.minimax.io/docs/pricing/overview. MiniMax-M3 has a context tier at 512K input tokens
  and a Priority service tier at 1.5x Standard; MiniMax-M3.1-Flash has neither. Cache reads have their own rate.
* Nebius Token Factory: https://nebius.com/services/token-factory/models/qwen-models-inference. No cached-input
  rate is published, so cached input is charged at the input rate.
Reasoning (thinking) tokens are reported inside output tokens by these APIs and are priced as output.
"""
from dataclasses import dataclass
from decimal import Decimal

PRICE_VERSION = "list-prices-2026-10-31"
MILLION = Decimal("1000000")


@dataclass(frozen=True)
class Rate:
    input: Decimal
    output: Decimal
    cache_read: Decimal | None = None  # None: no published cached rate; cached input is charged as input


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    source: str
    standard: Rate
    long_context: Rate | None = None        # applies when input tokens exceed context_threshold
    context_threshold: int | None = None
    priority: Rate | None = None            # service_tier=priority, up to the threshold
    priority_long_context: Rate | None = None


MINIMAX_SOURCE = "https://platform.minimax.io/docs/pricing/overview"
NEBIUS_SOURCE = "https://nebius.com/services/token-factory/models/qwen-models-inference"
D = Decimal

PRICES: dict[tuple[str, str], ModelPrice] = {
    ("minimax", "MiniMax-M3"): ModelPrice(
        "minimax", "MiniMax-M3", MINIMAX_SOURCE,
        standard=Rate(D("0.30"), D("1.20"), D("0.06")), long_context=Rate(D("0.60"), D("2.40"), D("0.12")),
        context_threshold=512_000,
        priority=Rate(D("0.45"), D("1.80"), D("0.09")), priority_long_context=Rate(D("0.90"), D("3.60"), D("0.18"))),
    ("minimax", "MiniMax-M3.1-Flash"): ModelPrice(
        "minimax", "MiniMax-M3.1-Flash", MINIMAX_SOURCE, standard=Rate(D("0.15"), D("0.60"), D("0.015"))),
    ("nebius", "Qwen/Qwen3-30B-A3B-Instruct-2507"): ModelPrice(
        "nebius", "Qwen/Qwen3-30B-A3B-Instruct-2507", NEBIUS_SOURCE, standard=Rate(D("0.10"), D("0.30"))),
    ("nebius", "Qwen/Qwen3.5-397B-A17B"): ModelPrice(
        "nebius", "Qwen/Qwen3.5-397B-A17B", NEBIUS_SOURCE, standard=Rate(D("0.60"), D("3.60"))),
}


@dataclass(frozen=True)
class CostEstimate:
    usd: Decimal | None
    price_version: str
    basis: str  # how it was computed, or why it is unknown

    def as_dict(self) -> dict:
        return {"usd": str(self.usd) if self.usd is not None else None, "price_version": self.price_version, "basis": self.basis}


def estimate(provider: str, model: str, input_tokens: int | None, output_tokens: int | None,
             cached_tokens: int | None = 0, service_tier: str = "standard") -> CostEstimate:
    price = PRICES.get((provider, model))
    if price is None:
        return CostEstimate(None, PRICE_VERSION, f"no published price configured for {provider}/{model}")
    if input_tokens is None or output_tokens is None:
        return CostEstimate(None, PRICE_VERSION, "the provider did not report token usage")
    long = price.context_threshold is not None and input_tokens > price.context_threshold
    if service_tier == "priority" and price.priority is not None:
        rate, tier = (price.priority_long_context if long else price.priority), "priority"
    else:
        rate, tier = (price.long_context if long and price.long_context else price.standard), "standard"
    cached = min(max(cached_tokens or 0, 0), input_tokens)
    cache_rate = rate.cache_read if rate.cache_read is not None else rate.input
    usd = ((input_tokens - cached) * rate.input + cached * cache_rate + output_tokens * rate.output) / MILLION
    context = f", >{price.context_threshold // 1000}K context" if long else ""
    cache = "" if not cached else (" (cached input at cache-read rate)" if rate.cache_read is not None
                                   else " (no published cached rate; cached input at input rate)")
    return CostEstimate(usd.quantize(D("0.000001")), PRICE_VERSION,
                        f"{tier} list price{context}{cache}; estimate, not an account charge")
