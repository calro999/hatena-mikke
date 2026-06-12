import os
import sys
import datetime
import urllib.request
import urllib.parse
import urllib.error
import json
import random
import re
from hatena_api import HatenaAPI
from article_generator import ArticleGenerator
from image_generator import ImageGenerator

CACHE_FILE = "posted_cache.txt"

# 商材データ定義
CHARACTERS = [
    "ちいかわ",
    "サンリオ",
    "パペットスンスン",
    "スヌーピー",
    "ポケモン",
    "スーパーマリオ",
    "スクイーズ"
]

HOBBIES = [
    "スクイーズ",
    "マスコット",
    "ガチャガチャ セット",
    "カプセルトイ フルコンプ",
    "ウエハース シール",
    "デコステッカー",
    "食玩 BOX 予約"
]

def load_cache() -> set:
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_cache(item_number: str):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_number}\n")

def generate_keyword() -> str:
    """AリストとBリストからランダムにキーワードを生成する。"""
    char = random.choice(CHARACTERS)
    if char == "スクイーズ":
        # スクイーズ（単体指定用）
        return "スクイーズ"
    hobby = random.choice(HOBBIES)
    return f"{char} {hobby}"

def fetch_rakuten_items(app_id: str, affiliate_id: str, keyword: str) -> list:
    """Fetches items from the Rakuten Ichiba Item Search API."""
    if not app_id or app_id.startswith("DUMMY"):
        print("Rakuten App ID not set. Using mock data for local dry-run.")
        return get_mock_items(keyword)

    print(f"Debug: RAKUTEN_APP_ID length is {len(app_id)}")
    print(f"Searching with Keyword: {keyword}")

    base_url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
    params = {
        "applicationId": app_id,
        "affiliateId": affiliate_id,
        "keyword": keyword,
        "genreId": "101164", # ホビー・おもちゃジャンル
        "sort": "standard",
        "hits": 10,
        "format": "json"
    }

    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    try:
        print(f"Requesting Rakuten Ichiba API: {url.split('applicationId=')[0]}applicationId=***")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = []
            for entry in data.get("Items", []):
                item_data = entry.get("Item", {})
                if item_data:
                    items.append({
                        "title": item_data.get("itemName"),
                        "itemCaption": item_data.get("itemCaption", ""),
                        "affiliateUrl": item_data.get("affiliateUrl"),
                        "itemCode": item_data.get("itemCode"), # itemNumberの代用として一意のitemCodeを使用
                        "price": f"{item_data.get('itemPrice', '')}円"
                    })
            return items
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
            print(f"Failed to fetch from Rakuten Ichiba API (HTTPError): {e}")
            print(f"Error Response Body: {error_body}")
        except Exception:
            print(f"Failed to fetch from Rakuten Ichiba API (HTTPError): {e}")
        return []
    except Exception as e:
        print(f"Failed to fetch from Rakuten Ichiba API: {e}")
        return []

def get_mock_items(keyword: str) -> list:
    """Returns mock data based on genre/keyword for testing/dry-run."""
    return [
        {
            "title": f"【予約商品】{keyword} かわいいコレクションDX 1BOX入り",
            "itemCaption": f"ファン必見！大人気『{keyword}』のコレクションフィギュアが遂に登場。細部までこだわり抜かれたハイクオリティな造形と、カラフルな塗装が特徴です。全種類コンプリート可能な豪華セット！お部屋にディスプレイして癒やしの空間を演出しましょう。",
            "affiliateUrl": "https://r18.afl.rakuten.co.jp/mock_hobby",
            "itemCode": "mock_hobby_001",
            "price": "3,980円"
        }
    ]

def main():
    print("=== Starting Rakuten Hobby Hatena Blog Poster ===")
    
    # 1. Configurations
    rakuten_app_id = os.environ.get("RAKUTEN_APP_ID", "DUMMY_APP_ID")
    rakuten_affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "DUMMY_AFFILIATE_ID")
    
    hatena_id = os.environ.get("HATENA_ID", "DUMMY_HATENA_ID")
    blog_id = os.environ.get("HATENA_BLOG_ID", "mikke-hobby.hatenablog.com")
    hatena_api_key = os.environ.get("HATENA_API_KEY", "")

    dry_run = not hatena_api_key or hatena_api_key.startswith("DUMMY")
    if dry_run:
        print("Warning: HATENA_API_KEY is not set. Running in DRY-RUN/DEMO mode.")

    # 2. Generate Search Keyword
    keyword = generate_keyword()
    print(f"Generated Keyword: {keyword}")

    # 3. Load Cache
    posted_cache = load_cache()
    print(f"Loaded {len(posted_cache)} posted items from cache.")

    # 4. Fetch Items
    items = fetch_rakuten_items(rakuten_app_id, rakuten_affiliate_id, keyword)
    if not items:
        print("Error: No items fetched from Rakuten Ichiba API.")
        sys.exit(1)

    print(f"Fetched {len(items)} items. Checking for new items...")

    # 5. Filter Unposted Items
    target_item = None
    for item in items:
        item_code = item.get("itemCode")
        if item_code and item_code not in posted_cache:
            target_item = item
            break

    if not target_item:
        print("All fetched items have already been posted. Nothing to do today.")
        sys.exit(0)

    print(f"Selected Item to Post: {target_item['title']} (Code: {target_item['itemCode']})")

    # 6. Generate Eyecatch Image
    print("Generating Eyecatch Image...")
    img_gen = ImageGenerator()
    eyecatch_path = "eyecatch.png"
    
    # カテゴリ判定
    category = "toy"
    title_lower = target_item["title"].lower()
    if any(w in title_lower for w in ["ガチャガチャ", "カプセルトイ"]):
        category = "capsule"
    elif any(w in title_lower for w in ["フィギュア", "マスコット", "ウエハース"]):
        category = "figure"

    img_gen.generate_eyecatch(
        prompt=target_item["title"],
        output_path=eyecatch_path,
        category=category
    )

    # 7. Generate Article Content
    print("Generating Article Content using LLM...")
    article_gen = ArticleGenerator()
    article_gen.load_model()
    
    title_raw = target_item["title"]
    clean_title = re.sub(r'【[^】]+】|\[[^\]]+\]', '', title_raw).strip()

    excerpt = target_item['itemCaption'][:150] + "..." if len(target_item['itemCaption']) > 150 else target_item['itemCaption']
    mapped_features = [
        f"注目のホビー・コレクションアイテム『{clean_title}』の紹介",
        f"商品の見どころ・あらすじ: {excerpt}"
    ]
    
    generator_input_item = {
        "title": target_item["title"],
        "clean_title": clean_title,
        "features": mapped_features,
        "price": target_item["price"],
        "url": target_item["affiliateUrl"]
    }
    
    llm_section = article_gen.generate_review_article(generator_input_item)

    # 8. Setup Hatena Client and Upload Eyecatch
    hatena_client = HatenaAPI(
        hatena_id=hatena_id,
        blog_id=blog_id,
        api_key=hatena_api_key
    )

    uploaded_image_url = hatena_client.upload_image_to_fotolife(eyecatch_path)
    if not uploaded_image_url:
        print("Fotolife upload failed or skipped. Using Unsplash fallback in HTML.")
        uploaded_image_url = img_gen._select_unsplash_image_url(
            target_item["title"], 
            category=category
        )

    # Translate/Format description
    print("Translating/formatting description...")
    translated_synopsis = article_gen.translate_synopsis(target_item['itemCaption'])

    # Construct HTML article
    img_html = f'<div style="text-align: center; margin: 20px 0;"><img src="{uploaded_image_url}" alt="{target_item["title"]}" style="max-width: 100%; height: auto; border-radius: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.08);"></div>'
    
    synopsis_html = f"""
<h3>商品紹介・あらすじ</h3>
<div style="background: #f9f9f9; padding: 18px 20px; border-left: 5px solid #FF5E00; margin: 20px 0; line-height: 1.6; color: #444; border-radius: 0 8px 8px 0; font-size: 15px;">
    {translated_synopsis}
</div>
"""

    cta_html = f"""
<div style="text-align: center; margin: 40px 0 20px 0;">
    <a href="{target_item['affiliateUrl']}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: #FF5E00; color: #fff; padding: 16px 32px; font-size: 18px; font-weight: bold; text-decoration: none; border-radius: 30px; box-shadow: 0 4px 15px rgba(255,94,0,0.3); text-align: center;">
        ＼ 楽天市場で詳細をチェックする ／
    </a>
</div>
"""

    # Google Analytics Tag (Required)
    ga_html = """<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-NFPP76LS9J"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-NFPP76LS9J');
</script>
"""

    article_content = f"{ga_html}\n{img_html}\n{llm_section}\n{synopsis_html}\n{cta_html}"
    blog_title = f"【注目ホビー】『{clean_title}』が登場！魅力・みどころまとめ"

    # 9. Post to Hatena Blog
    success = hatena_client.post_entry(
        title=blog_title,
        html_content=article_content,
        is_draft=False
    )

    if success:
        print("Successfully posted to Hatena Blog!")
        if not dry_run:
            save_cache(target_item["itemCode"])
            print(f"Added {target_item['itemCode']} to posted cache.")
    else:
        print("Failed to post entry.")
        sys.exit(1)

    print("=== Auto Post Process Completed! ===")

if __name__ == "__main__":
    main()
