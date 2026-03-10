from notion_client import Client as NotionClient
from notion_routine_client import create_or_update_row, get_next_number
from review_client import create_or_update_review, get_next_review_number
from datetime import datetime
import re
import os
from dotenv import load_dotenv

load_dotenv()

notion = NotionClient(auth=os.getenv("NOTION_TOKEN"))
PAGE_ID = os.getenv("ROUTINE_PAGE_ID")


def parse_heading(text: str):
    """
    제목에서 타입/담당자/날짜 추출
    '하루 루틴 표 - 외설(3/10)'  → ('routine', '외설', '2026-03-10')
    '하루 회고 - 외설 (3/10)'    → ('review',  '외설', '2026-03-10')
    """
    for pattern, kind in [
        (r"하루 루틴 표\s*-\s*(.+?)\s*\((\d+)/(\d+)\)", "routine"),
        (r"하루 회고\s*-\s*(.+?)\s*\((\d+)/(\d+)\)",    "review"),
    ]:
        match = re.search(pattern, text)
        if match:
            assignee = match.group(1).strip()
            month, day = int(match.group(2)), int(match.group(3))
            target_date = f"{datetime.today().year}-{month:02d}-{day:02d}"
            return kind, assignee, target_date
    return None


def parse_stars(text: str) -> int:
    """별점 파싱. ⭐ 이모지 또는 ★ 특수문자 모두 처리"""
    count = text.count("⭐")
    if count == 0:
        count = text.count("★")
    return count


def parse_table_rows(table_block_id: str) -> list:
    """표 블록 ID로 행 목록 반환 (헤더 스킵)"""
    table_rows = notion.blocks.children.list(block_id=table_block_id)
    rows = []
    header_skipped = False

    for row in table_rows.get("results", []):
        if row["type"] != "table_row":
            continue
        cells = row["table_row"]["cells"]

        if not header_skipped:
            header_skipped = True
            continue

        def get_cell(index):
            try:
                return cells[index][0]["plain_text"]
            except (IndexError, KeyError):
                return ""

        offset = 1 if len(cells) >= 5 else 0
        rows.append({
            "시간대":   get_cell(offset + 0),
            "내용":     get_cell(offset + 1),
            "특이사항": get_cell(offset + 2),
            "달성도":   get_cell(offset + 3),
        })

    return rows


def parse_review_blocks(blocks: list, start_index: int) -> dict:
    """회고 제목 다음 블록들에서 내용 파싱 (heading 블록도 처리)"""
    review = {
        "만족도": 0,
        "잘한 점": "",
        "아쉬운 점": "",
        "내일 개선할 점": "",
        "한 줄 정리": "",
    }
    key_map = {
        "잘한 점": "잘한 점",
        "아쉬운 점": "아쉬운 점",
        "내일 개선할 점": "내일 개선할 점",
        "한 줄 정리": "한 줄 정리",
    }
    current_key = None

    for block in blocks[start_index:]:
        btype = block["type"]

        # heading 블록도 읽되, 새 섹션(루틴/회고) 시작이면 종료
        if btype in ("heading_1", "heading_2", "heading_3"):
            texts = block[btype]["rich_text"]
            if not texts:
                continue
            raw = "".join(t["plain_text"] for t in texts)

            # 새 루틴/회고 섹션 시작이면 종료
            if parse_heading(raw) is not None:
                break

            # heading 텍스트도 파싱
            if "⭐" in raw or "★" in raw or "☆" in raw:
                review["만족도"] = parse_stars(raw)
                continue

            for key in key_map:
                if raw.startswith(key):
                    value = raw.split(":", 1)[-1].strip() if ":" in raw else ""
                    review[key_map[key]] = value
                    current_key = key_map[key]
                    break

        elif btype in ("paragraph", "bulleted_list_item", "numbered_list_item"):
            texts = block[btype]["rich_text"]
            if not texts:
                continue
            raw = "".join(t["plain_text"] for t in texts)

            # 별점
            if "⭐" in raw or "★" in raw or "☆" in raw:
                review["만족도"] = parse_stars(raw)
                continue

            # 키:값 파싱
            for key in key_map:
                if raw.startswith(key):
                    value = raw.split(":", 1)[-1].strip() if ":" in raw else ""
                    review[key_map[key]] = value
                    current_key = key_map[key]
                    break
            else:
                pass

    return review


def parse_page(page_id: str) -> tuple:
    """페이지 전체 블록 읽어서 루틴 표 목록, 회고 목록 반환"""
    blocks = notion.blocks.children.list(block_id=page_id).get("results", [])
    routine_tables = []
    reviews = []
    current_routine_meta = None

    for i, block in enumerate(blocks):
        btype = block["type"]

        if btype in ("heading_1", "heading_2", "heading_3"):
            texts = block[btype]["rich_text"]
            if not texts:
                continue
            raw = "".join(t["plain_text"] for t in texts)
            parsed = parse_heading(raw)

            if not parsed:
                current_routine_meta = None
                continue

            kind, assignee, target_date = parsed

            if kind == "routine":
                current_routine_meta = (assignee, target_date)

            elif kind == "review":
                current_routine_meta = None
                review = parse_review_blocks(blocks, i + 1)
                print(f"  [회고 파싱] {assignee} / {target_date} → {review}")
                reviews.append({
                    "assignee": assignee,
                    "target_date": target_date,
                    "review": review,
                })

        elif btype == "table" and current_routine_meta:
            assignee, target_date = current_routine_meta
            rows = parse_table_rows(block["id"])
            routine_tables.append({
                "assignee": assignee,
                "target_date": target_date,
                "rows": rows,
            })
            current_routine_meta = None

    return routine_tables, reviews


def sync():
    print("[SYNC 시작] 페이지 읽는 중...\n")

    routine_tables, reviews = parse_page(PAGE_ID)

    # ── 루틴 저장 ──
    total_routine = 0
    next_num = get_next_number()

    for table in routine_tables:
        assignee = table["assignee"]
        target_date = table["target_date"]
        rows = table["rows"]
        print(f"\n[루틴] 날짜: {target_date} / 담당자: {assignee} / {len(rows)}행")

        for row in rows:
            if not row["시간대"]:
                continue
            create_or_update_row(
                target_date=target_date,
                assignee=assignee,
                row=row,
                next_num=next_num
            )
            next_num += 1
            total_routine += 1

    # ── 회고 저장 ──
    total_review = 0
    next_review_num = get_next_review_number()

    for item in reviews:
        assignee = item["assignee"]
        target_date = item["target_date"]
        review = item["review"]
        print(f"\n[회고] 날짜: {target_date} / 담당자: {assignee} / 만족도: {review['만족도']}")

        create_or_update_review(
            target_date=target_date,
            assignee=assignee,
            review=review,
            next_num=next_review_num
        )
        next_review_num += 1
        total_review += 1

    print(f"\n[SYNC 완료] 루틴 {total_routine}행 / 회고 {total_review}건 처리됨")


if __name__ == "__main__":
    sync()
