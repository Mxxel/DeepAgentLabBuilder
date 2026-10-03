from langgraph.graph import END, START, StateGraph

from homelab_creator.graph.state import GraphState


def test_spec_and_errors_overwrite_not_appended():
    def set_spec(_state: GraphState) -> dict:
        return {"spec": {"idea": "b"}, "validation_errors": ["x"]}

    builder = StateGraph(GraphState)
    builder.add_node("n", set_spec)
    builder.add_edge(START, "n")
    builder.add_edge("n", END)
    out = builder.compile().invoke({"spec": {"idea": "a"}, "validation_errors": ["old"]})
    assert out["spec"]["idea"] == "b"
    assert out["validation_errors"] == ["x"]
