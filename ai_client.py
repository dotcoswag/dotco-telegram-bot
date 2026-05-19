"""
ai_client.py
------------
Thin wrapper around the Anthropic SDK for DotCo's enrichment step.

The whole module is designed so that the rest of the pipeline keeps working
when AI is unavailable:
- `is_enabled()` lets callers skip the AI block entirely when no key is set.
- `call_with_retry()` raises `QuotaExhausted` on auth/quota failures so the
  caller can stop further calls and finish the run without AI.
- All other failures return None; the caller decides what to do per row.
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# Approximate per-million-token prices (USD) for cost estimates shown to the user.
# These are not used for billing; the real cost is reported by the API.
PRICING = {
    HAIKU: {"in": 1.00, "out": 5.00},
    SONNET: {"in": 3.00, "out": 15.00},
}


class QuotaExhausted(Exception):
    """Raised on 401/402 or 429-with-quota. Caller must stop further calls."""


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def is_enabled() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return bool(key)


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (in_tokens / 1_000_000) * p["in"] + (out_tokens / 1_000_000) * p["out"]


def call_with_retry(*, model, system, messages, max_tokens=1024, max_retries=3):
    """Call Claude with retry. Returns (text, usage_dict) on success, (None, None) on
    soft failure. Raises QuotaExhausted on auth/quota failure — caller should stop.

    `system` may be a string OR a list of content blocks (use the list form to enable
    prompt caching via cache_control on the system block).
    """
    import anthropic
    client = _get_client()

    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            usage = {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
            }
            return text, usage

        except anthropic.AuthenticationError as e:
            raise QuotaExhausted(f"Authentication failed: {e}") from e

        except anthropic.PermissionDeniedError as e:
            raise QuotaExhausted(f"Permission denied (likely billing/quota): {e}") from e

        except anthropic.RateLimitError as e:
            retry_after = 30
            try:
                ra = getattr(e, "response", None)
                if ra is not None:
                    retry_after = int(ra.headers.get("retry-after", "30"))
            except Exception:
                pass
            if attempt >= max_retries:
                if retry_after > 60:
                    raise QuotaExhausted(f"Sustained rate limit / quota: {e}") from e
                return None, None
            print(f"      ⏳ Rate limited. Waiting {retry_after}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(retry_after)

        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            if attempt >= max_retries:
                print(f"      ⚠️  Network error after {max_retries} retries: {e}")
                return None, None
            wait = 2 ** attempt
            print(f"      ⚠️  Network error. Retry {attempt + 1}/{max_retries} in {wait}s...")
            time.sleep(wait)

        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                if attempt >= max_retries:
                    print(f"      ⚠️  Server error {status} after {max_retries} retries: {e}")
                    return None, None
                wait = 2 ** attempt
                print(f"      ⚠️  Server error {status}. Retry {attempt + 1}/{max_retries} in {wait}s...")
                time.sleep(wait)
            else:
                print(f"      ⚠️  API error {status}: {e}")
                return None, None

    return None, None
