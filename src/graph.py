"""LangGraph workflow definition."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import MessagesState, StateGraph

from src.helpers import add_reaction, chat, update_chat_info
from src.tools import create_tools

if TYPE_CHECKING:
    from src.types import ChatContext


@dataclass
class VanillaContext:
    """Runtime context for Vanilla chatbot."""

    chat_context: "ChatContext"
    chat_id: str


def build_graph(checkpointer: BaseCheckpointSaver):
    """
    Build the LangGraph workflow.

    The workflow has 3 nodes:
    - updateChatInfo: Validates messages, updates Square state, checks triggers
    - addReaction: Uses LLM to select and apply emoji reactions
    - chat: Generates responses using LLM with tools

    Args:
        checkpointer: Checkpoint saver for state persistence.

    Returns:
        Compiled graph.
    """
    graph = StateGraph(MessagesState, context_schema=VanillaContext)

    # Add nodes
    graph.add_node("updateChatInfo", update_chat_info)
    graph.add_node("addReaction", add_reaction)
    graph.add_node("chat", chat)

    # Add edges
    graph.add_edge("__start__", "updateChatInfo")

    return graph.compile(checkpointer=checkpointer)


def build_chat_agent(
    context: "ChatContext",
    chat_id: str,
    user_id: str | None = None,
) -> "create_agent":
    """
    Build a ReAct chat agent with SummarizationMiddleware.

    This creates a standalone agent for the chat node that handles
    tool calling and conversation summarization.

    Args:
        context: Chat context with search and scheduler instances.
        chat_id: Current chat ID for scheduling tasks.
        user_id: Current user ID for preferences (optional).

    Returns:
        Compiled agent graph.
    """
    from src import prompts

    # Create tools for this context
    tools = create_tools(
        context.search,
        scheduler=context.scheduler,
        chat_id=chat_id,
        preferences_store=context.preferences_store,
        user_id=user_id,
    )

    # Create summarization middleware
    summarization = SummarizationMiddleware(
        model="openai:gpt-4.1-mini",
        trigger=[("fraction", 0.8), ("messages", 50)],
        keep=("messages", 20),
    )

    # Build the agent with middleware
    system_prompt = prompts.VANILLA_PERSONALITY.format(bot_name=context.bot_name)

    agent = create_agent(
        model="openai:gpt-4.1",
        tools=tools,
        system_prompt=system_prompt,
        middleware=[summarization],
    )

    return agent
