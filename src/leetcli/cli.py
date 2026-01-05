import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

GRAPHQL_URL = "https://leetcode.com/graphql"
PROBLEM_LIST_URL = "https://leetcode.com/api/problems/all/"
LIST_TTL_SECONDS = 24 * 60 * 60
QUESTION_TTL_SECONDS = 7 * 24 * 60 * 60


LIST_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    total: totalNum
    questions: data {
      questionId
      questionFrontendId
      title
      titleSlug
      difficulty
      paidOnly
    }
  }
}
"""

DETAIL_QUERY = """
query question($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    content
    difficulty
    isPaidOnly
    topicTags {
      name
      slug
    }
  }
}
"""


class HtmlToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._in_pre = False
        self._pending_space = False
        self._list_prefix = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in {"p", "br"}:
            self._newline()
        elif tag == "pre":
            self._newline()
            self._in_pre = True
        elif tag == "code" and not self._in_pre:
            self._append("`")
        elif tag in {"ul", "ol"}:
            self._newline()
        elif tag == "li":
            self._newline()
            self._append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._newline()
            self._in_pre = False
        elif tag == "code" and not self._in_pre:
            self._append("`")
        elif tag in {"p", "br"}:
            self._newline()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._in_pre:
            self._append(data)
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._pending_space:
            self._append(" ")
            self._pending_space = False
        self._append(text)
        self._pending_space = True

    def _append(self, text: str) -> None:
        self._chunks.append(text)

    def _newline(self) -> None:
        if not self._chunks or self._chunks[-1].endswith("\n"):
            return
        self._chunks.append("\n")
        self._pending_space = False

    def get_text(self) -> str:
        return "".join(self._chunks).strip()


def html_to_text(html: str) -> str:
    parser = HtmlToText()
    parser.feed(html)
    return parser.get_text()


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color(text: str, code: str) -> str:
    if not supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return color(text, "1")


def dim(text: str) -> str:
    return color(text, "2")


def red(text: str) -> str:
    return color(text, "31")


def green(text: str) -> str:
    return color(text, "32")


def yellow(text: str) -> str:
    return color(text, "33")


def blue(text: str) -> str:
    return color(text, "34")


def difficulty_color(difficulty: str) -> str:
    if difficulty.lower() == "easy":
        return green(difficulty)
    if difficulty.lower() == "medium":
        return yellow(difficulty)
    if difficulty.lower() == "hard":
        return red(difficulty)
    return difficulty


def cache_dir() -> Path:
    custom = os.environ.get("LEETCLI_CACHE_DIR")
    if custom:
        path = Path(custom).expanduser()
    else:
        path = Path.cwd() / ".leetcli-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_path(name: str) -> Path:
    return cache_dir() / name


def load_cache(name: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    path = cache_path(name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, (int, float)):
        return None
    if time.time() - fetched_at > ttl_seconds:
        return None
    return payload.get("data")


def save_cache(name: str, data: Any) -> None:
    path = cache_path(name)
    payload = {"fetched_at": int(time.time()), "data": data}
    path.write_text(json.dumps(payload, indent=2))


def _operation_name(query: str) -> Optional[str]:
    match = re.search(r"query\s+(\w+)", query)
    if match:
        return match.group(1)
    return None


def post_graphql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "leetcli/0.1",
        "Origin": "https://leetcode.com",
        "Referer": "https://leetcode.com/problemset/",
    }
    session = os.environ.get("LEETCODE_SESSION")
    if session:
        headers["Cookie"] = f"LEETCODE_SESSION={session}"
    payload = {"query": query, "variables": variables}
    op_name = _operation_name(query)
    if op_name:
        payload["operationName"] = op_name
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    data = json.loads(raw.decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_problem_list_rest() -> List[Dict[str, Any]]:
    req = urllib.request.Request(
        PROBLEM_LIST_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "leetcli/0.1",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8"))
    items = []
    for entry in payload.get("stat_status_pairs", []):
        stat = entry.get("stat", {})
        difficulty = entry.get("difficulty", {}).get("level")
        if difficulty == 1:
            diff_label = "Easy"
        elif difficulty == 2:
            diff_label = "Medium"
        elif difficulty == 3:
            diff_label = "Hard"
        else:
            diff_label = "Unknown"
        items.append(
            {
                "questionId": str(stat.get("question_id", "")),
                "questionFrontendId": str(stat.get("frontend_question_id", "")),
                "title": stat.get("question__title", ""),
                "titleSlug": stat.get("question__title_slug", ""),
                "difficulty": diff_label,
                "paidOnly": entry.get("paid_only", False),
            }
        )
    return items


def fetch_problem_list() -> List[Dict[str, Any]]:
    cached = load_cache("problem_list.json", LIST_TTL_SECONDS)
    if cached:
        return cached
    all_items: List[Dict[str, Any]] = []
    skip = 0
    limit = 100
    try:
        while True:
            data = post_graphql(
                LIST_QUERY,
                {"categorySlug": "", "skip": skip, "limit": limit, "filters": {}},
            )
            problemset = data["problemsetQuestionList"]
            items = problemset["questions"]
            all_items.extend(items)
            skip += limit
            if len(all_items) >= problemset["total"] or not items:
                break
    except RuntimeError:
        all_items = fetch_problem_list_rest()
    save_cache("problem_list.json", all_items)
    return all_items


def fetch_question(slug: str) -> Dict[str, Any]:
    cache_name = f"question_{slug}.json"
    cached = load_cache(cache_name, QUESTION_TTL_SECONDS)
    if cached:
        return cached
    data = post_graphql(DETAIL_QUERY, {"titleSlug": slug})
    question = data["question"]
    save_cache(cache_name, question)
    return question


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_number(text: str) -> bool:
    return text.isdigit()


def find_by_id(items: Iterable[Dict[str, Any]], frontend_id: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("questionFrontendId") == frontend_id:
            return item
    return None


def find_matches(items: Iterable[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = normalize_text(query)
    matches = []
    for item in items:
        title = normalize_text(item.get("title", ""))
        slug = normalize_text(item.get("titleSlug", ""))
        if q in title or q in slug:
            matches.append(item)
    return matches


def render_search(matches: List[Dict[str, Any]], limit: int) -> str:
    lines = []
    for item in matches[:limit]:
        frontend_id = item.get("questionFrontendId")
        title = item.get("title")
        difficulty = difficulty_color(item.get("difficulty", ""))
        paid = item.get("paidOnly")
        paid_mark = " " + dim("(paid)") if paid else ""
        lines.append(f"{bold(frontend_id)} {title}  {difficulty}{paid_mark}")
    if not lines:
        return red("No matches.")
    return "\n".join(lines)


def render_question(question: Dict[str, Any]) -> str:
    frontend_id = question.get("questionFrontendId")
    title = question.get("title")
    difficulty = difficulty_color(question.get("difficulty", ""))
    tags = ", ".join(tag["name"] for tag in question.get("topicTags", []))
    header = f"{bold(f'#{frontend_id}')} {bold(title)}"
    meta = f"{difficulty}"
    if tags:
        meta = f"{meta}  {dim(tags)}"
    content = question.get("content") or ""
    text = html_to_text(content)
    link = f"https://leetcode.com/problems/{question.get('titleSlug')}/"
    parts = [header, meta, "", text, "", blue(link)]
    return "\n".join(part for part in parts if part is not None)


def resolve_slug(query: str, items: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    if is_number(query):
        item = find_by_id(items, query)
        if item:
            return item["titleSlug"], None
        return None, None
    if "-" in query and " " not in query:
        return query.strip(), None
    matches = find_matches(items, query)
    if not matches:
        return None, None
    if len(matches) == 1:
        return matches[0]["titleSlug"], None
    return None, matches


def cmd_search(args: argparse.Namespace) -> int:
    try:
        items = fetch_problem_list()
    except (urllib.error.URLError, RuntimeError) as exc:
        print(red(f"Failed to fetch problem list: {exc}"))
        return 1
    matches = find_matches(items, args.query)
    print(render_search(matches, args.limit))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    try:
        items = fetch_problem_list()
    except (urllib.error.URLError, RuntimeError) as exc:
        print(red(f"Failed to fetch problem list: {exc}"))
        return 1
    slug, matches = resolve_slug(args.query, items)
    if matches:
        print(render_search(matches, args.limit))
        print(dim("Multiple matches. Be more specific or pass an id."))
        return 1
    if not slug:
        print(red("Problem not found."))
        return 1
    try:
        question = fetch_question(slug)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(red(f"Failed to fetch problem details: {exc}"))
        return 1
    if question.get("isPaidOnly") and not question.get("content"):
        print(red("Paid-only problem. Set LEETCODE_SESSION to access full content."))
    print(render_question(question))
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    try:
        items = fetch_problem_list()
    except (urllib.error.URLError, RuntimeError) as exc:
        print(red(f"Failed to fetch problem list: {exc}"))
        return 1
    slug, matches = resolve_slug(args.query, items)
    if matches:
        print(render_search(matches, args.limit))
        print(dim("Multiple matches. Be more specific or pass an id."))
        return 1
    if not slug:
        print(red("Problem not found."))
        return 1
    url = f"https://leetcode.com/problems/{slug}/"
    webbrowser.open(url)
    print(blue(url))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lc", description="LeetCode problem fetcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search problems by title")
    search.add_argument("query", help="Title text or slug")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    get = subparsers.add_parser("get", help="Fetch a problem by id, title, or slug")
    get.add_argument("query", help="Problem id, title text, or slug")
    get.add_argument("--limit", type=int, default=10)
    get.set_defaults(func=cmd_get)

    open_cmd = subparsers.add_parser("open", help="Open a problem in your browser")
    open_cmd.add_argument("query", help="Problem id, title text, or slug")
    open_cmd.add_argument("--limit", type=int, default=10)
    open_cmd.set_defaults(func=cmd_open)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        exit_code = args.func(args)
    except KeyboardInterrupt:
        print(red("Cancelled."))
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
