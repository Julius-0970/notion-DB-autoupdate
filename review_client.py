from notion_client import Client as NotionClient
import os
from dotenv import load_dotenv

load_dotenv()

notion = NotionClient(auth=os.getenv("NOTION_TOKEN"))
REVIEW_DB_ID = os.getenv("REVIEW_DB_ID")


# 1. 다음 번호 반환
def get_next_review_number() -> int:
    response = notion.databases.query(
        database_id=REVIEW_DB_ID,
        sorts=[{"property": "제목", "direction": "descending"}],
        page_size=1
    )
    results = response.get("results", [])
    if not results:
        return 0
    last_title = results[0]["properties"]["제목"]["title"]
    if not last_title:
        return 0
    try:
        return int(last_title[0]["text"]["content"]) + 1
    except (ValueError, IndexError):
        return 0


# 2. 회고 생성 또는 수정 (날짜 + 담당자 조합으로 판단)
def create_or_update_review(target_date: str, assignee: str, review: dict, next_num: int = None):
    """
    review: {
        "만족도": 4,
        "잘한 점": "...",
        "아쉬운 점": "...",
        "내일 개선할 점": "...",
        "한 줄 정리": "..."
    }
    """
    existing = _find_review(target_date, assignee)

    properties = {
        "일자": {"date": {"start": target_date}},
        "담당자": {"select": {"name": assignee}},
        "만족도": {"number": review.get("만족도", 0)},
        "잘한 점": _text_prop(review.get("잘한 점", "")),
        "아쉬운 점": _text_prop(review.get("아쉬운 점", "")),
        "내일 개선할 점": _text_prop(review.get("내일 개선할 점", "")),
        "한 줄 정리": _text_prop(review.get("한 줄 정리", "")),
    }

    if existing:
        notion.pages.update(
            page_id=existing["page_id"],
            properties=properties
        )
        print(f"[UPDATE] 회고 {target_date} / {assignee}")
    else:
        num = next_num if next_num is not None else get_next_review_number()
        properties["제목"] = {
            "title": [{"text": {"content": str(num)}}]
        }
        notion.pages.create(
            parent={"database_id": REVIEW_DB_ID},
            properties=properties
        )
        print(f"[CREATE] 회고 {target_date} / {assignee} / 번호: {num}")


# ─── 내부 헬퍼 ───────────────────────────────────────────

def _find_review(target_date: str, assignee: str) -> dict | None:
    response = notion.databases.query(
        database_id=REVIEW_DB_ID,
        filter={
            "and": [
                {"property": "일자", "date": {"equals": target_date}},
                {"property": "담당자", "select": {"equals": assignee}},
            ]
        }
    )
    results = response.get("results", [])
    if not results:
        return None
    return {"page_id": results[0]["id"]}


def _text_prop(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value}}]}
