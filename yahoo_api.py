import os
import re
import random
import requests
from typing import List, Dict, Any, Optional

# ホビー・キャラクター系に特化したクリーンアップ
def clean_yahoo_mikke_title(title: str) -> str:
    """Yahoo!ショッピング特有のSEOキーワード詰め込みやPRタグを除去し、スマートで短い商品名に整形"""
    if not title:
        return "注目ホビー"

    cleaned = title
    # 括弧の除去
    brackets = [
        r'\{[^}]*\}', r'【[^】]*】', r'\[[^\]]*\]', r'［[^］]*］',
        r'（[^）]*）', r'\([^)]*\)', r'〈[^〉]*〉', r'《[^》]*》',
        r'〔[^〕]*〕'
    ]
    for b in brackets:
        cleaned = re.sub(b, ' ', cleaned)

    # 記号除去
    cleaned = re.sub(r'[★☆◆◇■□▲▼◎○〇♪!！?？※・]+', ' ', cleaned)

    # PRワード除去
    promo_words = [
        r'送料無料.*', r'あすつく', r'即納', r'ランキング\s*\d*位', r'第?\d+冠',
        r'クーポン(で|\s*利用で)?\d+%?OFF?', r'ポイント\s*\d+倍', r'PayPay\s*\d+倍',
        r'超PayPay祭', r'お買い物マラソン', r'セール', r'限定', r'正規品',
        r'公式', r'メーカー保証', r'ギフト', r'プレゼント', r'お祝い',
        r'202[4-7]年?(最新|新型)?', r'最新(版|型)?', r'新型', r'景品玩具', r'景品',
        r'おもちゃ', r'雑貨', r'ぷにぷに', r'ぷるぷる', r'もちもち', r'もちとろ',
        r'柔らかい', r'ストレス解消', r'子供', r'イベント', r'お祭り', r'夏祭り',
        r'詰め合わせ', r'かわいい', r'配送区分[A-Z0-9]', r'メール便', r'定形外'
    ]
    for pw in promo_words:
        cleaned = re.sub(pw, ' ', cleaned, flags=re.IGNORECASE)

    # 区切り文字で前半部を採用
    delimiters = [r'\s*\|\s*', r'\s*｜\s*', r'\s*／\s*', r'\s*/\s*', r'\s*－\s*', r'\s*:\s*', r'\s*：\s*']
    for delim in delimiters:
        parts = re.split(delim, cleaned)
        if parts and len(parts[0].strip()) >= 4:
            cleaned = parts[0]
            break

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
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

class YahooMikkeAPI:
    """Yahoo!ショッピング API (v3) - ホビー・キャラクターグッズ用"""
    
    BASE_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    
    CHARACTERS = [
        "ちいかわ", "スヌーピー", "サンリオ", "ポケモン", "スクイーズ", "パペットスンスン", "スーパーマリオ"
    ]
    
    HOBBIES = [
        "ガチャガチャ コンプリート",
        "シークレットBOX",
        "カプセルトイ 全種セット",
        "マスコット ぬいぐるみ",
        "ブラインドボックス フィギュア",
        "食玩 ウエハース"
    ]

    def __init__(self, client_id: str = "", affiliate_id: str = ""):
        self.client_id = client_id or os.environ.get("YAHOO_CLIENT_ID", "")
        self.affiliate_id = affiliate_id or os.environ.get("YAHOO_AFFILIATE_ID", "")

    def generate_random_keyword(self) -> str:
        char = random.choice(self.CHARACTERS)
        if char in ["スクイーズ", "サンリオ"]:
            return f"{char} グッズ"
        hobby = random.choice(self.HOBBIES)
        return f"{char} {hobby}"

    def search_items(self, query: str = "", hits: int = 30) -> List[Dict[str, Any]]:
        if not self.client_id:
            print("Warning: YAHOO_CLIENT_ID is not set.")
            return []

        if not query:
            query = self.generate_random_keyword()

        params = {
            "appid": self.client_id,
            "query": query,
            "results": min(hits, 30),
            "sort": "-score",
            "in_stock": "true",
            "image_size": 600
        }

        if self.affiliate_id:
            params["affiliate_type"] = "vc"
            params["affiliate_id"] = self.affiliate_id

        try:
            resp = requests.get(
                self.BASE_URL,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                items = []
                for raw in data.get("hits", []):
                    title = raw.get("name", "")
                    clean_title = clean_yahoo_mikke_title(title)
                    price_val = raw.get("price", 0)
                    price_str = f"{price_val:,}円" if isinstance(price_val, (int, float)) else str(price_val)

                    # 画像URL
                    image_url = ""
                    ex_img = raw.get("exImage")
                    if isinstance(ex_img, dict) and ex_img.get("url"):
                        image_url = ex_img.get("url")
                    elif isinstance(raw.get("image"), dict):
                        image_url = raw.get("image", {}).get("medium") or raw.get("image", {}).get("small", "")

                    item_url = raw.get("url", "")
                    item_code = raw.get("code") or raw.get("id") or item_url

                    items.append({
                        "title": title,
                        "clean_title": clean_title,
                        "price": price_str,
                        "affiliateUrl": item_url,
                        "imageUrl": image_url,
                        "itemCode": f"yahoo_{item_code}",
                        "itemCaption": raw.get("description", "") or f"{clean_title}の注目ホビーグッズです。",
                        "platform": "yahoo"
                    })
                return items
            else:
                print(f"Yahoo Mikke API error {resp.status_code}: {resp.text[:150]}")
                return []
        except Exception as e:
            print(f"Yahoo Mikke API request failed: {e}")
            return []
