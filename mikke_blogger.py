import base64
import tempfile
from playwright.sync_api import sync_playwright
import os
import sys
import datetime
import urllib.request
import urllib.parse
import urllib.error
import json
import random
import re
import time
import requests
from hatena_api import HatenaAPI
from article_generator import ArticleGenerator

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

# ホビーの種類定義
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
    """Aリスト and Bリストからランダムにキーワードを生成する。"""
    char = random.choice(CHARACTERS)
    if char in ["スクイーズ", "サンリオ"]:
        # スクイーズ、サンリオ（単体指定用）
        return char
    hobby = random.choice(HOBBIES)
    return f"{char} {hobby}"

def fetch_rakuten_items(app_id: str, access_key: str, affiliate_id: str, keyword: str) -> list:
    """Fetches items from the Rakuten Ichiba Item Search API."""
    if not app_id or app_id.startswith("DUMMY"):
        print("Rakuten App ID not set. Using mock data for local dry-run.")
        return get_mock_items(keyword)

    print(f"Debug: RAKUTEN_APP_ID length is {len(app_id)}")
    print(f"Searching with Keyword: {keyword}")

    base_url = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"
    params = {
        "applicationId": app_id,
        "affiliateId": affiliate_id,
        "keyword": keyword,
        "genreId": "101164", # ホビー・おもちゃジャンル
        "sort": "standard",
        "hits": 10,
        "format": "json"
    }

    if access_key:
        print(f"Debug: RAKUTEN_ACCESS_KEY is set. Length: {len(access_key)}")
        params["accessKey"] = access_key

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
                    # 商品画像URLの取得（中画像URLリストの最初を取得）
                    image_url = ""
                    medium_images = item_data.get("mediumImageUrls", [])
                    if medium_images and isinstance(medium_images, list) and len(medium_images) > 0:
                        image_url = medium_images[0].get("imageUrl", "")
                    
                    items.append({
                        "title": item_data.get("itemName"),
                        "itemCaption": item_data.get("itemCaption", ""),
                        "affiliateUrl": item_data.get("affiliateUrl"),
                        "itemCode": item_data.get("itemCode"), # itemNumberの代用として一意のitemCodeを使用
                        "price": f"{item_data.get('itemPrice', '')}円",
                        "imageUrl": image_url
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
            "price": "3,980円",
            "imageUrl": "https://images.unsplash.com/photo-1558882224-cca166733360?w=800&auto=format&fit=crop&q=80"
        }
    ]


def generate_room_comment_with_llm(item):
    title = item.get("title") or item.get("itemName")
    price = item.get("price") or item.get("itemPrice")
    
    prompt = f"""以下の楽天の商品情報を基にして、楽天ROOM用の紹介コメント（400文字以内）を生成してください。
【商品名】: {title}
【価格】: {price}

以下の要件を厳格に遵守してください：
1. 文字数は400文字以内（厳守。超えると投稿エラーになります）。
2. 親しみやすい話し言葉で、絵文字を5〜8個使用してください。
3. ハッシュタグを3〜5個（商品のカテゴリや関連するもの）含め、末尾に「#楽天市場」を必ず含めること。
4. URLや疑似リンク、プレースホルダー（「[リンクはこちら]」など）は絶対に含めないでください。
5. 出力は紹介コメントのテキストのみとし、前置きやMarkdownの装飾コードブロック等は一切含めないでください。
"""

    system_message = "あなたは楽天ROOMでフォロワー急増中の便利グッズ・アイデア雑貨専門インフルエンサーです。日常のちょっとした不満や悩みを解決してくれる驚きの便利アイテムや暮らしを豊かにする雑貨の魅力を、日本語のみで発信してください。"

    # 1. GitHub Models API
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if github_token:
        try:
            print("Attempting to generate ROOM comment with GitHub Models API...")
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            response = requests.post("https://models.inference.ai.azure.com/chat/completions", headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                result_text = response.json()["choices"][0]["message"]["content"].strip()
                if "```" in result_text:
                    result_text = result_text.replace("```", "")
                return result_text.strip()
        except Exception as e:
            print(f"GitHub Models API ROOM generation failed: {e}")

    # 2. Pollinations AI
    pollinations_models = ["openai-fast", "openai"]
    for model in pollinations_models:
        try:
            print(f"Attempting to generate ROOM comment with Pollinations AI (model: {model})...")
            response = requests.post(
                "https://text.pollinations.ai/",
                json={
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    "model": model
                },
                timeout=45
            )
            if response.status_code == 200 and len(response.text.strip()) > 30:
                result_text = response.text.strip()
                if "```" in result_text:
                    result_text = result_text.replace("```", "")
                return result_text.strip()
        except Exception as e:
            print(f"Pollinations AI ROOM ({model}) failed: {e}")

    # Fallback
    clean_title = title.replace("【", "").replace("】", "")[:50]
    return f"【おすすめ厳選アイテム】\n\n本当にセンス抜群でおすすめしたい素敵アイテムをご紹介します✨\nお買い物リストにぴったり🎀\n\n{clean_title}...\n\n#楽天市場 #お買い得 #おすすめ"


def post_to_rakuten_room(item_code, comment):
    session_b64 = os.environ.get("ROOM_SESSION_B64") or os.environ.get("BLOGGER_SESSION_B64")
    
    session_file_path = None
    if session_b64:
        try:
            decoded_str = base64.b64decode(session_b64).decode('utf-8')
            json.loads(decoded_str)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".json") as temp_file:
                temp_file.write(decoded_str)
                session_file_path = temp_file.name
        except Exception as e:
            print(f"ROOM_SESSION_B64 (or BLOGGER_SESSION_B64) decode failed: {e}")
            return
    elif os.path.exists("session.json"):
        print("Found local session.json. Using it for Rakuten Room.")
        session_file_path = "session.json"
    else:
        print("ROOM_SESSION_B64/BLOGGER_SESSION_B64 is not set and local session.json not found. Skipping Rakuten Room post.")
        return

    print(f"Posting to Rakuten Room (Item: {item_code}) using Playwright...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                storage_state=session_file_path,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            try:
                # ROOM投稿エディタへ遷移
                warp_url = f"https://room.rakuten.co.jp/mix?itemcode={item_code}&scid=we_room_upc60"
                page.goto(warp_url, wait_until="load", timeout=45000)
                time.sleep(4)

                # ログイン画面に飛ばされていないかチェック
                if "login.rakuten.co.jp" in page.url or "login" in page.url.lower():
                    print("Error: Session has expired or is invalid. Redirected to Rakuten login page. Skipping Rakuten Room post.")
                    return

                # 重複・すでにコレしているかチェック
                page_html = page.content()
                if any(term in page_html for term in ["すでにコレ", "すでに登録されています", "すでに登録"]):
                    print("This item has already been posted ('コレ！'済み) to Rakuten Room. Skipping.")
                    return

                # コメント入力欄 (textarea)
                comment_area = page.locator('textarea[placeholder*="コメント"], textarea[placeholder*="オススメ"], textarea[placeholder*="魅力"], textarea').first
                comment_area.wait_for(state="visible", timeout=15000)
                comment_area.fill(comment)
                time.sleep(1)

                # 投稿確定ボタン
                submit_btn = page.locator('button:has-text("投稿"), button:has-text("完了"), button:has-text("コレ！"), button[class*="submit"]').first
                submit_btn.scroll_into_view_if_needed()
                time.sleep(1)
                submit_btn.click(force=True)
                print("Clicked Rakuten Room submit button.")
                
                time.sleep(5)
                print("Successfully posted to Rakuten Room!")
            except Exception as inner_e:
                print(f"Error during Playwright interaction: {inner_e}")
                try:
                    page.screenshot(path="room_error.png")
                    print("Saved debug screenshot: room_error.png")
                except Exception as se:
                    print(f"Failed to take screenshot: {se}")
                raise inner_e

    except Exception as e:
        print(f"Error posting to Rakuten Room: {e}")
    finally:
        if session_file_path and session_file_path != "session.json" and os.path.exists(session_file_path):
            os.remove(session_file_path)


def main():
    print("=== Starting Rakuten Hobby Hatena Blog Poster ===")
    
    # 1. Configurations
    rakuten_app_id = os.environ.get("RAKUTEN_APP_ID", "DUMMY_APP_ID")
    rakuten_access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
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

    # 4. Fetch Items (With Retry on Empty Result)
    max_retries = 3
    items = []
    for attempt in range(max_retries):
        items = fetch_rakuten_items(rakuten_app_id, rakuten_access_key, rakuten_affiliate_id, keyword)
        if items:
            break
        print(f"Warning: No items fetched for keyword '{keyword}'. Retrying with a new keyword...")
        keyword = generate_keyword()
        print(f"New Generated Keyword: {keyword}")

    if not items:
        print("Error: No items fetched from Rakuten Ichiba API after multiple retries.")
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

    # 6. Generate Article Content
    print("Generating Article Content using LLM...")
    article_gen = ArticleGenerator()
    article_gen.load_model()
    
    title_raw = target_item["title"]
    clean_title = re.sub(r'【[^】]+】|\[[^\]]+\]', '', title_raw).strip()
    
    generator_input_item = {
        "title": target_item["title"],
        "clean_title": clean_title,
        "price": target_item["price"],
        "url": target_item["affiliateUrl"],
        "caption": target_item["itemCaption"]
    }
    
    llm_section = article_gen.generate_review_article(generator_input_item)

    # 7. Setup Hatena Client
    hatena_client = HatenaAPI(
        hatena_id=hatena_id,
        blog_id=blog_id,
        api_key=hatena_api_key
    )

    # 実際の商品の画像URLを直接使用
    product_image_url = target_item.get("imageUrl", "")
    if not product_image_url:
        product_image_url = "https://images.unsplash.com/photo-1558882224-cca166733360?w=800&auto=format&fit=crop&q=80" # フォールバック

    # Construct HTML article
    img_html = f'<div style="text-align: center; margin: 20px 0;"><img src="{product_image_url}" alt="{target_item["title"]}" style="max-width: 100%; height: auto; border-radius: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.08);"></div>'
    
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

    # LLMセクション、商品画像、アフィリエイトリンクの3要素のみにスリム化
    article_content = f"{ga_html}\n{img_html}\n{llm_section}\n{cta_html}"
    
    # 記事タイトルはLLMで生成されたものから抽出（<h2>タグの中身）を試みる
    blog_title = f"【注目ホビー】『{clean_title}』が登場！魅力・みどころまとめ"
    match = re.search(r'<h2>(.*?)</h2>', llm_section)
    if match:
        blog_title = match.group(1).strip()
        # 本文側のh2タグの重複を避けるためトリミング
        llm_section = llm_section.replace(match.group(0), "")
        article_content = f"{ga_html}\n{img_html}\n{llm_section}\n{cta_html}"

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
        
        # Post to Rakuten Room
        try:
            print("Generating Rakuten Room comment...")
            room_comment = generate_room_comment_with_llm(target_item)
            print(f"Generated ROOM Comment:\n{room_comment}")
            post_to_rakuten_room(target_item["itemCode"], room_comment)
        except Exception as room_e:
            print(f"Error during Rakuten Room post: {room_e}")
    else:
        print("Failed to post entry.")
        sys.exit(1)

    print("=== Auto Post Process Completed! ===")

if __name__ == "__main__":
    main()
