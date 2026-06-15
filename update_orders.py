import argparse
import calendar
import csv
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen
from xml.etree import ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.getenv("DART_API_KEY", "")
OUTPUT_FILE = os.path.join(BASE_DIR, "ship_order_summary.csv")
TARGET_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_order_targets.csv")
MONTHLY_SALES_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_monthly_sales.csv")
QUARTERLY_FINANCIALS_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_quarterly_financials.csv")
SEGMENT_REVENUE_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_segment_revenue.csv")
COST_STRUCTURE_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_cost_structure.csv")
RAW_MATERIAL_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_raw_material_prices.csv")
DELIVERY_VOLUME_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_delivery_volume.csv")
MARKET_CAP_OUTPUT_FILE = os.path.join(BASE_DIR, "ship_market_cap.csv")
FORECAST_SCRIPT_FILE = os.path.join(BASE_DIR, "forecast_financials.py")
PROJECT_PYTHON = os.path.join(os.path.dirname(BASE_DIR), ".venv", "bin", "python")
SEARCH_START_DATE = "20200101"
SEARCH_END_DATE = date.today().strftime("%Y%m%d")
ORDER_CORRECTION_LOOKBACK_DAYS = int(os.getenv("ORDER_CORRECTION_LOOKBACK_DAYS", "370"))
COST_STRUCTURE_START_DATE = "20190101"
DASHBOARD_FILE = os.path.join(BASE_DIR, "dashboard.py")
DASHBOARD_PORT = 8501
AUTO_START_DASHBOARD = True
OUTPUT_COLUMNS = [
    "회사",
    "공시일",
    "체결계약명",
    "유추선종",
    "수주_선박수",
    "계약금액",
    "계약기간_시작일",
    "계약기간_종료일",
    "매매기준환율",
    "수정_체결계약명",
    "수정_유추선종",
    "수정_수주_선박수",
    "수정_계약금액",
    "수정_계약기간_종료일",
    "계약해지",
    "공시명",
    "DART_URL",
    "정정공시_URL",
    "비고",
]
TARGET_OUTPUT_COLUMNS = [
    "회사",
    "목표연도",
    "목표구분",
    "수주목표",
    "목표단위",
    "수주목표_억불",
    "공시일",
    "공시명",
    "접수번호",
    "DART_URL",
]
MONTHLY_SALES_OUTPUT_COLUMNS = [
    "회사",
    "실적월",
    "매출구분",
    "매출액_백만원",
    "매출액_억원",
    "기준구분",
    "실적기간_시작일",
    "실적기간_종료일",
    "공시일",
    "공시명",
    "DART_URL",
]
QUARTERLY_FINANCIALS_OUTPUT_COLUMNS = [
    "회사",
    "실적분기",
    "매출액_억원",
    "영업이익_억원",
    "실적기간_시작일",
    "실적기간_종료일",
    "공시일",
    "공시명",
    "DART_URL",
]
SEGMENT_REVENUE_OUTPUT_COLUMNS = [
    "회사",
    "실적분기",
    "사업부문",
    "누적매출액_백만원",
    "누적매출액_억원",
    "분기매출액_백만원",
    "분기매출액_억원",
    "실적기간_시작일",
    "실적기간_종료일",
    "공시일",
    "공시명",
    "접수번호",
    "DART_URL",
]
COST_STRUCTURE_OUTPUT_COLUMNS = [
    "회사",
    "실적분기",
    "비용항목",
    "누적비용_백만원",
    "누적비용_억원",
    "분기비용_백만원",
    "분기비용_억원",
    "실적기간_시작일",
    "실적기간_종료일",
    "공시일",
    "공시명",
    "접수번호",
    "DART_URL",
]
RAW_MATERIAL_OUTPUT_COLUMNS = [
    "회사",
    "실적분기",
    "원재료항목",
    "가격",
    "단위",
    "공시일",
    "공시명",
    "접수번호",
    "DART_URL",
]
DELIVERY_VOLUME_OUTPUT_COLUMNS = [
    "회사",
    "실적분기",
    "품목",
    "누적기납품수량",
    "분기기납품수량",
    "실적기간_시작일",
    "실적기간_종료일",
    "공시일",
    "공시명",
    "접수번호",
    "DART_URL",
]
MARKET_CAP_OUTPUT_COLUMNS = [
    "회사",
    "stock_code",
    "기준일",
    "시가총액",
    "시가총액_억원",
    "시가총액_조원",
    "종가",
    "상장주식수",
    "수집일",
]

COMPANIES = {
    "HD현대중공업": {"stock_code": "329180", "corp_name": "HD현대중공업"},
    "HD현대미포": {"stock_code": "010620", "corp_name": "HD현대미포"},
    "HD한국조선해양": {"stock_code": "009540", "corp_name": "HD한국조선해양"},
    "삼성중공업": {"stock_code": "010140", "corp_name": "삼성중공업"},
    "한화오션": {"stock_code": "042660", "corp_name": "한화오션"},
    "대한조선": {"stock_code": "439260", "corp_name": "대한조선"},
}
MONTHLY_SALES_COMPANIES = {
    "HD현대중공업": COMPANIES["HD현대중공업"],
    "HD현대미포": COMPANIES["HD현대미포"],
    "HD현대삼호": COMPANIES["HD한국조선해양"],
}
QUARTERLY_FINANCIALS_COMPANIES = MONTHLY_SALES_COMPANIES
QUARTERLY_FINANCIALS_COMPANIES = {
    **QUARTERLY_FINANCIALS_COMPANIES,
    "삼성중공업": COMPANIES["삼성중공업"],
    "한화오션": COMPANIES["한화오션"],
    "대한조선": COMPANIES["대한조선"],
}
TARGET_REPORT_COMPANIES = {"HD현대중공업", "HD현대미포", "HD한국조선해양", "삼성중공업"}
MARKET_CAP_COMPANIES = {
    "HD현대중공업": COMPANIES["HD현대중공업"],
    "삼성중공업": COMPANIES["삼성중공업"],
    "한화오션": COMPANIES["한화오션"],
    "대한조선": COMPANIES["대한조선"],
}
MARCAP_RAW_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{year}.parquet"
MAX_CORRECTION_URLS = 3

SHIP_TYPE_KEYWORDS = {
    "LNG벙커링선": [
        "LNG BV",
        "LNG Bunkering",
        "LNG 벙커링",
        "LNG벙커링",
        "LNG Bunker",
        "LNG bunker",
    ],
    "LNG운반선": [
        "LNG운반선",
        "LNG 운반선",
        "LNG선",
        "LNG 선",
        "LNGC",
        "LNG CARRIER",
        "FSRU",
        "액화천연가스",
        "Liquefied Natural Gas",
    ],
    "가스선": ["VLEC", "ULEC", "에탄운반선", "LPG", "LPGC", "VLGC", "VLAC", "MGC", "LCO2", "암모니아", "Ammonia"],
    "컨테이너선": ["컨테이너선", "Container", "CONT", "TEU", "CONRO"],
    "탱커": ["원유운반선", "유조선", "탱커", "석유화학제품운반선", "VLCC", "Suezmax", "Aframax", "Product Carrier", "P/C선", "P/C", "T/K"],
    "벌크선": ["벌크선", "Bulk Carrier", "B/C선", "BC"],
    "자동차운반선": ["자동차운반선", "PCTC", "PCC", "Car Carrier", "RORO", "ROPAX", "RO-PAX"],
    "쇄빙선": ["쇄빙전용선", "쇄빙연구선", "쇄빙선", "Icebreaker"],
    "해양플랜트": ["FPSO", "FPS", "FPU", "FLNG", "해양플랜트", "해상플랫폼 상부 구조물", "Offshore", "부유식", "해양생산설비"],
    "특수선/방산": ["군함", "함정", "잠수함", "방산", "특수선", "호위함", "구축함", "수상함", "군수지원함", "해상풍력발전기 설치선"],
    "엔진기계": ["엔진발전기"],
    "토건": ["FAB동", "마감공사", "하이테크", "토목", "건축"],
}

ORDER_KEYWORDS = [
    "단일판매ㆍ공급계약체결",
    "단일판매ㆍ공급계약체결(자율공시)",
    "단일판매·공급계약체결",
    "[기재정정]단일판매ㆍ공급계약체결",
    "단일판매ㆍ공급계약해지",
    "공급계약"
]

EXCLUDED_ORDER_RECEIPTS = {
    # Old non-ship legacy projects pulled in by later correction filings.
    # These distort the ship order/backlog dashboard when the view starts from 2020.
    "20130805800023",  # Construction of Shuqaiq Steam Power Plant
    "20141112800082",  # Nasr Full Field Development Package 2
}

PARENT_COMPANY_WITH_SUBSIDIARIES = "HD한국조선해양"
COMPANY_NAME_ALIASES = {
    "현대중공업(주)": "HD현대중공업",
    "현대중공업": "HD현대중공업",
    "에이치디현대중공업(주)": "HD현대중공업",
    "에이치디현대중공업": "HD현대중공업",
    "HD현대중공업(주)": "HD현대중공업",
    "HD현대중공업": "HD현대중공업",
    "현대미포조선(주)": "HD현대미포",
    "현대미포조선": "HD현대미포",
    "에이치디현대미포(주)": "HD현대미포",
    "에이치디현대미포": "HD현대미포",
    "HD현대미포(주)": "HD현대미포",
    "HD현대미포": "HD현대미포",
    "현대삼호중공업(주)": "HD현대삼호",
    "현대삼호중공업": "HD현대삼호",
    "에이치디현대삼호(주)": "HD현대삼호",
    "에이치디현대삼호": "HD현대삼호",
    "HD현대삼호(주)": "HD현대삼호",
    "HD현대삼호": "HD현대삼호",
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("br", "p", "tr", "td", "th", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in ("p", "tr", "td", "th", "div", "table"):
            self.parts.append("\n")

    def text(self):
        text = " ".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n+ *", "\n", text)
        return text.strip()


def fetch_bytes(url, params):
    request_url = f"{url}?{urlencode(params)}"
    try:
        with urlopen(request_url, timeout=30) as response:
            return response.read()
    except HTTPError as e:
        raise RuntimeError(f"HTTP 오류: {e.code} {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"네트워크 오류: {e.reason}") from e


def post_json(url, params, headers=None):
    data = urlencode(params).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers=headers or {},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    except HTTPError as e:
        raise RuntimeError(f"HTTP 오류: {e.code} {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"네트워크 오류: {e.reason}") from e

    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 응답 파싱 실패: {text[:300]}") from e


def parse_dart_error(raw):
    try:
        error = ET.fromstring(raw.decode("utf-8", errors="ignore"))
    except ET.ParseError:
        return None

    status = error.findtext("status")
    message = error.findtext("message")
    if status or message:
        return f"DART API 오류(status={status or 'unknown'}): {message or '알 수 없는 오류'}"
    return None


def decode_document_bytes(raw):
    head = raw[:500].decode("ascii", errors="ignore")
    match = re.search(r'encoding=["\']?([A-Za-z0-9_-]+)', head, re.IGNORECASE)
    encodings = []
    if match:
        encodings.append(match.group(1))
    encodings.extend(["utf-8", "cp949", "euc-kr"])

    tried = set()
    for encoding in encodings:
        encoding = encoding.lower()
        if encoding in tried:
            continue
        tried.add(encoding)
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="replace")


def get_corp_codes():
    raw = fetch_bytes(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        {"crtfc_key": API_KEY},
    )

    if not zipfile.is_zipfile(io.BytesIO(raw)):
        dart_error = parse_dart_error(raw)
        if dart_error:
            raise RuntimeError(dart_error)
        preview = raw.decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"corpCode.xml 응답이 ZIP이 아닙니다: {preview}")

    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read(z.namelist()[0])

    root = ET.fromstring(xml)
    rows = []
    for item in root.findall("list"):
        rows.append({
            "corp_code": item.findtext("corp_code"),
            "corp_name": item.findtext("corp_name"),
            "stock_code": item.findtext("stock_code"),
            "modify_date": item.findtext("modify_date"),
        })
    return rows


def resolve_corp_code(corp_rows, stock_code=None, corp_name=None):
    if stock_code:
        for row in corp_rows:
            if row["stock_code"] == stock_code:
                return row["corp_code"]
        raise ValueError(f"stock_code로 corp_code를 찾지 못함: {corp_name} ({stock_code})")

    for row in corp_rows:
        if corp_name and corp_name in row["corp_name"]:
            return row["corp_code"]

    raise ValueError(f"corp_code를 찾지 못함: {corp_name}")


def search_filings(corp_code, start=SEARCH_START_DATE, end=SEARCH_END_DATE):
    all_rows = []
    page = 1

    while True:
        raw = fetch_bytes(
            "https://opendart.fss.or.kr/api/list.xml",
            {
                "crtfc_key": API_KEY,
                "corp_code": corp_code,
                "bgn_de": start,
                "end_de": end,
                "page_no": page,
                "page_count": 100,
                "sort": "date",
                "sort_mth": "desc",
            },
        )
        root = ET.fromstring(raw)
        status = root.findtext("status")
        message = root.findtext("message")

        if status not in ("000", "013"):
            raise RuntimeError(f"DART API 오류(status={status}): {message}")

        for item in root.findall("list"):
            all_rows.append({
                "rcept_dt": item.findtext("rcept_dt", ""),
                "report_nm": item.findtext("report_nm", ""),
                "rcept_no": item.findtext("rcept_no", ""),
            })

        total_page = int(root.findtext("total_page", "1"))
        if page >= total_page:
            break
        page += 1

    return all_rows


def download_document_text(rcept_no):
    raw = fetch_bytes(
        "https://opendart.fss.or.kr/api/document.xml",
        {"crtfc_key": API_KEY, "rcept_no": rcept_no},
    )

    dart_error = parse_dart_error(raw)
    if dart_error:
        raise RuntimeError(dart_error)

    texts = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                text = decode_document_bytes(z.read(name))
                parser = TextExtractor()
                parser.feed(text)
                texts.append(parser.text())
    except zipfile.BadZipFile:
        text = decode_document_bytes(raw)
        parser = TextExtractor()
        parser.feed(text)
        texts.append(parser.text())

    return "\n".join(texts)


def classify_ship_type(text):
    if re.search(r"LNG\s*Barge|LNG\s*바지|초대형\s*LNG\s*Barge", text, re.IGNORECASE):
        return "해양플랜트"
    text_lower = text.lower()
    found = []
    for ship_type, keywords in SHIP_TYPE_KEYWORDS.items():
        if any(keyword.lower() in text_lower for keyword in keywords):
            found.append(ship_type)
    return ", ".join(found) if found else "미분류"


def compact_text(text):
    return re.sub(r"\s+", " ", text).strip()


def clean_value(value):
    value = compact_text(value)
    value = re.sub(r"^\W+", "", value)
    value = re.sub(r"\W+$", "", value)
    return value.strip()


def first_match(text, patterns):
    target = compact_text(text)
    for pattern in patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            return clean_value(match.group(1))
    return ""


def extract_subsidiary_company(text):
    target = compact_text(text)
    patterns = [
        r"자회사인\s+(.+?)\s+의\s+주요경영사항",
        r"자회사명\s*:\s*(.+?)\s*-\s*자산총액비중",
        r"자회사명\s+(.+?)\s+자산총액비중",
    ]
    for pattern in patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            return compact_text(match.group(1)).strip(" :-")
    return ""


def normalize_company_name(company_name):
    company_name = compact_text(company_name)
    lookup_key = re.sub(r"\s+", "", company_name)
    for source, target in COMPANY_NAME_ALIASES.items():
        if lookup_key == re.sub(r"\s+", "", source):
            return target
    return company_name


def canonical_dashboard_company_name(company_name):
    return normalize_company_name(company_name)


def is_separately_collected_hd_hyundai_subsidiary(company_name):
    normalized = re.sub(r"\s+", "", company_name)
    return "현대중공업" in normalized or "현대미포" in normalized or "현대미포조선" in normalized


def display_company_name(parent_company, text):
    if parent_company != PARENT_COMPANY_WITH_SUBSIDIARIES:
        return normalize_company_name(parent_company)

    subsidiary = extract_subsidiary_company(text)
    return normalize_company_name(subsidiary or parent_company)


def target_company_name(company, text):
    return display_company_name(company, text)


def should_skip_parent_subsidiary_filing(parent_company, actual_company):
    return (
        parent_company == PARENT_COMPANY_WITH_SUBSIDIARIES
        and actual_company != parent_company
        and is_separately_collected_hd_hyundai_subsidiary(actual_company)
    )


def target_existing_company_names(company):
    if company == PARENT_COMPANY_WITH_SUBSIDIARIES:
        return {PARENT_COMPANY_WITH_SUBSIDIARIES, "HD현대삼호"}
    return {company}


def latest_contract_section(text):
    target = compact_text(text)
    markers = [
        "1. 판매ㆍ공급계약 구분",
        "1. 판매·공급계약 구분",
        "1. 판매ㆍ공급계약 해지 구분",
        "계약 내용 변경에 따른 정정공시",
        "정정공시 단일판매ㆍ공급계약 체결",
        "정정공시 단일판매·공급계약 체결",
    ]
    positions = [target.rfind(marker) for marker in markers]
    position = max(positions)
    if position >= 0:
        return target[position:]
    return target


def extract_contract_name(text):
    section = latest_contract_section(text)
    return first_match(section, [
        r"체결계약명\s+(.+?)\s+(?:2\.\s*)?계약내역",
        r"체결계약명\s+(.+?)\s+계약금액",
        r"계약명\s+(.+?)\s+(?:2\.\s*)?계약내역",
        r"세부내용\s+(.+?)\s+(?:2\.\s*)?계약내역",
    ])


def extract_contract_amount(text):
    section = latest_contract_section(text)
    return first_match(section, [
        r"계약금액\s*\(?원\)?\s*([0-9,]+)",
        r"계약금액\s*\(?천원\)?\s*([0-9,]+)",
        r"계약금액\s*\(?억원\)?\s*([0-9,.]+)",
        r"계약금액[^0-9]{0,30}([0-9,]+)\s*원",
        r"계약금액[^0-9]{0,30}([0-9,.]+)\s*억원",
    ])


def extract_contract_period(text):
    target = latest_contract_section(text)
    patterns = [
        r"계약기간\s+시작일\s+([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})\s+종료일\s+([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})",
        r"시작일\s+([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})\s+종료일\s+([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})",
        r"계약기간[^0-9]+([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})\s*(?:부터|~|-|∼|～|까지)\s*([0-9]{4}[-./][0-9]{2}[-./][0-9]{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return clean_value(match.group(1)), clean_value(match.group(2))
    return "", ""


def extract_exchange_rate(text):
    target = compact_text(text)
    patterns = [
        r"매매기준(?:율|환율)[^@]{0,80}@\s*([0-9,]+(?:\.[0-9]+)?)\s*/\s*원\s*/\s*(?:USD|US\$|\$|달러)",
        r"매매기준(?:율|환율)[^@]{0,80}@\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:원)?\s*/?\s*(?:USD|US\$|\$|달러)",
        r"(?:매매기준(?:율|환율)|최초\s*고시환율)[^0-9A-Z$]{0,80}(?:USD|US\$|\$|달러)\s*1\s*=?\s*([0-9,]+(?:\.[0-9]+)?)\s*원?",
        r"(?:매매기준(?:율|환율)|최초\s*고시환율)[^0-9A-Z$]{0,80}(?:1\s*)?(?:USD|US\$|\$|달러)\s*=?\s*([0-9,]+(?:\.[0-9]+)?)\s*원?",
        r"(?:매매기준(?:율|환율)|최초\s*고시환율)[^0-9A-Z$]{0,80}([0-9,]+(?:\.[0-9]+)?)\s*원?\s*/\s*(?:USD|US\$|\$|달러)",
        r"(?:1\s*)?(?:USD|US\$|\$|달러)\s*=\s*([0-9,]+(?:\.[0-9]+)?)\s*원?",
        r"(?:USD|US\$|\$|달러)\s*1\s*=\s*([0-9,]+(?:\.[0-9]+)?)\s*원?",
        r"@\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:원)?\s*/?\s*(?:USD|US\$|\$|달러)",
        r"(?:USD|US\$|\$|달러)\s*당\s*([0-9,]+(?:\.[0-9]+)?)\s*원",
    ]
    for pattern in patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            return clean_value(match.group(1))
    return ""


def extract_ship_count(contract_name):
    counts = [int(match) for match in re.findall(r"([0-9]+)\s*척", contract_name)]
    if not counts:
        return ""
    return str(sum(counts))


def normalize_date(value):
    value = compact_text(value)
    match = re.search(r"([0-9]{4})[-./년 ]+([0-9]{1,2})[-./월 ]+([0-9]{1,2})", value)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}{int(month):02d}{int(day):02d}"


def format_output_date(value):
    normalized = normalize_date(value)
    if not normalized and re.fullmatch(r"[0-9]{8}", str(value).strip()):
        normalized = str(value).strip()
    if not normalized:
        return value
    return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"


def normalize_storage_date(value):
    normalized = normalize_date(value)
    if normalized:
        return normalized

    value = str(value).strip()
    if re.fullmatch(r"[0-9]{8}", value):
        return value
    return ""


def extract_receipt_no_from_url(url):
    match = re.search(r"rcpNo=([0-9]+)", str(url))
    return match.group(1) if match else ""


def order_receipt_no(row):
    return row.get("접수번호") or row.get("rcept_no") or extract_receipt_no_from_url(row.get("DART_URL", ""))


def is_excluded_order_row(row):
    return order_receipt_no(row) in EXCLUDED_ORDER_RECEIPTS


def normalize_correction_urls(urls):
    url_list = [
        url.strip()
        for url in str(urls).split("|")
        if url.strip() and url.strip().lower() not in {"nan", "none"}
    ]
    if not url_list:
        return ""
    unique_urls = list(dict.fromkeys(url_list))
    ordered_urls = sorted(unique_urls, key=lambda url: extract_receipt_no_from_url(url) or url)
    return " | ".join(ordered_urls[-MAX_CORRECTION_URLS:])


def correction_backfill_start_date():
    start = (date.today() - timedelta(days=ORDER_CORRECTION_LOOKBACK_DAYS)).strftime("%Y%m%d")
    return max(SEARCH_START_DATE, start)


def extract_correction_related_date(text):
    return normalize_date(first_match(text, [
        r"정정관련\s*공시서류제출일\s+([0-9]{4}[-./][0-9]{1,2}[-./][0-9]{1,2})",
        r"정정관련\s*공시서류제출일\s+([0-9]{4}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일)",
    ]))


def extract_original_disclosure_date(text):
    target = compact_text(text)
    patterns = [
        r"([0-9]{4}[-./][0-9]{1,2}[-./][0-9]{1,2})[^.]{0,80}공시하였습니다",
        r"([0-9]{4}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일)[^.]{0,80}공시하였습니다",
    ]
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return normalize_date(match.group(1))
    return ""


CORRECTION_ITEM_RE = re.compile(
    r"\d+\.\s*(?:판매\s*[ㆍ·]\s*공급계약\s*구분\s*-\s*)?(?:"
    r"체결계약명|"
    r"(?:계약내역\s*-\s*)?계약금액\s*\(원\)|"
    r"(?:계약내역\s*-\s*)?매출액대비\s*\(%\)|"
    r"계약기간\s*-\s*(?:시작일|종료일)|"
    r"주요\s*계약조건\s*-\s*(?:계약금[·ㆍ]?선급금\s*유무|대금지급\s*조건\s*등|[^0-9]{1,40})|"
    r"기타\s*투자판단과\s*관련한\s*중요사항"
    r")",
    re.IGNORECASE,
)


def short_text(value, limit=120):
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def extract_correction_reason(text):
    reason = first_match(text, [
        r"정정사유\s+(.+?)\s+\d+\.\s*정정사항",
        r"정정사유\s+(.+?)\s+정정사항",
        r"정정사유\s+(.+?)\s+정정항목",
    ])
    return re.sub(r"\s+\d+$", "", reason).strip()


def extract_correction_section(text):
    target = compact_text(text)
    start = target.find("정정사항")
    if start < 0:
        start = target.find("정정항목 정정전 정정후")
    if start < 0:
        return ""

    section = target[start:]
    end_patterns = [
        r"\s단일판매\s*[ㆍ·]\s*공급계약\s*(?:체결|해지)\s+1\.",
        r"\s정정공시\s+단일판매\s*[ㆍ·]\s*공급계약\s*체결\s+1\.",
        r"\s계약\s*내용\s*변경에\s*따른\s*정정공시\s+1\.",
        r"\s【\s*대표이사\s*등의\s*확인\s*】",
    ]
    end_positions = []
    for pattern in end_patterns:
        match = re.search(pattern, section)
        if match:
            end_positions.append(match.start())

    if end_positions:
        section = section[:min(end_positions)]

    section = re.sub(r"^정정사항\s*", "", section)
    section = re.sub(r"^정정항목\s+정정전\s+정정후\s*", "", section)
    return compact_text(section)


def clean_correction_item_name(value):
    value = compact_text(value)
    value = re.sub(r"^\d+\.\s*", "", value)
    value = re.sub(r"^판매\s*[ㆍ·]\s*공급계약\s*구분\s*-\s*", "", value)
    value = re.sub(r"^계약내역\s*-\s*", "", value)
    value = value.replace("·", "ㆍ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def summarize_correction_payload(item_name, payload):
    payload = compact_text(payload)
    payload = re.sub(r"^정정전\s+정정후\s*", "", payload)
    payload = payload.strip()
    if not payload:
        return ""

    date_values = re.findall(
        r"[0-9]{4}[-./][0-9]{1,2}[-./][0-9]{1,2}|(?<![0-9])-+(?![0-9])",
        payload,
    )
    if "계약기간" in item_name and len(date_values) >= 2:
        return f"{item_name} 변경: {date_values[0]} -> {date_values[1]}"

    if "매출액대비" in item_name:
        numbers = re.findall(r"[0-9]+(?:\.[0-9]+)?", payload)
        if len(numbers) >= 2:
            return f"{item_name} 변경: {numbers[0]}% -> {numbers[1]}%"

    if "(문구 삭제)" in payload or "문구 삭제" in payload:
        return f"{item_name} 변경: 문구 삭제"

    values = re.findall(r"(?<![0-9A-Za-z가-힣])(?:-|유|무)(?![0-9A-Za-z가-힣])", payload)
    if "유무" in item_name and len(values) >= 2:
        return f"{item_name} 변경: {values[0]} -> {values[1]}"

    return f"{item_name} 변경: {short_text(payload)}"


def extract_correction_note(text):
    section = extract_correction_section(text)
    summaries = []

    if section:
        matches = list(CORRECTION_ITEM_RE.finditer(section))
        for idx, match in enumerate(matches):
            item_name = clean_correction_item_name(match.group(0))
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
            payload = section[match.end():end]
            summary = summarize_correction_payload(item_name, payload)
            if summary and summary not in summaries:
                summaries.append(summary)

    if summaries:
        return "; ".join(summaries[:3])

    reason = extract_correction_reason(text)
    if reason:
        return f"정정사유: {short_text(reason)}"
    if section:
        return f"정정사항: {short_text(section, 180)}"
    return ""


def is_correction_filing(report_nm):
    return "[기재정정]" in report_nm or "정정" in report_nm


def is_termination_filing(report_nm, text=""):
    target = report_nm + " " + text[:2000]
    return "계약해지" in target or "공급계약해지" in target


def extract_contract_fields(text):
    contract_name = extract_contract_name(text)
    start_date, end_date = extract_contract_period(text)
    ship_source = contract_name or text[:3000]
    return {
        "체결계약명": contract_name,
        "유추선종": classify_ship_type(ship_source),
        "수주_선박수": extract_ship_count(contract_name),
        "계약금액": extract_contract_amount(text),
        "계약기간_시작일": start_date,
        "계약기간_종료일": end_date,
        "매매기준환율": extract_exchange_rate(text),
        "수정_체결계약명": "",
        "수정_유추선종": "",
        "수정_수주_선박수": "",
        "수정_계약금액": "",
        "수정_계약기간_종료일": "",
        "계약해지": "",
        "비고": "",
    }


def is_order_related(report_nm, text=""):
    target = report_nm + " " + text[:3000]
    return any(keyword in target for keyword in ORDER_KEYWORDS)


def is_target_report(report_nm, text=""):
    target = report_nm + " " + text[:2000]
    compact_target = re.sub(r"\s+", "", target)
    return "영업실적등에대한전망" in compact_target and "공정공시" in compact_target


def is_monthly_sales_report(report_nm):
    compact_name = re.sub(r"\s+", "", report_nm)
    return (
        "영업(잠정)실적" in compact_name
        and "공정공시" in compact_name
        and "연결재무제표기준" not in compact_name
    )


def is_quarterly_financials_report(report_nm):
    compact_name = re.sub(r"\s+", "", report_nm)
    return "영업(잠정)실적" in compact_name and "공정공시" in compact_name


def is_regular_financial_report(report_nm):
    compact_name = re.sub(r"\s+", "", report_nm)
    return any(name in compact_name for name in ("분기보고서", "반기보고서", "사업보고서"))


def load_existing_rows(path, columns):
    if not os.path.exists(path):
        return []

    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {col: row.get(col, "") for col in columns}
            if is_excluded_order_row(cleaned):
                continue
            if "매출구분" in columns and not cleaned.get("매출구분"):
                cleaned["매출구분"] = "전체"
            cleaned["공시일"] = normalize_storage_date(cleaned.get("공시일", ""))
            if "접수번호" not in cleaned or not cleaned.get("접수번호"):
                cleaned["접수번호"] = extract_receipt_no_from_url(cleaned.get("DART_URL", ""))
            rows.append(cleaned)
    return rows


def disclosure_key(row):
    receipt_no = row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
    if receipt_no:
        return ("receipt", receipt_no)
    return (
        "fallback",
        row.get("회사", ""),
        row.get("공시일", ""),
        row.get("체결계약명", ""),
        row.get("계약금액", ""),
        row.get("DART_URL", ""),
    )


def merge_order_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        if is_excluded_order_row(row):
            continue
        normalized = row.copy()
        if not normalized.get("매출구분"):
            normalized["매출구분"] = "전체"
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        merged[disclosure_key(normalized)] = normalized
    return list(merged.values())


def refresh_derived_order_fields(rows):
    for row in rows:
        contract_name = row.get("체결계약명", "")
        if contract_name:
            row["유추선종"] = classify_ship_type(contract_name)
            row["수주_선박수"] = extract_ship_count(contract_name)

        revised_contract_name = row.get("수정_체결계약명", "")
        if revised_contract_name:
            row["수정_유추선종"] = classify_ship_type(revised_contract_name)
            row["수정_수주_선박수"] = extract_ship_count(revised_contract_name)

        row["정정공시_URL"] = normalize_correction_urls(row.get("정정공시_URL", ""))
    return rows


def latest_disclosure_date(rows):
    dates = [
        normalize_storage_date(row.get("공시일", ""))
        for row in rows
    ]
    dates = [value for value in dates if value]
    return max(dates) if dates else SEARCH_START_DATE


def normalize_market_cap_date(value):
    normalized = normalize_date(value)
    if normalized:
        return normalized
    value = str(value).strip()
    if re.fullmatch(r"[0-9]{8}", value):
        return value
    return ""


def latest_market_cap_date(rows):
    dates = [
        normalize_market_cap_date(row.get("기준일", ""))
        for row in rows
    ]
    dates = [value for value in dates if value]
    return max(dates) if dates else ""


def parse_yyyymmdd(value):
    value = normalize_market_cap_date(value)
    if not value:
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def add_months(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def market_cap_target_dates(start_yyyymmdd, end_yyyymmdd):
    start = parse_yyyymmdd(start_yyyymmdd)
    end = parse_yyyymmdd(end_yyyymmdd)
    if not start or not end or start > end:
        return []

    target_dates = set()
    current = date(start.year, start.month, 1)
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, last_day)
        if start <= month_end <= end:
            target_dates.add(month_end)
        current = add_months(current, 1)

    target_dates.add(end)
    return sorted(target_dates)


def clean_int(value):
    value = str(value).replace(",", "").strip()
    if not value or value == "-":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def fetch_krx_market_cap_rows(trade_date):
    payload = post_json(
        "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "locale": "ko_KR",
            "mktId": "ALL",
            "trdDd": trade_date.strftime("%Y%m%d"),
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("block1") or []
    return rows if isinstance(rows, list) else []


def fetch_pykrx_market_cap_rows(trade_date):
    try:
        from pykrx import stock
    except ImportError:
        return None

    try:
        df = stock.get_market_cap_by_ticker(trade_date.strftime("%Y%m%d"), market="ALL")
    except Exception:
        return []
    if df is None or df.empty:
        return []

    rows = []
    for ticker, row in df.iterrows():
        rows.append({
            "ISU_SRT_CD": str(ticker).zfill(6),
            "MKTCAP": row.get("시가총액", ""),
            "TDD_CLSPRC": row.get("종가", ""),
            "LIST_SHRS": row.get("상장주식수", ""),
        })
    return rows


def fetch_marcap_market_cap_rows(target_dates, companies, min_allowed_date=None, max_backtrack_days=10):
    if not target_dates:
        return [], set()

    try:
        import pandas as pd
    except ImportError:
        return [], set()

    years = sorted({target.year for target in target_dates} | {min(target_dates).year - 1})
    stock_codes = {meta["stock_code"] for meta in companies.values()}
    frames = []
    for year in years:
        if year < 1995:
            continue
        url = MARCAP_RAW_URL.format(year=year)
        try:
            frame = pd.read_parquet(url)
        except Exception:
            continue
        if frame.empty or "Code" not in frame.columns or "Date" not in frame.columns:
            continue
        frame["Code"] = frame["Code"].astype(str).str.zfill(6)
        frame = frame[frame["Code"].isin(stock_codes)].copy()
        if frame.empty:
            continue
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.date
        frames.append(frame)

    if not frames:
        return [], set()

    data = pd.concat(frames, ignore_index=True)
    available_dates = sorted(date_value for date_value in data["Date"].dropna().unique())
    rows = []
    covered_targets = set()
    for target_date in target_dates:
        min_date = target_date - timedelta(days=max_backtrack_days)
        if min_allowed_date and min_date < min_allowed_date:
            min_date = min_allowed_date
        candidates = [
            date_value
            for date_value in available_dates
            if min_date <= date_value <= target_date
        ]
        if not candidates:
            continue
        trade_date = max(candidates)
        day = data[data["Date"].eq(trade_date)]
        krx_like_rows = []
        for record in day.to_dict("records"):
            krx_like_rows.append({
                "ISU_SRT_CD": record.get("Code", ""),
                "MKTCAP": record.get("Marcap", ""),
                "TDD_CLSPRC": record.get("Close", ""),
                "LIST_SHRS": record.get("Stocks", ""),
            })
        built_rows = build_market_cap_rows(trade_date, krx_like_rows, companies)
        if built_rows:
            print(f"시가총액 수집(marcap): 기준일 {target_date:%Y-%m-%d} -> 거래일 {trade_date:%Y-%m-%d} ({len(built_rows)}건)")
            rows.extend(built_rows)
            covered_targets.add(target_date)
    return rows, covered_targets


def fetch_krx_market_cap_asof(target_date, max_backtrack_days=10):
    for offset in range(max_backtrack_days + 1):
        trade_date = target_date - timedelta(days=offset)
        rows = fetch_pykrx_market_cap_rows(trade_date)
        if rows is None:
            rows = fetch_krx_market_cap_rows(trade_date)
        if rows:
            return trade_date, rows
    return None, []


def build_market_cap_rows(trade_date, krx_rows, companies):
    by_code = {
        str(row.get("ISU_SRT_CD", "")).zfill(6): row
        for row in krx_rows
    }
    today = date.today().strftime("%Y-%m-%d")
    results = []
    for company, meta in companies.items():
        stock_code = meta["stock_code"]
        row = by_code.get(stock_code)
        if not row:
            continue

        market_cap = clean_int(row.get("MKTCAP"))
        close_price = clean_int(row.get("TDD_CLSPRC"))
        listed_shares = clean_int(row.get("LIST_SHRS"))
        if market_cap is None:
            continue

        results.append({
            "회사": company,
            "stock_code": stock_code,
            "기준일": trade_date.strftime("%Y-%m-%d"),
            "시가총액": market_cap,
            "시가총액_억원": round(market_cap / 100_000_000, 4),
            "시가총액_조원": round(market_cap / 1_000_000_000_000, 6),
            "종가": close_price if close_price is not None else "",
            "상장주식수": listed_shares if listed_shares is not None else "",
            "수집일": today,
        })
    return results


def market_cap_key(row):
    stock_code = str(row.get("stock_code", "")).strip()
    if stock_code and stock_code.isdigit():
        stock_code = stock_code.zfill(6)
    return (row.get("회사", ""), stock_code, normalize_market_cap_date(row.get("기준일", "")))


def merge_market_cap_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["기준일"] = format_output_date(normalized.get("기준일", ""))
        stock_code = str(normalized.get("stock_code", "")).strip()
        if stock_code and stock_code.isdigit():
            normalized["stock_code"] = stock_code.zfill(6)
        key = market_cap_key(normalized)
        if key[2]:
            merged[key] = normalized
    return list(merged.values())


def parse_sales_unit(text):
    match = re.search(r"단위\s*[:：]\s*([^, ]+)", compact_text(text))
    return match.group(1) if match else ""


def parse_performance_periods(text):
    target = compact_text(text)
    labels = [
        ("당기실적", "당기실적"),
        ("전기실적", "전기실적"),
        ("전년동기실적", "전년동기실적"),
    ]
    periods = {}
    for key, label in labels:
        match = re.search(
            rf"{label}\s+([0-9]{{4}}[-./][0-9]{{2}}[-./][0-9]{{2}})\s*~\s*([0-9]{{4}}[-./][0-9]{{2}}[-./][0-9]{{2}})",
            target,
        )
        if match:
            start_date = format_output_date(match.group(1))
            end_date = format_output_date(match.group(2))
            periods[key] = (start_date, end_date)

    if len(periods) == len(labels):
        return periods

    header_match = re.search(r"구분\s+당기실적.+?매출액\s+당해실적", target)
    header = header_match.group(0) if header_match else target[:3000]
    quarter_matches = re.findall(
        r"\(\s*'?(?:(?P<yyyy>[0-9]{4})|(?P<yy>[0-9]{2}))\s*(?:년|\.)\s*(?P<quarter>[1-4])\s*(?:분기|Q)\s*\)",
        header,
        re.IGNORECASE,
    )
    if quarter_matches:
        for (key, _), match in zip(labels, quarter_matches[:3]):
            yyyy, yy, quarter = match
            year = int(yyyy or f"20{yy}")
            quarter = int(quarter)
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            end_day = calendar.monthrange(year, end_month)[1]
            periods[key] = (
                f"{year:04d}-{start_month:02d}-01",
                f"{year:04d}-{end_month:02d}-{end_day:02d}",
            )
        return periods

    month_matches = re.findall(
        r"\((?:'?(?P<yy>[0-9]{2})|(?P<yyyy>[0-9]{4}))\.?\s*(?P<month>[0-9]{1,2})월\s*\)",
        header,
    )
    if len(month_matches) >= 3:
        for (key, _), match in zip(labels, month_matches[:3]):
            yy, yyyy, month = match
            year = int(yyyy or f"20{yy}")
            month = int(month)
            end_day = calendar.monthrange(year, month)[1]
            periods[key] = (
                f"{year:04d}-{month:02d}-01",
                f"{year:04d}-{month:02d}-{end_day:02d}",
            )
    return periods


def parse_sales_number(value):
    value = compact_text(value)
    value = value.replace("−", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"^[△▲]\s*", "-", value)
    value = re.sub(r"^\((.+)\)$", r"-\1", value)
    if not value or value == "-":
        return None
    value = re.sub(r"[^0-9,.\-]", "", value)
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def sales_to_million_krw(value, unit):
    number = parse_sales_number(value)
    if number is None:
        return None

    normalized_unit = compact_text(unit)
    if "억원" in normalized_unit:
        return number * 100
    if "백만원" in normalized_unit:
        return number
    if "천원" in normalized_unit:
        return number / 1_000
    if "원" in normalized_unit:
        return number / 1_000_000
    return number


def amount_to_100m_krw(value, unit):
    number = parse_sales_number(value)
    if number is None:
        return None

    normalized_unit = compact_text(unit)
    if "억원" in normalized_unit:
        return number
    if "백만원" in normalized_unit:
        return number / 100
    if "천원" in normalized_unit:
        return number / 100_000
    if "원" in normalized_unit:
        return number / 100_000_000
    return number


def format_number(value):
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def quarter_label_from_period(start_date, end_date):
    start_norm = normalize_storage_date(start_date)
    end_norm = normalize_storage_date(end_date)
    if not start_norm or not end_norm:
        return ""

    start_year = int(start_norm[:4])
    start_month = int(start_norm[4:6])
    end_year = int(end_norm[:4])
    end_month = int(end_norm[4:6])
    if start_year != end_year:
        return ""

    quarter = (end_month - 1) // 3 + 1
    if start_month != (quarter - 1) * 3 + 1:
        return ""
    return f"{end_year}Q{quarter}"


def report_quarter_from_name(report_nm):
    match = re.search(r"\((20[0-9]{2})[.년/-]\s*([0-9]{1,2})", report_nm)
    if not match:
        return "", "", ""
    year = int(match.group(1))
    month = int(match.group(2))
    if month not in (3, 6, 9, 12):
        return "", "", ""
    quarter = month // 3
    end_day = calendar.monthrange(year, month)[1]
    return f"{year}Q{quarter}", f"{year:04d}-01-01", f"{year:04d}-{month:02d}-{end_day:02d}"


def extract_metric_current_value(text, metric_name):
    target = compact_text(text)
    match = re.search(rf"{metric_name}\s+당해실적\s+(.+?)\s+누계실적", target)
    if not match:
        return ""
    tokens = match.group(1).split()
    return tokens[0] if tokens else ""


def extract_monthly_sales_rows(company, filing, report_nm, text):
    target = compact_text(text)
    periods = parse_performance_periods(target)
    unit = parse_sales_unit(target)
    match = re.search(r"매출액\s+당해실적\s+(.+?)\s+누계실적", target)
    if not match:
        return []

    tokens = match.group(1).split()
    header = target[:match.start()]
    prior_year_index = 4 if "흑자적자전환" in header else 3
    sales_tokens = {
        "당기실적": tokens[0] if len(tokens) > 0 else "",
        "전기실적": tokens[1] if len(tokens) > 1 else "",
        "전년동기실적": tokens[prior_year_index] if len(tokens) > prior_year_index else "",
    }

    rows = []
    for basis, value in sales_tokens.items():
        if basis not in periods:
            continue

        sales_million = sales_to_million_krw(value, unit)
        if sales_million is None:
            continue

        start_date, end_date = periods[basis]
        if start_date[:7] != end_date[:7]:
            continue

        rows.append({
            "회사": company,
            "실적월": start_date[:7],
            "매출구분": "전체",
            "매출액_백만원": format_number(sales_million),
            "매출액_억원": format_number(sales_million / 100),
            "기준구분": basis,
            "실적기간_시작일": start_date,
            "실적기간_종료일": end_date,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        })
    return rows


def monthly_sales_key(row):
    return (row.get("회사", ""), row.get("실적월", ""), row.get("매출구분", "전체") or "전체")


def merge_monthly_sales_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = monthly_sales_key(normalized)
        prev = merged.get(key)
        if prev is None or (normalized.get("공시일", ""), normalized.get("접수번호", "")) >= (
            prev.get("공시일", ""),
            prev.get("접수번호", ""),
        ):
            merged[key] = normalized
    return list(merged.values())


def extract_quarterly_financial_rows(company, filing, report_nm, text):
    target = compact_text(text)
    periods = parse_performance_periods(target)
    if "당기실적" not in periods:
        return []

    start_date, end_date = periods["당기실적"]
    quarter_label = quarter_label_from_period(start_date, end_date)
    if not quarter_label:
        return []
    if start_date[:7] == end_date[:7]:
        return []

    unit = parse_sales_unit(target)
    revenue_100m = amount_to_100m_krw(extract_metric_current_value(target, "매출액"), unit)
    operating_profit_100m = amount_to_100m_krw(extract_metric_current_value(target, "영업이익"), unit)
    if revenue_100m is None and operating_profit_100m is None:
        return []

    return [{
        "회사": company,
        "실적분기": quarter_label,
        "매출액_억원": format_number(revenue_100m),
        "영업이익_억원": format_number(operating_profit_100m),
        "실적기간_시작일": start_date,
        "실적기간_종료일": end_date,
        "공시일": filing["rcept_dt"],
        "공시명": report_nm,
        "접수번호": filing["rcept_no"],
        "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
    }]


def quarter_dates(year, quarter):
    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    end_day = calendar.monthrange(year, end_month)[1]
    return f"{year:04d}-{start_month:02d}-01", f"{year:04d}-{end_month:02d}-{end_day:02d}"


def extract_metric_values_from_statement(section, metric_name):
    label_pattern = metric_name
    if metric_name == "영업이익":
        label_pattern = r"(?:영업이익|영업손실)"
    match = re.search(
        rf"({label_pattern})(?:\([^)]*\))?\s+((?:[△▲]?\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?\s+){{2,6}})",
        section,
    )
    if not match:
        return []
    values = re.findall(r"[△▲]?\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?", match.group(2))
    if metric_name == "영업이익" and "손실" in match.group(1):
        values = [
            value if str(value).startswith("-") or str(value).startswith("(") else f"-{value}"
            for value in values
        ]
    return values


def extract_operating_profit_token(section):
    match = re.search(
        r"(영업이익|영업손실)(?:\([^)]*\))?\s+([△▲]?\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)",
        section,
    )
    if not match:
        return ""
    value = match.group(2)
    if "손실" in match.group(1) and not value.startswith("-") and not value.startswith("("):
        value = f"-{value}"
    return value


def extract_regular_income_statement_rows(company, filing, report_nm, text):
    quarter, _, _ = report_quarter_from_name(report_nm)
    if not quarter:
        return []
    year = int(quarter[:4])
    q_num = int(quarter[-1])
    if q_num == 4:
        return []

    target = compact_text(text)
    start = target.find("연결 손익계산서")
    if start < 0:
        start = target.find("손익계산서")
    if start < 0:
        return []
    end_candidates = [
        pos for pos in [
            target.find("연결 포괄손익계산서", start + 1),
            target.find("포괄손익계산서", start + 1),
            target.find("연결 자본변동표", start + 1),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 5000
    section = target[start:end]
    if "3개월" not in section or "누적" not in section:
        return []

    unit = parse_sales_unit(section) or "원"
    revenue_values = extract_metric_values_from_statement(section, "매출액")
    profit_values = extract_metric_values_from_statement(section, "영업이익")
    if len(revenue_values) < 2 and len(profit_values) < 2:
        return []

    rows = []
    for idx, row_year, is_comparative in [(0, year, False), (2, year - 1, True)]:
        if len(revenue_values) <= idx and len(profit_values) <= idx:
            continue
        start_date, end_date = quarter_dates(row_year, q_num)
        rows.append({
            "회사": company,
            "실적분기": f"{row_year}Q{q_num}",
            "매출액_억원": format_number(amount_to_100m_krw(revenue_values[idx], unit)) if len(revenue_values) > idx else "",
            "영업이익_억원": format_number(amount_to_100m_krw(profit_values[idx], unit)) if len(profit_values) > idx else "",
            "실적기간_시작일": start_date,
            "실적기간_종료일": end_date,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
            "분기실적_직접추출": "Y",
            "비교표시여부": "Y" if is_comparative else "",
        })
    return rows


def extract_regular_report_cumulative_financial_rows(company, filing, report_nm, text):
    quarter, start_date, end_date = report_quarter_from_name(report_nm)
    if not quarter:
        return []
    income_statement_rows = extract_regular_income_statement_rows(company, filing, report_nm, text)
    if income_statement_rows:
        return income_statement_rows

    target = compact_text(text)
    start = -1
    for pattern in ["요약연결재무정보", "요약 연결재무정보", "요약재무정보"]:
        positions = [match.start() for match in re.finditer(re.escape(pattern), target)]
        if positions:
            start = next((pos for pos in positions if "(단위" in target[pos:pos + 250]), -1)
            if start < 0:
                start = next((pos for pos in positions if "매출액" in target[pos:pos + 2500]), positions[0])
            break
    if start < 0:
        return []
    end_candidates = [
        pos for pos in [
            target.find("나. 요약 별도재무정보", start),
            target.find("2. 연결재무제표", start),
            target.find("II. 사업의 내용", start),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 7000
    section = target[start:end]
    unit = parse_sales_unit(section) or "백만원"

    revenue = first_match(section, [r"매출액\s+(-?[0-9][0-9,]*(?:\.[0-9]+)?)"])
    operating_profit = extract_operating_profit_token(section)
    revenue_100m = amount_to_100m_krw(revenue, unit)
    operating_profit_100m = amount_to_100m_krw(operating_profit, unit)
    if revenue_100m is None and operating_profit_100m is None:
        return []

    return [{
        "회사": company,
        "실적분기": quarter,
        "매출액_억원": format_number(revenue_100m),
        "영업이익_억원": format_number(operating_profit_100m),
        "실적기간_시작일": start_date,
        "실적기간_종료일": end_date,
        "공시일": filing["rcept_dt"],
        "공시명": report_nm,
        "접수번호": filing["rcept_no"],
        "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        "누적실적여부": "Y",
    }]


def quarterly_financials_key(row):
    return (row.get("회사", ""), row.get("실적분기", ""))


def convert_regular_report_cumulative_rows(rows):
    normalized = list(rows)
    for company in sorted({row.get("회사", "") for row in normalized}):
        company_rows = [row for row in normalized if row.get("회사", "") == company]
        regular_cumulative = {
            row.get("실적분기", ""): (
                parse_sales_number(row.get("매출액_억원", "")),
                parse_sales_number(row.get("영업이익_억원", "")),
            )
            for row in company_rows
            if is_regular_financial_report(row.get("공시명", ""))
            and normalize_storage_date(row.get("실적기간_시작일", ""))[4:6] == "01"
        }
        if not regular_cumulative:
            continue

        current_by_quarter = {}
        for row in sorted(company_rows, key=lambda item: item.get("실적분기", "")):
            quarter = row.get("실적분기", "")
            if not re.fullmatch(r"[0-9]{4}Q[1-4]", quarter):
                continue
            q_num = int(quarter[-1])
            revenue = parse_sales_number(row.get("매출액_억원", ""))
            operating_profit = parse_sales_number(row.get("영업이익_억원", ""))

            if is_regular_financial_report(row.get("공시명", "")):
                if row.get("분기실적_직접추출") == "Y":
                    current_by_quarter[quarter] = (revenue, operating_profit)
                    continue
                if q_num > 1 and normalize_storage_date(row.get("실적기간_시작일", ""))[4:6] != "01":
                    current_by_quarter[quarter] = (revenue, operating_profit)
                    continue
                cumulative_revenue, cumulative_profit = regular_cumulative.get(quarter, (None, None))
                if q_num > 1:
                    prev_quarter = f"{quarter[:4]}Q{q_num - 1}"
                    prev_cumulative_revenue, prev_cumulative_profit = regular_cumulative.get(prev_quarter, (None, None))
                    if prev_cumulative_revenue is None:
                        prev_cumulative_revenue = sum(
                            value[0] for key, value in current_by_quarter.items()
                            if key.startswith(quarter[:4]) and key < quarter and value[0] is not None
                        )
                    if prev_cumulative_profit is None:
                        prev_cumulative_profit = sum(
                            value[1] for key, value in current_by_quarter.items()
                            if key.startswith(quarter[:4]) and key < quarter and value[1] is not None
                        )
                    if cumulative_revenue is not None and prev_cumulative_revenue is not None:
                        if cumulative_revenue >= prev_cumulative_revenue:
                            revenue = cumulative_revenue - prev_cumulative_revenue
                    if cumulative_profit is not None and prev_cumulative_profit is not None:
                        if cumulative_profit >= prev_cumulative_profit:
                            operating_profit = cumulative_profit - prev_cumulative_profit
                else:
                    revenue = cumulative_revenue
                    operating_profit = cumulative_profit

                row["매출액_억원"] = format_number(revenue) if revenue is not None else ""
                row["영업이익_억원"] = format_number(operating_profit) if operating_profit is not None else ""
                row_start, row_end = quarter_dates(int(quarter[:4]), q_num)
                row["실적기간_시작일"] = row_start
                row["실적기간_종료일"] = row_end

            current_by_quarter[quarter] = (revenue, operating_profit)
    return normalized


def merge_quarterly_financial_rows(existing_rows, new_rows):
    merged = {}
    def row_rank(row):
        # 직접 해당분기 3개월 실적을 우선하고, 전년동기 비교표시 행은 보조 데이터로만 사용한다.
        if row.get("비교표시여부") == "Y":
            return 0
        if row.get("분기실적_직접추출") == "Y":
            return 2
        return 1

    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = quarterly_financials_key(normalized)
        prev = merged.get(key)
        if prev is None or (
            row_rank(normalized),
            normalized.get("공시일", ""),
            normalized.get("접수번호", ""),
        ) >= (
            row_rank(prev),
            prev.get("공시일", ""),
            prev.get("접수번호", ""),
        ):
            merged[key] = normalized
    return convert_regular_report_cumulative_rows(list(merged.values()))


def segment_revenue_key(row):
    return (row.get("회사", ""), row.get("실적분기", ""), row.get("사업부문", ""))


def parse_sales_performance_segment_section(target):
    start = target.find("가. 매출실적")
    if start < 0:
        start = target.find("가. 매출 실적")
    if start < 0:
        start = target.find("매출실적")
    if start < 0:
        start = target.find("매출 실적")
    if start < 0:
        return {}

    end_candidates = [
        pos for pos in [
            target.find("나. 판매경로", start),
            target.find("나. 판매방법", start),
            target.find("다. 수주상황", start),
            target.find("5. 위험관리", start),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 3000
    section = target[start:end]
    if "사업부문" not in section:
        return {}

    unit = parse_sales_unit(section) or "백만원"
    segments = {}
    hanwha_segments = parse_hanwha_sales_performance_segment_section(section, unit)
    if hanwha_segments:
        return hanwha_segments

    segment_names = [
        "조선해양",
        "토건",
        "상선",
        "해양 및 특수선",
        "해양및특수선",
        "EP 및 특수선",
        "EP및특수선",
        "E&I",
        "기타",
        "연결조정",
    ]
    segment_aliases = {
        "해양 및 특수선": "해양및특수선",
        "EP 및 특수선": "EP및특수선",
    }
    boundary = "|".join(re.escape(name) for name in segment_names + ["내부매출액", "합계", "합 계"])
    for segment in segment_names:
        body_match = re.search(
            rf"{re.escape(segment)}\s+(?P<body>.*?)(?=\s+(?:{boundary})\s+|$)",
            section,
            flags=re.DOTALL,
        )
        if not body_match:
            continue
        body = body_match.group("body")
        export_value = first_match(body, [r"수\s*출\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)"])
        domestic_value = first_match(body, [r"내\s*수\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)"])
        total_value = first_match(body, [r"합\s*계\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)"])

        export_amount = sales_to_million_krw(export_value, unit) or 0.0
        domestic_amount = sales_to_million_krw(domestic_value, unit) or 0.0
        total_amount = sales_to_million_krw(total_value, unit)
        summed_amount = export_amount + domestic_amount
        if total_amount is not None and abs(total_amount - summed_amount) <= max(1.0, abs(total_amount) * 0.01):
            amount = total_amount
        elif summed_amount > 0:
            amount = summed_amount
        else:
            amount = total_amount
        if amount is not None:
            segments[segment_aliases.get(segment, segment)] = amount
    return segments


def parse_hanwha_sales_performance_segment_section(section, unit):
    if "상선" not in section or "해양" not in section or "합 계" not in section:
        return {}

    segment_patterns = {
        "상선": r"상선",
        "해양및특수선": r"해양\s*및\s*특수선",
        "EP및특수선": r"EP(?:\(\*\))?\s*및\s*특수선",
        "E&I": r"E&I",
        "기타": r"기타",
        "연결조정": r"연결조정",
    }
    boundary = "|".join(pattern for pattern in segment_patterns.values()) + r"|합\s*계|나\.\s*판매"
    segments = {}

    for segment, pattern in segment_patterns.items():
        match = re.search(
            rf"(?:^|\s){pattern}\s+(?P<body>.*?)(?=\s+(?:{boundary})\s+|$)",
            section,
            flags=re.DOTALL,
        )
        if not match:
            continue
        body = match.group("body")
        export_value = first_match(body, [r"수\s*출\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)"])
        domestic_value = first_match(body, [r"내\s*수\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)"])
        if export_value or domestic_value:
            export_amount = sales_to_million_krw(export_value, unit) or 0.0
            domestic_amount = sales_to_million_krw(domestic_value, unit) or 0.0
            amount = export_amount + domestic_amount
        else:
            number = first_match(body, [
                r"(?:기타\s+){0,2}(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)",
                r"(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)",
            ])
            amount = sales_to_million_krw(number, unit)
            if segment == "연결조정" and amount is not None:
                amount = -abs(amount)
        if amount is not None:
            segments[segment] = amount
    if "기타" not in segments:
        other_value = first_match(section, [
            r"기타\s+기타\s+기타\s+(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)",
        ])
        other_amount = sales_to_million_krw(other_value, unit)
        if other_amount is not None:
            segments["기타"] = other_amount
    return segments


def parse_segment_revenue_section(text):
    target = compact_text(text)
    sales_performance_segments = parse_sales_performance_segment_section(target)
    if sales_performance_segments:
        return sales_performance_segments

    start = target.find("사업부문별 현황")
    if start < 0:
        start = target.find("사업부문 대 상 회 사 명")
    if start < 0:
        start = target.find("가. 사업의 현황")
    if start < 0:
        start = target.find("사업부문")
    if start < 0:
        return {}
    end_candidates = [
        pos for pos in [
            target.find("나. 주요 사업", start),
            target.find("나. 주요사업", start),
            target.find("다. 주요 원재료", start),
            target.find("2. 주요 제품", start),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 6000
    section = target[start:end]

    segments = {}
    segment_names = [
        "조선해양",
        "조선·해양",
        "조선ㆍ해양",
        "조선",
        "상선",
        "해양 및 특수선",
        "해양및특수선",
        "EP 및 특수선",
        "EP및특수선",
        "E&I",
        "연결조정",
        "해양플랜트",
        "엔진기계",
        "토건",
        "기타",
        "합계",
    ]
    segment_aliases = {
        "조선·해양": "조선해양",
        "조선ㆍ해양": "조선해양",
        "해양 및 특수선": "해양및특수선",
        "EP 및 특수선": "EP및특수선",
    }
    boundary = "|".join(re.escape(name) for name in segment_names)
    for segment in segment_names:
        match = re.search(
            rf"(?:^|\s){re.escape(segment)}\s+(?P<body>.*?)(?=\s+(?:{boundary})\s+|※|나\.\s*주요|$)",
            section,
            flags=re.DOTALL,
        )
        if not match:
            continue
        numbers = re.findall(r"(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*\(\s*[0-9.]+\s*%?\s*\)", match.group("body"))
        if not numbers:
            continue
        amount = parse_sales_number(numbers[-1])
        if amount is not None:
            segments[segment_aliases.get(segment, segment)] = amount
    if "합계" in segments and "기타" not in segments:
        known_total = sum(
            segments.get(name, 0)
            for name in [
                "조선해양",
                "조선",
                "상선",
                "해양및특수선",
                "EP및특수선",
                "E&I",
                "연결조정",
                "해양플랜트",
                "엔진기계",
                "토건",
            ]
        )
        other = segments["합계"] - known_total
        if other >= 0:
            segments["기타"] = other
    if segments:
        return segments

    start = target.find("주요 제품 등의 현황")
    if start < 0:
        return {}
    end_candidates = [
        pos for pos in [
            target.find("나. 주요 제품", start + 1),
            target.find("나. 주요제품", start + 1),
            target.find("나. 주요 제품 등의 가격", start + 1),
            target.find("3. 원재료", start + 1),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 2500
    section = target[start:end]
    unit = parse_sales_unit(section) or "백만원"
    for segment in ["조선해양", "토건", "상선", "해양 및 특수선", "해양및특수선", "EP 및 특수선", "EP및특수선", "E&I", "기타"]:
        match = re.search(
            rf"{re.escape(segment)}\s+.*?([0-9][0-9,]*(?:\.[0-9]+)?)\s*\(\s*[0-9.]+\s*%?\s*\)",
            section,
            flags=re.DOTALL,
        )
        if not match:
            continue
        amount = sales_to_million_krw(match.group(1), unit)
        if amount is not None:
            segments[{"해양 및 특수선": "해양및특수선", "EP 및 특수선": "EP및특수선"}.get(segment, segment)] = amount
    return segments


def parse_daehan_production_performance_section(text):
    target = compact_text(text)
    start = target.find("(2) 생산실적")
    if start < 0:
        start = target.find("생산실적 (단위")
    if start < 0:
        return {}
    end_candidates = [
        pos for pos in [
            target.find("(3) 당해", start),
            target.find("당해 사업연도의 가동률", start),
            target.find("라. 생산설비", start),
        ]
        if pos > start
    ]
    end = min(end_candidates) if end_candidates else start + 2500
    section = target[start:end]
    unit = parse_sales_unit(section) or "백만원"

    products = ["원유운반선", "정유운반선", "컨테이너선", "기타", "합 계", "합계"]
    segments = {}
    for idx, product in enumerate(products):
        product_pattern = re.escape(product).replace("\\ ", r"\s*")
        match = re.search(rf"{product_pattern}(?:\(\*\d+\))?", section)
        if not match:
            continue

        next_positions = []
        for next_product in products[idx + 1:]:
            next_pattern = re.escape(next_product).replace("\\ ", r"\s*")
            next_match = re.search(rf"{next_pattern}(?:\(\*\d+\))?", section[match.end():])
            if next_match:
                next_positions.append(match.end() + next_match.start())
        body_end = min(next_positions) if next_positions else len(section)
        body = section[match.end():body_end]
        tokens = re.findall(r"\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-", body)
        if not tokens:
            amount = None
        else:
            value_token = tokens[1] if product == "기타" and len(tokens) > 1 and tokens[0] == "-" else tokens[0]
            amount = 0.0 if value_token == "-" else sales_to_million_krw(value_token, unit)
        if amount is None:
            continue

        normalized = "합계" if "합" in product else product
        segments[normalized] = amount

    return segments


def extract_segment_revenue_rows(company, filing, report_nm, text):
    quarter_label, start_date, end_date = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    if company == "대한조선":
        segment_amounts = parse_daehan_production_performance_section(text)
    else:
        segment_amounts = parse_segment_revenue_section(text)
    rows = []
    for segment, revenue_million in segment_amounts.items():
        rows.append({
            "회사": company,
            "실적분기": quarter_label,
            "사업부문": segment,
            "누적매출액_백만원": format_number(revenue_million),
            "누적매출액_억원": format_number(revenue_million / 100),
            "분기매출액_백만원": "",
            "분기매출액_억원": "",
            "실적기간_시작일": start_date,
            "실적기간_종료일": end_date,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        })
    return rows


def section_between(target, start_patterns, end_patterns, fallback_length=7000):
    starts = []
    for pattern in start_patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if match:
            starts.append(match.start())
    if not starts:
        return ""
    start = min(starts)
    end_positions = []
    for pattern in end_patterns:
        match = re.search(pattern, target[start + 1:], re.IGNORECASE)
        if match:
            end_positions.append(start + 1 + match.start())
    end = min(end_positions) if end_positions else start + fallback_length
    return target[start:end]


def extract_trailing_numbers(text, limit=8):
    return re.findall(r"\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?", text)[-limit:]


COST_NATURE_ITEMS = [
    "재고자산의 변동",
    "재고자산의 매입액",
    "원재료매입",
    "원재료 매입",
    "원재료 및 저장품 사용액",
    "원재료 사용액",
    "원재료사용액",
    "재료비",
    "외주가공비",
    "외주용역비",
    "외주비",
    "종업원 급여",
    "종업원급여",
    "급여",
    "퇴직급여비용, 확정급여제도",
    "당기손익에 포함되는 퇴직급여비용",
    "퇴직급여비용",
    "퇴직급여",
    "상각비",
    "감가상각비",
    "사용권자산감가상각비",
    "사용권자산상각비",
    "무형자산상각비",
    "복리후생비",
    "세금과공과",
    "임차료",
    "지급수수료",
    "제수수료",
    "여비교통비",
    "관리용역비",
    "수선유지비",
    "운반보관료",
    "소모품비",
    "광고선전비",
    "현지운영비",
    "기술용역비",
    "공사손실충당금전입액(환입액)",
    "공사손실충당금전입액",
    "공사손실충당금환입액",
    "성격별 비용 합계",
    "기타",
    "합 계",
    "합계",
]

SELLING_ADMIN_ITEMS = [
    "종업원급여, 판관비",
    "종업원급여",
    "퇴직급여, 판관비",
    "퇴직급여",
    "복리후생비, 판관비",
    "복리후생비",
    "감가상각비, 판관비",
    "감가상각비",
    "사용권자산상각비",
    "세금과공과, 판관비",
    "세금과공과",
    "지급수수료, 판관비",
    "지급수수료",
    "수선비, 판관비",
    "수선비",
    "보험료, 판관비",
    "보험료",
    "수도광열비, 판관비",
    "수도광열비",
    "전력비, 판관비",
    "전력비",
    "보증수리비(환입)",
    "대손상각비(대손충당금환입)",
    "유형자산과 무형자산 상각비",
    "경상연구개발비",
    "기타판매비와관리비",
    "기타",
    "합 계",
    "합계",
]


def canonical_cost_item(item):
    item = compact_text(item).replace(" ", "")
    item = re.sub(r",?판관비$", "", item)
    aliases = {
        "재고자산의변동": "재고자산변동",
        "재고자산의매입액": "원재료",
        "원재료매입": "원재료",
        "원재료및저장품사용액": "원재료",
        "원재료사용액": "원재료",
        "원재료사용": "원재료",
        "재료비": "원재료",
        "외주가공비": "외주가공비",
        "외주용역비": "외주가공비",
        "외주비": "외주가공비",
        "종업원급여": "인건비",
        "급여": "인건비",
        "퇴직급여비용,확정급여제도": "퇴직급여",
        "당기손익에포함되는퇴직급여비용": "퇴직급여",
        "퇴직급여비용": "퇴직급여",
        "퇴직급여": "퇴직급여",
        "상각비": "감가상각비",
        "감가상각비": "감가상각비",
        "사용권자산감가상각비": "사용권자산상각비",
        "사용권자산상각비": "사용권자산상각비",
        "무형자산상각비": "무형자산상각비",
        "복리후생비": "복리후생비",
        "세금과공과": "세금과공과",
        "임차료": "임차료",
        "지급수수료": "지급수수료",
        "제수수료": "지급수수료",
        "여비교통비": "여비교통비",
        "관리용역비": "관리용역비",
        "수선유지비": "수선비",
        "운반보관료": "운반보관료",
        "소모품비": "소모품비",
        "광고선전비": "광고선전비",
        "현지운영비": "현지운영비",
        "기술용역비": "기술용역비",
        "공사손실충당금전입액(환입액)": "공사손실충당금",
        "공사손실충당금전입액": "공사손실충당금",
        "공사손실충당금환입액": "공사손실충당금",
        "기타비용": "영업외_기타비용",
        "기타판매비와관리비": "기타",
        "수선비": "수선비",
        "보험료": "보험료",
        "수도광열비": "수도광열비",
        "전력비": "전력비",
        "성격별비용합계": "합계",
        "기타": "기타",
        "합계": "합계",
    }
    return aliases.get(item, item)


def parse_cost_nature_section(text):
    target = compact_text(text)
    section = section_between(
        target,
        [r"비용의\s*성격별\s*분류"],
        [
            r"\d+\.\s*판매비와\s*관리비",
            r"판매비와\s*관리비",
            r"\d+\.\s*금융",
            r"\d+\.\s*기타수익",
            r"\d+\.\s*법인세",
            r"영업외",
            r"우발",
            r"약정",
        ],
        fallback_length=9000,
    )
    if not section:
        return {}

    unit = parse_sales_unit(section) or "백만원"
    boundary = "|".join(re.escape(item) for item in sorted(COST_NATURE_ITEMS, key=len, reverse=True))
    rows = {}
    matches = list(re.finditer(rf"(?:^|\s)({boundary})\s+", section))
    for idx, match in enumerate(matches):
        item = canonical_cost_item(match.group(1))
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        payload = section[match.end():end]
        numbers = extract_trailing_numbers(payload)
        if not numbers:
            continue
        amount = sales_to_million_krw(numbers[0], unit)
        if amount is None:
            continue
        rows[item] = amount
    return rows


def parse_cost_nature_blocks(text):
    target = compact_text(text)
    section = section_between(
        target,
        [r"비용의\s*성격별\s*분류"],
        [
            r"\d+\.\s*기타수익",
            r"\d+\.\s*기타수익과\s*비용",
            r"\d+\.\s*금융",
            r"\d+\.\s*법인세",
            r"기타수익\s*및\s*기타비용",
            r"특수관계자",
        ],
        fallback_length=4500,
    )
    if not section:
        return []

    block_pattern = re.compile(r"(당분기|당반기|전분기|전반기|전기|당기)(?!손익)\s*(?:\(단위\s*[:：]\s*([^) ]+)\))?")
    block_matches = list(block_pattern.finditer(section))
    if not block_matches:
        return []

    item_boundary = "|".join(re.escape(item) for item in sorted(COST_NATURE_ITEMS, key=len, reverse=True))
    blocks = []
    for idx, block_match in enumerate(block_matches):
        label = block_match.group(1)
        unit = block_match.group(2) or parse_sales_unit(section[block_match.start():block_match.start() + 220]) or parse_sales_unit(section) or "백만원"
        end = block_matches[idx + 1].start() if idx + 1 < len(block_matches) else len(section)
        block_text = section[block_match.end():end]
        item_matches = list(re.finditer(rf"(?:^|\s)({item_boundary})\s+", block_text))
        values = {}
        for item_idx, item_match in enumerate(item_matches):
            item = compact_text(item_match.group(1))
            item_end = item_matches[item_idx + 1].start() if item_idx + 1 < len(item_matches) else len(block_text)
            payload = block_text[item_match.end():item_end]
            numbers = extract_trailing_numbers(payload, limit=4)
            if not numbers:
                continue
            cumulative_cost = sales_to_million_krw(numbers[0], unit)
            if cumulative_cost is None:
                continue
            values[canonical_cost_item(item)] = cumulative_cost
        if values:
            blocks.append({
                "label": label,
                "values": values,
            })
    return blocks


def parse_selling_admin_section(text):
    target = compact_text(text)
    section = section_between(
        target,
        [
            r"판매비와\s*관리비에\s*대한\s*공시",
            r"판매비와관리비에\s*대한\s*공시",
            r"\d+\.\s*판매비와\s*관리비\s*\(연결\)",
            r"\d+\.\s*판매비와\s*관리비",
        ],
        [
            r"\d+\.\s*기타수익",
            r"\d+\.\s*기타수익과\s*비용",
            r"\d+\.\s*금융",
            r"\d+\.\s*법인세",
            r"\d+\.\s*비용의\s*성격별\s*분류",
            r"비용의\s*성격별\s*분류",
            r"기타수익\s*및\s*기타비용",
        ],
        fallback_length=3500,
    )
    if not section:
        return {}

    unit = parse_sales_unit(section) or "천원"
    boundary = "|".join(re.escape(item) for item in sorted(SELLING_ADMIN_ITEMS, key=len, reverse=True))
    rows = {}
    matches = list(re.finditer(rf"(?:^|\s)({boundary})\s+", section))
    for idx, match in enumerate(matches):
        item = compact_text(match.group(1))
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        payload = section[match.end():end]
        numbers = extract_trailing_numbers(payload)
        if not numbers:
            continue
        amount = sales_to_million_krw(numbers[0], unit)
        if amount is None:
            continue
        key = f"판관비_{canonical_cost_item(item)}"
        if key not in rows:
            rows[key] = amount
    return rows


def parse_selling_admin_blocks(text):
    target = compact_text(text)
    section = section_between(
        target,
        [
            r"판매비와\s*관리비에\s*대한\s*공시",
            r"판매비와관리비에\s*대한\s*공시",
            r"\d+\.\s*판매비와\s*관리비\s*\(연결\)",
            r"\d+\.\s*판매비와\s*관리비",
        ],
        [
            r"\d+\.\s*비용의\s*성격별\s*분류",
            r"비용의\s*성격별\s*분류",
            r"\d+\.\s*기타수익",
            r"\d+\.\s*기타수익과\s*비용",
            r"\d+\.\s*금융",
            r"\d+\.\s*법인세",
            r"기타수익\s*및\s*기타비용",
        ],
        fallback_length=4500,
    )
    if not section:
        return []

    block_pattern = re.compile(r"(당분기|당반기|전분기|전반기|전기|당기)(?!손익)\s*(?:\(단위\s*[:：]\s*([^) ]+)\))?")
    block_matches = list(block_pattern.finditer(section))
    if not block_matches:
        return []

    item_boundary = "|".join(re.escape(item) for item in sorted(SELLING_ADMIN_ITEMS, key=len, reverse=True))
    blocks = []
    for idx, block_match in enumerate(block_matches):
        label = block_match.group(1)
        unit = block_match.group(2) or parse_sales_unit(section[block_match.start():block_match.start() + 220]) or parse_sales_unit(section) or "천원"
        end = block_matches[idx + 1].start() if idx + 1 < len(block_matches) else len(section)
        block_text = section[block_match.end():end]
        has_quarter_and_cumulative = "3개월" in block_text[:220] and "누적" in block_text[:220]
        item_matches = list(re.finditer(rf"(?:^|\s)({item_boundary})\s+", block_text))
        values = {}
        for item_idx, item_match in enumerate(item_matches):
            item = compact_text(item_match.group(1))
            item_end = item_matches[item_idx + 1].start() if item_idx + 1 < len(item_matches) else len(block_text)
            payload = block_text[item_match.end():item_end]
            numbers = extract_trailing_numbers(payload, limit=4)
            if not numbers:
                continue
            quarter_cost = None
            cumulative_cost = None
            if has_quarter_and_cumulative and len(numbers) >= 2:
                quarter_cost = sales_to_million_krw(numbers[0], unit)
                cumulative_cost = sales_to_million_krw(numbers[1], unit)
            else:
                cumulative_cost = sales_to_million_krw(numbers[0], unit)
            key = f"판관비_{canonical_cost_item(item)}"
            values[key] = (quarter_cost, cumulative_cost)
        if values:
            blocks.append({
                "label": label,
                "has_quarter_and_cumulative": has_quarter_and_cumulative,
                "values": values,
            })
    return blocks


def comparative_year_for_label(current_year, label):
    return current_year - 1 if label.startswith("전") else current_year


def cost_nature_rows_from_blocks(company, filing, report_nm, text):
    quarter_label, _, _ = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    current_year = int(quarter_label[:4])
    current_quarter = int(quarter_label[-1])
    rows = []
    for block in parse_cost_nature_blocks(text):
        year = comparative_year_for_label(current_year, block["label"])
        target_quarter = current_quarter
        if block["label"] in {"당기", "전기"}:
            target_quarter = 4
        start_date, end_date = quarter_dates(year, target_quarter)
        for item, cumulative_cost in block["values"].items():
            rows.append({
                "회사": company,
                "실적분기": f"{year}Q{target_quarter}",
                "비용항목": item,
                "누적비용_백만원": format_number(cumulative_cost),
                "누적비용_억원": format_number(cumulative_cost / 100),
                "분기비용_백만원": "",
                "분기비용_억원": "",
                "실적기간_시작일": start_date,
                "실적기간_종료일": end_date,
                "공시일": filing["rcept_dt"],
                "공시명": report_nm,
                "접수번호": filing["rcept_no"],
                "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
            })
    return rows


def selling_admin_rows_from_blocks(company, filing, report_nm, text):
    quarter_label, _, _ = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    current_year = int(quarter_label[:4])
    current_quarter = int(quarter_label[-1])
    rows = []
    for block in parse_selling_admin_blocks(text):
        year = comparative_year_for_label(current_year, block["label"])
        target_quarter = current_quarter
        if block["label"] in {"당기", "전기"}:
            target_quarter = 4
        start_date, end_date = quarter_dates(year, target_quarter)
        for item, (quarter_cost, cumulative_cost) in block["values"].items():
            if cumulative_cost is None and quarter_cost is None:
                continue
            rows.append({
                "회사": company,
                "실적분기": f"{year}Q{target_quarter}",
                "비용항목": item,
                "누적비용_백만원": format_number(cumulative_cost),
                "누적비용_억원": format_number(cumulative_cost / 100) if cumulative_cost is not None else "",
                "분기비용_백만원": format_number(quarter_cost),
                "분기비용_억원": format_number(quarter_cost / 100) if quarter_cost is not None else "",
                "실적기간_시작일": start_date,
                "실적기간_종료일": end_date,
                "공시일": filing["rcept_dt"],
                "공시명": report_nm,
                "접수번호": filing["rcept_no"],
                "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
            })
            if block["has_quarter_and_cumulative"] and target_quarter == 2 and cumulative_cost is not None and quarter_cost is not None:
                first_quarter_cost = cumulative_cost - quarter_cost
                q1_start, q1_end = quarter_dates(year, 1)
                rows.append({
                    "회사": company,
                    "실적분기": f"{year}Q1",
                    "비용항목": item,
                    "누적비용_백만원": format_number(first_quarter_cost),
                    "누적비용_억원": format_number(first_quarter_cost / 100),
                    "분기비용_백만원": format_number(first_quarter_cost),
                    "분기비용_억원": format_number(first_quarter_cost / 100),
                    "실적기간_시작일": q1_start,
                    "실적기간_종료일": q1_end,
                    "공시일": filing["rcept_dt"],
                    "공시명": report_nm,
                    "접수번호": filing["rcept_no"],
                    "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
                })
    return rows


def extract_cost_structure_rows(company, filing, report_nm, text):
    quarter_label, start_date, end_date = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    costs = {}
    costs.update(parse_cost_nature_section(text))
    costs.update(parse_selling_admin_section(text))
    rows = []
    for item, cost_million in costs.items():
        rows.append({
            "회사": company,
            "실적분기": quarter_label,
            "비용항목": item,
            "누적비용_백만원": format_number(cost_million),
            "누적비용_억원": format_number(cost_million / 100),
            "분기비용_백만원": "",
            "분기비용_억원": "",
            "실적기간_시작일": start_date,
            "실적기간_종료일": end_date,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        })
    rows.extend(cost_nature_rows_from_blocks(company, filing, report_nm, text))
    rows.extend(selling_admin_rows_from_blocks(company, filing, report_nm, text))
    return rows


def parse_raw_material_price_section(text):
    target = compact_text(text)
    section = section_between(
        target,
        [r"주요\s*원재료\s*등의\s*가격변동\s*추이"],
        [r"나\.\s*생산", r"생산설비", r"매출\s*및\s*수주", r"설비의\s*신설"],
        fallback_length=4500,
    )
    if not section:
        section = section_between(
            target,
            [r"가격변동\s*추이"],
            [r"나\.\s*생산", r"생산설비", r"매출\s*및\s*수주", r"설비의\s*신설"],
            fallback_length=4500,
        )
    if not section:
        return []
    unit_match = re.search(r"단위\s*[:：]\s*([^) ]+)", section)
    unit = unit_match.group(1) if unit_match else ""
    material_pattern = re.compile(
        r"STEEL\s*PLATE|SECTION|후판|강재|형강|철판|원재료|철강|강판|PLATE|STEEL|PAINT|EPOXY|EPOXT|도료",
        re.IGNORECASE,
    )
    candidates = []
    direct_materials = [
        (r"STEEL\s*PLATE", "STEEL PLATE"),
        (r"SECTION", "형강"),
        (r"후\s*판", "후판"),
        (r"형\s*강", "형강"),
        (r"EPOX[YT]\s*PAINT|PAINT|EPOXY|EPOXT", "PAINT"),
    ]
    for pattern, label in direct_materials:
        for match in re.finditer(
            rf"{pattern}(?:\s*\(([^)]*)\))?\s+([0-9][0-9,]*(?:\.[0-9]+)?)",
            section,
            re.IGNORECASE,
        ):
            candidates.append((label, match.group(2), match.group(1) or unit))

    for match in re.finditer(r"([A-Za-z가-힣·ㆍ/()\-\s]{2,35})\s+([0-9][0-9,]*(?:\.[0-9]+)?)", section):
        item = compact_text(match.group(1)).strip(" :-")
        if not item or any(skip in item for skip in ("구분", "당분기", "전분기", "가격변동", "품목", "분기")):
            continue
        if "기준으로변경" in item or "산출기준" in item:
            continue
        compact_item = re.sub(r"\s+", "", item)
        if not material_pattern.search(item) and not material_pattern.search(compact_item):
            continue
        if len(item) > 30:
            continue
        item = re.sub(r"^(?:[0-9]{4}\s*)?년\s+", "", item).strip()
        item_unit_match = re.search(r"\(([^)]+)\)", item)
        item_unit = item_unit_match.group(1) if item_unit_match else unit
        item = re.sub(r"\([^)]*\)", "", item).strip()
        item = re.sub(r"\s+", "", item)
        if item.upper().endswith("STEELPLATE"):
            item = "STEEL PLATE"
        elif item.upper().endswith("SECTION"):
            item = "형강"
        elif item.endswith("후판"):
            item = "후판"
        elif item.endswith("형강"):
            item = "형강"
        elif "PAINT" in item.upper() or "EPOXY" in item.upper() or "EPOXT" in item.upper() or item.endswith("도료"):
            item = "PAINT"
        numeric_value = parse_sales_number(match.group(2))
        if item != "PAINT" and numeric_value is not None and numeric_value < 10_000:
            continue
        candidates.append((item, match.group(2), item_unit))
    deduped = []
    seen = set()
    for item, value, unit in candidates:
        key = (item, value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((item, value, unit))
    return deduped[:20]


def extract_raw_material_price_rows(company, filing, report_nm, text):
    quarter_label, _, _ = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    rows = []
    for item, value, unit in parse_raw_material_price_section(text):
        rows.append({
            "회사": company,
            "실적분기": quarter_label,
            "원재료항목": item,
            "가격": value,
            "단위": unit,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        })
    return rows


def parse_delivery_volume_section(text):
    target = compact_text(text)
    anchor = target.find("기초수주잔액")
    if anchor >= 0:
        start = max(0, target.rfind("다. 수주상황", 0, anchor))
        if start < 0:
            start = max(0, anchor - 500)
        end_candidates = [
            pos for pos in [
                target.find("5. 위험관리", anchor),
                target.find("라. 판매", anchor),
                target.find("III. 재무", anchor),
            ]
            if pos > anchor
        ]
        end = min(end_candidates) if end_candidates else anchor + 5000
        section = target[start:end]
    else:
        section = section_between(
            target,
            [r"다\.\s*수주상황", r"수주상황"],
            [r"5\.\s*위험관리", r"라\.\s*판매", r"나\.\s*판매", r"III\.\s*재무"],
            fallback_length=5000,
        )
    if not section or "기납품" not in section:
        return {}

    rows = {}
    patterns = [
        r"(선박)\s+[^0-9]{0,10}[0-9]{2}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일까지\s+-\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+[0-9][0-9,]*(?:\.[0-9]+)?\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+[0-9][0-9,]*(?:\.[0-9]+)?\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+[0-9][0-9,]*(?:\.[0-9]+)?\s+"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+[0-9][0-9,]*(?:\.[0-9]+)?",
        r"(조선해양|선박|탱커|원유운반선|컨테이너선|석유화학제품운반선|합\s*계)"
        r".{0,180}?기납품액\s+수량\s+([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(조선해양|선박|탱커|원유운반선|컨테이너선|석유화학제품운반선|합\s*계)"
        r".{0,260}?수주총액\s+수량\s+[0-9,.\-]+\s+금액\s+[0-9,.\-]+\s+기납품액\s+수량\s+([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, section, re.IGNORECASE):
            item = compact_text(match.group(1)).replace(" ", "")
            item = "합계" if "합계" in item else item
            quantity_group = 4 if len(match.groups()) >= 5 else 2
            quantity = parse_sales_number(match.group(quantity_group))
            if quantity is not None:
                rows[item] = quantity

    if not rows:
        # DART text often flattens the table. Use the line containing 합계 as a fallback:
        # 품목 수주일자 납기 수주총액 수량 금액 기납품액 수량 금액 수주잔고 수량 금액
        for match in re.finditer(r"합\s*계\s+((?:\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)\s+){2,8}", section):
            numbers = extract_trailing_numbers(match.group(0), limit=8)
            if len(numbers) >= 4:
                quantity = parse_sales_number(numbers[2])
                if quantity is not None:
                    rows["합계"] = quantity
                    break
    return rows


def extract_delivery_volume_rows(company, filing, report_nm, text):
    quarter_label, start_date, end_date = report_quarter_from_name(report_nm)
    if not quarter_label:
        return []
    volumes = parse_delivery_volume_section(text)
    rows = []
    for item, cumulative_quantity in volumes.items():
        rows.append({
            "회사": company,
            "실적분기": quarter_label,
            "품목": item,
            "누적기납품수량": format_number(cumulative_quantity),
            "분기기납품수량": "",
            "실적기간_시작일": start_date,
            "실적기간_종료일": end_date,
            "공시일": filing["rcept_dt"],
            "공시명": report_nm,
            "접수번호": filing["rcept_no"],
            "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        })
    return rows


def delivery_volume_key(row):
    return (row.get("회사", ""), row.get("실적분기", ""), row.get("품목", ""))


def add_quarterly_delivery_volume(rows):
    normalized = []
    for row in rows:
        copied = row.copy()
        copied["공시일"] = normalize_storage_date(copied.get("공시일", ""))
        if not copied.get("접수번호"):
            copied["접수번호"] = extract_receipt_no_from_url(copied.get("DART_URL", ""))
        normalized.append(copied)

    for company in sorted({row.get("회사", "") for row in normalized}):
        for item in sorted({row.get("품목", "") for row in normalized if row.get("회사", "") == company}):
            item_rows = [row for row in normalized if row.get("회사") == company and row.get("품목") == item]
            item_rows.sort(key=lambda row: row.get("실적분기", ""))
            cumulative_by_quarter = {
                row.get("실적분기", ""): parse_sales_number(row.get("누적기납품수량", ""))
                for row in item_rows
            }
            for row in item_rows:
                quarter = row.get("실적분기", "")
                cumulative = cumulative_by_quarter.get(quarter)
                if cumulative is None or not quarter[-1:].isdigit():
                    continue
                q_num = int(quarter[-1])
                year = quarter[:4]
                if q_num == 1:
                    quarter_quantity = cumulative
                else:
                    prev_cumulative = cumulative_by_quarter.get(f"{year}Q{q_num - 1}")
                    quarter_quantity = None if prev_cumulative is None else cumulative - prev_cumulative
                if quarter_quantity is not None:
                    row["분기기납품수량"] = format_number(max(0.0, quarter_quantity))
    return normalized


def merge_delivery_volume_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = delivery_volume_key(normalized)
        prev = merged.get(key)
        if prev is None or (normalized.get("공시일", ""), normalized.get("접수번호", "")) >= (
            prev.get("공시일", ""),
            prev.get("접수번호", ""),
        ):
            merged[key] = normalized
    return add_quarterly_delivery_volume(list(merged.values()))


def add_quarterly_segment_revenue(rows):
    normalized = []
    for row in rows:
        copied = row.copy()
        copied["공시일"] = normalize_storage_date(copied.get("공시일", ""))
        if not copied.get("접수번호"):
            copied["접수번호"] = extract_receipt_no_from_url(copied.get("DART_URL", ""))
        normalized.append(copied)

    for company in sorted({row.get("회사", "") for row in normalized}):
        for segment in sorted({row.get("사업부문", "") for row in normalized if row.get("회사", "") == company}):
            segment_rows = [
                row for row in normalized
                if row.get("회사", "") == company and row.get("사업부문", "") == segment
            ]
            segment_rows.sort(key=lambda row: row.get("실적분기", ""))
            cumulative_by_quarter = {
                row.get("실적분기", ""): parse_sales_number(row.get("누적매출액_백만원", ""))
                for row in segment_rows
            }
            for row in segment_rows:
                quarter = row.get("실적분기", "")
                cumulative = cumulative_by_quarter.get(quarter)
                if cumulative is None or not quarter[-1:].isdigit():
                    continue
                year = quarter[:4]
                q_num = int(quarter[-1])
                if q_num <= 1:
                    quarter_revenue = cumulative
                else:
                    prev_cumulative = cumulative_by_quarter.get(f"{year}Q{q_num - 1}")
                    if prev_cumulative is None:
                        quarter_revenue = None
                    else:
                        quarter_revenue = cumulative - prev_cumulative
                if quarter_revenue is not None:
                    row["분기매출액_백만원"] = format_number(quarter_revenue)
                    row["분기매출액_억원"] = format_number(quarter_revenue / 100)
                    row_start, row_end = quarter_dates(int(year), q_num)
                    row["실적기간_시작일"] = row_start
                    row["실적기간_종료일"] = row_end
    return normalized


def merge_segment_revenue_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = segment_revenue_key(normalized)
        prev = merged.get(key)
        if prev is None or (normalized.get("공시일", ""), normalized.get("접수번호", "")) >= (
            prev.get("공시일", ""),
            prev.get("접수번호", ""),
        ):
            merged[key] = normalized
    return add_quarterly_segment_revenue(list(merged.values()))


def cost_structure_key(row):
    return (row.get("회사", ""), row.get("실적분기", ""), row.get("비용항목", ""))


def raw_material_key(row):
    return (row.get("회사", ""), row.get("실적분기", ""), row.get("원재료항목", ""))


def report_period_matches_row(row):
    report_quarter, _, _ = report_quarter_from_name(compact_text(row.get("공시명", "")))
    return report_quarter == row.get("실적분기", "")


def disclosure_preference(row):
    return (
        1 if report_period_matches_row(row) else 0,
        row.get("공시일", ""),
        row.get("접수번호", ""),
    )


def add_quarterly_cost_structure(rows):
    normalized = []
    for row in rows:
        copied = row.copy()
        copied["공시일"] = normalize_storage_date(copied.get("공시일", ""))
        if not copied.get("접수번호"):
            copied["접수번호"] = extract_receipt_no_from_url(copied.get("DART_URL", ""))
        normalized.append(copied)

    for company in sorted({row.get("회사", "") for row in normalized}):
        for item in sorted({row.get("비용항목", "") for row in normalized if row.get("회사", "") == company}):
            item_rows = [
                row for row in normalized
                if row.get("회사", "") == company and row.get("비용항목", "") == item
            ]
            item_rows.sort(key=lambda row: row.get("실적분기", ""))
            cumulative_by_quarter = {
                row.get("실적분기", ""): parse_sales_number(row.get("누적비용_백만원", ""))
                for row in item_rows
            }
            quarter_sum_by_year = {}
            for row in item_rows:
                quarter = row.get("실적분기", "")
                cumulative = cumulative_by_quarter.get(quarter)
                if cumulative is None or not quarter[-1:].isdigit():
                    continue
                reported_quarter_cost = parse_sales_number(row.get("분기비용_백만원", ""))
                year = quarter[:4]
                q_num = int(quarter[-1])
                row_start = normalize_storage_date(row.get("실적기간_시작일", ""))
                quarter_start, quarter_end = quarter_dates(int(year), q_num)
                is_annual_report = (
                    "사업보고서" in row.get("공시명", "")
                    and "분기보고서" not in row.get("공시명", "")
                    and "반기보고서" not in row.get("공시명", "")
                )
                if row.get("비용항목", "").startswith("판관비_") and is_annual_report:
                    previous_quarter_sum = quarter_sum_by_year.get(year)
                    quarter_cost = (
                        None
                        if previous_quarter_sum is None
                        else cumulative - previous_quarter_sum
                    )
                elif row.get("비용항목", "").startswith("판관비_") and not is_annual_report:
                    quarter_cost = reported_quarter_cost if reported_quarter_cost is not None else cumulative
                elif row_start == quarter_start or q_num <= 1:
                    quarter_cost = reported_quarter_cost if reported_quarter_cost is not None else cumulative
                else:
                    prev_cumulative = cumulative_by_quarter.get(f"{year}Q{q_num - 1}")
                    quarter_cost = (
                        reported_quarter_cost
                        if reported_quarter_cost is not None
                        else cumulative / q_num if prev_cumulative is None and q_num == 2
                        else None if prev_cumulative is None else cumulative - prev_cumulative
                    )
                if quarter_cost is not None:
                    row["분기비용_백만원"] = format_number(quarter_cost)
                    row["분기비용_억원"] = format_number(quarter_cost / 100)
                    row["실적기간_시작일"] = quarter_start
                    row["실적기간_종료일"] = quarter_end
                    if row.get("비용항목", "").startswith("판관비_") and not is_annual_report:
                        quarter_sum_by_year[year] = quarter_sum_by_year.get(year, 0.0) + quarter_cost
    return normalized


def merge_cost_structure_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = cost_structure_key(normalized)
        prev = merged.get(key)
        if prev is None or disclosure_preference(normalized) >= disclosure_preference(prev):
            merged[key] = normalized
    return add_quarterly_cost_structure(list(merged.values()))


def merge_raw_material_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows + new_rows:
        normalized = row.copy()
        normalized["공시일"] = normalize_storage_date(normalized.get("공시일", ""))
        if not normalized.get("접수번호"):
            normalized["접수번호"] = extract_receipt_no_from_url(normalized.get("DART_URL", ""))
        key = raw_material_key(normalized)
        prev = merged.get(key)
        if prev is None or (normalized.get("공시일", ""), normalized.get("접수번호", "")) >= (
            prev.get("공시일", ""),
            prev.get("접수번호", ""),
        ):
            merged[key] = normalized
    return list(merged.values())


def save_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_target_csv(rows):
    with open(TARGET_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def save_monthly_sales_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(MONTHLY_SALES_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MONTHLY_SALES_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_quarterly_financials_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(QUARTERLY_FINANCIALS_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=QUARTERLY_FINANCIALS_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_segment_revenue_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(SEGMENT_REVENUE_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SEGMENT_REVENUE_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_cost_structure_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(COST_STRUCTURE_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COST_STRUCTURE_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_raw_material_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(RAW_MATERIAL_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_MATERIAL_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_delivery_volume_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["공시일"] = format_output_date(output_row.get("공시일", ""))
        output_rows.append(output_row)

    with open(DELIVERY_VOLUME_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=DELIVERY_VOLUME_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def save_market_cap_csv(rows):
    output_rows = []
    for row in rows:
        output_row = row.copy()
        output_row["기준일"] = format_output_date(output_row.get("기준일", ""))
        output_rows.append(output_row)

    with open(MARKET_CAP_OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MARKET_CAP_OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def extract_target_year(text, fallback_date):
    target = compact_text(text)
    patterns = [
        r"전망대상기간\s+([0-9]{4})\s*년",
        r"전망\s*대상기간\s+([0-9]{4})\s*년",
        r"대상기간\s+([0-9]{4})\s*년",
        r"([0-9]{4})\s*년\s+(?:영업실적|수주목표|수주\s*목표)",
    ]
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return match.group(1)
    return fallback_date[:4]


def normalize_target_unit(unit):
    unit = compact_text(unit).upper()
    unit = unit.replace("＄", "$").replace("US$", "USD")
    if not unit:
        return "억불"
    return unit


def target_value_to_100m_usd(value, unit):
    number = to_float(value)
    if number is None:
        return ""

    unit = normalize_target_unit(unit)
    if "억" in unit and ("불" in unit or "달러" in unit or "USD" in unit or "$" in unit):
        return f"{number:g}"
    if "백만" in unit and ("불" in unit or "달러" in unit or "USD" in unit or "$" in unit):
        return f"{number / 100:g}"
    if ("MILLION" in unit or "MN" in unit) and ("USD" in unit or "$" in unit):
        return f"{number / 100:g}"
    if "천" in unit and ("불" in unit or "달러" in unit or "USD" in unit or "$" in unit):
        return f"{number / 100000:g}"
    if "불" in unit or "달러" in unit or "USD" in unit or "$" in unit:
        return f"{number / 100000000:g}"
    return ""


def to_float(value):
    value = compact_text(str(value)).replace(",", "")
    match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def plausible_target_number(value):
    number = to_float(value)
    if number is None:
        return False
    if number.is_integer() and 1900 <= number <= 2100:
        return False
    return 0 < number < 100000


def first_target_number(text):
    for value in re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", text):
        if plausible_target_number(value):
            return value
    return ""


def target_unit_near(text, start=0):
    target = compact_text(text)
    left = max(0, start - 120)
    right = min(len(target), start + 180)
    window = target[left:right]

    patterns = [
        r"수주\s*목표(?:금액)?\s*\(([^)]*(?:억불|백만불|달러|USD|US\$|\$|MILLION)[^)]*)\)",
        r"단위\s*[:：]\s*([^,\s)]*(?:억불|백만불|달러|USD|US\$|\$|MILLION)[^,\s)]*)",
        r"\(([^)]*(?:억불|백만불|달러|USD|US\$|\$|MILLION)[^)]*)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, window, re.IGNORECASE)
        if match:
            return normalize_target_unit(match.group(1))
    return "억불"


def target_row(company, filing, report_nm, year, segment, value, unit):
    unit = normalize_target_unit(unit)
    return {
        "회사": company,
        "목표연도": year,
        "목표구분": segment,
        "수주목표": clean_value(value),
        "목표단위": unit,
        "수주목표_억불": target_value_to_100m_usd(value, unit),
        "공시일": filing["rcept_dt"],
        "공시명": report_nm,
        "접수번호": filing["rcept_no"],
        "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
    }


def extract_samsung_targets(company, filing, report_nm, text):
    target = compact_text(text).replace("ㆍ", "·")
    year = extract_target_year(text, filing["rcept_dt"])
    patterns = [
        r"조선\s*[·ㆍ]\s*해양\s*수주\s*목표\s*\(([^)]*)\)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"조선\s*[·ㆍ]\s*해양\s*수주\s*목표[^0-9]{0,80}([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            unit, value = match.group(1), match.group(2)
        else:
            value = match.group(1)
            unit = target_unit_near(target, match.start())
        if plausible_target_number(value):
            return [target_row(company, filing, report_nm, year, "조선·해양", value, unit)]
    return []


def extract_segment_targets(company, filing, report_nm, text, segments):
    target = compact_text(text).replace("ㆍ", "·")
    year = extract_target_year(text, filing["rcept_dt"])
    rows = []

    for segment, segment_pattern in segments:
        patterns = [
            rf"(?:{segment_pattern})\s*\(([^)]*(?:억불|백만불|달러|USD|US\$|\$|MILLION)[^)]*)\)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
            rf"(?:{segment_pattern})[^0-9]{{0,80}}([0-9][0-9,]*(?:\.[0-9]+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, target, re.IGNORECASE)
            if not match:
                continue
            if len(match.groups()) == 2:
                unit, value = match.group(1), match.group(2)
            else:
                value = match.group(1)
                unit = target_unit_near(target, match.start())
            if plausible_target_number(value):
                rows.append(target_row(company, filing, report_nm, year, segment, value, unit))
                break

    return rows


def extract_generic_target(company, filing, report_nm, text, segment="조선"):
    target = compact_text(text).replace("ㆍ", "·")
    year = extract_target_year(text, filing["rcept_dt"])

    amount_matches = re.findall(
        r"수주\s*\(([^)]*(?:억불|백만불|달러|USD|US\$|\$|MILLION)[^)]*)\)\s*[:：]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        target,
        re.IGNORECASE,
    )
    if amount_matches:
        unit, value = amount_matches[-1 if is_correction_filing(report_nm) else 0]
        if plausible_target_number(value):
            return [target_row(company, filing, report_nm, year, segment, value, unit)]

    patterns = [
        r"수주\s*목표(?:금액)?\s*\(([^)]*)\)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"수주\s*목표(?:금액)?[^0-9]{0,100}([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, target, re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            unit, value = match.group(1), match.group(2)
        else:
            value = match.group(1)
            unit = target_unit_near(target, match.start())
        if plausible_target_number(value):
            return [target_row(company, filing, report_nm, year, segment, value, unit)]

    target_pos = target.find("수주")
    if target_pos >= 0:
        value = first_target_number(target[target_pos:target_pos + 260])
        if value:
            return [target_row(company, filing, report_nm, year, segment, value, target_unit_near(target, target_pos))]
    return []


def extract_order_targets(company, filing, report_nm, text):
    actual_company = target_company_name(company, text)
    if should_skip_parent_subsidiary_filing(company, actual_company):
        return []
    if company == "삼성중공업":
        return extract_samsung_targets(actual_company, filing, report_nm, text)
    if company == "HD현대중공업":
        return extract_segment_targets(actual_company, filing, report_nm, text, [
            ("조선", r"조선"),
            ("특수선", r"특수선"),
            ("해양/플랜트", r"해양\s*/\s*플랜트|해양플랜트|해양"),
        ])
    if company == "HD한국조선해양":
        return extract_generic_target(actual_company, filing, report_nm, text, "조선")
    if company == "HD현대미포":
        return extract_generic_target(actual_company, filing, report_nm, text, "조선")
    return []


def dedupe_target_rows(rows):
    latest = {}
    for row in rows:
        key = (row["회사"], row["목표연도"], row["목표구분"])
        prev = latest.get(key)
        if prev is None or (row["공시일"], row["접수번호"]) >= (prev["공시일"], prev["접수번호"]):
            latest[key] = row
    return sorted(
        latest.values(),
        key=lambda row: (row["목표연도"], row["회사"], row["목표구분"]),
        reverse=True,
    )



def is_dashboard_running(host="127.0.0.1", port=DASHBOARD_PORT):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def dashboard_processes():
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []

    processes = []
    port_token = f"--server.port {DASHBOARD_PORT}"
    target_path = os.path.abspath(DASHBOARD_FILE)
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        pid_text, _, command = stripped.partition(" ")
        if not pid_text.isdigit():
            continue
        if "streamlit" not in command or "dashboard.py" not in command:
            continue
        if port_token not in command and f"--server.port={DASHBOARD_PORT}" not in command:
            continue

        processes.append({
            "pid": int(pid_text),
            "command": command,
            "is_target": target_path in command,
        })
    return processes


def stop_stale_dashboard_processes():
    stopped = False
    for process in dashboard_processes():
        if process["is_target"]:
            continue
        try:
            os.kill(process["pid"], 15)
            stopped = True
        except OSError:
            continue
    return stopped


def dashboard_command():
    streamlit = shutil.which("streamlit")
    if streamlit:
        return [
            streamlit,
            "run",
            DASHBOARD_FILE,
            "--server.headless",
            "true",
            "--server.port",
            str(DASHBOARD_PORT),
        ]

    uv = shutil.which("uv")
    if uv:
        return [
            uv,
            "run",
            "streamlit",
            "run",
            DASHBOARD_FILE,
            "--server.headless",
            "true",
            "--server.port",
            str(DASHBOARD_PORT),
        ]

    return None


def start_dashboard():
    if not AUTO_START_DASHBOARD:
        return

    project_dir = BASE_DIR
    dashboard_path = DASHBOARD_FILE
    dashboard_url = f"http://localhost:{DASHBOARD_PORT}"

    if not os.path.exists(dashboard_path):
        print(f"대시보드 파일이 없어 자동 실행을 건너뜁니다: {dashboard_path}")
        return

    if is_dashboard_running():
        target_running = any(process["is_target"] for process in dashboard_processes())
        if not target_running and stop_stale_dashboard_processes():
            print("이전 경로의 대시보드를 종료하고 새 경로로 다시 실행합니다.")
            time.sleep(1)
        else:
            print(f"대시보드 실행 중: {dashboard_url}")
            return

    if is_dashboard_running():
        print(f"대시보드 실행 중: {dashboard_url}")
        return

    command = dashboard_command()
    if not command:
        print("streamlit 또는 uv를 찾지 못해 대시보드를 자동 실행하지 못했습니다.")
        return

    try:
        subprocess.Popen(
            command,
            cwd=project_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        print(f"대시보드 자동 실행 실패: {e}")
        return

    print(f"대시보드 실행: {dashboard_url}")


def build_result_row(company, filing, report_nm, text):
    fields = extract_contract_fields(text)
    rcept_no = filing["rcept_no"]
    return {
        "회사": company,
        "공시일": filing["rcept_dt"],
        **fields,
        "공시명": report_nm,
        "접수번호": rcept_no,
        "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        "정정공시_URL": "",
        "비고": fields.get("비고", ""),
    }


def build_correction_record(company, corp_code, filing, report_nm, text):
    related_date = extract_correction_related_date(text)
    if not related_date and is_termination_filing(report_nm, text):
        related_date = extract_original_disclosure_date(text)

    return {
        "회사": company,
        "corp_code": corp_code,
        "공시일": filing["rcept_dt"],
        "공시명": report_nm,
        "접수번호": filing["rcept_no"],
        "DART_URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing['rcept_no']}",
        "정정관련공시일": related_date,
        "계약해지": is_termination_filing(report_nm, text),
        "비고": extract_correction_note(text),
        "fields": extract_contract_fields(text),
    }


def collect_recent_order_corrections(company, corp_code, start_date, seen_receipts):
    corrections = []
    filings = search_filings(corp_code, start=start_date, end=SEARCH_END_DATE)
    for filing in filings:
        report_nm = compact_text(filing["report_nm"])
        rcept_no = filing["rcept_no"]
        if rcept_no in seen_receipts:
            continue
        if not any(keyword in report_nm for keyword in ORDER_KEYWORDS):
            continue
        if not (is_correction_filing(report_nm) or is_termination_filing(report_nm)):
            continue

        try:
            text = download_document_text(rcept_no)
        except Exception as e:
            print(f"정정공시 보강 다운로드 실패: {company} {rcept_no} {e}")
            continue

        if not is_order_related(report_nm, text):
            continue

        actual_company = display_company_name(company, text)
        if should_skip_parent_subsidiary_filing(company, actual_company):
            continue

        corrections.append(build_correction_record(actual_company, corp_code, filing, report_nm, text))
        seen_receipts.add(rcept_no)

    return corrections


def correction_contract_names(original, correction):
    names = [
        correction.get("fields", {}).get("체결계약명", ""),
        original.get("체결계약명", ""),
        original.get("수정_체결계약명", ""),
    ]
    return [name for name in dict.fromkeys(names) if name]


def register_correction_alias(aliases, original, correction):
    company = original.get("회사") or correction.get("회사")
    correction_date = correction.get("공시일", "")
    if not company or not correction_date:
        return
    names = correction_contract_names(original, correction)
    for name in names:
        aliases[(company, correction_date, name)] = original
    aliases.setdefault((company, correction_date, ""), original)


def find_original_row(results, correction, aliases=None):
    aliases = aliases or {}
    related_date = correction["정정관련공시일"]
    contract_name = correction["fields"].get("체결계약명", "")

    if contract_name and (correction["회사"], related_date, contract_name) in aliases:
        return aliases[(correction["회사"], related_date, contract_name)]
    if (correction["회사"], related_date, "") in aliases:
        return aliases[(correction["회사"], related_date, "")]

    candidates = [
        row for row in results
        if row["회사"] == correction["회사"] and row["공시일"] == related_date
    ]
    if not candidates:
        return None

    if contract_name:
        for row in candidates:
            if contract_name in correction_contract_names(row, correction):
                return row

    return candidates[0] if len(candidates) == 1 else None


def add_missing_original_rows(results, corrections):
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in results
    }
    existing_receipts.discard("")
    added = 0

    for correction in corrections:
        if find_original_row(results, correction) is not None:
            continue

        related_date = correction["정정관련공시일"]
        if not related_date:
            continue

        filings = search_filings(correction["corp_code"], start=related_date, end=related_date)
        for filing in filings:
            report_nm = compact_text(filing["report_nm"])
            rcept_no = filing["rcept_no"]

            if rcept_no in EXCLUDED_ORDER_RECEIPTS:
                continue
            if rcept_no in existing_receipts:
                continue
            if is_correction_filing(report_nm) or is_termination_filing(report_nm):
                continue
            if not any(keyword in report_nm for keyword in ORDER_KEYWORDS):
                continue

            try:
                text = download_document_text(rcept_no)
            except Exception as e:
                print(f"원 공시 다운로드 실패: {correction['회사']} {rcept_no} {e}")
                continue

            if not is_order_related(report_nm, text):
                continue

            results.append(build_result_row(correction["회사"], filing, report_nm, text))
            existing_receipts.add(rcept_no)
            added += 1

    return added


def apply_corrections(results, corrections):
    unmatched = []
    aliases = {}
    for correction in sorted(corrections, key=lambda row: (row.get("공시일", ""), row.get("접수번호", ""))):
        original = find_original_row(results, correction, aliases)
        if original is None:
            unmatched.append(correction)
            continue

        fields = correction["fields"]
        tracked_changed = False
        if fields.get("체결계약명") and fields["체결계약명"] != original.get("체결계약명"):
            original["수정_체결계약명"] = fields["체결계약명"]
            original["수정_유추선종"] = fields.get("유추선종", "")
            original["수정_수주_선박수"] = fields.get("수주_선박수", "")
            tracked_changed = True

        if fields.get("유추선종") and fields["유추선종"] != original.get("유추선종"):
            original["수정_유추선종"] = fields["유추선종"]
            tracked_changed = True

        if fields.get("수주_선박수") and fields["수주_선박수"] != original.get("수주_선박수"):
            original["수정_수주_선박수"] = fields["수주_선박수"]
            tracked_changed = True

        if fields.get("계약금액") and fields["계약금액"] != original.get("계약금액"):
            original["수정_계약금액"] = fields["계약금액"]
            tracked_changed = True

        if fields.get("계약기간_종료일") and fields["계약기간_종료일"] != original.get("계약기간_종료일"):
            original["수정_계약기간_종료일"] = fields["계약기간_종료일"]
            tracked_changed = True

        if correction["계약해지"]:
            original["계약해지"] = "Y"
            tracked_changed = True

        if not tracked_changed and correction.get("비고"):
            note = f"{correction['공시일']} 정정: {correction['비고']}"
            existing_note = original.get("비고", "")
            if note not in existing_note.split(" | "):
                original["비고"] = " | ".join(
                    part for part in [existing_note, note] if part
                )

        correction_url = correction["DART_URL"]
        existing_urls = original.get("정정공시_URL", "")
        if correction_url and correction_url not in existing_urls.split(" | "):
            original["정정공시_URL"] = " | ".join(
                url for url in [existing_urls, correction_url] if url
            )
            original["정정공시_URL"] = normalize_correction_urls(original.get("정정공시_URL", ""))
        register_correction_alias(aliases, original, correction)

    if unmatched:
        print(f"원 공시를 찾지 못해 정정/해지 반영을 생략한 공시: {len(unmatched)}건")


def collect_monthly_sales(corp_rows, companies=None):
    existing_rows = load_existing_rows(MONTHLY_SALES_OUTPUT_FILE, MONTHLY_SALES_OUTPUT_COLUMNS)
    default_search_start_date = latest_disclosure_date(existing_rows)
    if default_search_start_date > SEARCH_END_DATE:
        default_search_start_date = SEARCH_END_DATE

    print(f"월별 매출 기본 검색 범위: {format_output_date(default_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")

    new_rows = []
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_rows
    }
    existing_receipts.discard("")

    allowed_companies = set(companies or MONTHLY_SALES_COMPANIES)
    for output_company, meta in MONTHLY_SALES_COMPANIES.items():
        if output_company not in allowed_companies:
            continue
        company_existing_rows = [row for row in existing_rows if row.get("회사") == output_company]
        search_start_date = latest_disclosure_date(company_existing_rows) if company_existing_rows else SEARCH_START_DATE
        if search_start_date > SEARCH_END_DATE:
            search_start_date = SEARCH_END_DATE
        print(f"월별 매출 검색 범위({output_company}): {format_output_date(search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")
        print(f"월별 매출 조회 중: {output_company}")
        corp_code = resolve_corp_code(
            corp_rows,
            stock_code=meta["stock_code"],
            corp_name=meta["corp_name"],
        )
        filings = search_filings(corp_code, start=search_start_date, end=SEARCH_END_DATE)
        for filing in filings:
            report_nm = compact_text(filing["report_nm"])
            rcept_no = filing["rcept_no"]

            if not is_monthly_sales_report(report_nm):
                continue
            if output_company == "HD현대삼호" and "자회사의 주요경영사항" not in report_nm:
                continue
            if output_company == "HD현대중공업" and rcept_no in existing_receipts:
                continue
            if output_company == "HD현대미포" and rcept_no in existing_receipts:
                continue
            if output_company == "HD현대삼호" and rcept_no in existing_receipts:
                continue

            try:
                text = download_document_text(rcept_no)
            except Exception as e:
                print(f"월별 매출 문서 다운로드 실패: {output_company} {rcept_no} {e}")
                continue

            actual_company = output_company
            if output_company == "HD현대삼호":
                actual_company = normalize_company_name(extract_subsidiary_company(text) or output_company)
                if actual_company != "HD현대삼호":
                    continue

            new_rows.extend(extract_monthly_sales_rows(actual_company, filing, report_nm, text))

    rows = merge_monthly_sales_rows(existing_rows, new_rows)
    rows.sort(key=lambda row: (row.get("실적월", ""), row.get("회사", "")), reverse=True)
    save_monthly_sales_csv(rows)
    print(
        f"월별 매출 저장 완료: {MONTHLY_SALES_OUTPUT_FILE} "
        f"(기존 {len(existing_rows)}건, 신규 후보 {len(new_rows)}건, 전체 {len(rows)}건)"
    )
    return bool(new_rows)


def collect_quarterly_financials(corp_rows, companies=None):
    existing_rows = load_existing_rows(QUARTERLY_FINANCIALS_OUTPUT_FILE, QUARTERLY_FINANCIALS_OUTPUT_COLUMNS)
    force_quarterly_refresh = os.getenv("FORCE_QUARTERLY_REFRESH") == "1"
    allowed_companies = set(companies or QUARTERLY_FINANCIALS_COMPANIES)
    if force_quarterly_refresh:
        existing_rows = [
            row for row in existing_rows
            if row.get("회사") not in allowed_companies
        ]
    default_search_start_date = latest_disclosure_date(existing_rows)
    if default_search_start_date > SEARCH_END_DATE:
        default_search_start_date = SEARCH_END_DATE

    print(f"분기 실적 기본 검색 범위: {format_output_date(default_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")

    new_rows = []
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_rows
    }
    existing_receipts.discard("")

    for output_company, meta in QUARTERLY_FINANCIALS_COMPANIES.items():
        if output_company not in allowed_companies:
            continue
        company_existing_rows = [row for row in existing_rows if row.get("회사") == output_company]
        search_start_date = latest_disclosure_date(company_existing_rows) if company_existing_rows else SEARCH_START_DATE
        if force_quarterly_refresh:
            search_start_date = SEARCH_START_DATE
        if output_company in {"대한조선", "삼성중공업", "HD현대미포"} and len(company_existing_rows) < 8:
            search_start_date = SEARCH_START_DATE
        if output_company == "삼성중공업":
            existing_quarters = {row.get("실적분기", "") for row in company_existing_rows}
            invalid_q4 = any(
                row.get("실적분기", "").endswith("Q4")
                and parse_sales_number(row.get("매출액_억원", "")) is not None
                and parse_sales_number(row.get("매출액_억원", "")) <= 0
                for row in company_existing_rows
            )
            current_year = int(SEARCH_END_DATE[:4])
            if invalid_q4 or any(f"{year}Q4" not in existing_quarters for year in range(2023, current_year)):
                search_start_date = min(search_start_date, "20230101")
        if search_start_date > SEARCH_END_DATE:
            search_start_date = SEARCH_END_DATE
        print(f"분기 실적 검색 범위({output_company}): {format_output_date(search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")

        if output_company == "HD현대중공업":
            sources = [(meta, "own"), (COMPANIES["HD한국조선해양"], "subsidiary")]
        elif output_company == "HD현대삼호":
            sources = [(COMPANIES["HD한국조선해양"], "subsidiary")]
        else:
            sources = [(meta, "own")]

        for source_meta, source_type in sources:
            print(f"분기 실적 조회 중: {output_company} ({source_type})")
            corp_code = resolve_corp_code(
                corp_rows,
                stock_code=source_meta["stock_code"],
                corp_name=source_meta["corp_name"],
            )
            filings = search_filings(corp_code, start=search_start_date, end=SEARCH_END_DATE)
            for filing in filings:
                report_nm = compact_text(filing["report_nm"])
                compact_report_nm = re.sub(r"\s+", "", report_nm)
                rcept_no = filing["rcept_no"]
                regular_report_for_financials = (
                    output_company in {"대한조선", "삼성중공업", "HD현대미포", "한화오션"}
                    and source_type == "own"
                    and is_regular_financial_report(report_nm)
                )
                quarterly_fair_disclosure = is_quarterly_financials_report(report_nm)

                if not quarterly_fair_disclosure and not regular_report_for_financials:
                    continue
                if quarterly_fair_disclosure and source_type == "own" and "연결재무제표기준" not in compact_report_nm:
                    continue
                if quarterly_fair_disclosure and source_type == "subsidiary" and "자회사의 주요경영사항" not in report_nm:
                    continue
                if rcept_no in existing_receipts and not regular_report_for_financials:
                    continue

                try:
                    text = download_document_text(rcept_no)
                except Exception as e:
                    print(f"분기 실적 문서 다운로드 실패: {output_company} {rcept_no} {e}")
                    continue

                actual_company = output_company
                if source_type == "subsidiary":
                    actual_company = normalize_company_name(extract_subsidiary_company(text) or "")
                    if actual_company != output_company:
                        continue

                if regular_report_for_financials:
                    new_rows.extend(extract_regular_report_cumulative_financial_rows(actual_company, filing, report_nm, text))
                else:
                    new_rows.extend(extract_quarterly_financial_rows(actual_company, filing, report_nm, text))

    rows = merge_quarterly_financial_rows(existing_rows, new_rows)
    rows.sort(key=lambda row: (row.get("실적분기", ""), row.get("회사", "")), reverse=True)
    save_quarterly_financials_csv(rows)
    print(
        f"분기 실적 저장 완료: {QUARTERLY_FINANCIALS_OUTPUT_FILE} "
        f"(기존 {len(existing_rows)}건, 신규 후보 {len(new_rows)}건, 전체 {len(rows)}건)"
    )
    return bool(new_rows)


def collect_segment_revenue(corp_rows, companies=None):
    existing_rows = load_existing_rows(SEGMENT_REVENUE_OUTPUT_FILE, SEGMENT_REVENUE_OUTPUT_COLUMNS)
    force_segment_refresh = os.getenv("FORCE_SEGMENT_REFRESH") == "1"
    allowed_companies = set(companies or ["HD현대중공업", "삼성중공업", "한화오션", "대한조선"])
    if force_segment_refresh:
        existing_rows = [row for row in existing_rows if row.get("회사") not in allowed_companies]
    search_start_date = SEARCH_START_DATE if force_segment_refresh else latest_disclosure_date(existing_rows) if existing_rows else SEARCH_START_DATE
    if search_start_date > SEARCH_END_DATE:
        search_start_date = SEARCH_END_DATE

    print(f"부문별 매출 검색 범위: {format_output_date(search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")

    new_rows = []
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_rows
    }
    existing_receipts.discard("")

    for output_company in ["HD현대중공업", "삼성중공업", "한화오션", "대한조선"]:
        if output_company not in allowed_companies:
            continue
        company_existing_rows = [] if force_segment_refresh else [row for row in existing_rows if row.get("회사") == output_company]
        company_search_start_date = SEARCH_START_DATE if force_segment_refresh else latest_disclosure_date(company_existing_rows) if company_existing_rows else SEARCH_START_DATE
        if company_search_start_date > SEARCH_END_DATE:
            company_search_start_date = SEARCH_END_DATE
        print(
            f"부문별 매출 검색 범위({output_company}): "
            f"{format_output_date(company_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}"
        )

        meta = COMPANIES[output_company]
        corp_code = resolve_corp_code(
            corp_rows,
            stock_code=meta["stock_code"],
            corp_name=meta["corp_name"],
        )
        filings = search_filings(corp_code, start=company_search_start_date, end=SEARCH_END_DATE)
        for filing in filings:
            report_nm = compact_text(filing["report_nm"])
            rcept_no = filing["rcept_no"]

            if not is_regular_financial_report(report_nm):
                continue
            if rcept_no in existing_receipts:
                continue

            try:
                text = download_document_text(rcept_no)
            except Exception as e:
                print(f"부문별 매출 문서 다운로드 실패: {output_company} {rcept_no} {e}")
                continue

            rows = extract_segment_revenue_rows(output_company, filing, report_nm, text)
            if not rows:
                print(f"부문별 매출 추출 실패: {output_company} {report_nm} {rcept_no}")
            new_rows.extend(rows)

    rows = merge_segment_revenue_rows(existing_rows, new_rows)
    rows.sort(key=lambda row: (row.get("실적분기", ""), row.get("사업부문", "")), reverse=True)
    save_segment_revenue_csv(rows)
    print(
        f"부문별 매출 저장 완료: {SEGMENT_REVENUE_OUTPUT_FILE} "
        f"(기존 {len(existing_rows)}건, 신규 후보 {len(new_rows)}건, 전체 {len(rows)}건)"
    )
    return bool(new_rows)


def collect_cost_structure(corp_rows, companies=None):
    existing_cost_rows = load_existing_rows(COST_STRUCTURE_OUTPUT_FILE, COST_STRUCTURE_OUTPUT_COLUMNS)
    existing_raw_rows = load_existing_rows(RAW_MATERIAL_OUTPUT_FILE, RAW_MATERIAL_OUTPUT_COLUMNS)
    force_cost_refresh = os.getenv("FORCE_COST_REFRESH") == "1"
    allowed_companies = set(companies or ["삼성중공업", "대한조선", "한화오션"])
    if force_cost_refresh:
        existing_cost_rows = [
            row for row in existing_cost_rows
            if row.get("회사") not in allowed_companies
        ]
        existing_raw_rows = [
            row for row in existing_raw_rows
            if row.get("회사") not in allowed_companies
        ]
    new_cost_rows = []
    new_raw_rows = []
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_cost_rows + existing_raw_rows
    }
    existing_receipts.discard("")

    for output_company in ["삼성중공업", "대한조선", "한화오션"]:
        if output_company not in allowed_companies:
            continue
        company_existing_rows = [
            row for row in existing_cost_rows + existing_raw_rows
            if row.get("회사") == output_company
        ]
        company_search_start_date = latest_disclosure_date(company_existing_rows) if company_existing_rows else "20230101"
        if force_cost_refresh:
            company_search_start_date = COST_STRUCTURE_START_DATE
        if output_company in {"대한조선", "한화오션"} and len(company_existing_rows) < 8:
            company_search_start_date = SEARCH_START_DATE
        if company_search_start_date > SEARCH_END_DATE:
            company_search_start_date = SEARCH_END_DATE
        print(
            f"비용/원재료 검색 범위({output_company}): "
            f"{format_output_date(company_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}"
        )

        meta = COMPANIES[output_company]
        corp_code = resolve_corp_code(
            corp_rows,
            stock_code=meta["stock_code"],
            corp_name=meta["corp_name"],
        )
        filings = search_filings(corp_code, start=company_search_start_date, end=SEARCH_END_DATE)
        for filing in filings:
            report_nm = compact_text(filing["report_nm"])
            rcept_no = filing["rcept_no"]
            if not is_regular_financial_report(report_nm):
                continue
            if rcept_no in existing_receipts:
                continue

            try:
                text = download_document_text(rcept_no)
            except Exception as e:
                print(f"비용/원재료 문서 다운로드 실패: {output_company} {rcept_no} {e}")
                continue

            cost_rows = extract_cost_structure_rows(output_company, filing, report_nm, text)
            raw_rows = extract_raw_material_price_rows(output_company, filing, report_nm, text)
            if not cost_rows:
                print(f"비용 성격별 분류 추출 실패: {output_company} {report_nm} {rcept_no}")
            new_cost_rows.extend(cost_rows)
            new_raw_rows.extend(raw_rows)

    cost_rows = merge_cost_structure_rows(existing_cost_rows, new_cost_rows)
    raw_rows = merge_raw_material_rows(existing_raw_rows, new_raw_rows)
    cost_rows.sort(key=lambda row: (row.get("실적분기", ""), row.get("비용항목", "")), reverse=True)
    raw_rows.sort(key=lambda row: (row.get("실적분기", ""), row.get("원재료항목", "")), reverse=True)
    save_cost_structure_csv(cost_rows)
    save_raw_material_csv(raw_rows)
    print(
        f"비용 구조 저장 완료: {COST_STRUCTURE_OUTPUT_FILE} "
        f"(기존 {len(existing_cost_rows)}건, 신규 후보 {len(new_cost_rows)}건, 전체 {len(cost_rows)}건)"
    )
    print(
        f"원재료 가격 저장 완료: {RAW_MATERIAL_OUTPUT_FILE} "
        f"(기존 {len(existing_raw_rows)}건, 신규 후보 {len(new_raw_rows)}건, 전체 {len(raw_rows)}건)"
    )
    return bool(new_cost_rows or new_raw_rows)


def collect_delivery_volume(corp_rows, companies=None):
    existing_rows = load_existing_rows(DELIVERY_VOLUME_OUTPUT_FILE, DELIVERY_VOLUME_OUTPUT_COLUMNS)
    force_refresh = os.getenv("FORCE_DELIVERY_REFRESH") == "1"
    if force_refresh:
        existing_rows = []
    new_rows = []
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_rows
    }
    existing_receipts.discard("")

    output_company = "대한조선"
    if companies is not None and output_company not in set(companies):
        print("기납품 수량 수집 생략: 선택 회사에 대한조선 없음")
        return False
    company_search_start_date = latest_disclosure_date(existing_rows) if existing_rows else "20240101"
    if force_refresh:
        company_search_start_date = "20240101"
    if company_search_start_date > SEARCH_END_DATE:
        company_search_start_date = SEARCH_END_DATE
    print(
        f"기납품 수량 검색 범위({output_company}): "
        f"{format_output_date(company_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}"
    )

    meta = COMPANIES[output_company]
    corp_code = resolve_corp_code(
        corp_rows,
        stock_code=meta["stock_code"],
        corp_name=meta["corp_name"],
    )
    filings = search_filings(corp_code, start=company_search_start_date, end=SEARCH_END_DATE)
    for filing in filings:
        report_nm = compact_text(filing["report_nm"])
        rcept_no = filing["rcept_no"]
        if not is_regular_financial_report(report_nm):
            continue
        if rcept_no in existing_receipts:
            continue

        try:
            text = download_document_text(rcept_no)
        except Exception as e:
            print(f"기납품 수량 문서 다운로드 실패: {output_company} {rcept_no} {e}")
            continue

        rows = extract_delivery_volume_rows(output_company, filing, report_nm, text)
        if not rows:
            print(f"기납품 수량 추출 실패: {output_company} {report_nm} {rcept_no}")
        new_rows.extend(rows)

    rows = merge_delivery_volume_rows(existing_rows, new_rows)
    rows.sort(key=lambda row: (row.get("실적분기", ""), row.get("품목", "")), reverse=True)
    save_delivery_volume_csv(rows)
    print(
        f"기납품 수량 저장 완료: {DELIVERY_VOLUME_OUTPUT_FILE} "
        f"(기존 {len(existing_rows)}건, 신규 후보 {len(new_rows)}건, 전체 {len(rows)}건)"
    )
    return bool(new_rows)


def run_financial_forecast(fast=False):
    if not os.path.exists(FORECAST_SCRIPT_FILE):
        print(f"분기 실적 예측 스크립트 없음: {FORECAST_SCRIPT_FILE}")
        return

    python_executable = PROJECT_PYTHON if os.path.exists(PROJECT_PYTHON) else sys.executable
    command = [python_executable, FORECAST_SCRIPT_FILE]
    if fast:
        command.extend(["--use-cached-scurve", "--skip-backtest"])
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"분기 실적 예측 실패: {result.stderr.strip()}")


def collect_market_cap(companies=None):
    allowed_companies = set(companies or MARKET_CAP_COMPANIES)
    selected_market_cap_companies = {
        name: meta
        for name, meta in MARKET_CAP_COMPANIES.items()
        if name in allowed_companies
    }
    if not selected_market_cap_companies:
        print("시가총액 수집 대상 회사가 없습니다.")
        return False

    existing_rows = load_existing_rows(MARKET_CAP_OUTPUT_FILE, MARKET_CAP_OUTPUT_COLUMNS)
    existing_rows = [
        row for row in existing_rows
        if row.get("회사", "") in MARKET_CAP_COMPANIES
    ]
    last_date = latest_market_cap_date(existing_rows)
    if last_date:
        start = parse_yyyymmdd(last_date) + timedelta(days=1)
        search_start_date = start.strftime("%Y%m%d")
    else:
        search_start_date = SEARCH_START_DATE

    if search_start_date > SEARCH_END_DATE:
        print(f"시가총액 수집 생략: 이미 최신입니다. 마지막 기준일 {format_output_date(last_date)}")
        return False

    target_dates = market_cap_target_dates(search_start_date, SEARCH_END_DATE)
    print(
        f"시가총액 검색 범위: {format_output_date(search_start_date)} ~ "
        f"{format_output_date(SEARCH_END_DATE)} ({len(target_dates)}개 기준일 후보)"
    )

    new_rows = []
    marcap_rows, covered_targets = fetch_marcap_market_cap_rows(
        target_dates,
        selected_market_cap_companies,
        min_allowed_date=parse_yyyymmdd(search_start_date),
    )
    new_rows.extend(marcap_rows)

    fetched_trade_dates = set()
    for target_date in target_dates:
        if target_date in covered_targets:
            continue
        trade_date, krx_rows = fetch_krx_market_cap_asof(target_date)
        if not trade_date or not krx_rows:
            print(f"KRX 시가총액 데이터 없음: {target_date:%Y-%m-%d}")
            continue
        if trade_date in fetched_trade_dates:
            continue
        fetched_trade_dates.add(trade_date)

        rows = build_market_cap_rows(trade_date, krx_rows, selected_market_cap_companies)
        if rows:
            print(f"시가총액 수집: 기준일 {target_date:%Y-%m-%d} -> 거래일 {trade_date:%Y-%m-%d} ({len(rows)}건)")
            new_rows.extend(rows)
        time.sleep(0.2)

    rows = merge_market_cap_rows(existing_rows, new_rows)
    rows.sort(key=lambda row: (normalize_market_cap_date(row.get("기준일", "")), row.get("회사", "")), reverse=True)
    save_market_cap_csv(rows)
    print(
        f"시가총액 저장 완료: {MARKET_CAP_OUTPUT_FILE} "
        f"(기존 {len(existing_rows)}건, 신규 후보 {len(new_rows)}건, 전체 {len(rows)}건)"
    )
    return len(rows) > len(existing_rows)


TASK_ALIASES = {
    "all": {"orders", "monthly", "quarterly", "segment", "cost", "delivery", "marketcap", "forecast", "dashboard"},
    "daily": {"orders", "marketcap", "dashboard"},
    "monthly-run": {"monthly", "forecast", "dashboard"},
    "quarterly-run": {"quarterly", "segment", "cost", "delivery", "forecast", "dashboard"},
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="DART 조선 수주/실적 데이터 수집 및 대시보드 실행",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=["all"],
        choices=[
            "all",
            "daily",
            "monthly-run",
            "quarterly-run",
            "orders",
            "monthly",
            "quarterly",
            "segment",
            "cost",
            "delivery",
            "marketcap",
            "forecast",
            "dashboard",
        ],
        help=(
            "실행할 작업. 예: --tasks orders, --tasks monthly forecast, "
            "--tasks quarterly segment cost delivery marketcap forecast"
        ),
    )
    parser.add_argument(
        "--companies",
        nargs="+",
        default=None,
        help="지정 회사만 수집. 예: --companies 대한조선 삼성중공업",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="작업 완료 후 대시보드를 실행하지 않음",
    )
    parser.add_argument(
        "--force-forecast",
        action="store_true",
        help="수집 신규 데이터가 없어도 예측을 실행",
    )
    parser.add_argument(
        "--forecast-fast",
        action="store_true",
        help="예측 실행 시 기존 S-curve/백테스트를 재사용",
    )
    return parser.parse_args()


def selected_tasks(task_args):
    tasks = set()
    for task in task_args:
        tasks.update(TASK_ALIASES.get(task, {task}))
    return tasks


def normalize_company_label(value):
    return re.sub(r"[\s()㈜주식회사]+", "", str(value)).lower()


def filter_companies(companies):
    if not companies:
        return COMPANIES
    normalized = {normalize_company_label(company) for company in companies}
    selected = {
        name: meta
        for name, meta in COMPANIES.items()
        if normalize_company_label(name) in normalized
        or normalize_company_label(meta.get("corp_name", "")) in normalized
    }
    missing = sorted(normalized - {normalize_company_label(name) for name in selected})
    if missing:
        print(f"회사 필터에서 찾지 못한 항목: {', '.join(missing)}")
    return selected


def collect_orders_and_targets(corp_rows, companies):
    if not API_KEY:
        raise RuntimeError("API_KEY가 비어 있습니다.")

    existing_results = load_existing_rows(OUTPUT_FILE, OUTPUT_COLUMNS)
    existing_target_results = load_existing_rows(TARGET_OUTPUT_FILE, TARGET_OUTPUT_COLUMNS)
    force_full_order_refresh = os.getenv("FORCE_FULL_ORDER_REFRESH") == "1"
    default_search_start_date = latest_disclosure_date(existing_results)
    if default_search_start_date > SEARCH_END_DATE:
        default_search_start_date = SEARCH_END_DATE

    print(f"기본 검색 범위: {format_output_date(default_search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")

    new_results = []
    corrections = []
    correction_receipts = set()
    target_results = existing_target_results.copy()
    existing_receipts = {
        row.get("접수번호") or extract_receipt_no_from_url(row.get("DART_URL", ""))
        for row in existing_results
    }
    existing_receipts.discard("")

    for company, meta in companies.items():
        if company == PARENT_COMPANY_WITH_SUBSIDIARIES:
            company_existing_rows = [
                row for row in existing_results
                if row.get("회사") in {PARENT_COMPANY_WITH_SUBSIDIARIES, "HD현대삼호"}
            ]
        else:
            company_existing_rows = [row for row in existing_results if row.get("회사") == company]
        search_start_date = latest_disclosure_date(company_existing_rows) if company_existing_rows else SEARCH_START_DATE
        if force_full_order_refresh:
            search_start_date = SEARCH_START_DATE
        if company in TARGET_REPORT_COMPANIES:
            target_names = target_existing_company_names(company)
            company_target_rows = [
                row for row in existing_target_results
                if row.get("회사") in target_names
            ]
            if not company_target_rows:
                search_start_date = SEARCH_START_DATE
        if search_start_date > SEARCH_END_DATE:
            search_start_date = SEARCH_END_DATE
        print(f"검색 범위({company}): {format_output_date(search_start_date)} ~ {format_output_date(SEARCH_END_DATE)}")
        print(f"조회 중: {company}")
        corp_code = resolve_corp_code(
            corp_rows,
            stock_code=meta["stock_code"],
            corp_name=meta["corp_name"],
        )

        filings = search_filings(corp_code, start=search_start_date, end=SEARCH_END_DATE)
        for row in filings:
            report_nm = compact_text(row["report_nm"])
            rcept_no = row["rcept_no"]

            if rcept_no in EXCLUDED_ORDER_RECEIPTS:
                continue
            if is_target_report(report_nm):
                if company == PARENT_COMPANY_WITH_SUBSIDIARIES and "자회사의 주요경영사항" not in report_nm:
                    continue
                try:
                    text = download_document_text(rcept_no)
                except Exception as e:
                    print(f"수주목표 문서 다운로드 실패: {company} {rcept_no} {e}")
                    text = ""

                target_rows = extract_order_targets(company, row, report_nm, text)
                if target_rows:
                    target_results.extend(target_rows)
                continue

            if not any(keyword in report_nm for keyword in ORDER_KEYWORDS):
                continue

            if (
                rcept_no in existing_receipts
                and not is_correction_filing(report_nm)
                and not is_termination_filing(report_nm)
            ):
                continue

            try:
                text = download_document_text(rcept_no)
            except Exception as e:
                print(f"문서 다운로드 실패: {company} {rcept_no} {e}")
                text = ""

            if not is_order_related(report_nm, text):
                continue

            actual_company = display_company_name(company, text)
            if should_skip_parent_subsidiary_filing(company, actual_company):
                continue

            if is_correction_filing(report_nm) or is_termination_filing(report_nm, text):
                corrections.append(build_correction_record(actual_company, corp_code, row, report_nm, text))
                correction_receipts.add(rcept_no)
                continue

            new_results.append(build_result_row(actual_company, row, report_nm, text))

        correction_start_date = correction_backfill_start_date()
        if correction_start_date < search_start_date:
            print(
                f"정정공시 보강 검색({company}): "
                f"{format_output_date(correction_start_date)} ~ {format_output_date(SEARCH_END_DATE)}"
            )
            corrections.extend(
                collect_recent_order_corrections(
                    company,
                    corp_code,
                    correction_start_date,
                    correction_receipts,
                )
            )

    results = merge_order_rows(existing_results, new_results)
    added = add_missing_original_rows(results, corrections)
    apply_corrections(results, corrections)
    refresh_derived_order_fields(results)
    results.sort(key=lambda row: (row["공시일"], row["회사"]), reverse=True)
    save_csv(results)
    target_results = dedupe_target_rows(target_results)
    save_target_csv(target_results)
    print(
        f"저장 완료: {OUTPUT_FILE} "
        f"(기존 {len(existing_results)}건, 신규 {len(new_results)}건, 전체 {len(results)}건, "
        f"원 공시 추가 {added}건, 정정/해지 {len(corrections)}건 반영 시도)"
    )
    print(f"수주목표 저장 완료: {TARGET_OUTPUT_FILE} ({len(target_results)}건)")
    return bool(new_results or corrections)


def main():
    args = parse_args()
    tasks = selected_tasks(args.tasks)
    companies = filter_companies(args.companies)
    if not companies:
        raise RuntimeError("실행 대상 회사가 없습니다.")

    print(f"실행 작업: {', '.join(sorted(tasks))}")
    print(f"실행 회사: {', '.join(companies.keys())}")
    corp_rows = get_corp_codes()
    updated = False

    if "orders" in tasks:
        updated = collect_orders_and_targets(corp_rows, companies) or updated
    if "monthly" in tasks:
        updated = collect_monthly_sales(corp_rows, companies.keys()) or updated
    if "quarterly" in tasks:
        updated = collect_quarterly_financials(corp_rows, companies.keys()) or updated
    if "segment" in tasks:
        updated = collect_segment_revenue(corp_rows, companies.keys()) or updated
    if "cost" in tasks:
        updated = collect_cost_structure(corp_rows, companies.keys()) or updated
    if "delivery" in tasks:
        updated = collect_delivery_volume(corp_rows, companies.keys()) or updated
    if "marketcap" in tasks:
        updated = collect_market_cap(companies.keys()) or updated

    if "forecast" in tasks:
        if updated or args.force_forecast or os.getenv("RUN_FINANCIAL_FORECAST") == "1":
            run_financial_forecast(fast=args.forecast_fast)
        else:
            print("분기 실적 예측 생략: 신규 업데이트 없음 (--force-forecast 사용 시 강제 실행)")

    if "dashboard" in tasks and not args.no_dashboard:
        start_dashboard()


if __name__ == "__main__":
    main()
