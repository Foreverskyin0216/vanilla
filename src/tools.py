"""LangChain tools for Vanilla chatbot."""

import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from src.preferences import UserPreferencesStore
from src.scheduler import Scheduler, parse_cron_expression, parse_start_time
from src.search import Search

# URL detection regex pattern
URL_PATTERN = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")

if TYPE_CHECKING:
    from src.types import Member

# Tool descriptions
WEBSEARCH_DESCRIPTION = """當使用者的問題涉及以下任何情況時，必須使用此工具：
  - 天氣預報、氣溫、是否會下雨
  - 最新新聞、時事動態
  - 股價、匯率、加密貨幣價格
  - 交通狀況、路況資訊
  - 特定事件的最新進展
  - 科技新聞、產品發布資訊
  - 體育賽事結果、比分
  - 任何需要即時或最新資料的問題
  - 當使用者提供網址（URL）並要求分析、摘要或擷取內容時

  重要：任何關於「最新」「目前」「現在」的問題都應該使用此工具。
  重要：當使用者提供 URL 時，會自動擷取該網頁內容進行分析。
"""

DATETIME_DESCRIPTION = "查詢當前日期和時間。當使用者詢問現在幾點、今天日期、星期幾等問題時使用。"

SCHEDULE_TASK_DESCRIPTION = """設定定時任務或安排活動。使用 Cron 表達式來設定靈活的排程。

  Cron 格式：分 時 日 月 星期
  - * * * * * - 每分鐘
  - 0 * * * * - 每小時整點
  - 0 9 * * * - 每天 9:00
  - */5 * * * * - 每 5 分鐘
  - 0 9 * * 1 - 每週一 9:00
  - 0 9,18 * * * - 每天 9:00 和 18:00
  - 0 9 1 * * - 每月 1 日 9:00
  - 30 14 * * * - 每天 14:30

  開始時間格式：
  - "now" - 立即開始
  - "14:30" - 今天 14:30 開始（若已過則明天）
  - "2024-01-15 14:30" - 指定日期時間開始

  執行次數：
  - 1 - 只執行一次（預設）
  - 5 - 執行 5 次
  - -1 - 無限執行
"""

LIST_TASKS_DESCRIPTION = "查看目前設定的所有排程任務，包括等待中、已完成和已取消的任務。"

CANCEL_TASK_DESCRIPTION = "取消一個已設定的排程任務。需要提供任務 ID（前8位即可）。"

UPDATE_TASK_DESCRIPTION = """修改一個已設定的排程任務。可以修改訊息內容、觸發時間（Cron 表達式）或描述。

  只能修改狀態為「等待中」的任務。
  至少需要提供一個要修改的欄位（message、cron 或 description）。

  Cron 格式：分 時 日 月 星期
  - 0 9 * * * - 每天 9:00
  - 0 14 * * * - 每天 14:00
  - 30 8 * * 1-5 - 週一到週五 8:30
"""

# User preference tool descriptions
SET_PREFERENCE_DESCRIPTION = """記住用戶的個人偏好規則。用於永久記住用戶的特殊要求。

  規則類型 (rule_type)：
  - nickname: 稱呼方式（例如：用戶要求你叫他「小王爺」）
  - trigger: 觸發規則（例如：每次說話都要先說「晚安」）
  - behavior: 行為規則（例如：不要用敬語）
  - custom: 其他自定義規則

  常用規則鍵 (rule_key)：
  - call_me: 用於 nickname 類型，表示如何稱呼用戶

  範例：
  - 用戶說「以後叫我小王爺」→ rule_type='nickname', rule_key='call_me', rule_value='小王爺'
  - 用戶說「每次跟我說話要先說晚安」→ rule_type='trigger', rule_key='greeting', rule_value='晚安'
"""

GET_PREFERENCES_DESCRIPTION = "查看用戶已設定的所有個人偏好規則。"

DELETE_PREFERENCE_DESCRIPTION = """刪除用戶的一個個人偏好規則。

  需要提供：
  - rule_type: 規則類型（nickname, trigger, behavior, custom）
  - rule_key: 規則鍵（例如：call_me, greeting）

  範例：
  - 用戶說「不要再叫我小王爺了」→ rule_type='nickname', rule_key='call_me'
"""

SET_NICKNAME_FOR_USER_DESCRIPTION = """為群組中的另一個用戶設定暱稱。當 A 用戶想為 B 用戶設定暱稱時使用。

  使用此工具時，必須提供目標用戶的識別符 (target_user_identifier)。

  目標用戶識別符格式：
  - 格式為「名稱#ID前6位」，例如「小明#abc123」
  - 可以在聊天記錄中找到用戶的識別符

  範例：
  - 用戶說「叫小明#abc123小王爺」→ target_user_identifier='小明#abc123', nickname='小王爺'
  - 用戶說「以後叫那個 John#xyz789 約翰大帝」→ target_user_identifier='John#xyz789', nickname='約翰大帝'

  注意：只有暱稱規則可以為其他用戶設定，其他規則（trigger, behavior, custom）只能為自己設定。
"""


def format_search_results(answer: str | None, results: list[dict]) -> str:
    """Format search results into a readable string."""
    formatted = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['content']}" for i, r in enumerate(results)
    )
    result = f"Search Results:\n\n{formatted}"
    if answer:
        result += f"\n\nSummary: {answer}"
    return result


def format_extract_results(results: list, failed_results: list) -> str:
    """Format URL extraction results into a readable string.

    Args:
        results: List of ExtractResultItem objects with successful extractions.
        failed_results: List of FailedExtractItem objects with url and error fields.
    """
    if not results and failed_results:
        failed_lines = [f"- {r.url}\n  Error: {r.error}" for r in failed_results]
        return "Failed to extract content from the following URLs:\n" + "\n".join(failed_lines)

    formatted_parts = []
    for r in results:
        content = r.raw_content
        # Truncate very long content to avoid overwhelming the context
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (content truncated)"
        formatted_parts.append(f"URL: {r.url}\n\n{content}")

    result = "Web Content Extraction Results:\n\n" + "\n\n---\n\n".join(formatted_parts)

    if failed_results:
        failed_lines = [f"- {r.url}\n  Error: {r.error}" for r in failed_results]
        result += "\n\nFailed to extract content from the following URLs:\n" + "\n".join(
            failed_lines
        )

    return result


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    return URL_PATTERN.findall(text)


def get_formatted_datetime(timezone: str) -> str:
    """Get formatted datetime for a timezone."""
    try:
        tz = ZoneInfo(timezone)
    except KeyError:
        tz = ZoneInfo("Asia/Taipei")

    now = datetime.now(tz)
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday = weekdays[now.weekday()]

    date_str = f"{now.year}-{now.month:02d}-{now.day:02d}"
    time_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    return f"{date_str} {weekday} {time_str}"


def create_tools(
    search: Search,
    scheduler: Scheduler | None = None,
    chat_id: str | None = None,
    preferences_store: UserPreferencesStore | None = None,
    user_id: str | None = None,
    members: list["Member"] | None = None,
) -> list:
    """
    Create LangChain tools with the given instances.

    Args:
        search: Search instance for web search.
        scheduler: Scheduler instance for task scheduling (optional).
        chat_id: Current chat ID for scheduling tasks (optional).
        preferences_store: User preferences store for persistent rules (optional).
        user_id: Current user ID for preferences (optional).
        members: List of chat members for cross-user preference lookup (optional).

    Returns:
        List of LangChain tools.
    """

    @tool(description=WEBSEARCH_DESCRIPTION)
    async def websearch(
        question: str,
        topic: Literal["general", "news"] = "general",
    ) -> str:
        """
        Search the web for information or extract content from URLs.

        Args:
            question: 搜尋問題，請使用完整的句子或關鍵詞組合。若包含 URL，會自動擷取該網頁內容。
            topic: 搜尋主題：news 用於新聞時事、體育賽事、即時事件；general 用於其他一般查詢
        """
        # Check if the question contains URLs
        urls = extract_urls(question)

        if urls:
            # Extract content from URLs
            extract_result = await search.extract(urls)
            return format_extract_results(extract_result.results, extract_result.failed_results)

        # Regular search
        result = await search.search(question, topic)
        results_dict = [{"title": r.title, "content": r.content} for r in result.results]
        return format_search_results(result.answer, results_dict)

    @tool(description=DATETIME_DESCRIPTION)
    def get_datetime(timezone: str = "Asia/Taipei") -> str:
        """
        Get the current date and time.

        Args:
            timezone: IANA 時區名稱
        """
        return get_formatted_datetime(timezone)

    tools = [websearch, get_datetime]

    # Add scheduler tools if scheduler is provided
    if scheduler and chat_id:

        @tool(description=SCHEDULE_TASK_DESCRIPTION)
        async def schedule_task(
            message: str,
            cron: str,
            start_time: str = "now",
            description: str = "",
            max_triggers: int = 1,
        ) -> str:
            """
            設定一個定時任務（使用 Cron 表達式）。

            Args:
                message: 要發送的訊息內容
                cron: Cron 表達式（格式：分 時 日 月 星期）
                start_time: 開始時間（"now"、"14:30"、"2024-01-15 14:30"）
                description: 任務描述（可選）
                max_triggers: 最大執行次數（-1 為無限執行，預設為 1）
            """
            try:
                cron_expr = parse_cron_expression(cron)
            except ValueError as e:
                return f"Error: {e}"

            try:
                start_at = parse_start_time(start_time)
            except ValueError as e:
                return f"Error: {e}"

            try:
                task = await scheduler.create_task(
                    chat_id=chat_id,
                    message=message,
                    cron_expression=cron_expr,
                    start_at=start_at,
                    max_triggers=max_triggers,
                    description=description,
                )
            except ValueError as e:
                return f"Error: {e}"

            return f"Task scheduled!\n\n{task.to_readable_string()}"

        @tool(description=LIST_TASKS_DESCRIPTION)
        def list_scheduled_tasks() -> str:
            """查看目前所有排程任務。"""
            return scheduler.list_tasks(chat_id)

        @tool(description=CANCEL_TASK_DESCRIPTION)
        async def cancel_scheduled_task(task_id: str) -> str:
            """
            取消一個排程任務。

            Args:
                task_id: 任務 ID（完整或前8位）
            """
            # Only search tasks belonging to this chat (isolation)
            matching_tasks = [
                t
                for t in scheduler.tasks.values()
                if t.chat_id == chat_id and (t.id.startswith(task_id) or t.id[:8] == task_id[:8])
            ]

            if not matching_tasks:
                return f"Task not found: {task_id}"

            if len(matching_tasks) > 1:
                return "Multiple matching tasks found, please provide a more complete ID"

            task = matching_tasks[0]
            if await scheduler.cancel_task(task.id):
                return f"Task cancelled: {task.description or task.id[:8]}"
            else:
                return "Cannot cancel task (may be completed or already cancelled)"

        @tool(description=UPDATE_TASK_DESCRIPTION)
        async def update_scheduled_task(
            task_id: str,
            message: str | None = None,
            cron: str | None = None,
            description: str | None = None,
        ) -> str:
            """
            修改一個排程任務的訊息、時間或描述。

            Args:
                task_id: 任務 ID（完整或前8位）
                message: 新的訊息內容（可選）
                cron: 新的 Cron 表達式（可選）
                description: 新的任務描述（可選）
            """
            # At least one field must be provided
            if message is None and cron is None and description is None:
                return "Error: 至少需要提供一個要修改的欄位（message、cron 或 description）"

            # Only search tasks belonging to this chat (isolation)
            matching_tasks = [
                t
                for t in scheduler.tasks.values()
                if t.chat_id == chat_id and (t.id.startswith(task_id) or t.id[:8] == task_id[:8])
            ]

            if not matching_tasks:
                return f"Task not found: {task_id}"

            if len(matching_tasks) > 1:
                return "Multiple matching tasks found, please provide a more complete ID"

            task = matching_tasks[0]

            # Validate cron if provided
            if cron is not None:
                try:
                    cron = parse_cron_expression(cron)
                except ValueError as e:
                    return f"Error: {e}"

            try:
                updated_task = await scheduler.update_task(
                    task_id=task.id,
                    message=message,
                    cron_expression=cron,
                    description=description,
                )
            except ValueError as e:
                return f"Error: {e}"

            if updated_task:
                return f"Task updated!\n\n{updated_task.to_readable_string()}"
            else:
                return "Cannot update task (may be completed or cancelled)"

        tools.extend(
            [schedule_task, list_scheduled_tasks, cancel_scheduled_task, update_scheduled_task]
        )

    # Add preference tools if preferences store and user_id are provided
    if preferences_store and user_id:

        @tool(description=SET_PREFERENCE_DESCRIPTION)
        async def set_user_preference(
            rule_type: Literal["nickname", "trigger", "behavior", "custom"],
            rule_key: str,
            rule_value: str,
        ) -> str:
            """
            記住用戶的個人偏好規則（僅限此聊天室）。

            Args:
                rule_type: 規則類型（nickname=稱呼, trigger=觸發規則, behavior=行為規則, custom=自定義）
                rule_key: 規則鍵（例如：call_me, greeting）
                rule_value: 規則值（例如：小王爺, 晚安）
            """
            if not chat_id:
                return "Error: Cannot save preference without chat context"

            try:
                pref = await preferences_store.set_preference(
                    user_id=user_id,
                    chat_id=chat_id,
                    rule_type=rule_type,
                    rule_key=rule_key,
                    rule_value=rule_value,
                )
                return f"Preference saved!\n\n{pref.to_readable_string()}"
            except Exception as e:
                return f"Error: {e}"

        @tool(description=GET_PREFERENCES_DESCRIPTION)
        async def get_user_preferences() -> str:
            """查看用戶在此聊天室的所有個人偏好規則。"""
            if not chat_id:
                return "Error: Cannot get preferences without chat context"

            prefs = await preferences_store.get_preferences_for_user(
                user_id=user_id,
                chat_id=chat_id,
                active_only=True,
            )
            if not prefs:
                return "No preferences set for this user in this chat."

            parts = [f"User has {len(prefs)} preference(s) in this chat:\n"]
            for pref in prefs:
                parts.append(pref.to_readable_string())
                parts.append("---")
            return "\n".join(parts)

        @tool(description=DELETE_PREFERENCE_DESCRIPTION)
        async def delete_user_preference(
            rule_type: Literal["nickname", "trigger", "behavior", "custom"],
            rule_key: str,
        ) -> str:
            """
            刪除用戶在此聊天室的一個個人偏好規則。

            Args:
                rule_type: 規則類型（nickname, trigger, behavior, custom）
                rule_key: 規則鍵（例如：call_me, greeting）
            """
            if not chat_id:
                return "Error: Cannot delete preference without chat context"

            deleted = await preferences_store.delete_preference(
                user_id=user_id,
                chat_id=chat_id,
                rule_type=rule_type,
                rule_key=rule_key,
            )

            if deleted:
                return f"Preference deleted: {rule_type}/{rule_key}"
            else:
                return f"Preference not found: {rule_type}/{rule_key}"

        tools.extend([set_user_preference, get_user_preferences, delete_user_preference])

        # Add cross-user nickname tool if members list is provided
        if members is not None:

            @tool(description=SET_NICKNAME_FOR_USER_DESCRIPTION)
            async def set_nickname_for_user(
                target_user_identifier: str,
                nickname: str,
            ) -> str:
                """
                為群組中的另一個用戶設定暱稱。

                Args:
                    target_user_identifier: 目標用戶的識別符（格式為「名稱#ID前6位」）
                    nickname: 要設定的暱稱
                """
                if not chat_id:
                    return "Error: Cannot save preference without chat context"

                # Parse the target user identifier to find the user ID
                # Format: "DisplayName#abc123" where abc123 is the first 6 chars of member ID
                if "#" not in target_user_identifier:
                    return (
                        "Error: 無效的用戶識別符格式。"
                        "請使用「名稱#ID前6位」的格式，例如「小明#abc123」"
                    )

                parts = target_user_identifier.rsplit("#", 1)
                if len(parts) != 2:
                    return (
                        "Error: 無效的用戶識別符格式。"
                        "請使用「名稱#ID前6位」的格式，例如「小明#abc123」"
                    )

                target_name, short_id = parts
                short_id = short_id.lower()

                # Find the member with matching short ID
                target_member = None
                for member in members:
                    if member.id[:6].lower() == short_id:
                        target_member = member
                        break

                if not target_member:
                    # Try partial match on display name as fallback
                    matching_members = [
                        m
                        for m in members
                        if m.name.lower() == target_name.lower()
                        or m.id[:6].lower().startswith(short_id[:3])
                    ]
                    if len(matching_members) == 1:
                        target_member = matching_members[0]
                    elif len(matching_members) > 1:
                        member_list = ", ".join(f"{m.name}#{m.id[:6]}" for m in matching_members)
                        return (
                            f"Error: 找到多個符合的用戶。請提供更完整的識別符。"
                            f"可能的用戶：{member_list}"
                        )
                    else:
                        return (
                            f"Error: 找不到用戶「{target_user_identifier}」。"
                            "請確認該用戶在此群組中，並使用正確的識別符格式。"
                        )

                # Set the nickname preference for the target user
                try:
                    pref = await preferences_store.set_preference(
                        user_id=target_member.id,
                        chat_id=chat_id,
                        rule_type="nickname",
                        rule_key="call_me",
                        rule_value=nickname,
                    )
                    return (
                        f"已為用戶 {target_member.name}#{target_member.id[:6]} "
                        f"設定暱稱「{nickname}」\n\n{pref.to_readable_string()}"
                    )
                except Exception as e:
                    return f"Error: {e}"

            tools.append(set_nickname_for_user)

    return tools
