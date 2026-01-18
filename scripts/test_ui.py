#!/usr/bin/env python3
"""
Interactive test UI for Vanilla chatbot using Rich.

This script provides a terminal-based UI to interact with the LangGraph workflow,
displaying AI responses and tool usage in real-time.

Usage:
    uv run python scripts/test_ui.py
"""

import asyncio
import os
import sys
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import prompts  # noqa: E402
from src.scheduler import Scheduler  # noqa: E402
from src.search import Search  # noqa: E402
from src.tools import create_tools  # noqa: E402

# Initialize Rich console
console = Console()


# Test UI chat ID (used for scheduler context)
TEST_UI_CHAT_ID = "test-ui-session"


class ChatSession:
    """Manages a chat session with the LLM using create_agent with SummarizationMiddleware."""

    def __init__(self, bot_name: str = "香草"):
        self.bot_name = bot_name
        self.messages: list[dict[str, Any]] = []
        self.search = Search()
        self.scheduler = Scheduler()
        self.scheduler.set_message_sender(self._send_scheduled_message)
        self.tools = create_tools(self.search, scheduler=self.scheduler, chat_id=TEST_UI_CHAT_ID)
        self.tool_map = {t.name: t for t in self.tools}

        # System prompt
        self.system_prompt = prompts.VANILLA_PERSONALITY.format(bot_name=bot_name)

        # Create SummarizationMiddleware
        summarization = SummarizationMiddleware(
            model="openai:gpt-4.1-mini",
            trigger=[("fraction", 0.8), ("messages", 50)],
            keep=("messages", 20),
        )

        # Initialize the agent with tools and middleware
        self.agent = create_agent(
            model="openai:gpt-4.1",
            tools=self.tools,
            system_prompt=self.system_prompt,
            middleware=[summarization],
        )

    async def _send_scheduled_message(self, chat_id: str, message: str) -> None:
        """Send a scheduled message (displays in console for test UI)."""
        console.print()
        console.print(
            Panel(
                Markdown(message),
                title="⏰ 排程訊息",
                border_style="yellow",
            )
        )
        console.print()

    async def send_message(self, user_input: str) -> tuple[str, list[dict]]:
        """
        Send a message and get a response using create_agent.

        Returns:
            Tuple of (response_text, list of tool calls made)
        """
        # Add user message
        self.messages.append({"role": "user", "content": user_input})
        tool_calls_info: list[dict] = []

        # Build messages for agent (without system prompt, it's configured in agent)
        agent_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages
            if m.get("role") != "system"
        ]

        # Invoke the agent
        result = await self.agent.ainvoke({"messages": agent_messages})

        # Extract tool calls from the result
        result_messages = result.get("messages", [])
        for msg in result_messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_info = {
                        "name": tool_call.get("name", ""),
                        "args": tool_call.get("args", {}),
                        "result": None,
                    }
                    tool_calls_info.append(tool_info)
            # Capture tool results
            if hasattr(msg, "type") and msg.type == "tool":
                # Update the last tool_info with result
                if tool_calls_info:
                    tool_calls_info[-1]["result"] = msg.content

        # Extract the last AI response
        answer = ""
        for msg in reversed(result_messages):
            if hasattr(msg, "content") and msg.content:
                # Skip tool messages
                if hasattr(msg, "type") and msg.type == "tool":
                    continue
                answer = str(msg.content)
                break

        clean_answer = (
            answer.replace(f"{self.bot_name}:", "").replace(f"{self.bot_name}：", "").strip()
        )

        # Add assistant response to history
        self.messages.append({"role": "assistant", "content": clean_answer})

        return clean_answer, tool_calls_info

    def clear_history(self):
        """Clear chat history but keep system prompt."""
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def start_scheduler(self):
        """Start the scheduler background worker."""
        self.scheduler.start()

    def stop_scheduler(self):
        """Stop the scheduler background worker."""
        self.scheduler.stop()


def display_header():
    """Display the application header."""
    console.print()
    console.print(
        Panel(
            Text("Vanilla 測試 UI", style="bold magenta", justify="center"),
            subtitle="輸入 /help 查看指令 | /quit 離開",
            border_style="magenta",
        )
    )
    console.print()


def display_tool_usage(tool_calls: list[dict]):
    """Display tool usage in a table."""
    if not tool_calls:
        return

    console.print()
    table = Table(
        title="🔧 Tool 使用",
        title_style="bold cyan",
        border_style="cyan",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Tool", style="yellow")
    table.add_column("參數", style="green")
    table.add_column("結果", style="white", max_width=60)

    for call in tool_calls:
        args_str = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
        result_str = str(call["result"])
        if len(result_str) > 100:
            result_str = result_str[:100] + "..."
        table.add_row(call["name"], args_str, result_str)

    console.print(table)


def display_response(response: str):
    """Display the AI response."""
    console.print()
    console.print(Panel(Markdown(response), title="🤖 香草", border_style="green"))


def display_user_message(message: str):
    """Display the user's message."""
    console.print()
    console.print(Panel(message, title="👤 You", border_style="blue"))


def display_help():
    """Display help information."""
    help_text = """
**指令列表：**

| 指令 | 說明 |
|------|------|
| `/help` | 顯示此幫助訊息 |
| `/clear` | 清除對話歷史 |
| `/history` | 顯示對話歷史 |
| `/tasks` | 查看排程任務 |
| `/quit` | 離開程式 |

**使用方式：**
直接輸入訊息與香草對話，她會以古典宮廷仕女的方式回應。
你可以請香草設定提醒或排程任務，例如「10分鐘後提醒我喝水」。
    """
    console.print(Panel(Markdown(help_text), title="幫助", border_style="yellow"))


def display_history(messages: list[dict]):
    """Display chat history."""
    console.print()
    console.print(Rule("對話歷史", style="yellow"))
    console.print()

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        elif hasattr(msg, "type"):
            role = msg.type
            content = msg.content if hasattr(msg, "content") else str(msg)

        if role == "system":
            continue
        elif role == "user":
            console.print(f"[blue]👤 You:[/blue] {content}")
        elif role == "assistant":
            if content:
                console.print(f"[green]🤖 香草:[/green] {content}")
        elif role == "tool":
            console.print(f"[cyan]🔧 Tool:[/cyan] {content[:50]}...")

    console.print()


async def main():
    """Main function to run the chat UI."""
    display_header()

    # Initialize session
    bot_name = os.getenv("CATGIRL_NAME", "香草")
    session = ChatSession(bot_name=bot_name)

    # Start the scheduler
    session.start_scheduler()

    console.print(f"[dim]機器人名稱: {bot_name}[/dim]")
    console.print(f"[dim]可用 Tools: {', '.join(session.tool_map.keys())}[/dim]")
    console.print("[dim]排程器: 已啟動[/dim]")
    console.print()

    try:
        while True:
            try:
                # Get user input
                user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
                user_input = user_input.strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    cmd = user_input.lower()
                    if cmd == "/quit" or cmd == "/exit" or cmd == "/q":
                        console.print("[yellow]再見！[/yellow]")
                        break
                    elif cmd == "/help":
                        display_help()
                        continue
                    elif cmd == "/clear":
                        session.clear_history()
                        console.print("[yellow]對話歷史已清除[/yellow]")
                        continue
                    elif cmd == "/history":
                        display_history(session.messages)
                        continue
                    elif cmd == "/tasks":
                        tasks_info = session.scheduler.list_tasks(TEST_UI_CHAT_ID)
                        console.print(Panel(tasks_info, title="📋 排程任務", border_style="cyan"))
                        continue
                    else:
                        console.print(f"[red]未知指令: {cmd}[/red]")
                        continue

                # Display user message
                display_user_message(user_input)

                # Send message and get response
                with console.status("[bold green]思考中...", spinner="dots"):
                    response, tool_calls = await session.send_message(user_input)

                # Display tool usage if any
                display_tool_usage(tool_calls)

                # Display response
                display_response(response)

            except KeyboardInterrupt:
                console.print("\n[yellow]使用 /quit 離開[/yellow]")
            except EOFError:
                console.print("\n[yellow]再見！[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]錯誤: {e}[/red]")
    finally:
        # Stop the scheduler when exiting
        session.stop_scheduler()
        console.print("[dim]排程器已停止[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
