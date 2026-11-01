"""Check a model provider's configuration without revealing credentials. Synthetic request only.

  python -m src.backend.scripts.check_model_provider                 # the provider in AGENT_MODEL_PROVIDER
  python -m src.backend.scripts.check_model_provider --provider nebius --model Qwen/Qwen3-30B-A3B-Instruct-2507
  python -m src.backend.scripts.check_model_provider --no-call        # configuration and model list only

Prints the provider, host, model, whether a key is present (never the key), whether the model is offered to this
account, and the outcome of one small synthetic decision request. Refuses to run in production.
"""
import argparse
import os
import sys

from src.backend.app.agents.infrastructure.model import ModelDecider
from src.backend.app.agents.infrastructure.providers import (
    ConfigurationError, ProviderError, build_client, list_models, load_config,
)


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Check a recovery model provider without revealing credentials")
    parser.add_argument("--provider", default=env.get("AGENT_MODEL_PROVIDER", ""))
    parser.add_argument("--model")
    parser.add_argument("--no-call", action="store_true")
    args = parser.parse_args(argv)
    if env.get("APP_ENV", "").lower() == "production":
        print("refusing to run in production", file=sys.stderr)
        return 2
    try:
        config = load_config(args.provider.strip().lower(), env, model=args.model)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}")
        return 2
    for key, value in config.describe().items():
        print(f"{key}: {value}")
    if not config.api_key and config.provider != "anthropic":
        print(f"{config.provider.upper()}_API_KEY is not set")
        return 2
    if config.provider in ("minimax", "nebius"):
        try:
            offered = list_models(config)
            print(f"model offered to this account: {config.model in offered if offered else 'unknown (empty model list)'}"
                  f" ({len(offered)} models listed)")
        except ProviderError as exc:
            print(f"model list: unavailable ({exc})")
    if args.no_call:
        return 0
    from src.backend.scripts.evaluate_recovery_model import scenarios
    case = scenarios()[0]
    decision = ModelDecider(build_client(config)).decide(case["context"])
    call = decision.call or {}
    print(f"synthetic request: outcome={call.get('outcome')} mode={decision.mode} option={decision.option_id} "
          f"latency_ms={call.get('latency_ms')} tokens={call.get('usage')} est_cost={call.get('cost', {}).get('usd')} "
          f"structured_mode={call.get('structured_mode')} fallback={decision.fallback_reason}")
    return 0 if decision.mode == "model" else 1


if __name__ == "__main__":
    raise SystemExit(main())
