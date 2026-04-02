import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

USER_AGENT = "AutoFlyGeocoder/1.0"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
COUNTRY_REPLACEMENTS = {
    "日本": "Japan",
    "台灣": "Taiwan",
    "台湾": "Taiwan",
    "美國": "USA",
    "美国": "USA",
    "英國": "United Kingdom",
    "英国": "United Kingdom",
    "韓國": "South Korea",
    "韩国": "South Korea",
}


def build_url(query, limit):
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": str(limit),
        "addressdetails": "1",
    }
    return f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}"


def geocode(query, limit):
    url = build_url(query, limit)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def extract_query_from_google_maps_url(text):
    match = re.search(r"https?://\S+", text)
    if not match:
        return text

    url = match.group(0)
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    for key in ("q", "query", "destination"):
        if key in params and params[key]:
            return params[key][0]

    path = urllib.parse.unquote(parsed.path)
    place_match = re.search(r"/place/([^/]+)", path)
    if place_match:
        return place_match.group(1).replace("+", " ")

    return text.replace(url, " ").strip()


def normalize_address_text(text):
    text = extract_query_from_google_maps_url(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\n", ", ")
    text = text.replace("｜", " ")
    text = text.replace("•", ", ")
    text = text.replace("·", ", ")
    text = text.replace("／", "/")
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("〒", "")
    text = re.sub(r"\((.*?)\)", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"([0-9A-Za-z])([一-龥ぁ-んァ-ヶ])", r"\1, \2", text)
    text = re.sub(r"([一-龥ぁ-んァ-ヶ])([0-9A-Za-z])", r"\1, \2", text)

    for source, target in COUNTRY_REPLACEMENTS.items():
        text = text.replace(source, target)

    text = text.replace("〒", "")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(,\s*){2,}", ", ", text)
    return text.strip(" ,")


def build_query_variants(query):
    normalized = normalize_address_text(query)
    variants = []

    def add(value):
        value = value.strip(" ,")
        if value and value not in variants:
            variants.append(value)

    add(query.strip())
    add(normalized)
    add(normalized.replace("/", ", "))
    add(re.sub(r"\b\d{3}-\d{4}\b", "", normalized))
    add(re.sub(r"\b\d{5}(?:-\d{4})?\b", "", normalized))
    add(re.sub(r"\b(?:Japan|Taiwan|USA|United Kingdom|South Korea)\b", "", normalized, flags=re.IGNORECASE))

    if "," in normalized:
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) >= 2:
            add(", ".join(parts[-4:]))
            add(", ".join(parts[-3:]))
            add(", ".join(parts[-2:]))

    return variants


def geocode_with_fallback(query, limit):
    attempts = []
    for variant in build_query_variants(query):
        results = geocode(variant, limit)
        attempts.append(variant)
        if results:
            return variant, results, attempts
    return None, [], attempts


def print_results(original_query, used_query, results, attempts):
    if not results:
        print(f"找不到地址: {original_query}")
        print("已嘗試以下查詢變體：")
        for attempt in attempts:
            print(f"- {attempt}")
        print()
        print("請試著把地址改成更容易搜尋的格式：")
        print("- 地標, 城市, 國家")
        print("- 門牌, 街道, 區, 城市, 郵遞區號, 國家")
        print("- 直接貼 Google Maps 地址時，盡量保留主要地址本體，不要混入店家介紹文字")
        print("- 若原本是中文或日文地址，可嘗試改成英文或羅馬字")
        print()
        print("例如：")
        print('- "Tokyo Tower, Tokyo, Japan"')
        print('- "1600 Amphitheatre Parkway, Mountain View, CA, USA"')
        print('- "2 Chome-27-2 Hashimoto, Nishi Ward, Fukuoka, 819-0031, Japan"')
        return 1

    print(f"原始輸入: {original_query}")
    if used_query != original_query:
        print(f"實際查詢: {used_query}")
    print()

    for index, item in enumerate(results, start=1):
        lat = item["lat"]
        lng = item["lon"]
        display_name = item.get("display_name", "(無描述)")
        print(f"[{index}] {display_name}")
        print(f"    lat={lat}")
        print(f"    lng={lng}")
        print(f"    fly.py 指令: python fly.py set --lat {lat} --lng {lng}")
        print()

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto Fly address to latitude/longitude helper."
    )
    parser.add_argument("query", nargs="+", help="Address text to geocode")
    parser.add_argument("--limit", type=int, default=3, help="Maximum number of matches to show")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    query = " ".join(args.query).strip()

    if args.limit < 1:
        print("--limit 必須大於等於 1")
        sys.exit(2)

    try:
        used_query, results, attempts = geocode_with_fallback(query, args.limit)
    except urllib.error.HTTPError as exc:
        print(f"地理編碼服務回傳 HTTP 錯誤: {exc.code}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"無法連線到地理編碼服務: {exc.reason}")
        print("請確認目前有網路，且 OpenStreetMap Nominatim 可連線。")
        sys.exit(1)
    except Exception as exc:
        print(f"查詢地址失敗: {exc}")
        sys.exit(1)

    sys.exit(print_results(query, used_query or query, results, attempts))
