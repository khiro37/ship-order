import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import altair as alt
import pandas as pd
import streamlit as st


CSV_PATH = Path(__file__).with_name("ship_order_summary.csv")
TARGET_CSV_PATH = Path(__file__).with_name("ship_order_targets.csv")
MARKET_CAP_CSV_PATH = Path(__file__).with_name("ship_market_cap.csv")
RUNTIME_DIR = Path(__file__).with_name("_runtime")
REQUESTS_PATH = RUNTIME_DIR / "requests.csv"
ANALYTICS_PATH = RUNTIME_DIR / "analytics.json"
REQUEST_COMMENT_MARKER = "<!-- ship-order-dashboard-request:v1 -->"
BACKLOG_HORIZON_YEARS = 4
MARKET_CAP_BACKLOG_START_DATE = pd.Timestamp("2023-01-01")
NO_TARGET_COMPANIES = {"대한조선", "한화오션"}
ANALYSIS_EXCLUDED_SHIP_TYPES = {"엔진기계"}
MERGER_EFFECTIVE_DATE = pd.Timestamp("2026-01-01")
MERGER_SOURCE_COMPANY = "HD현대미포"
MERGER_TARGET_COMPANY = "HD현대중공업"
PERIOD_OPTIONS = {
    "월별": ("월", "월_정렬"),
    "분기별": ("분기", "분기_정렬"),
    "연도별": ("연도", "연도_정렬"),
}
BACKLOG_PERIOD_FREQ = {
    "월별": "M",
    "분기별": "Q",
    "연도별": "Y",
}
PERIOD_DELTA_PREFIX = {
    "월별": "전월대비",
    "분기별": "전분기대비",
    "연도별": "전년대비",
}


st.set_page_config(
    page_title="조선 수주 대시보드 (By 워렌넝구)",
    page_icon="",
    layout="wide",
)


def to_number(series):
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip().replace("", pd.NA),
        errors="coerce",
    )


def to_ratio(series):
    values = to_number(series)
    if values.abs().max(skipna=True) and values.abs().max(skipna=True) > 1:
        values = values / 100
    return values


def format_percent(value, decimals=2):
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.{decimals}f}%"


def use_revision(df, base_col, revised_col):
    revised = df[revised_col].astype(str).str.strip()
    base = df[base_col].astype(str).str.strip()
    return revised.where(revised.ne(""), base)


def normalize_company_name(series):
    return series.astype(str).str.strip().replace({
        "현대삼호중공업(주)": "HD현대삼호",
        "현대삼호중공업": "HD현대삼호",
        "에이치디현대삼호(주)": "HD현대삼호",
        "에이치디현대삼호": "HD현대삼호",
        "HD현대삼호(주)": "HD현대삼호",
    })


def company_mask_with_hhi_merger(df, date_col, selected_companies):
    selected = set(selected_companies)
    dates = pd.to_datetime(df[date_col], errors="coerce")
    source = df["회사"].eq(MERGER_SOURCE_COMPANY)
    after_merger = dates.ge(MERGER_EFFECTIVE_DATE)

    normal_company = ~source & df["회사"].isin(selected)
    source_before_merger = source & ~after_merger & (MERGER_SOURCE_COMPANY in selected)
    source_after_merger = source & after_merger & (MERGER_TARGET_COMPANY in selected)
    return normal_company | source_before_merger | source_after_merger


def apply_hhi_merger_by_date(df, date_col):
    result = df.copy()
    dates = pd.to_datetime(result[date_col], errors="coerce")
    mask = result["회사"].eq(MERGER_SOURCE_COMPANY) & dates.ge(MERGER_EFFECTIVE_DATE)
    result.loc[mask, "회사"] = MERGER_TARGET_COMPANY
    return result


def apply_hhi_merger_as_of(df, as_of_date):
    result = df.copy()
    if pd.Timestamp(as_of_date) >= MERGER_EFFECTIVE_DATE:
        result.loc[result["회사"].eq(MERGER_SOURCE_COMPANY), "회사"] = MERGER_TARGET_COMPANY
    return result


def parse_date_series(series):
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    return parsed.fillna(pd.to_datetime(text, errors="coerce"))


def target_segment(ship_type):
    if ship_type == "엔진기계":
        return "엔진기계"
    if ship_type == "해양플랜트":
        return "해양/플랜트"
    if ship_type == "특수선/방산":
        return "특수선"
    return "조선"


@st.cache_data
def load_data(csv_path, mtime):
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    required_cols = [
        "회사",
        "공시일",
        "체결계약명",
        "유추선종",
        "수주_선박수",
        "계약금액",
        "계약기간_종료일",
        "매매기준환율",
        "수정_체결계약명",
        "수정_유추선종",
        "수정_수주_선박수",
        "수정_계약금액",
        "수정_계약기간_종료일",
        "계약해지",
        "DART_URL",
        "정정공시_URL",
        "비고",
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["회사"] = normalize_company_name(df["회사"])
    df["공시일_dt"] = parse_date_series(df["공시일"])
    df["최종_체결계약명"] = use_revision(df, "체결계약명", "수정_체결계약명")
    df["최종_유추선종"] = use_revision(df, "유추선종", "수정_유추선종")
    df["최종_수주_선박수"] = to_number(use_revision(df, "수주_선박수", "수정_수주_선박수"))
    df["최종_계약금액"] = to_number(use_revision(df, "계약금액", "수정_계약금액"))
    df["최종_계약기간_종료일"] = use_revision(df, "계약기간_종료일", "수정_계약기간_종료일")
    df["최종_계약기간_종료일_dt"] = pd.to_datetime(df["최종_계약기간_종료일"], errors="coerce")
    df["해지여부"] = df["계약해지"].astype(str).str.upper().eq("Y")

    df["계약금액_억원"] = df["최종_계약금액"] / 100_000_000
    df["계약금액_조원"] = df["최종_계약금액"] / 1_000_000_000_000
    df["환율"] = to_number(df["매매기준환율"])
    df["계약금액_억불"] = df["최종_계약금액"] / df["환율"] / 100_000_000
    df["척당단가_억원"] = df["계약금액_억원"] / df["최종_수주_선박수"]
    df["목표구분"] = df["최종_유추선종"].map(target_segment)

    df["월_정렬"] = df["공시일_dt"].dt.to_period("M").dt.to_timestamp()
    df["분기_정렬"] = df["공시일_dt"].dt.to_period("Q").dt.start_time
    df["연도_정렬"] = df["공시일_dt"].dt.to_period("Y").dt.start_time
    df["월"] = df["공시일_dt"].dt.strftime("%Y-%m")
    df["분기"] = df["공시일_dt"].dt.to_period("Q").astype(str)
    df["연도"] = df["공시일_dt"].dt.year.astype("Int64").astype(str)
    df["인도월_정렬"] = df["최종_계약기간_종료일_dt"].dt.to_period("M").dt.to_timestamp()
    df["인도분기_정렬"] = df["최종_계약기간_종료일_dt"].dt.to_period("Q").dt.start_time
    df["인도연도_정렬"] = df["최종_계약기간_종료일_dt"].dt.to_period("Y").dt.start_time
    df["인도월"] = df["최종_계약기간_종료일_dt"].dt.strftime("%Y-%m")
    df["인도분기"] = df["최종_계약기간_종료일_dt"].dt.to_period("Q").astype(str)
    df["인도연도"] = df["최종_계약기간_종료일_dt"].dt.year.astype("Int64").astype(str)

    return df[df["공시일_dt"].notna()].copy()


@st.cache_data
def load_targets(csv_path, mtime):
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    required_cols = [
        "회사",
        "목표연도",
        "목표구분",
        "수주목표",
        "목표단위",
        "수주목표_억불",
        "공시일",
        "공시명",
        "DART_URL",
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["회사"] = normalize_company_name(df["회사"])
    df["목표연도"] = pd.to_numeric(df["목표연도"], errors="coerce").astype("Int64").astype(str)
    df["수주목표_억불"] = to_number(df["수주목표_억불"])
    df["공시일_dt"] = parse_date_series(df["공시일"])
    df = df[~df["목표구분"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES)]
    return df[df["목표연도"].ne("<NA>")].copy()


@st.cache_data
def load_market_cap(csv_path, mtime):
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    required_cols = ["회사", "기준일"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["회사"] = normalize_company_name(df["회사"])
    df["기준일_dt"] = parse_date_series(df["기준일"])

    if "시가총액_억원" in df.columns:
        df["시가총액_억원"] = to_number(df["시가총액_억원"])
    elif "시가총액_조원" in df.columns:
        df["시가총액_억원"] = to_number(df["시가총액_조원"]) * 10_000
    elif "시가총액" in df.columns:
        market_cap = to_number(df["시가총액"])
        df["시가총액_억원"] = market_cap
        if market_cap.max(skipna=True) and market_cap.max(skipna=True) > 1_000_000:
            df["시가총액_억원"] = market_cap / 100_000_000
    else:
        df["시가총액_억원"] = pd.NA

    df["시가총액_조원"] = df["시가총액_억원"] / 10_000
    df = df[~df["회사"].isin(["HD현대삼호", "HD현대미포"])].copy()
    return (
        df[df["회사"].ne("") & df["기준일_dt"].notna() & df["시가총액_조원"].notna()]
        .sort_values(["회사", "기준일_dt"])
        .copy()
    )


def attach_market_cap_asof(backlog_company, market_cap):
    backlog_company = backlog_company.copy()
    market_cap = market_cap.copy()
    backlog_company["기간_말일"] = pd.to_datetime(backlog_company["기간_말일"], errors="coerce").astype("datetime64[ns]")
    market_cap["기준일_dt"] = pd.to_datetime(market_cap["기준일_dt"], errors="coerce").astype("datetime64[ns]")

    if backlog_company.empty:
        return backlog_company.assign(
            기준일=pd.NA,
            기준일_dt=pd.NaT,
            시가총액_억원=pd.NA,
            시가총액_조원=pd.NA,
            시가총액_수주잔고배율=pd.NA,
        )
    if market_cap.empty:
        return backlog_company.iloc[0:0].assign(
            기준일=pd.NA,
            기준일_dt=pd.NaT,
            시가총액_억원=pd.NA,
            시가총액_조원=pd.NA,
            시가총액_수주잔고배율=pd.NA,
        )

    merged_rows = []
    cap_cols = ["기준일", "기준일_dt", "시가총액_억원", "시가총액_조원"]
    for company, rows in backlog_company.groupby("회사", dropna=False):
        caps = market_cap[market_cap["회사"].eq(company)].sort_values("기준일_dt")
        if caps.empty:
            continue
        merged = pd.merge_asof(
            rows.sort_values("기간_말일"),
            caps[cap_cols],
            left_on="기간_말일",
            right_on="기준일_dt",
            direction="backward",
        )
        merged_rows.append(merged)

    if not merged_rows:
        return backlog_company.iloc[0:0].assign(
            기준일=pd.NA,
            기준일_dt=pd.NaT,
            시가총액_억원=pd.NA,
            시가총액_조원=pd.NA,
            시가총액_수주잔고배율=pd.NA,
        )

    result = pd.concat(merged_rows, ignore_index=True)
    result = result[result["시가총액_조원"].notna()].copy()
    result["시가총액_수주잔고배율"] = result["시가총액_조원"] / result["잔고_계약금액_조원"]
    result.loc[result["잔고_계약금액_조원"].le(0), "시가총액_수주잔고배율"] = pd.NA
    return result.sort_values(["기간_말일", "회사"])


def aggregate(df, group_cols):
    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(
            수주건수=("공시일", "size"),
            수주_선박수=("최종_수주_선박수", "sum"),
            계약금액_억원=("계약금액_억원", "sum"),
            계약금액_억불=("계약금액_억불", "sum"),
        )
        .reset_index()
    )
    grouped["계약금액_조원"] = grouped["계약금액_억원"] / 10_000
    grouped["척당_평균단가_억원"] = grouped["계약금액_억원"] / grouped["수주_선박수"]
    grouped.loc[grouped["수주_선박수"].le(0), "척당_평균단가_억원"] = pd.NA
    return grouped


def numeric_sum(series):
    return pd.to_numeric(series, errors="coerce").sum(min_count=1)


def with_total_row(table, label_col, sum_cols, derived_cols=None, label="합계"):
    if table.empty:
        return table

    result = table.copy()
    total = {col: "" for col in result.columns}
    if label_col in total:
        total[label_col] = label

    for col in sum_cols:
        if col in result.columns:
            total[col] = numeric_sum(result[col])

    for col, numerator_col, denominator_col, multiplier in derived_cols or []:
        if col not in result.columns:
            continue
        numerator = total.get(numerator_col, numeric_sum(result[numerator_col]) if numerator_col in result.columns else pd.NA)
        denominator = total.get(denominator_col, numeric_sum(result[denominator_col]) if denominator_col in result.columns else pd.NA)
        total[col] = (
            numerator / denominator * multiplier
            if pd.notna(numerator) and pd.notna(denominator) and denominator != 0
            else pd.NA
        )

    return pd.concat([result, pd.DataFrame([total])], ignore_index=True)


def with_pivot_totals(table):
    if table.empty:
        return table

    result = table.copy()
    count_cols = [col for col in result.columns if "비중" not in str(col)]
    if count_cols:
        result["합계"] = result[count_cols].sum(axis=1)
        result.loc["합계", count_cols + ["합계"]] = result[count_cols + ["합계"]].sum(axis=0)
    return result


def render_dataframe_with_pinned_total(table, label_col=None, total_label="합계", **dataframe_kwargs):
    if table.empty:
        st.dataframe(table, **dataframe_kwargs)
        return

    if label_col and label_col in table.columns:
        total_mask = table[label_col].astype(str).eq(total_label)
        body = table.loc[~total_mask].copy()
        total = table.loc[total_mask].copy()
    elif total_label in table.index:
        body = table.drop(index=total_label).copy()
        total = table.loc[[total_label]].copy()
    else:
        body = table
        total = table.iloc[0:0].copy()

    st.dataframe(body, **dataframe_kwargs)
    if not total.empty:
        st.dataframe(total, **dataframe_kwargs)


def metric_value(value, suffix="", decimals=1):
    if pd.isna(value):
        return "-"
    return f"{value:,.{decimals}f}{suffix}"


def metric_delta_pct(current, previous, period_label):
    current = pd.to_numeric(pd.Series([current]), errors="coerce").iloc[0]
    previous = pd.to_numeric(pd.Series([previous]), errors="coerce").iloc[0]
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    prefix = PERIOD_DELTA_PREFIX.get(period_label, "직전대비")
    return f"{prefix} {(current - previous) / abs(previous) * 100:+,.1f}%"


def metric_delta_display(current, previous, period_label):
    current = pd.to_numeric(pd.Series([current]), errors="coerce").iloc[0]
    previous = pd.to_numeric(pd.Series([previous]), errors="coerce").iloc[0]
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    change = (current - previous) / abs(previous) * 100
    prefix = PERIOD_DELTA_PREFIX.get(period_label, "직전대비")
    if change > 0:
        return {"text": f"↑ {prefix} +{change:,.1f}%", "color": "#d93025", "bg": "#fde8e7"}
    if change < 0:
        return {"text": f"↓ {prefix} {change:,.1f}%", "color": "#1a73e8", "bg": "#e8f0fe"}
    return {"text": f"→ {prefix} +0.0%", "color": "#5f6368", "bg": "#f1f3f4"}


def render_colored_metric(column, label, value, delta=None):
    delta_html = ""
    if delta:
        delta_html = (
            f"<span style=\"display:inline-block;margin-top:0.75rem;padding:0.25rem 0.55rem;"
            f"border-radius:999px;background:{delta['bg']};color:{delta['color']};"
            f"font-size:0.95rem;font-weight:700;\">{delta['text']}</span>"
        )
    column.markdown(
        f"""
        <div style="padding:0.15rem 0 1.05rem 0;">
            <div style="font-size:1.05rem;font-weight:700;color:#31333f;margin-bottom:0.55rem;">{label}</div>
            <div style="font-size:3.05rem;line-height:1.1;font-weight:500;color:#31333f;">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def latest_previous_slices(data, date_col="기간_말일"):
    if data.empty or date_col not in data.columns:
        return data.iloc[0:0], data.iloc[0:0]
    ordered = sorted(pd.to_datetime(data[date_col], errors="coerce").dropna().unique())
    if not ordered:
        return data.iloc[0:0], data.iloc[0:0]
    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) >= 2 else None
    latest_slice = data[pd.to_datetime(data[date_col], errors="coerce").eq(latest)]
    previous_slice = (
        data[pd.to_datetime(data[date_col], errors="coerce").eq(previous)]
        if previous is not None
        else data.iloc[0:0]
    )
    return latest_slice, previous_slice


def latest_period_metric_delta(data, value_col, period_col, period_label, agg="sum"):
    if data.empty or not period_col or period_col not in data.columns or value_col not in data.columns:
        return None
    period_data = data[[period_col, value_col]].copy()
    period_data[value_col] = pd.to_numeric(period_data[value_col], errors="coerce")
    period_data = period_data[period_data[period_col].notna()]
    if period_data.empty:
        return None
    if agg == "count":
        grouped = period_data.groupby(period_col, dropna=False).size().sort_index()
    else:
        grouped = period_data.groupby(period_col, dropna=False)[value_col].sum(min_count=1).sort_index()
    if len(grouped) < 2:
        return None
    return metric_delta_pct(grouped.iloc[-1], grouped.iloc[-2], period_label)


def latest_period_avg_delta(data, numerator_col, denominator_col, period_col, period_label):
    if (
        data.empty
        or not period_col
        or period_col not in data.columns
        or numerator_col not in data.columns
        or denominator_col not in data.columns
    ):
        return None
    period_data = data[[period_col, numerator_col, denominator_col]].copy()
    period_data[numerator_col] = pd.to_numeric(period_data[numerator_col], errors="coerce")
    period_data[denominator_col] = pd.to_numeric(period_data[denominator_col], errors="coerce")
    period_data = period_data[period_data[period_col].notna()]
    if period_data.empty:
        return None
    grouped = (
        period_data.groupby(period_col, dropna=False)
        .agg(numerator=(numerator_col, "sum"), denominator=(denominator_col, "sum"))
        .sort_index()
    )
    grouped["avg"] = grouped["numerator"] / grouped["denominator"]
    grouped.loc[grouped["denominator"].le(0), "avg"] = pd.NA
    grouped = grouped[grouped["avg"].notna()]
    if len(grouped) < 2:
        return None
    return metric_delta_pct(grouped["avg"].iloc[-1], grouped["avg"].iloc[-2], period_label)


def render_metrics(container, data, period_col=None, period_label=None):
    total_orders = len(data)
    total_ships = data["최종_수주_선박수"].sum(skipna=True)
    total_amount = data["계약금액_조원"].sum(skipna=True)
    avg_price = data["계약금액_억원"].sum(skipna=True) / total_ships if total_ships else pd.NA

    with container:
        metric_cols = st.columns(4)
        metric_cols[0].metric("수주 건수", f"{total_orders:,}건")
        metric_cols[1].metric("수주 선박 수", metric_value(total_ships, "척", 0))
        metric_cols[2].metric("계약금액", metric_value(total_amount, "조원", 2))
        metric_cols[3].metric("척당 평균단가", metric_value(avg_price, "억원/척", 1))


def period_rows(start_date, end_date, period_label):
    periods = pd.period_range(start=start_date, end=end_date, freq=BACKLOG_PERIOD_FREQ[period_label])
    rows = []
    for period in periods:
        rows.append({
            "기간": str(period),
            "기간_시작일": period.start_time.normalize(),
            "기간_말일": period.end_time.normalize(),
        })
    return pd.DataFrame(rows)


def format_period_sort_values(series, period_label):
    dates = pd.to_datetime(series, errors="coerce")
    if period_label == "월별":
        return dates.dt.strftime("%Y-%m").fillna("")
    if period_label == "분기별":
        quarters = dates.dt.to_period("Q")
        return quarters.map(lambda period: f"{period.year}-{period.quarter}Q" if pd.notna(period) else "")
    return dates.dt.strftime("%Y").fillna("")


def format_period_sort_column(table, sort_col, period_label):
    if table.empty or sort_col not in table.columns:
        return table
    result = table.copy()
    result[sort_col] = format_period_sort_values(result[sort_col], period_label)
    return result


def backlog_snapshot(df, periods, selected_companies=None):
    rows = []
    for period in periods.itertuples(index=False):
        active = df[
            df["공시일_dt"].le(period.기간_말일)
            & (
                df["최종_계약기간_종료일_dt"].isna()
                | df["최종_계약기간_종료일_dt"].ge(period.기간_말일)
            )
        ]
        active = apply_hhi_merger_as_of(active, period.기간_말일)
        if selected_companies is not None:
            active = active[active["회사"].isin(selected_companies)]
        if active.empty:
            continue

        grouped = aggregate(active, ["회사", "최종_유추선종"])
        grouped.insert(0, "기간", period.기간)
        grouped.insert(1, "기간_말일", period.기간_말일)
        rows.append(grouped)

    if not rows:
        return pd.DataFrame(columns=[
            "기간",
            "기간_말일",
            "회사",
            "최종_유추선종",
            "수주건수",
            "수주_선박수",
            "계약금액_억원",
            "계약금액_조원",
            "척당_평균단가_억원",
        ])
    return pd.concat(rows, ignore_index=True)


def selection_rows(event, selection_name):
    if not event:
        return []

    selection = event.get("selection", {})
    rows = selection.get(selection_name, [])
    if isinstance(rows, list):
        return rows
    if isinstance(rows, dict) and rows:
        values = {
            key: value if isinstance(value, list) else [value]
            for key, value in rows.items()
        }
        max_len = max((len(value) for value in values.values()), default=0)
        return [
            {
                key: value[index] if index < len(value) else ""
                for key, value in values.items()
            }
            for index in range(max_len)
        ]
    return []


def apply_chart_selection(table, rows, fields):
    if not rows:
        return table, []

    selected_values = {
        tuple(str(row.get(field, "")) for field in fields)
        for row in rows
    }
    if not selected_values:
        return table, []

    filtered = table[
        table.apply(
            lambda row: tuple(str(row.get(field, "")) for field in fields) in selected_values,
            axis=1,
        )
    ]
    labels = [
        " / ".join(f"{field}: {value}" for field, value in zip(fields, values))
        for values in sorted(selected_values)
    ]
    return filtered, labels


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def runtime_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def save_json(path, data):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def secret_value(name, default=""):
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)


def visitor_id():
    if "_public_dashboard_visitor_id" not in st.session_state:
        st.session_state["_public_dashboard_visitor_id"] = uuid.uuid4().hex
    return st.session_state["_public_dashboard_visitor_id"]


def update_analytics():
    visitor = visitor_id()
    day = today_key()
    analytics = load_json(ANALYTICS_PATH, {"daily": {}})
    daily = analytics.setdefault("daily", {})
    row = daily.setdefault(day, {"page_views": 0, "visitors": []})
    row["page_views"] = int(row.get("page_views", 0)) + 1
    visitors = set(row.get("visitors", []))
    visitors.add(visitor)
    row["visitors"] = sorted(visitors)
    save_json(ANALYTICS_PATH, analytics)
    return analytics


def analytics_frame():
    analytics = load_json(ANALYTICS_PATH, {"daily": {}})
    rows = []
    for day, values in analytics.get("daily", {}).items():
        rows.append({
            "일자": day,
            "조회수": int(values.get("page_views", 0)),
            "이용자수": len(set(values.get("visitors", []))),
        })
    if not rows:
        return pd.DataFrame(columns=["일자", "조회수", "이용자수"])
    return pd.DataFrame(rows).sort_values("일자", ascending=False)


def append_request(name, category, message):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "요청ID": uuid.uuid4().hex,
        "작성일시": runtime_now(),
        "작성자": str(name).strip(),
        "구분": category,
        "내용": str(message).strip(),
        "방문자ID": visitor_id(),
    }
    append_request_to_github(row)
    row_df = pd.DataFrame([row])
    if REQUESTS_PATH.exists():
        existing = pd.read_csv(REQUESTS_PATH, dtype=str).fillna("")
        result = pd.concat([existing, row_df], ignore_index=True)
    else:
        result = row_df
    result.to_csv(REQUESTS_PATH, index=False, encoding="utf-8-sig")


def load_requests():
    requests = load_requests_from_github()
    if not REQUESTS_PATH.exists():
        local = pd.DataFrame(columns=["요청ID", "작성일시", "작성자", "구분", "내용", "방문자ID"])
    else:
        local = pd.read_csv(REQUESTS_PATH, dtype=str).fillna("")
        if "요청ID" not in local.columns:
            local["요청ID"] = ""
    combined = pd.concat([requests, local], ignore_index=True)
    if combined.empty:
        return pd.DataFrame(columns=["요청ID", "작성일시", "작성자", "구분", "내용", "방문자ID"])
    combined["요청ID"] = combined["요청ID"].where(
        combined["요청ID"].astype(str).str.strip().ne(""),
        combined.apply(
            lambda row: f"{row.get('작성일시', '')}|{row.get('작성자', '')}|{row.get('구분', '')}|{row.get('내용', '')}",
            axis=1,
        ),
    )
    return (
        combined.drop_duplicates("요청ID", keep="first")
        .sort_values("작성일시", ascending=False)
        .reset_index(drop=True)
    )


def github_request_config():
    token = secret_value("REQUESTS_GITHUB_TOKEN") or secret_value("GITHUB_TOKEN")
    repo = secret_value("REQUESTS_GITHUB_REPO") or secret_value("GITHUB_REPOSITORY")
    issue_number = str(secret_value("REQUESTS_ISSUE_NUMBER", "")).strip()
    return token, repo, issue_number


def github_requests_enabled():
    token, repo, issue_number = github_request_config()
    return bool(token and repo and issue_number)


def github_api(method, path, payload=None):
    token, repo, _ = github_request_config()
    if not token or not repo:
        raise RuntimeError("GitHub 요청 저장소 설정이 없습니다.")
    url = f"https://api.github.com/repos/{repo}{path}"
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API 오류({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"GitHub API 연결 오류: {error.reason}") from error
    return json.loads(body) if body else None


def request_comment_body(row):
    payload = {
        "요청ID": row.get("요청ID", ""),
        "작성일시": row.get("작성일시", ""),
        "작성자": row.get("작성자", ""),
        "구분": row.get("구분", ""),
        "내용": row.get("내용", ""),
        "방문자ID": row.get("방문자ID", ""),
    }
    return f"{REQUEST_COMMENT_MARKER}\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```"


def append_request_to_github(row):
    if not github_requests_enabled():
        return
    _, _, issue_number = github_request_config()
    github_api(
        "POST",
        f"/issues/{issue_number}/comments",
        {"body": request_comment_body(row)},
    )


def parse_request_comment(body):
    if REQUEST_COMMENT_MARKER not in body:
        return None
    match = re.search(r"```json\s*(\{.*?\})\s*```", body, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return {
        "요청ID": str(payload.get("요청ID", "")),
        "작성일시": str(payload.get("작성일시", "")),
        "작성자": str(payload.get("작성자", "")),
        "구분": str(payload.get("구분", "")),
        "내용": str(payload.get("내용", "")),
        "방문자ID": str(payload.get("방문자ID", "")),
    }


def load_requests_from_github():
    if not github_requests_enabled():
        return pd.DataFrame(columns=["요청ID", "작성일시", "작성자", "구분", "내용", "방문자ID"])
    _, _, issue_number = github_request_config()
    rows = []
    page = 1
    while True:
        comments = github_api(
            "GET",
            f"/issues/{issue_number}/comments?per_page=100&page={page}",
        )
        if not comments:
            break
        for comment in comments:
            parsed = parse_request_comment(str(comment.get("body", "")))
            if parsed:
                rows.append(parsed)
        if len(comments) < 100:
            break
        page += 1
    return pd.DataFrame(rows, columns=["요청ID", "작성일시", "작성자", "구분", "내용", "방문자ID"])


def admin_password():
    try:
        return st.secrets.get("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "")


analytics_snapshot = update_analytics()


if not CSV_PATH.exists():
    st.error("ship_order_summary.csv 파일이 없습니다. 공개용 데이터 CSV를 함께 배포해 주세요.")
    st.stop()

df = load_data(str(CSV_PATH), CSV_PATH.stat().st_mtime)
if TARGET_CSV_PATH.exists():
    targets = load_targets(str(TARGET_CSV_PATH), TARGET_CSV_PATH.stat().st_mtime)
else:
    targets = pd.DataFrame(columns=[
        "회사",
        "목표연도",
        "목표구분",
        "수주목표",
        "목표단위",
        "수주목표_억불",
        "공시일",
        "공시명",
        "DART_URL",
        "공시일_dt",
    ])

if MARKET_CAP_CSV_PATH.exists():
    market_cap = load_market_cap(str(MARKET_CAP_CSV_PATH), MARKET_CAP_CSV_PATH.stat().st_mtime)
else:
    market_cap = pd.DataFrame(columns=[
        "회사",
        "기준일",
        "기준일_dt",
        "시가총액_억원",
        "시가총액_조원",
    ])

st.title("조선 수주 대시보드 (By 워렌넝구)")
st.caption("2020년 1월 1일부터 수집된 내역입니다.")

with st.sidebar:
    st.header("필터")
    date_min = df["공시일_dt"].min().date()
    date_max = df["공시일_dt"].max().date()
    years = sorted(df["공시일_dt"].dt.year.dropna().astype(int).unique())
    selected_years = st.multiselect("공시연도", years, default=years)
    start_date, end_date = st.slider(
        "공시일 범위",
        min_value=date_min,
        max_value=date_max,
        value=(date_min, date_max),
        format="YYYY-MM-DD",
    )

    companies = sorted(df["회사"].dropna().unique())
    selected_companies = st.multiselect("회사", companies, default=companies)

    ship_types = sorted(
        df.loc[
            ~df["최종_유추선종"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES),
            "최종_유추선종",
        ]
        .dropna()
        .unique()
    )
    selected_ship_types = st.multiselect("선종", ship_types, default=ship_types)

    include_cancelled = st.toggle("계약해지 포함", value=False)
    show_unclassified = st.toggle("미분류 포함", value=True)

content_mask = df["최종_유추선종"].isin(selected_ship_types)
if not include_cancelled:
    content_mask &= ~df["해지여부"]
if not show_unclassified:
    content_mask &= df["최종_유추선종"].ne("미분류")

base_mask = df["회사"].isin(selected_companies) & content_mask

date_mask = (
    df["공시일_dt"].dt.year.isin(selected_years)
    & df["공시일_dt"].dt.date.ge(start_date)
    & df["공시일_dt"].dt.date.le(end_date)
)

mask = (
    base_mask
    & date_mask
)

analysis_base_mask = base_mask & ~df["최종_유추선종"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES)
analysis_mask = analysis_base_mask & date_mask

raw_view = df.loc[mask].copy()
view = df.loc[analysis_mask].copy()
overview_company_mask = company_mask_with_hhi_merger(df, "공시일_dt", selected_companies)
overview_analysis_mask = content_mask & overview_company_mask & date_mask & ~df["최종_유추선종"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES)
overview_view = apply_hhi_merger_by_date(df.loc[overview_analysis_mask].copy(), "공시일_dt")
delivery_company_mask = company_mask_with_hhi_merger(df, "최종_계약기간_종료일_dt", selected_companies)
delivery_analysis_mask = content_mask & delivery_company_mask & date_mask & ~df["최종_유추선종"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES)
delivery_overview_view = apply_hhi_merger_by_date(df.loc[delivery_analysis_mask].copy(), "최종_계약기간_종료일_dt")
backlog_base = df.loc[content_mask & ~df["최종_유추선종"].isin(ANALYSIS_EXCLUDED_SHIP_TYPES)].copy()

metric_slot = st.container()

period_label = st.segmented_control(
    "집계 단위",
    options=list(PERIOD_OPTIONS.keys()),
    default="분기별",
)
period_col, period_sort_col = PERIOD_OPTIONS[period_label]
backlog_start_date = pd.Timestamp(start_date).normalize()
backlog_kpi_end_date = pd.Timestamp(end_date).normalize()
backlog_end_date = pd.Timestamp(end_date).normalize() + pd.DateOffset(years=BACKLOG_HORIZON_YEARS)
selected_periods = period_rows(backlog_start_date.date(), backlog_end_date.date(), period_label)
kpi_periods = period_rows(backlog_start_date.date(), backlog_kpi_end_date.date(), period_label)

summary = aggregate(overview_view, [period_sort_col, period_col, "회사", "최종_유추선종"])
summary = summary.sort_values([period_sort_col, "회사", "최종_유추선종"])

tab_overview, tab_backlog, tab_target, tab_ship_type, tab_price, tab_table, tab_request, tab_admin = st.tabs(
    ["수주 추이", "수주잔고", "목표 대비", "회사·선종", "척당 단가", "원자료", "요청", "관리자"]
)

with tab_overview:
    period_company = aggregate(overview_view, [period_sort_col, period_col, "회사"]).sort_values(period_sort_col)
    period_ship_type = aggregate(overview_view, [period_sort_col, period_col, "최종_유추선종"]).sort_values(period_sort_col)
    period_total = aggregate(overview_view, [period_sort_col, period_col]).sort_values(period_sort_col)
    delivery_period_col = f"인도{period_col}"
    delivery_period_sort_col = f"인도{period_sort_col}"
    delivery_view = delivery_overview_view[delivery_overview_view["최종_계약기간_종료일_dt"].notna()].copy()
    delivery_company = (
        aggregate(delivery_view, [delivery_period_sort_col, delivery_period_col, "회사"])
        .sort_values([delivery_period_sort_col, "회사"])
        if not delivery_view.empty
        else pd.DataFrame(columns=[delivery_period_sort_col, delivery_period_col, "회사", "수주건수", "수주_선박수", "계약금액_억원", "계약금액_억불", "계약금액_조원"])
    )
    delivery_total = (
        aggregate(delivery_view, [delivery_period_sort_col, delivery_period_col])
        .sort_values(delivery_period_sort_col)
        if not delivery_view.empty
        else pd.DataFrame(columns=[delivery_period_sort_col, delivery_period_col, "수주건수", "수주_선박수", "계약금액_억원", "계약금액_억불", "계약금액_조원"])
    )
    period_company = format_period_sort_column(period_company, period_sort_col, period_label)
    period_ship_type = format_period_sort_column(period_ship_type, period_sort_col, period_label)
    period_total = format_period_sort_column(period_total, period_sort_col, period_label)
    delivery_company = format_period_sort_column(delivery_company, delivery_period_sort_col, period_label)
    delivery_total = format_period_sort_column(delivery_total, delivery_period_sort_col, period_label)

    control_left, control_right = st.columns([1.1, 1])
    with control_left:
        company_select_mode = st.segmented_control(
            "회사 차트 선택 기준",
            options=["기간 전체", "회사별 조각"],
            default="회사별 조각",
            key=f"company_select_mode_{period_label}",
        )
    with control_right:
        delivery_metric = st.segmented_control(
            "인도 차트 지표",
            options=["선박수", "계약금액"],
            default="선박수",
            key=f"delivery_metric_{period_label}",
        )

    company_select_fields = [period_col] if company_select_mode == "기간 전체" else [period_col, "회사"]
    delivery_select_fields = [delivery_period_col] if company_select_mode == "기간 전체" else [delivery_period_col, "회사"]
    amount_select = alt.selection_point(name="trend_amount_select", fields=company_select_fields, toggle=True)
    delivery_select = alt.selection_point(name="trend_delivery_select", fields=delivery_select_fields, toggle=True)
    left, right = st.columns([1.1, 1])

    with left:
        st.markdown("**기간별 수주금액 차트**")
        amount_base = (
            alt.Chart(period_company)
            .mark_bar()
            .encode(
                x=alt.X(f"{period_col}:N", sort=period_company[period_col].drop_duplicates().tolist(), title=period_label),
                y=alt.Y("계약금액_조원:Q", title="계약금액(조원)"),
                color=alt.Color("회사:N", title="회사"),
                opacity=alt.condition(amount_select, alt.value(1), alt.value(0.35)),
                tooltip=["회사", period_col, "수주건수", "수주_선박수", alt.Tooltip("계약금액_조원:Q", format=",.2f")],
            )
        )
        if company_select_mode == "기간 전체":
            amount_hitbox = (
                alt.Chart(period_total)
                .mark_bar(opacity=0.001)
                .encode(
                    x=alt.X(f"{period_col}:N", sort=period_total[period_col].drop_duplicates().tolist(), title=period_label),
                    y=alt.Y("계약금액_조원:Q"),
                    tooltip=[period_col, alt.Tooltip("계약금액_조원:Q", format=",.2f")],
                )
                .add_params(amount_select)
            )
            amount_chart = alt.layer(amount_base, amount_hitbox).properties(height=360)
        else:
            amount_chart = amount_base.add_params(amount_select).properties(height=360)

        amount_event = st.altair_chart(
            amount_chart,
            width="stretch",
            key=f"trend_amount_{period_label}",
            on_select="rerun",
            selection_mode="trend_amount_select",
        )

    with right:
        st.markdown("**기간별 인도 차트**")
        delivery_y_col = "수주_선박수" if delivery_metric == "선박수" else "계약금액_조원"
        delivery_y_title = "인도 선박 수(척)" if delivery_metric == "선박수" else "인도 계약금액(조원)"
        delivery_base = (
            alt.Chart(delivery_company)
            .mark_bar()
            .encode(
                x=alt.X(
                    f"{delivery_period_col}:N",
                    sort=delivery_company[delivery_period_col].drop_duplicates().tolist(),
                    title=f"인도 {period_label}",
                ),
                y=alt.Y(f"{delivery_y_col}:Q", title=delivery_y_title),
                color=alt.Color("회사:N", title="회사"),
                opacity=alt.condition(delivery_select, alt.value(1), alt.value(0.35)),
                tooltip=[
                    delivery_period_col,
                    "회사",
                    alt.Tooltip("수주건수:Q", title="계약건수", format=",.0f"),
                    alt.Tooltip("수주_선박수:Q", title="인도 선박 수", format=",.0f"),
                    alt.Tooltip("계약금액_조원:Q", title="인도 계약금액(조원)", format=",.2f"),
                ],
            )
        )
        if company_select_mode == "기간 전체":
            delivery_hitbox = (
                alt.Chart(delivery_total)
                .mark_bar(opacity=0.001)
                .encode(
                    x=alt.X(
                        f"{delivery_period_col}:N",
                        sort=delivery_total[delivery_period_col].drop_duplicates().tolist(),
                        title=f"인도 {period_label}",
                    ),
                    y=alt.Y(f"{delivery_y_col}:Q"),
                    tooltip=[
                        delivery_period_col,
                        alt.Tooltip("수주_선박수:Q", title="인도 선박 수", format=",.0f"),
                        alt.Tooltip("계약금액_조원:Q", title="인도 계약금액(조원)", format=",.2f"),
                    ],
                )
                .add_params(delivery_select)
            )
            delivery_chart = alt.layer(delivery_base, delivery_hitbox).properties(height=360)
        else:
            delivery_chart = delivery_base.add_params(delivery_select).properties(height=360)
        delivery_event = st.altair_chart(
            delivery_chart,
            width="stretch",
            key=f"trend_delivery_{period_label}_{delivery_metric}",
            on_select="rerun",
            selection_mode="trend_delivery_select",
        )

    ship_type_select_mode = st.segmented_control(
        "선종 차트 선택 기준",
        options=["기간 전체", "선종별 조각"],
        default="선종별 조각",
        key=f"ship_type_select_mode_{period_label}",
    )
    ship_type_select_fields = [period_col] if ship_type_select_mode == "기간 전체" else [period_col, "최종_유추선종"]
    ship_type_select = alt.selection_point(name="trend_type_select", fields=ship_type_select_fields, toggle=True)
    ship_type_base = (
        alt.Chart(period_ship_type)
        .mark_bar()
        .encode(
            x=alt.X(f"{period_col}:N", sort=period_ship_type[period_col].drop_duplicates().tolist(), title=period_label),
            y=alt.Y("계약금액_조원:Q", title="계약금액(조원)"),
            color=alt.Color("최종_유추선종:N", title="선종"),
            opacity=alt.condition(ship_type_select, alt.value(1), alt.value(0.35)),
            tooltip=[
                period_col,
                alt.Tooltip("최종_유추선종:N", title="선종"),
                "수주건수",
                "수주_선박수",
                alt.Tooltip("계약금액_조원:Q", format=",.2f"),
            ],
        )
    )
    if ship_type_select_mode == "기간 전체":
        ship_type_hitbox = (
            alt.Chart(period_total)
            .mark_bar(opacity=0.001)
            .encode(
                x=alt.X(f"{period_col}:N", sort=period_total[period_col].drop_duplicates().tolist(), title=period_label),
                y=alt.Y("계약금액_조원:Q"),
                tooltip=[period_col, alt.Tooltip("계약금액_조원:Q", format=",.2f")],
            )
            .add_params(ship_type_select)
        )
        ship_type_amount_chart = alt.layer(ship_type_base, ship_type_hitbox).properties(height=360)
    else:
        ship_type_amount_chart = ship_type_base.add_params(ship_type_select).properties(height=360)

    ship_type_event = st.altair_chart(
        ship_type_amount_chart,
        width="stretch",
        key=f"trend_type_{period_label}",
        on_select="rerun",
        selection_mode="trend_type_select",
    )

    selected_summary = summary.copy()
    selected_metric_view = overview_view.copy()
    selected_delivery_metric_view = delivery_overview_view.copy()
    active_labels = []
    for event, selection_name, fields in [
        (amount_event, "trend_amount_select", company_select_fields),
        (ship_type_event, "trend_type_select", ship_type_select_fields),
    ]:
        rows = selection_rows(event, selection_name)
        selected_summary, labels = apply_chart_selection(selected_summary, rows, fields)
        selected_metric_view, _ = apply_chart_selection(selected_metric_view, rows, fields)
        selected_delivery_metric_view, _ = apply_chart_selection(selected_delivery_metric_view, rows, fields)
        active_labels.extend(labels)

    delivery_rows = selection_rows(delivery_event, "trend_delivery_select")
    if delivery_rows:
        selected_metric_view, delivery_labels = apply_chart_selection(
            selected_delivery_metric_view,
            delivery_rows,
            delivery_select_fields,
        )
        if delivery_labels:
            active_labels.extend([f"인도 {label}" for label in delivery_labels])
        selected_summary = aggregate(
            selected_metric_view,
            [period_sort_col, period_col, "회사", "최종_유추선종"],
        ).sort_values([period_sort_col, "회사", "최종_유추선종"])

    if active_labels:
        st.caption("선택: " + " | ".join(active_labels))

    render_metrics(metric_slot, selected_metric_view, period_sort_col, period_label)

    overview_table = selected_summary[
        [period_col, "회사", "최종_유추선종", "수주건수", "수주_선박수", "계약금액_억원", "척당_평균단가_억원"]
    ]
    overview_table = with_total_row(
        overview_table,
        period_col,
        ["수주건수", "수주_선박수", "계약금액_억원"],
        [("척당_평균단가_억원", "계약금액_억원", "수주_선박수", 1)],
    )
    render_dataframe_with_pinned_total(
        overview_table,
        label_col=period_col,
        width="stretch",
        hide_index=True,
        column_config={
            "최종_유추선종": "선종",
            "계약금액_억원": st.column_config.NumberColumn("계약금액(억원)", format="%.1f"),
            "척당_평균단가_억원": st.column_config.NumberColumn("척당 평균단가(억원)", format="%.1f"),
        },
    )

with tab_backlog:
    backlog = backlog_snapshot(backlog_base, selected_periods, selected_companies)
    backlog_kpi = backlog_snapshot(backlog_base, kpi_periods, selected_companies)
    st.caption(
        f"수주잔고는 공시일 범위 시작일 {backlog_start_date.date()}부터 "
        f"종료일+{BACKLOG_HORIZON_YEARS}년 {backlog_end_date.date()}까지 각 {period_label} 기간말 기준으로 계산합니다."
    )
    if backlog.empty:
        st.warning("선택한 조건에 해당하는 수주잔고가 없습니다.")
    else:
        latest_backlog, previous_backlog = latest_previous_slices(backlog_kpi)
        latest_ships = latest_backlog["수주_선박수"].sum()
        previous_ships = previous_backlog["수주_선박수"].sum() if not previous_backlog.empty else pd.NA
        latest_amount = latest_backlog["계약금액_조원"].sum()
        previous_amount = previous_backlog["계약금액_조원"].sum() if not previous_backlog.empty else pd.NA
        latest_contracts = latest_backlog["수주건수"].sum()
        previous_contracts = previous_backlog["수주건수"].sum() if not previous_backlog.empty else pd.NA
        backlog_cols = st.columns(3)
        render_colored_metric(
            backlog_cols[0],
            "최근 기준 잔고 선박 수",
            metric_value(latest_ships, "척", 0),
            metric_delta_display(latest_ships, previous_ships, period_label),
        )
        render_colored_metric(
            backlog_cols[1],
            "최근 기준 잔고 금액",
            metric_value(latest_amount, "조원", 2),
            metric_delta_display(latest_amount, previous_amount, period_label),
        )
        render_colored_metric(
            backlog_cols[2],
            "최근 기준 잔고 계약 수",
            f"{latest_contracts:,.0f}건",
            metric_delta_display(latest_contracts, previous_contracts, period_label),
        )

        backlog_company = (
            backlog.groupby(["기간", "기간_말일", "회사"], dropna=False)
            .agg(
                잔고_계약수=("수주건수", "sum"),
                잔고_선박수=("수주_선박수", "sum"),
                잔고_계약금액_조원=("계약금액_조원", "sum"),
            )
            .reset_index()
            .sort_values("기간_말일")
        )

        backlog_company_select = alt.selection_point(
            name="backlog_company_select",
            fields=["회사"],
            toggle=True,
        )
        backlog_metric = st.segmented_control(
            "잔고 차트 지표",
            options=["선박수", "계약금액"],
            default="계약금액",
            key=f"backlog_metric_{period_label}",
        )
        backlog_y_col = "잔고_선박수" if backlog_metric == "선박수" else "잔고_계약금액_조원"
        backlog_y_title = "수주잔고 선박 수(척)" if backlog_metric == "선박수" else "수주잔고 금액(조원)"
        st.markdown("**기간별 수주잔고 차트**")
        backlog_company_chart = (
            alt.Chart(backlog_company)
            .mark_line(point=True)
            .encode(
                x=alt.X("기간:N", sort=backlog_company["기간"].drop_duplicates().tolist(), title=period_label),
                y=alt.Y(f"{backlog_y_col}:Q", title=backlog_y_title),
                color=alt.Color("회사:N", title="회사"),
                opacity=alt.condition(backlog_company_select, alt.value(1), alt.value(0.35)),
                tooltip=[
                    "기간",
                    "회사",
                    alt.Tooltip("잔고_계약수:Q", title="잔고 계약 수", format=",.0f"),
                    alt.Tooltip("잔고_선박수:Q", title="잔고 선박 수", format=",.0f"),
                    alt.Tooltip("잔고_계약금액_조원:Q", title="잔고 계약금액(조원)", format=",.2f"),
                ],
            )
            .add_params(backlog_company_select)
            .properties(height=360)
        )
        backlog_company_event = st.altair_chart(
            backlog_company_chart,
            width="stretch",
            key=f"backlog_company_{period_label}_{backlog_metric}",
            on_select="rerun",
            selection_mode="backlog_company_select",
        )

        selected_backlog = backlog.copy()
        selected_backlog_labels = []
        selected_backlog, selected_backlog_labels = apply_chart_selection(
            selected_backlog,
            selection_rows(backlog_company_event, "backlog_company_select"),
            ["회사"],
        )

        if selected_backlog_labels:
            st.caption("선택: " + " | ".join(selected_backlog_labels))

        backlog_ship_type = (
            selected_backlog.groupby(["기간", "기간_말일", "최종_유추선종"], dropna=False)
            .agg(
                잔고_계약수=("수주건수", "sum"),
                잔고_선박수=("수주_선박수", "sum"),
                잔고_계약금액_조원=("계약금액_조원", "sum"),
            )
            .reset_index()
            .sort_values("기간_말일")
        )
        period_amount_total = backlog_ship_type.groupby("기간")["잔고_계약금액_조원"].transform("sum")
        period_ship_total = backlog_ship_type.groupby("기간")["잔고_선박수"].transform("sum")
        backlog_ship_type["선종_금액비중"] = backlog_ship_type["잔고_계약금액_조원"] / period_amount_total * 100
        backlog_ship_type["선종_선박수비중"] = backlog_ship_type["잔고_선박수"] / period_ship_total * 100
        backlog_ship_type.loc[period_amount_total.le(0), "선종_금액비중"] = pd.NA
        backlog_ship_type.loc[period_ship_total.le(0), "선종_선박수비중"] = pd.NA

        backlog_ship_type_chart = (
            alt.Chart(backlog_ship_type)
            .mark_area()
            .encode(
                x=alt.X("기간:N", sort=backlog_ship_type["기간"].drop_duplicates().tolist(), title=period_label),
                y=alt.Y("잔고_계약금액_조원:Q", stack="zero", title="선종별 수주잔고 금액(조원)"),
                color=alt.Color("최종_유추선종:N", title="선종"),
                tooltip=[
                    "기간",
                    alt.Tooltip("최종_유추선종:N", title="선종"),
                    alt.Tooltip("잔고_계약수:Q", format=",.0f"),
                    alt.Tooltip("잔고_선박수:Q", format=",.0f"),
                    alt.Tooltip("잔고_계약금액_조원:Q", format=",.2f"),
                    alt.Tooltip("선종_금액비중:Q", title="금액 비중(%)", format=",.1f"),
                    alt.Tooltip("선종_선박수비중:Q", title="선박 수 비중(%)", format=",.1f"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(backlog_ship_type_chart, width="stretch")

        st.markdown("**수주잔고 대비 시가총액**")
        if market_cap.empty:
            st.info("ship_market_cap.csv 파일이 없어 시가총액 배율 차트를 표시하지 못했습니다. 파일 형식은 회사, 기준일, 시가총액_억원 컬럼을 기준으로 합니다.")
        else:
            selected_backlog_company = (
                selected_backlog.groupby(["기간", "기간_말일", "회사"], dropna=False)
                .agg(
                    잔고_계약수=("수주건수", "sum"),
                    잔고_선박수=("수주_선박수", "sum"),
                    잔고_계약금액_조원=("계약금액_조원", "sum"),
                )
                .reset_index()
                .sort_values("기간_말일")
            )
            selected_backlog_company = selected_backlog_company.merge(
                selected_periods[["기간", "기간_시작일"]],
                on="기간",
                how="left",
            )
            market_cap_compare = attach_market_cap_asof(selected_backlog_company, market_cap)
            latest_market_cap_date = pd.to_datetime(market_cap["기준일_dt"], errors="coerce").max()
            market_cap_compare["기간_시작일"] = pd.to_datetime(
                market_cap_compare["기간_시작일"], errors="coerce"
            )
            market_cap_compare = market_cap_compare[
                market_cap_compare["기간_시작일"].ge(MARKET_CAP_BACKLOG_START_DATE)
                & market_cap_compare["기간_시작일"].le(latest_market_cap_date)
            ].copy()
            market_cap_compare["시총_기준일"] = pd.to_datetime(
                market_cap_compare["기준일_dt"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")

            if market_cap_compare.empty:
                st.info("선택한 기간과 회사에 맞는 시가총액 데이터가 없습니다.")
            else:
                latest_market_cap_compare, previous_market_cap_compare = latest_previous_slices(market_cap_compare)
                latest_total_market_cap = latest_market_cap_compare["시가총액_조원"].sum(skipna=True)
                previous_total_market_cap = (
                    previous_market_cap_compare["시가총액_조원"].sum(skipna=True)
                    if not previous_market_cap_compare.empty
                    else pd.NA
                )
                latest_total_backlog = latest_market_cap_compare["잔고_계약금액_조원"].sum(skipna=True)
                previous_total_backlog = (
                    previous_market_cap_compare["잔고_계약금액_조원"].sum(skipna=True)
                    if not previous_market_cap_compare.empty
                    else pd.NA
                )
                latest_ratio = latest_total_market_cap / latest_total_backlog if latest_total_backlog else pd.NA
                previous_ratio = (
                    previous_total_market_cap / previous_total_backlog
                    if not pd.isna(previous_total_backlog) and previous_total_backlog
                    else pd.NA
                )
                ratio_cols = st.columns(3)
                render_colored_metric(
                    ratio_cols[0],
                    "최근 기준 시가총액",
                    metric_value(latest_total_market_cap, "조원", 2),
                    metric_delta_display(latest_total_market_cap, previous_total_market_cap, period_label),
                )
                render_colored_metric(
                    ratio_cols[1],
                    "최근 기준 수주잔고",
                    metric_value(latest_total_backlog, "조원", 2),
                    metric_delta_display(latest_total_backlog, previous_total_backlog, period_label),
                )
                render_colored_metric(
                    ratio_cols[2],
                    "시총 / 수주잔고",
                    metric_value(latest_ratio, "배", 2),
                    metric_delta_display(latest_ratio, previous_ratio, period_label),
                )

                market_cap_period_order = market_cap_compare["기간"].drop_duplicates().tolist()
                market_cap_chart = (
                    alt.Chart(market_cap_compare)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("기간:N", sort=market_cap_period_order, title=period_label),
                        y=alt.Y("시가총액_수주잔고배율:Q", title="시가총액 / 수주잔고(배)"),
                        color=alt.Color("회사:N", title="회사"),
                        tooltip=[
                            "기간",
                            "회사",
                            alt.Tooltip("시총_기준일:N", title="시총 기준일"),
                            alt.Tooltip("시가총액_조원:Q", title="시가총액(조원)", format=",.2f"),
                            alt.Tooltip("잔고_계약금액_조원:Q", title="수주잔고(조원)", format=",.2f"),
                            alt.Tooltip("시가총액_수주잔고배율:Q", title="시총/수주잔고(배)", format=",.2f"),
                        ],
                    )
                    .properties(height=320)
                )
                st.altair_chart(market_cap_chart, width="stretch")

        backlog_table = selected_backlog.sort_values(["기간_말일", "회사", "최종_유추선종"])[
            ["기간", "회사", "최종_유추선종", "수주건수", "수주_선박수", "계약금액_억원", "계약금액_조원"]
        ]
        st.dataframe(
            backlog_table,
            width="stretch",
            hide_index=True,
            column_config={
                "최종_유추선종": "선종",
                "수주건수": "잔고 계약 수",
                "수주_선박수": st.column_config.NumberColumn("잔고 선박 수", format="%.0f"),
                "계약금액_억원": st.column_config.NumberColumn("잔고 계약금액(억원)", format="%.1f"),
                "계약금액_조원": st.column_config.NumberColumn("잔고 계약금액(조원)", format="%.2f"),
            },
        )

with tab_target:
    st.caption("공시 수주목표는 DART 전망 공시에서 가져오고, 실적은 계약별 공시 환율로 억불 환산한 값입니다.")

    actual_source = view.copy()
    target_disclosure_dates = targets["공시일_dt"].dt.date
    target_rows = targets[
        targets["회사"].isin(selected_companies)
        & targets["목표연도"].isin([str(year) for year in selected_years])
        & target_disclosure_dates.ge(start_date)
        & target_disclosure_dates.le(end_date)
    ].copy()

    comparison_rows = []
    for target in target_rows.itertuples(index=False):
        actual = actual_source[
            actual_source["회사"].eq(target.회사)
            & actual_source["연도"].eq(str(target.목표연도))
        ]
        if target.목표구분 not in ("조선·해양", "합계", "전체"):
            actual = actual[actual["목표구분"].eq(target.목표구분)]

        actual_usd = actual["계약금액_억불"].sum(skipna=True)
        target_usd = target.수주목표_억불
        achievement = actual_usd / target_usd * 100 if pd.notna(target_usd) and target_usd else pd.NA
        comparison_rows.append({
            "연도": str(target.목표연도),
            "회사": target.회사,
            "기준유형": "공시 수주목표",
            "목표구분": target.목표구분,
            "기준_억불": target_usd,
            "실적_억불": actual_usd,
            "달성률": achievement,
            "수주건수": len(actual),
            "수주_선박수": actual["최종_수주_선박수"].sum(skipna=True),
            "실적_계약금액_억원": actual["계약금액_억원"].sum(skipna=True),
            "환율누락_계약금액_억원": actual.loc[actual["계약금액_억불"].isna(), "계약금액_억원"].sum(skipna=True),
            "목표원문": target.수주목표,
            "목표단위": target.목표단위,
            "목표공시일": target.공시일,
            "목표공시_URL": target.DART_URL,
        })

    yearly_actual = (
        actual_source.groupby(["회사", "연도"], dropna=False)
        .agg(
            실적_억불=("계약금액_억불", "sum"),
            실적_계약금액_억원=("계약금액_억원", "sum"),
            수주건수=("공시일", "size"),
            수주_선박수=("최종_수주_선박수", "sum"),
            환율누락_계약금액_억원=("계약금액_억불", lambda value: actual_source.loc[value.index[value.isna()], "계약금액_억원"].sum()),
        )
        .reset_index()
        .sort_values(["회사", "연도"])
    )
    for company in sorted(NO_TARGET_COMPANIES & set(selected_companies)):
        company_actual = yearly_actual[yearly_actual["회사"].eq(company)].copy()
        company_actual["기준_억불"] = company_actual["실적_억불"].shift(1)
        for row in company_actual.itertuples(index=False):
            if str(row.연도) not in [str(year) for year in selected_years]:
                continue
            comparison_rows.append({
                "연도": str(row.연도),
                "회사": row.회사,
                "기준유형": "전년도 수주실적",
                "목표구분": "전체",
                "기준_억불": row.기준_억불,
                "실적_억불": row.실적_억불,
                "달성률": row.실적_억불 / row.기준_억불 * 100 if pd.notna(row.기준_억불) and row.기준_억불 else pd.NA,
                "수주건수": row.수주건수,
                "수주_선박수": row.수주_선박수,
                "실적_계약금액_억원": row.실적_계약금액_억원,
                "환율누락_계약금액_억원": row.환율누락_계약금액_억원,
                "목표원문": "",
                "목표단위": "억불",
                "목표공시일": "",
                "목표공시_URL": "",
            })

    comparison = pd.DataFrame(comparison_rows)
    if comparison.empty:
        st.warning("선택한 조건에 해당하는 수주목표 또는 전년도 비교 데이터가 없습니다. 공개용 CSV가 갱신되면 반영됩니다.")
    else:
        totals = (
            comparison.groupby(["연도", "회사", "기준유형"], dropna=False)
            .agg(
                기준_억불=("기준_억불", lambda value: value.sum(min_count=1)),
                실적_억불=("실적_억불", lambda value: value.sum(min_count=1)),
                수주건수=("수주건수", "sum"),
                수주_선박수=("수주_선박수", "sum"),
            )
            .reset_index()
        )
        totals["달성률"] = totals["실적_억불"] / totals["기준_억불"] * 100
        totals["달성률_label"] = totals["달성률"].map(lambda value: f"{value:,.0f}%" if pd.notna(value) else "")
        totals = totals.sort_values(["연도", "회사"])
        year_order = totals["연도"].drop_duplicates().tolist()
        company_order = [company for company in selected_companies if company in set(totals["회사"])]

        target_bars = (
            alt.Chart(totals)
            .mark_bar(opacity=0.75)
            .encode(
                x=alt.X("연도:N", sort=year_order, title="연도"),
                xOffset=alt.XOffset("회사:N", sort=company_order),
                y=alt.Y("기준_억불:Q", title="수주목표/실적(억불)"),
                color=alt.Color("회사:N", sort=company_order, title="회사"),
                tooltip=[
                    "연도",
                    "회사",
                    "기준유형",
                    alt.Tooltip("기준_억불:Q", title="목표/전년(억불)", format=",.2f"),
                    alt.Tooltip("실적_억불:Q", title="수주실적(억불)", format=",.2f"),
                    alt.Tooltip("달성률:Q", title="달성률(%)", format=",.1f"),
                ],
            )
        )

        actual_points = (
            alt.Chart(totals)
            .mark_point(
                shape="diamond",
                filled=True,
                size=170,
                color="#FFD166",
                stroke="#111827",
                strokeWidth=1.8,
            )
            .encode(
                x=alt.X("연도:N", sort=year_order, title="연도"),
                xOffset=alt.XOffset("회사:N", sort=company_order),
                y=alt.Y("실적_억불:Q"),
                tooltip=[
                    "연도",
                    "회사",
                    "기준유형",
                    alt.Tooltip("기준_억불:Q", title="목표/전년(억불)", format=",.2f"),
                    alt.Tooltip("실적_억불:Q", title="수주실적(억불)", format=",.2f"),
                    alt.Tooltip("달성률:Q", title="달성률(%)", format=",.1f"),
                ],
            )
        )

        achievement_label_outline = (
            alt.Chart(totals[totals["달성률_label"].ne("")])
            .mark_text(
                dy=-15,
                fontSize=11,
                fontWeight="bold",
                color="#111827",
                stroke="white",
                strokeWidth=3,
            )
            .encode(
                x=alt.X("연도:N", sort=year_order, title="연도"),
                xOffset=alt.XOffset("회사:N", sort=company_order),
                y=alt.Y("실적_억불:Q"),
                text=alt.Text("달성률_label:N"),
            )
        )
        achievement_labels = (
            alt.Chart(totals[totals["달성률_label"].ne("")])
            .mark_text(dy=-15, fontSize=11, fontWeight="bold", color="#111827")
            .encode(
                x=alt.X("연도:N", sort=year_order, title="연도"),
                xOffset=alt.XOffset("회사:N", sort=company_order),
                y=alt.Y("실적_억불:Q"),
                text=alt.Text("달성률_label:N"),
            )
        )

        target_chart = alt.layer(target_bars, actual_points, achievement_label_outline, achievement_labels).properties(height=460)
        st.altair_chart(target_chart, width="stretch")

        comparison_table = comparison.sort_values(["연도", "회사", "목표구분"], ascending=[False, True, True])
        comparison_table = with_total_row(
            comparison_table,
            "연도",
            [
                "기준_억불",
                "실적_억불",
                "수주건수",
                "수주_선박수",
                "실적_계약금액_억원",
                "환율누락_계약금액_억원",
            ],
            [("달성률", "실적_억불", "기준_억불", 100)],
        )
        render_dataframe_with_pinned_total(
            comparison_table,
            label_col="연도",
            width="stretch",
            hide_index=True,
            column_config={
                "기준_억불": st.column_config.NumberColumn("목표/전년(억불)", format="%.2f"),
                "실적_억불": st.column_config.NumberColumn("수주실적(억불)", format="%.2f"),
                "달성률": st.column_config.NumberColumn("달성률(%)", format="%.1f"),
                "수주_선박수": st.column_config.NumberColumn("수주 선박 수", format="%.0f"),
                "실적_계약금액_억원": st.column_config.NumberColumn("실적 계약금액(억원)", format="%.1f"),
                "환율누락_계약금액_억원": st.column_config.NumberColumn("환율누락 금액(억원)", format="%.1f"),
                "목표공시_URL": st.column_config.LinkColumn("목표 공시"),
            },
        )

with tab_ship_type:
    type_summary = aggregate(view, ["회사", "최종_유추선종"]).sort_values("계약금액_억원", ascending=False)
    company_amount_total = type_summary.groupby("회사")["계약금액_억원"].transform("sum")
    company_ship_total = type_summary.groupby("회사")["수주_선박수"].transform("sum")
    type_summary["회사내_계약금액비중"] = type_summary["계약금액_억원"] / company_amount_total * 100
    type_summary["회사내_선박수비중"] = type_summary["수주_선박수"] / company_ship_total * 100
    type_summary.loc[company_amount_total.le(0), "회사내_계약금액비중"] = pd.NA
    type_summary.loc[company_ship_total.le(0), "회사내_선박수비중"] = pd.NA
    left, right = st.columns([1.1, 1])

    with left:
        type_chart = (
            alt.Chart(type_summary)
            .mark_bar()
            .encode(
                x=alt.X("계약금액_억원:Q", title="계약금액(억원)"),
                y=alt.Y("최종_유추선종:N", sort="-x", title="선종"),
                color=alt.Color("회사:N", title="회사"),
                tooltip=[
                    "회사",
                    alt.Tooltip("최종_유추선종:N", title="선종"),
                    alt.Tooltip("회사내_계약금액비중:Q", title="선종 비중(금액)", format=",.1f"),
                    alt.Tooltip("회사내_선박수비중:Q", title="선종 비중(선박 수)", format=",.1f"),
                    "수주건수",
                    "수주_선박수",
                    alt.Tooltip("계약금액_억원:Q", format=",.1f"),
                ],
            )
            .properties(height=420)
        )
        st.altair_chart(type_chart, width="stretch")

    with right:
        ship_mix = type_summary.pivot_table(
            index="최종_유추선종",
            columns="회사",
            values="수주_선박수",
            aggfunc="sum",
            fill_value=0,
        )
        ship_ratio_mix = type_summary.pivot_table(
            index="최종_유추선종",
            columns="회사",
            values="회사내_선박수비중",
            aggfunc="sum",
            fill_value=0,
        )

        display_mix = ship_mix.copy().astype(object)
        for row_label in ship_mix.index:
            for company in ship_mix.columns:
                count = ship_mix.loc[row_label, company]
                ratio = ship_ratio_mix.loc[row_label, company]
                display_mix.loc[row_label, company] = f"{count:,.0f} ({ratio:,.1f}%)" if count else ""

        display_mix["합계"] = ship_mix.sum(axis=1).map(lambda value: f"{value:,.0f}")
        total_row = {}
        for company in ship_mix.columns:
            total_count = ship_mix[company].sum()
            total_row[company] = f"{total_count:,.0f} (100.0%)" if total_count else ""
        total_row["합계"] = f"{ship_mix.to_numpy().sum():,.0f}"
        display_mix.loc["합계"] = total_row

        render_dataframe_with_pinned_total(display_mix, width="stretch")

with tab_price:
    unit_price = aggregate(view, [period_sort_col, period_col, "최종_유추선종"])
    unit_price = unit_price.dropna(subset=["척당_평균단가_억원"]).sort_values(period_sort_col)

    price_session_key = f"price_selected_ship_types_{period_label}"
    price_reset_key = f"{price_session_key}_reset"
    selected_price_ship_types = st.session_state.get(price_session_key, [])

    control_cols = st.columns([1, 4])
    with control_cols[0]:
        if st.button(
            "전체 선종 보기",
            key=f"price_reset_button_{period_label}",
            disabled=not selected_price_ship_types,
            width="stretch",
        ):
            st.session_state[price_session_key] = []
            st.session_state[price_reset_key] = st.session_state.get(price_reset_key, 0) + 1
            st.rerun()
    with control_cols[1]:
        if selected_price_ship_types:
            st.caption("선택: " + " | ".join(selected_price_ship_types))
        else:
            st.caption("전체 선종 표시 중")

    selected_price = (
        unit_price[unit_price["최종_유추선종"].isin(selected_price_ship_types)].copy()
        if selected_price_ship_types
        else unit_price.copy()
    )
    unit_price = format_period_sort_column(unit_price, period_sort_col, period_label)
    selected_price = format_period_sort_column(selected_price, period_sort_col, period_label)
    period_order = unit_price[period_col].drop_duplicates().tolist()
    price_ship_select = alt.selection_point(
        name="price_ship_select",
        fields=["최종_유추선종"],
        toggle="true",
        on="click",
    )

    price_visible = (
        alt.Chart(selected_price)
        .mark_line(point=True, strokeWidth=3 if selected_price_ship_types else 2)
        .encode(
            x=alt.X(f"{period_col}:N", sort=period_order, title=period_label),
            y=alt.Y("척당_평균단가_억원:Q", title="척당 평균단가(억원/척)"),
            color=alt.Color("최종_유추선종:N", title="선종"),
            tooltip=[period_col, "최종_유추선종", "수주_선박수", alt.Tooltip("척당_평균단가_억원:Q", format=",.1f")],
        )
    )
    price_hit = (
        alt.Chart(selected_price)
        .mark_line(point=False, strokeWidth=18, opacity=0.001)
        .encode(
            x=alt.X(f"{period_col}:N", sort=period_order, title=period_label),
            y=alt.Y("척당_평균단가_억원:Q"),
            color=alt.Color("최종_유추선종:N", legend=None),
        )
        .add_params(price_ship_select)
    )

    if selected_price_ship_types:
        price_context = (
            alt.Chart(unit_price)
            .mark_line(point=False, opacity=0.08, strokeWidth=1)
            .encode(
                x=alt.X(f"{period_col}:N", sort=period_order, title=period_label),
                y=alt.Y("척당_평균단가_억원:Q", axis=None),
                color=alt.Color("최종_유추선종:N", legend=None),
                tooltip=[period_col, "최종_유추선종", "수주_선박수", alt.Tooltip("척당_평균단가_억원:Q", format=",.1f")],
            )
        )
        price_context_hit = (
            alt.Chart(unit_price)
            .mark_line(point=False, strokeWidth=16, opacity=0.001)
            .encode(
                x=alt.X(f"{period_col}:N", sort=period_order, title=period_label),
                y=alt.Y("척당_평균단가_억원:Q", axis=None),
                color=alt.Color("최종_유추선종:N", legend=None),
            )
            .add_params(price_ship_select)
        )
        price_chart = (
            alt.layer(price_context, price_context_hit, price_visible, price_hit)
            .resolve_scale(y="independent")
            .properties(height=430)
        )
    else:
        price_chart = alt.layer(price_visible, price_hit).properties(height=430)

    price_event = st.altair_chart(
        price_chart,
        width="stretch",
        key=f"price_chart_{period_label}_{st.session_state.get(price_reset_key, 0)}",
        on_select="rerun",
        selection_mode="price_ship_select",
    )

    price_selection = price_event.get("selection", {}) if price_event else {}
    if "price_ship_select" in price_selection:
        clicked_ship_types = sorted({
            row.get("최종_유추선종", "")
            for row in selection_rows(price_event, "price_ship_select")
            if row.get("최종_유추선종", "")
        })
        if clicked_ship_types != selected_price_ship_types:
            st.session_state[price_session_key] = clicked_ship_types
            st.rerun()

    company_price_source = (
        view[view["최종_유추선종"].isin(selected_price_ship_types)].copy()
        if selected_price_ship_types
        else view.copy()
    )
    company_unit_price = aggregate(company_price_source, [period_sort_col, period_col, "회사"])
    company_unit_price = company_unit_price.dropna(subset=["척당_평균단가_억원"]).sort_values(period_sort_col)
    company_unit_price = format_period_sort_column(company_unit_price, period_sort_col, period_label)
    company_price_period_order = company_unit_price[period_col].drop_duplicates().tolist()
    st.markdown("**회사별 척당 평균단가 차트**")
    if company_unit_price.empty:
        st.info("선택한 조건의 회사별 척당 평균단가 데이터가 없습니다.")
    else:
        company_price_chart = (
            alt.Chart(company_unit_price)
            .mark_line(point=True)
            .encode(
                x=alt.X(f"{period_col}:N", sort=company_price_period_order, title=period_label),
                y=alt.Y("척당_평균단가_억원:Q", title="척당 평균단가(억원/척)"),
                color=alt.Color("회사:N", title="회사"),
                tooltip=[
                    period_col,
                    "회사",
                    "수주건수",
                    alt.Tooltip("수주_선박수:Q", title="수주 선박 수", format=",.0f"),
                    alt.Tooltip("계약금액_억원:Q", title="계약금액(억원)", format=",.1f"),
                    alt.Tooltip("척당_평균단가_억원:Q", title="척당 평균단가(억원)", format=",.1f"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(company_price_chart, width="stretch")

    price_table = selected_price[
        [period_col, "최종_유추선종", "수주건수", "수주_선박수", "계약금액_억원", "척당_평균단가_억원"]
    ]
    price_table = with_total_row(
        price_table,
        period_col,
        ["수주건수", "수주_선박수", "계약금액_억원"],
        [("척당_평균단가_억원", "계약금액_억원", "수주_선박수", 1)],
    )
    render_dataframe_with_pinned_total(
        price_table,
        label_col=period_col,
        width="stretch",
        hide_index=True,
        column_config={
            "최종_유추선종": "선종",
            "계약금액_억원": st.column_config.NumberColumn("계약금액(억원)", format="%.1f"),
            "척당_평균단가_억원": st.column_config.NumberColumn("척당 평균단가(억원)", format="%.1f"),
        },
    )

with tab_table:
    detail_cols = [
        "공시일",
        "회사",
        "최종_체결계약명",
        "최종_유추선종",
        "최종_수주_선박수",
        "계약금액_억원",
        "척당단가_억원",
        "최종_계약기간_종료일",
        "계약해지",
        "DART_URL",
        "정정공시_URL",
        "비고",
    ]
    details = raw_view.sort_values("공시일_dt", ascending=False)[detail_cols]
    display_details = details.copy()
    correction_urls = display_details["정정공시_URL"].fillna("").astype(str).map(
        lambda value: [
            url.strip()
            for url in value.split("|")
            if url.strip() and url.strip().lower() not in {"nan", "none"}
        ]
    )
    max_correction_url_count = int(correction_urls.map(len).max() or 0)
    correction_url_cols = []
    for index in range(max_correction_url_count):
        col = f"정정공시{index + 1}_URL"
        display_details[col] = correction_urls.map(
            lambda urls, url_index=index: urls[url_index] if len(urls) > url_index else ""
        )
        correction_url_cols.append(col)
    display_cols = []
    for col in detail_cols:
        if col == "정정공시_URL":
            display_cols.extend(correction_url_cols)
        else:
            display_cols.append(col)
    display_details = display_details[display_cols]
    correction_column_config = {
        col: st.column_config.LinkColumn(col.replace("_URL", "")) for col in correction_url_cols
    }
    st.dataframe(
        display_details,
        width="stretch",
        hide_index=True,
        column_config={
            "최종_체결계약명": "체결계약명",
            "최종_유추선종": "선종",
            "최종_수주_선박수": st.column_config.NumberColumn("수주 선박 수", format="%.0f"),
            "계약금액_억원": st.column_config.NumberColumn("계약금액(억원)", format="%.1f"),
            "척당단가_억원": st.column_config.NumberColumn("척당단가(억원)", format="%.1f"),
            "최종_계약기간_종료일": "계약기간 종료일",
            "DART_URL": st.column_config.LinkColumn("DART"),
            **correction_column_config,
        },
    )

    csv = details.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "필터 결과 다운로드",
        csv,
        file_name="ship_order_dashboard_filtered.csv",
        mime="text/csv",
    )

with tab_request:
    st.subheader("요청 및 건의사항")
    st.write("대시보드 개선 요청, 데이터 오류 의심 건, 추가로 보고 싶은 지표를 남겨 주세요.")
    with st.form("public_request_form", clear_on_submit=True):
        requester = st.text_input("이름 또는 닉네임", placeholder="선택 입력")
        category = st.selectbox("구분", ["데이터 오류", "기능 요청", "차트 개선", "기타"])
        message = st.text_area("내용", height=180, placeholder="요청 내용을 적어 주세요.")
        submitted = st.form_submit_button("요청 보내기")
        if submitted:
            if not message.strip():
                st.warning("내용을 입력해 주세요.")
            else:
                try:
                    append_request(requester, category, message)
                    st.success("요청이 저장되었습니다.")
                except Exception as error:
                    st.error(f"요청 저장 중 오류가 발생했습니다: {error}")
    if github_requests_enabled():
        st.caption("요청 내용은 관리자 확인용 GitHub Issue에 누적 저장됩니다.")
    else:
        st.caption("요청 저장소가 설정되지 않아 런타임 파일에 임시 저장됩니다. 영구 보관하려면 관리자에게 GitHub 요청 저장소 설정을 요청해 주세요.")

with tab_admin:
    st.subheader("관리자 모드")
    configured_password = admin_password()
    if not configured_password:
        st.info("관리자 비밀번호가 설정되지 않았습니다. Streamlit Secrets에 `ADMIN_PASSWORD`를 설정하면 관리자 모드를 사용할 수 있습니다.")
    else:
        password = st.text_input("관리자 비밀번호", type="password")
        if password != configured_password:
            st.warning("관리자 비밀번호를 입력해 주세요.")
        else:
            st.success("관리자 모드가 활성화되었습니다.")
            stats = analytics_frame()
            requests = load_requests()
            request_store_status = "GitHub Issue 영구 저장" if github_requests_enabled() else "런타임 파일 임시 저장"

            metric_cols = st.columns(4)
            metric_cols[0].metric("총 조회수", f"{int(stats['조회수'].sum()) if not stats.empty else 0:,}")
            metric_cols[1].metric("최근 일자 조회수", f"{int(stats.iloc[0]['조회수']) if not stats.empty else 0:,}")
            metric_cols[2].metric("최근 일자 이용자수", f"{int(stats.iloc[0]['이용자수']) if not stats.empty else 0:,}")
            metric_cols[3].metric("누적 요청", f"{len(requests):,}")
            st.caption(f"요청 저장 방식: {request_store_status}")

            st.subheader("일간 조회 통계")
            st.dataframe(stats, width="stretch", hide_index=True)
            if not stats.empty:
                st.download_button(
                    "조회 통계 다운로드",
                    stats.to_csv(index=False).encode("utf-8-sig"),
                    file_name="ship_public_analytics.csv",
                    mime="text/csv",
                )

            st.subheader("요청 목록")
            st.dataframe(
                requests.drop(columns=["방문자ID"], errors="ignore"),
                width="stretch",
                hide_index=True,
            )
            if not requests.empty:
                st.download_button(
                    "요청 목록 다운로드",
                    requests.to_csv(index=False).encode("utf-8-sig"),
                    file_name="ship_public_requests.csv",
                    mime="text/csv",
                )
