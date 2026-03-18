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


# 키워드 유사어 매핑
REVIEW_KEY_ALIASES = {
    "잘한 점": ["잘한 점", "잘한점", "잘한거", "잘한 것", "좋았던 점", "좋았던점"],
    "아쉬운 점": ["아쉬운 점", "아쉬운점", "아쉬움", "아쉬운거", "아쉬운 것", "부족한 점", "부족한점"],
    "내일 개선할 점": ["내일 개선할 점", "내일개선할점", "개선할 점", "개선할점", "개선점", "내일 할 것", "내일할것"],
    "한 줄 정리": ["한 줄 정리", "한줄정리", "한 줄", "한줄", "총평", "정리"],
}

EXCLUDE_WORDS = {"하루", "루틴", "회고", "표", "오늘", "일정", "기록", "정리"}
 
def _match_review_key(text: str) -> str | None:
    """텍스트에서 유사어 포함 여부로 회고 키 반환"""
    for canonical, aliases in REVIEW_KEY_ALIASES.items():
        for alias in aliases:
            if text.startswith(alias):
                return canonical
    return None


def parse_heading(text: str):
    if "루틴" in text:
        kind = "routine"
    elif "회고" in text:
        kind = "review"
    else:
        return None

    # 키워드 제외하고 이름 추출
    candidates = re.findall(r"([가-힣]{2,4}|[a-zA-Z]{2,})", text)
    assignee = next((w for w in candidates if w not in EXCLUDE_WORDS), None)
    if not assignee:
        return None

    # 날짜 추출
    date_match = (
        re.search(r"(\d{1,2})[/](\d{1,2})", text) or
        re.search(r"(\d{1,2})[-](\d{1,2})", text) or
        re.search(r"(\d{1,2})[.](\d{1,2})", text) or
        re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    )
    if not date_match:
        return None

    month, day = int(date_match.group(1)), int(date_match.group(2))
    target_date = f"{datetime.today().year}-{month:02d}-{day:02d}"

    return kind, assignee, target_date

# 별점 파싱. ⭐ 이모지 또는 ★ 특수문자 모두 처리
def parse_stars(text: str) -> int:
    count = text.count("⭐")
    if count == 0:
        count = text.count("★")
    return count

# 표 블록 ID로 행 목록 반환
def parse_table_rows(table_block_id: str) -> list:
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

# 회고 블록 파싱 진행
def parse_review_blocks(blocks: list, start_index: int) -> dict:
    review = {
        "만족도": 0,
        "잘한 점": "",
        "아쉬운 점": "",
        "내일 개선할 점": "",
        "한 줄 정리": "",
    }
 
    current_key = None
    waiting_for_stars = False  # "만족도" heading 다음 블록에서 별점 대기
 
    for block in blocks[start_index:]:
        btype = block["type"]
 
        # 새 루틴/회고 섹션 시작이면 종료
        if btype in ("heading_1", "heading_2", "heading_3"):
            texts = block[btype]["rich_text"]
            if not texts:
                continue
            raw = "".join(t["plain_text"] for t in texts).strip()
 
            if parse_heading(raw) is not None:
                break
 
            # "만족도" 단독 heading → 다음 블록에서 별점 찾기
            if "만족도" in raw and not any(c in raw for c in ["⭐", "★"]):
                waiting_for_stars = True
                current_key = None
                continue
 
            # heading 안에 별점이 있는 경우
            if "⭐" in raw or "★" in raw:
                review["만족도"] = parse_stars(raw)
                waiting_for_stars = False
                continue
 
            # 회고 키워드 매핑
            matched_key = _match_review_key(raw)
            if matched_key:
                waiting_for_stars = False
                value = raw.split(":", 1)[-1].strip() if ":" in raw else ""
                review[matched_key] = value
                current_key = matched_key if not value else None
            else:
                current_key = None
 
        elif btype in ("paragraph", "bulleted_list_item", "numbered_list_item"):
            texts = block[btype]["rich_text"]
            if not texts:
                continue
            raw = "".join(t["plain_text"] for t in texts).strip()
 
            # 별점 대기 중이거나 별점 포함된 블록
            if waiting_for_stars and ("⭐" in raw or "★" in raw):
                review["만족도"] = parse_stars(raw)
                waiting_for_stars = False
                continue
 
            if "⭐" in raw or "★" in raw:
                review["만족도"] = parse_stars(raw)
                continue
 
            # 회고 키워드 매핑
            matched_key = _match_review_key(raw)
            if matched_key:
                waiting_for_stars = False
                value = raw.split(":", 1)[-1].strip() if ":" in raw else ""
                review[matched_key] = value
                current_key = matched_key if not value else None
            elif current_key and current_key != "만족도":

                # 이전 키의 내용이 다음 줄에 이어지는 경우
                review[current_key] = (review[current_key] + " " + raw).strip()
 
    return review
 
 
# 페이지 전체 파싱
def parse_page(page_id: str) -> tuple:
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
 
 
# 메인 싱크
def sync():
    print("[SYNC 시작] 페이지 읽는 중...\n")
 
    routine_tables, reviews = parse_page(PAGE_ID)
 
    # 루틴 저장
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
 
    # 회고 저장
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
