"""Application contracts behind agent tools; no provider calls or real writes."""

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Context:
    """Supply only from a trusted authenticated application session."""

    allowed_reference: str
    can_request_review: bool = False


class Backend(Protocol):
    def lookup(self, reference: str) -> object: ...

    def request_review(self, reference: str) -> object: ...


def dispatch(name: str, arguments: object, context: Context, backend: Backend) -> dict:
    """Return bounded facts; untrusted input never becomes an authorization grant."""
    if name not in {"lookup_order", "request_review"}:
        return {"outcome": "invalid_tool"}
    if not isinstance(arguments, dict) or set(arguments) != {"reference"}:
        return {"outcome": "invalid_arguments"}
    reference = arguments["reference"]
    if (
        not isinstance(reference, str)
        or re.fullmatch(r"ORD-[0-9]{4}", reference) is None
    ):
        return {"outcome": "invalid_arguments"}
    if reference != context.allowed_reference:
        return {"outcome": "forbidden"}
    if name == "request_review" and context.can_request_review is not True:
        return {"outcome": "forbidden"}
    try:
        result = (
            backend.lookup(reference)
            if name == "lookup_order"
            else backend.request_review(reference)
        )
    except TimeoutError:
        return {"outcome": "unavailable", "reason": "timeout"}
    except Exception:  # noqa: BLE001 — sanitize arbitrary backend failures at this boundary
        # Never return exception text: it can contain secrets or backend details.
        return {"outcome": "unavailable", "reason": "backend_error"}
    if name == "lookup_order":
        if result is None:
            return {"outcome": "unknown", "reference": reference}
        if (
            not isinstance(result, dict)
            or set(result) != {"reference", "status"}
            or result["reference"] != reference
            or not isinstance(result["status"], str)
            or result["status"] not in {"processing", "shipped", "held"}
        ):
            return {"outcome": "invalid_response"}
        return {"outcome": "known", "facts": dict(result)}
    if (
        not isinstance(result, dict)
        or set(result) != {"reference", "review_id", "status"}
        or result["reference"] != reference
        or not isinstance(result["review_id"], str)
        or re.fullmatch(r"REV-[0-9]{4}", result["review_id"]) is None
        or result["status"] != "pending_review"
    ):
        return {"outcome": "invalid_response"}
    return {"outcome": "pending_review", "facts": dict(result)}
