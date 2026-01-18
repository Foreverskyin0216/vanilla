"""Tests for graph module."""

from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph


class TestBuildGraph:
    """Tests for build_graph function."""

    def test_build_graph_returns_compiled_graph(self):
        """Test build_graph returns a compiled graph."""
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer)

        assert graph is not None

    def test_build_graph_has_nodes(self):
        """Test build_graph creates expected nodes."""
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer)

        # The compiled graph should have the nodes
        nodes = graph.get_graph().nodes
        node_names = list(nodes.keys())

        assert "updateChatInfo" in node_names
        assert "addReaction" in node_names
        assert "chat" in node_names

    def test_build_graph_has_start_edge(self):
        """Test build_graph has edge from start to updateChatInfo."""
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer)

        # Check the graph structure
        graph_def = graph.get_graph()
        edges = list(graph_def.edges)

        # Should have an edge from __start__ to updateChatInfo
        start_edges = [e for e in edges if e.source == "__start__"]
        assert len(start_edges) > 0
        assert any(e.target == "updateChatInfo" for e in start_edges)
