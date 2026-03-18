from notion_client import Client as NotionClient
import os
from dotenv import load_dotenv

load_dotenv()

notion = NotionClient(auth=os.getenv("NOTION_TOKEN"))
DATABASE_ID = os.getenv("ROUTINE_DB_ID")


# 번호 세팅 (시작 0, 추가 +1씩 진행)
def get_next_number() -> int:
    response = notion.databases.query(
        database_id=DATABASE_ID,
        sorts=[{"property": "번호", "direction": "descending"}],
        page_size=1
    )
    results = response.get("results", [])
    if not results:
        return 0
    last_title = results[0]["properties"]["번호"]["title"]
    if not last_title:
        return 0
    try:
        return int(last_title[0]["text"]["content"]) + 1
    except (ValueError, IndexError):
        return 0


# 일자 + 담당자로 행 조회
def query_by_date(target_date: str, assignee: str) -> list:
    response = notion.databases.query(
        database_id=DATABASE_ID,
        filter={
            "and": [
                {"property": "일자", "date": {"equals": target_date}},
                {"property": "담당자", "select": {"equals": assignee}},
            ]
        }
    )
    rows = []
    for page in response.get("results", []):
        props = page["properties"]
        rows.append({
            "page_id": page["id"],
            "번호": _get_title(props, "번호"),
            "일자": _get_date(props, "일자"),
            "시간대": _get_text(props, "시간대"),
            "담당자": _get_select(props, "담당자"),
            "내용": _get_text(props, "내용"),
            "특이사항": _get_text(props, "특이사항"),
            "달성도": _get_text(props, "달성도"),
        })
    return rows


# 행 생성 or 수정 (날짜 + 담당자 + 시간대)
def create_or_update_row(target_date: str, assignee: str, row: dict, next_num: int = None):
    """
    row: {"시간대": ..., "내용": ..., "특이사항": ..., "달성도": ...}
    next_num: 외부에서 번호 직접 지정 (None이면 DB에서 조회)
    """
    existing = _find_row(target_date, assignee, row["시간대"])

    properties = {
        "시간대": _text_prop(row.get("시간대", "")),
        "담당자": {"select": {"name": assignee}},
        "내용": _text_prop(row.get("내용", "")),
        "특이사항": _text_prop(row.get("특이사항", "")),
        "달성도": _text_prop(str(row.get("달성도", ""))),
        "일자": {"date": {"start": target_date}},
    }

    if existing:
        notion.pages.update(
            page_id=existing["page_id"],
            properties=properties
        )
        print(f"[UPDATE] {target_date} / {assignee} / {row['시간대']}")
    else:
        num = next_num if next_num is not None else get_next_number()
        properties["번호"] = {
            "title": [{"text": {"content": str(num)}}]
        }
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties=properties
        )
        print(f"[CREATE] {target_date} / {assignee} / {row['시간대']} / 번호: {num}")


# 내부 헬퍼
def _find_row(target_date: str, assignee: str, time_slot: str) -> dict | None:
    response = notion.databases.query(
        database_id=DATABASE_ID,
        filter={
            "and": [
                {"property": "일자", "date": {"equals": target_date}},
                {"property": "담당자", "select": {"equals": assignee}},
                {"property": "시간대", "rich_text": {"equals": time_slot}},
            ]
        }
    )
    results = response.get("results", [])
    if not results:
        return None
    return {"page_id": results[0]["id"]}


def _get_title(props, key) -> str:
    try:
        return props[key]["title"][0]["text"]["content"]
    except (KeyError, IndexError):
        return ""

def _get_text(props, key) -> str:
    try:
        return props[key]["rich_text"][0]["text"]["content"]
    except (KeyError, IndexError):
        return ""

def _get_date(props, key) -> str:
    try:
        return props[key]["date"]["start"]
    except (KeyError, TypeError):
        return ""

def _get_select(props, key) -> str:
    try:
        return props[key]["select"]["name"]
    except (KeyError, TypeError):
        return ""

def _text_prop(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value}}]}
