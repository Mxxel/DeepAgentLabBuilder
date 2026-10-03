from langgraph.types import Command


def interrupt_kind(result) -> str:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return ""
    first = interrupts[0]
    value = getattr(first, "value", first)
    if isinstance(value, dict):
        return str(value.get("interrupt_kind") or "")
    return ""


def interrupt_payload(result) -> dict:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return {}
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {}


def approve_writes(graph, cfg, result):
    while interrupt_kind(result) == "hitl_tool":
        payload = interrupt_payload(result)
        if payload.get("tool") != "write_session_files":
            break
        result = graph.invoke(Command(resume="approve"), cfg)
    return result
