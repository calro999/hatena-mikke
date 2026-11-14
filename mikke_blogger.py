from external_links import find_best_external_link, generate_external_link_html
from typing import Optional, Set, Dict, Any
import time
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
from bluesky_api import BlueskyAPI
from yahoo_api import YahooMikkeAPI
from toggle_mode import get_next_platform, save_current_platform

CACHE_FILE = "posted_cache.txt"

# 商材データ定義（実際に売れている人気キャラクター・ジャンル）
CHARACTERS = [
    "ちいかわ",
    "スヌーピー",
    "サンリオ",
    "ポケモン",
    "スクイーズ",
    "パペットスンスン",
    "スーパーマリオ"
]

# ホビーの種類定義（売れ筋のガチャガチャ、シークレットBOX、スクイーズ等）
HOBBIES = [
    "ガチャガチャ",
    "シークレットBOX",
    "スクイーズ",
    "カプセルトイ",
    "マスコット ぬいぐるみ",
    "ブラインドボックス",
    "コンプリートセット",
    "食玩 ウエハース"
]

def clean_mikke_product_title(title: str) -> str:
    """楽天特有の大量SEOワード・記号・配送情報を除去し、短くスマートで惹きつける商品名に整形"""
    if not title:
        return "注目ホビー"

    cleaned = title

    # 1. 括弧の中身を除去（ただし括弧内に主要キャラ名がある場合は保護）
    brackets = [
        r'\{[^}]*\}', r'【[^】]*】', r'\[[^\]]*\]', r'［[^］]*］',
        r'（[^）]*）', r'\([^)]*\)', r'〈[^〉]*〉', r'《[^》]*》',
        r'〔[^〕]*〕'
    ]
    char_match = re.search(r'【([^】]*(?:ちいかわ|スヌーピー|サンリオ|ポケモン|マリオ|スクイーズ)[^】]*)】', cleaned)
    salvaged_char = ""
    if char_match:
        salvaged_char = re.sub(r'★|☆|限定|韓国|日本|公式', '', char_match.group(1)).strip()

    for b in brackets:
        cleaned = re.sub(b, ' ', cleaned)

    # 2. 装飾記号・PR記号の削除
    cleaned = re.sub(r'[★☆◆◇■□▲▼◎○〇♪!！?？※・]+', ' ', cleaned)

    # 3. 楽天プロモーションワード・発送情報・景品タグ等
    promo_words = [
        r'送料無料.*', r'あす楽', r'即納', r'ランキング\s*\d*位', r'第?\d+冠',
        r'クーポン(で|\s*利用で)?\d+%?OFF?', r'ポイント\s*\d+倍', r'P\d+倍',
        r'スーパーSALE', r'お買い物マラソン', r'セール', r'限定', r'正規品',
        r'公式', r'メーカー保証', r'ギフト', r'プレゼント', r'お祝い',
        r'202[4-7]年?(最新|新型)?', r'最新(版|型)?', r'新型', r'景品玩具', r'景品',
        r'おもちゃ', r'雑貨', r'ぷにぷに', r'ぷるぷる', r'もちもち', r'もちとろ',
        r'柔らかい', r'ストレス解消', r'子供', r'イベント', r'お祭り', r'夏祭り',
        r'詰め合わせ', r'かわいい', r'配送区分[A-Z0-9]', r'メール便', r'定形外',
        r'ボンボンドロップシール', r'ボンドロ'
    ]
    for pw in promo_words:
        cleaned = re.sub(pw, ' ', cleaned, flags=re.IGNORECASE)

    # 4. 区切り文字で前半部を採用
    delimiters = [r'\s*\|\s*', r'\s*｜\s*', r'\s*／\s*', r'\s*/\s*', r'\s*－\s*', r'\s*:\s*', r'\s*：\s*']
    for delim in delimiters:
        parts = re.split(delim, cleaned)
        if parts and len(parts[0].strip()) >= 4:
            cleaned = parts[0]
            break

    # 5. 空白の正規化と末尾数値の除去
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+\d+$', '', cleaned)

    if salvaged_char and salvaged_char not in cleaned:
        cleaned = f"{salvaged_char} {cleaned}".strip()

    # 6. 単語単位でスマートに短縮（最大24文字程度）
    words = cleaned.split()
    if words:
        result = []
        cur_len = 0
        for w in words:
            if cur_len + len(w) + (1 if result else 0) <= 24:
                result.append(w)
                cur_len += len(w) + (1 if len(result) > 1 else 0)
            elif not result:
                result.append(w[:22])
                break
            else:
                break
        cleaned = ' '.join(result)

    return cleaned if len(cleaned) >= 3 else title[:20].strip()

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
        "hits": 30,
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
    import random
    title = item.get("itemName") or item.get("title") or ""
    price = item.get("itemPrice") or item.get("price") or ""
    caption = item.get("itemCaption") or item.get("catchcopy") or ""

    prompt = f"""以下の楽天の商品情報を基にして、楽天ROOM用の紹介コメント（400文字以内）を生成してください。
【商品名】: {title}
【価格】: {price}円
【商品説明・特徴】: {caption[:200]}

以下の要件を厳格に遵守してください：
1. 口調・トーン：ターゲット層に刺さる自然なレビュー口調とし、「これかわいい！」「これ気になってた！」「これ便利だよ！」といった決まりきった定型文・挨拶パターンは絶対に使用しないでください。商品独自の具体的おすすめポイントや魅力を解説してください。
2. 文字数：400文字以内（厳守。超えると投稿エラーになります）。
3. 絵文字：5〜8個使用して華やかにすること。
4. ハッシュタグ：3〜5個（商品のカテゴリや関連するもの）含め、末尾に「#楽天市場」を必ず含めること。
5. URLや疑似リンク、プレースホルダー（「[リンクはこちら]」など）は絶対に含めないでください。
6. 出力は紹介コメントのテキストのみとし、前置きやMarkdownの装飾コードブロック等は一切含めないでください。
"""

    system_message = (
        "あなたは楽天ROOMでフォロワーから高い信頼を得ている商品レビュー専門のインフルエンサーです。"
        "定型文やテンプレート的な表現は一切使わず、商品の具体的な良さや使うシーンが目に浮かぶような魅力的で自然なオリジナル紹介文を作成してください。"
    )

    def clean_text(text):
        return text.replace("```", "").strip()

    # 1. Gemini API（最優先。thinking無効化・全parts結合で安定化）
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-2.5-pro",
            "gemini-3.1-pro"
        ]
        for model_name in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_message}\n\n{prompt}"}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 600}
                }
                if any(v in model_name for v in ["2.5", "3.", "3-"]):
                    payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
                res = requests.post(url, json=payload, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    candidate = data.get("candidates", [{}])[0]
                    parts = candidate.get("content", {}).get("parts", [])
                    text = clean_text("".join(p.get("text", "") for p in parts if p.get("text")))
                    if len(text) > 30:
                        print(f"Successfully generated ROOM comment via Gemini API ({model_name}).")
                        return text
                    finish = candidate.get("finishReason", "UNKNOWN")
                    print(f"Gemini ({model_name}) short/empty. finishReason={finish}, text_len={len(text)}")
                else:
                    print(f"Gemini API ({model_name}) returned {res.status_code}: {res.text[:150]}")
            except Exception as e:
                print(f"Gemini API ({model_name}) error: {e}")

    # 2. Groq API
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        for model_name in ["llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192"]:
            try:
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model_name,
                    "messages": [{"role": "system", "content": system_message}, {"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 600
                }
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25)
                if res.status_code == 200:
                    text = clean_text(res.json()["choices"][0]["message"]["content"])
                    if len(text) > 30:
                        print(f"Successfully generated ROOM comment via Groq API ({model_name}).")
                        return text
                else:
                    print(f"Groq API ({model_name}) returned {res.status_code}: {res.text[:100]}")
            except Exception as e:
                print(f"Groq API ({model_name}) error: {e}")

    # 3. OpenRouter API（有効な無料モデルを使用）
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        for model_name in ["google/gemma-3-27b-it:free", "mistralai/mistral-nemo:free", "meta-llama/llama-3.2-3b-instruct:free"]:
            try:
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "RakutenRoomBot"
                }
                payload = {
                    "model": model_name,
                    "messages": [{"role": "system", "content": system_message}, {"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 600
                }
                res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    text = clean_text(res.json()["choices"][0]["message"]["content"])
                    if len(text) > 30:
                        print(f"Successfully generated ROOM comment via OpenRouter ({model_name}).")
                        return text
                else:
                    print(f"OpenRouter ({model_name}) returned {res.status_code}: {res.text[:100]}")
            except Exception as e:
                print(f"OpenRouter ({model_name}) error: {e}")

    # 4. GitHub Models API（GH_TOKENがPATの場合のみ）
    gh_token = os.environ.get("GH_TOKEN")
    if gh_token and not gh_token.startswith("ghs_"):
        for model_name in ["gpt-4o-mini", "gpt-4o", "Meta-Llama-3.1-8B-Instruct"]:
            try:
                headers = {"Authorization": f"Bearer {gh_token}", "Content-Type": "application/json"}
                payload = {
                    "model": model_name,
                    "messages": [{"role": "system", "content": system_message}, {"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 600
                }
                res = requests.post("https://models.inference.ai.azure.com/chat/completions", headers=headers, json=payload, timeout=25)
                if res.status_code == 200:
                    text = clean_text(res.json()["choices"][0]["message"]["content"])
                    if len(text) > 30:
                        print(f"Successfully generated ROOM comment via GitHub Models API ({model_name}).")
                        return text
                else:
                    print(f"GitHub Models API ({model_name}) returned {res.status_code}: {res.text[:100]}")
            except Exception as e:
                print(f"GitHub Models API ({model_name}) error: {e}")

    print("WARNING: All LLM API calls failed. Generating dynamic item-aware comment.")
    clean_title = title.replace("【", "").replace("】", "").replace("！", "").replace("✨", "")[:45]
    words = [w for w in clean_title.split() if len(w) > 1]
    keyword = words[0] if words else "おすすめ"

    starters = [
        f"注目の『{clean_title}』をピックアップ！デザイン・クオリティともに満足感の高い一品✨",
        f"ファン必見！『{clean_title}』の細部までこだわった作りが本当に素敵🛍️",
        f"見つけた瞬間テンション上がった『{clean_title}』！自分用にもプレゼントにも◎👍",
        f"話題の注目アイテム『{clean_title}』をご紹介！毎日の生活に彩りを添えてくれますね🎁",
        f"クオリティが高くておすすめの『{clean_title}』！気になる方はお早めにチェック✨"
    ]
    starter = random.choice(starters)

    bodies = [
        "細部まで丁寧につくられており、手にとったときの満足感が違います！コレクションにもおすすめ😊",
        "実用性はもちろん見た目の完成度も抜群。お部屋に飾るだけで気分が上がります✨",
        "評価が高くプレゼントしても喜ばれること間違いなしの優秀グッズ！🛍️",
        "限定感もあり見逃せない注目アイテム。お気に入りに追加してチェックしてみてください👍"
    ]
    body = random.choice(bodies)

    price_info = f"（価格: {price}円）" if price else ""
    return f"{starter}\n\n{body}\n{price_info}\n\n#{keyword} #楽天市場 #おすすめアイテム #コレ"



def post_to_rakuten_room(item_code, comment):
    room_session = os.environ.get("ROOM_SESSION_B64")
    hatena_session = os.environ.get("HATENA_SESSION_B64")
    
    session_b64 = None
    if room_session and room_session.strip():
        print("Using ROOM_SESSION_B64 for Rakuten Room.")
        session_b64 = room_session
    elif hatena_session and hatena_session.strip():
        print("ROOM_SESSION_B64 is empty. Using HATENA_SESSION_B64 as fallback for Rakuten Room.")
        session_b64 = hatena_session
    
    session_file_path = None
    if session_b64:
        try:
            decoded_str = base64.b64decode(session_b64).decode('utf-8')
            if "rakuten.co.jp" not in decoded_str and "rakuten.com" not in decoded_str:
                print("Warning: The resolved session JSON does not seem to contain Rakuten cookies. Login to Rakuten Room might fail.")
            json.loads(decoded_str)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".json") as temp_file:
                temp_file.write(decoded_str)
                session_file_path = temp_file.name
        except Exception as e:
            print(f"Session decode failed: {e}")
            return
    elif os.path.exists("session.json"):
        print("Found local session.json. Using it for Rakuten Room.")
        session_file_path = "session.json"
    else:
        print("ROOM_SESSION_B64/HATENA_SESSION_B64 is not set and local session.json not found. Skipping Rakuten Room post.")
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


def post_single_article(
    post_index: int,
    total_posts: int,
    posted_cache: set,
    hatena_client: HatenaAPI,
    article_gen: ArticleGenerator,
    rakuten_app_id: str,
    rakuten_access_key: str,
    rakuten_affiliate_id: str,
    yahoo_client: Optional[YahooMikkeAPI],
    forced_platform: str,
    dry_run: bool
) -> bool:
    print(f"\n==================================================")
    print(f"=== Starting Mikke Post Batch [{post_index}/{total_posts}] ===")
    print(f"==================================================")

    platform = get_next_platform(forced_platform)
    print(f"Selected Platform for Post #{post_index}: {platform.upper()}")

    # Fetch Unposted Items
    max_keyword_attempts = 20
    target_item = None

    if platform == "yahoo" and yahoo_client:
        print("--- Fetching items from Yahoo! Shopping API ---")
        for attempt in range(max_keyword_attempts):
            keyword = yahoo_client.generate_random_keyword()
            print(f"Attempt {attempt + 1}/{max_keyword_attempts} - (Yahoo: {keyword})")
            items = yahoo_client.search_items(query=keyword, hits=30)
            if not items:
                continue
            random.shuffle(items)
            for item in items:
                item_code = item.get("itemCode")
                if item_code and item_code not in posted_cache:
                    target_item = item
                    break
            if target_item:
                break
    else:
        if platform == "yahoo" and not yahoo_client:
            print("YAHOO_CLIENT_ID not found. Falling back to Rakuten.")
            platform = "rakuten"
        print("--- Fetching items from Rakuten API ---")
        for attempt in range(max_keyword_attempts):
            keyword = generate_keyword()
            print(f"Attempt {attempt + 1}/{max_keyword_attempts} - (Rakuten: {keyword})")
            items = fetch_rakuten_items(rakuten_app_id, rakuten_access_key, rakuten_affiliate_id, keyword)
            if not items:
                continue
            for item in items:
                item_code = item.get("itemCode")
                if item_code and item_code not in posted_cache:
                    target_item = item
                    break
            if target_item:
                break

    if not target_item:
        print(f"Warning: Could not find any unposted items for Post #{post_index}.")
        return False

    print(f"Selected Item to Post: {target_item['title']} (Code: {target_item['itemCode']})")

    # Generate Article Content
    title_raw = target_item["title"]
    clean_title = clean_mikke_product_title(title_raw)
    
    generator_input_item = {
        "title": target_item["title"],
        "clean_title": clean_title,
        "price": target_item["price"],
        "url": target_item["affiliateUrl"],
        "caption": target_item["itemCaption"]
    }
    
    gen_title, desc_html, body_html = article_gen.generate_review_article(generator_input_item)
    blog_title = gen_title
    print(f"Generated Blog Title: {blog_title}")

    # Images & Styling
    product_image_url = target_item.get("imageUrl", "")
    if not product_image_url:
        product_image_url = "https://images.unsplash.com/photo-1558882224-cca166733360?w=800&auto=format&fit=crop&q=80"

    affiliate_link = target_item.get("affiliateUrl", "")

    if platform == "yahoo":
        platform_name = "Yahoo!ショッピング"
        badge_title = "Yahoo!ショッピング 公式・優良取扱店"
        btn_gradient = "linear-gradient(135deg, #ff0033 0%, #ff334b 100%)"
        btn_shadow = "rgba(255,0,51,0.3)"
        notice_txt = "※人気商品のため早期に在庫切れとなる場合がございます。PayPayポイント還元や最新の在庫状況は上記リンクよりご確認ください。"
    else:
        platform_name = "楽天市場"
        badge_title = "楽天市場 公式ショップ・優良取扱店"
        btn_gradient = "linear-gradient(135deg, #FF6B00 0%, #FF8533 100%)"
        btn_shadow = "rgba(255,107,0,0.35)"
        notice_txt = "※人気商品のため早期に在庫切れや完売となる場合がございます。最新の在庫状況は上記リンクよりご確認ください。"

    img_html = f'''
<div style="text-align: center; margin: 25px 0 20px 0;">
    <a href="{affiliate_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; text-decoration: none;">
        <img src="{product_image_url}" alt="{clean_title}" style="width: 100%; max-width: 600px; height: auto; border-radius: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); display: block; margin: 0 auto;">
    </a>
    <p style="font-size: 11px; color: #888; margin-top: 8px;">（※画像クリックで{platform_name}の商品ページへ直接移動できます）</p>
</div>
'''
    
    early_cta_html = f"""
<div style="margin: 20px 0 30px 0; padding: 16px 20px; background: #fff8f0; border: 2px solid #ffcca3; border-radius: 14px; text-align: center;">
    <p style="font-size: 14px; color: #d9480f; font-weight: bold; margin: 0 0 10px 0;">＼ 在庫限り・売り切れ前に即確保！ ／</p>
    <a href="{affiliate_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: {btn_gradient}; color: #fff; padding: 14px 32px; font-size: 16px; font-weight: bold; text-decoration: none; border-radius: 30px; box-shadow: 0 4px 14px {btn_shadow};">
        {platform_name}で「{clean_title}」の在庫・価格を見る 🛒
    </a>
</div>
"""

    closing_cta_html = f"""
<div style="margin: 40px 0 25px 0; padding: 24px 20px; background: #fffbf7; border: 2px solid #ffe3cc; border-radius: 18px; text-align: center; box-shadow: 0 6px 18px rgba(0,0,0,0.05);">
    <span style="display: inline-block; background: #333333; color: #fff; font-size: 12px; font-weight: bold; padding: 4px 14px; border-radius: 20px; margin-bottom: 12px;">{badge_title}</span>
    <div style="font-size: 18px; font-weight: bold; color: #222; margin-bottom: 8px; line-height: 1.4;">{clean_title}</div>
    <div style="font-size: 20px; font-weight: bold; color: #d9480f; margin-bottom: 18px;">{target_item.get('price', '')}</div>
    <a href="{affiliate_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: {btn_gradient}; color: #ffffff; padding: 16px 36px; font-size: 17px; font-weight: bold; text-decoration: none; border-radius: 35px; box-shadow: 0 6px 16px {btn_shadow}; text-align: center;">
        ＼ {platform_name}で詳細＆ユーザー口コミをチェック ／
    </a>
    <p style="font-size: 11px; color: #888; margin-top: 12px; margin-bottom: 0;">{notice_txt}</p>
</div>
"""

    ga_html = """<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-NFPP76LS9J"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-NFPP76LS9J');
</script>
"""

    ext_target = find_best_external_link(target_item.get('title', ''), target_item.get('itemCaption', '') or target_item.get('caption', ''))
    ext_link_html = generate_external_link_html(ext_target)
    if ext_link_html:
        print(f"[EXTERNAL-LINK] Added affinity link to {ext_target['domain']}")
    article_content = f"{ga_html}\n{desc_html}\n{img_html}\n{early_cta_html}\n{body_html}\n{ext_link_html}\n{closing_cta_html}"

    published_entry_url = hatena_client.post_entry(
        title=blog_title,
        html_content=article_content,
        is_draft=False
    )

    if published_entry_url:
        print(f"Successfully posted Post #{post_index} to Hatena Blog!")
        if not dry_run:
            save_cache(target_item["itemCode"])
            posted_cache.add(target_item["itemCode"])
            print(f"Added {target_item['itemCode']} to posted cache.")
        
        save_current_platform(platform)
        print(f"Rotated platform state: last was {platform}")

        # Post to Rakuten Room (Only for Rakuten items)
        if platform == "rakuten":
            try:
                print("Generating Rakuten Room comment...")
                room_comment = generate_room_comment_with_llm(target_item)
                print(f"Generated ROOM Comment:\n{room_comment}")
                post_to_rakuten_room(target_item["itemCode"], room_comment)
            except Exception as room_e:
                print(f"Error during Rakuten Room post: {room_e}")

        # Post to Bluesky
        try:
            print("Preparing to post to Bluesky (@mikke-hobby.bsky.social)...")
            bsky = BlueskyAPI()
            bsky_text = bsky.generate_post_text(
                item={
                    "title": target_item["title"],
                    "clean_title": clean_title,
                    "price": target_item.get("price", ""),
                    "url": target_item.get("affiliateUrl", "")
                },
                blog_url=published_entry_url,
                genre="hobby"
            )
            print(f"Generated Bluesky Post Text:\n---\n{bsky_text}\n---")
            bsky.post(bsky_text)
        except Exception as bsky_e:
            print(f"Warning: Failed to post to Bluesky: {bsky_e}")

        return True
    else:
        print(f"Failed to post entry for Post #{post_index}.")
        return False

def main():
    print("=== Starting Hobby Hatena Blog Poster (Rakuten & Yahoo Hybrid) ===")
    
    # 1. Configurations
    rakuten_app_id = os.environ.get("RAKUTEN_APP_ID", "DUMMY_APP_ID")
    rakuten_access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
    rakuten_affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "DUMMY_AFFILIATE_ID")

    yahoo_client_id = os.environ.get("YAHOO_CLIENT_ID", "")
    yahoo_affiliate_id = os.environ.get("YAHOO_AFFILIATE_ID", "")
    
    hatena_id = os.environ.get("HATENA_ID", "DUMMY_HATENA_ID")
    blog_id = os.environ.get("HATENA_BLOG_ID", "mikke-hobby.hatenablog.com")
    hatena_api_key = os.environ.get("HATENA_API_KEY", "")

    forced_platform = os.environ.get("POST_PLATFORM", "").strip().lower()

    dry_run = not hatena_api_key or hatena_api_key.startswith("DUMMY")
    if dry_run:
        print("Warning: HATENA_API_KEY is not set. Running in DRY-RUN/DEMO mode.")

    posted_cache = load_cache()

    yahoo_client = None
    if yahoo_client_id:
        yahoo_client = YahooMikkeAPI(client_id=yahoo_client_id, affiliate_id=yahoo_affiliate_id)

    hatena_client = HatenaAPI(
        hatena_id=hatena_id,
        blog_id=blog_id,
        api_key=hatena_api_key
    )

    article_gen = ArticleGenerator()
    article_gen.load_model()

    posts_per_run = int(os.environ.get("POSTS_PER_RUN", "2"))
    successful_posts = 0

    for idx in range(1, posts_per_run + 1):
        success = post_single_article(
            post_index=idx,
            total_posts=posts_per_run,
            posted_cache=posted_cache,
            hatena_client=hatena_client,
            article_gen=article_gen,
            rakuten_app_id=rakuten_app_id,
            rakuten_access_key=rakuten_access_key,
            rakuten_affiliate_id=rakuten_affiliate_id,
            yahoo_client=yahoo_client,
            forced_platform=forced_platform,
            dry_run=dry_run
        )
        if success:
            successful_posts += 1

        if idx < posts_per_run:
            print(f"Waiting 15 seconds before next post...")
            time.sleep(15)

    print(f"\n=== Auto Post Process Completed: {successful_posts}/{posts_per_run} posts published successfully ===")
    if successful_posts == 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
