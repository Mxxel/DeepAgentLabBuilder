from langgraph.types import interrupt

from homelab_creator.workers.invoke import WorkerBudgetError, WorkerOutcome, invoke_worker


def test_invoke_worker_timeout_skip(monkeypatch):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise TimeoutError("Request timed out.")

    answers = iter(["skip"])

    def fake_interrupt(payload):
        assert payload.get("interrupt_kind") == "worker_budget"
        assert payload.get("error") == "timeout"
        return next(answers)

    monkeypatch.setattr("homelab_creator.workers.invoke.interrupt", fake_interrupt)
    out = invoke_worker(boom)
    assert out is WorkerOutcome.skip
    assert calls["n"] == 1


def test_invoke_worker_timeout_retry_then_ok(monkeypatch):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("timed out")
        return "ok"

    answers = iter(["retry"])

    monkeypatch.setattr(
        "homelab_creator.workers.invoke.interrupt",
        lambda _p: next(answers),
    )
    assert invoke_worker(flaky) == "ok"
    assert calls["n"] == 2


def test_invoke_worker_budget_propagates_hitl_path(monkeypatch):
    monkeypatch.setattr("homelab_creator.workers.invoke.interrupt", lambda _p: "ask_stop")

    def budget():
        raise WorkerBudgetError("recursion")

    assert invoke_worker(budget) is WorkerOutcome.ask_stop


def test_invoke_worker_does_not_swallow_graph_bubble_up():
    from langgraph.errors import GraphInterrupt

    def hitl():
        raise GraphInterrupt(())

    try:
        invoke_worker(hitl)
    except GraphInterrupt:
        return
    raise AssertionError("expected GraphInterrupt to propagate")
