from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Iterable
from uuid import uuid4

# 在 Windows 上强制使用 UTF-8，以确保 emoji 和其他宽字符能通过
# JSONL 桥接正确传递到 Web UI。
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ORIGINAL_STDOUT = sys.stdout


def event_stdout():
    if sys.stdout.__class__.__name__ == "_DiscardStream":
        return ORIGINAL_STDOUT
    return sys.stdout


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 InsightForge agent 循环。")
    parser.add_argument("--session", default="", help="运行开始前要激活的已有会话 ID。")
    parser.add_argument("--new-session", action="store_true", help="运行开始前创建并激活一个新的空会话。")
    parser.add_argument("--new-session-name", default="", help="新创建会话的显示名称。")
    parser.add_argument("--jsonl", action="store_true", help="每行输出一个 JSON 事件。")
    parser.add_argument("--once", default="", help="运行单个提示后退出。若省略且 stdin 不是 TTY，则将 stdin 作为单个提示消费。")
    parser.add_argument("--stdin-repl", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def load_runtime():
    from agent_runtime import build_runtime

    return build_runtime(".")


def load_session_index():
    from agent_runtime.session_index import SessionIndex

    return SessionIndex(".")


def print_event(event: dict[str, Any], *, jsonl: bool) -> None:
    out = event_stdout()
    if jsonl:
        print(json.dumps(event, ensure_ascii=False, default=str), file=out, flush=True)
        return
    event_type = event.get("type")
    if event_type == "turn":
        print(f"· turn: {event.get('turn_id', '')}", file=out, flush=True)
    elif event_type == "token":
        print(event.get("delta", ""), end="", file=out, flush=True)
    elif event_type == "tool_start":
        tool = event.get("tool", {})
        print(f"\n· tool: {tool.get('name')} 已启动", file=out, flush=True)
    elif event_type == "tool_progress":
        progress = event.get("progress", {})
        tool = event.get("tool", {})
        print(f"· tool: {tool.get('name')} {progress.get('stage', '运行中')}: {progress.get('message', '')}", file=out, flush=True)
    elif event_type == "tool_result":
        result = event["tool_result"]
        status = "完成" if result.get("ok") else "错误"
        print(f"· tool: {result.get('name')} {status}", file=out, flush=True)
    elif event_type == "terminal":
        stream = event.get("stream", "stdout")
        print(f"· terminal[{stream}]: {event.get('line', '')}", file=out, flush=True)
    elif event_type == "status":
        print(f"· status: {event.get('phase')}: {event.get('message', '')}", file=out, flush=True)
    elif event_type == "session":
        session = (event.get("session") or {}).get("session") or {}
        if session:
            print(f"· session: {session.get('session_id')} {session.get('stage', '')}", file=out, flush=True)
    elif event_type == "done":
        print("", file=out, flush=True)
    elif event_type == "error":
        print(f"\nerror: {event.get('message', '')}", file=out, flush=True)


def prompt_inputs(args: argparse.Namespace) -> Iterable[str]:
    if args.once:
        yield args.once
        return
    if args.stdin_repl:
        for line in sys.stdin:
            user_input = line.strip()
            if user_input:
                yield user_input
        return
    if not sys.stdin.isatty():
        payload = sys.stdin.read().strip()
        if payload:
            yield payload
        return
    while True:
        try:
            user_input = input("› " if not args.jsonl else "")
        except EOFError:
            break
        if user_input.strip():
            yield user_input.strip()


async def amain(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.session and args.new_session:
        print("错误: --session 和 --new-session 不能同时使用", file=sys.stderr)
        return 2
    if args.new_session_name and not args.new_session:
        print("错误: --new-session-name 需要配合 --new-session", file=sys.stderr)
        return 2
    session_index = load_session_index()
    if args.new_session:
        try:
            if args.new_session_name:
                session_index.create(project_name=args.new_session_name)
            else:
                session_index.create()
        except ValueError as exc:
            print(f"错误: 无效的会话 ID: {exc}", file=sys.stderr)
            return 2
    elif args.session:
        try:
            session_index.set_active(args.session)
        except KeyError:
            print(f"错误: 未知的会话 ID: {args.session}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"错误: 无效的会话 ID: {exc}", file=sys.stderr)
            return 2
    # 偏好管理器：加载全局 + 会话 yaml，注入 adapter 单例
    # 在 load_runtime() 之前发射 preference_state，确保前端即使在 runtime 加载失败时也能收到偏好
    from agents.preference_manager import PreferenceMgr
    import agent_runtime.insightforge_adapters as _adapters
    pref_mgr = PreferenceMgr(".", session_index)
    _adapters.current_preference = pref_mgr
    print_event({"type": "preference_state", "version": pref_mgr.version, "preferences": pref_mgr.snapshot()}, jsonl=args.jsonl)

    runtime = load_runtime()

    interactive = sys.stdin.isatty() and not args.once
    if interactive and not args.jsonl:
        print("InsightForge agent 已就绪。按 Ctrl+C 退出。")
    for user_input in prompt_inputs(args):
        # JSONL 分发：拦截 preference_updated 事件（E1）
        if args.stdin_repl:
            try:
                payload = json.loads(user_input)
            except (json.JSONDecodeError, ValueError):
                payload = None
            if isinstance(payload, dict) and payload.get("type") == "preference_updated":
                try:
                    pref_mgr.apply_preference_updated(payload)
                except (ValueError, TypeError) as exc:
                    print_event({"type": "error", "message": f"malformed preference_updated event discarded: {exc}"}, jsonl=args.jsonl)
                continue
        if user_input.strip() == "/compact":
            turn_id = f"turn-{uuid4().hex[:12]}"
            print_event({"type": "turn", "turn_id": turn_id, "turn": {"id": turn_id}}, jsonl=args.jsonl)
            print_event({"type": "status", "turn_id": turn_id, "phase": "compact", "message": "压缩上下文"}, jsonl=args.jsonl)
            message = await runtime.compact_history(reason="manual")
            print_event({"type": "token", "turn_id": turn_id, "delta": message}, jsonl=args.jsonl)
            print_event({"type": "done", "turn_id": turn_id, "assistant": message, "tool_results": []}, jsonl=args.jsonl)
            print_event({"type": "session", "turn_id": turn_id, "session": runtime.session_index.snapshot()}, jsonl=args.jsonl)
            continue
        try:
            async for event in runtime.stream_events(user_input):
                print_event(event, jsonl=args.jsonl)
        except Exception as exc:
            # 保持 REPL 存活：一次失败的轮次不能杀掉进程
            # （否则会连带杀掉通过 stdio 驱动我们的 Web UI）。
            turn_id = f"turn-{uuid4().hex[:12]}"
            print_event({"type": "error", "turn_id": turn_id, "message": f"轮次失败: {exc}"}, jsonl=args.jsonl)
            print_event({"type": "done", "turn_id": turn_id, "assistant": "", "tool_results": []}, jsonl=args.jsonl)
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(amain()))
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
