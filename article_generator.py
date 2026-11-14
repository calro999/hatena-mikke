import os
import re
import requests
import json
import time
import random
from typing import Dict, Any, Optional, Tuple

def sanitize_llm_output(content, valid_affiliate_url=""):
    if not content:
        return ""
    url_pattern = r'https?://[^\s"<>\'\)]+'
    def replace_url(match):
        found_url = match.group(0)
        allowed_domains = ["room.rakuten.co.jp", "hb.afl.rakuten.co.jp", "rakuten.co.jp", "hatena.ne.jp", "kurakaji.vercel.app", "croud-travel.pages.dev", "tigyu-mens.vercel.app", "qualia-navi.vercel.app"]
        if any(d in found_url for d in allowed_domains):
            return found_url
        return valid_affiliate_url if valid_affiliate_url else "https://room.rakuten.co.jp/jack555/items"
    
    sanitized = re.sub(url_pattern, replace_url, content)
    sanitized = sanitized.replace("Amazon", "楽天市場").replace("アマゾン", "楽天市場").replace("ヤフー", "楽天市場").replace("Yahoo!", "楽天市場")
    return sanitized

class ArticleGenerator:
    def __init__(self, model_id: str = ""):
        pass

    def load_model(self):
        print("ArticleGenerator: Initialized using online free API router.")
        pass

    def translate_synopsis(self, text: str) -> str:
        return text

    def generate_review_article(self, item: Dict[str, Any]) -> Tuple[str, str, str]:
        """
        Gemini などの LLM を用いて、
        (title, description_html, content_html) を生成して返す。
        """
        title = item.get("title", "")
        clean_title = item.get("clean_title", title)
        price = item.get("price", "")
        url = item.get("affiliateUrl") or item.get("url", "")
        caption = item.get("caption", "")

        prompt = f"""あなたは「新作ホビー・ガチャ・食玩・人気キャラクターグッズ」の魅力を熱量たっぷりに伝えるプロのレビューライターです。
以下の楽天市場ホビー商品の情報を元に、読者が検索結果やSNSから流入した瞬間に心を奪われ、「絶対に欲しい！」と衝動買いしたくなる記事を作成してください。

【対象商品情報】
正式商品名: {title}
製品名略称: {clean_title}
価格: {price}
商品の説明・詳細:
{caption}

【必須の出力フォーマット（厳格遵守）】
必ず以下のセクション区切り記号を使って出力してください。

---TITLE---
商品の魅力・ワクワク感・ベネフィットが一目で突き刺さる【完全独自のブログ記事タイトル】を1つだけ出力。
※「【話題】」「【速報】」「【本音レビュー】」「まとめ」などのテンプレート接頭辞は【絶対に使用禁止】です。
※不自然な空白や途切れを絶対に作らず、30文字以内の自然で引きのある日本語にしてください。

---DESCRIPTION---
検索エンジンやブログ一覧の「ディスクリプション（抜粋）」として表示される、記事冒頭のリード文（3行・約100〜130文字）。
※記号の羅列やアフィリエイト文言は一切書かず、どんなキャラクターのどんな魅力的な商品なのか、なぜ今手に入れるべきなのかを最初の3行で魅力的に伝えてください。

---CONTENT---
読者が引き込まれる本文HTML（800〜1200文字程度）。
見出し（<h3>）、段落（<p>）、箇条書き（<ul><li>）、太字（<b>）を使って美しく整形してください。
造形の可愛さ・コレクションや開封のワクワク感・完売前の購入推奨を熱く感情豊かに執筆してください。
前置きや挨拶、解説文は一切不要です。
"""

        generators = [
            ("Gemini API (Free Tier)", self._generate_with_gemini),
            ("Groq API", self._generate_with_groq),
            ("GitHub Models API (Free for Actions/PAT)", self._generate_with_github_models),
            ("OpenRouter Free API", self._generate_with_openrouter),
        ]

        raw_text = None
        for name, gen_fn in generators:
            try:
                print(f"Attempting article generation with {name}...")
                res = gen_fn(prompt)
                if res and len(res.strip()) > 300:
                    raw_text = res.strip()
                    print(f"Successfully generated article using {name}!")
                    break
            except Exception as e:
                print(f"Error calling {name}: {e}. Trying next fallback...")

        parsed_title, parsed_desc, parsed_content = self._parse_generated_output(raw_text, clean_title, title, price)
        return parsed_title, parsed_desc, parsed_content

    def _parse_generated_output(self, raw_text: Optional[str], clean_title: str, title: str, price: str) -> Tuple[str, str, str]:
        if raw_text and "---TITLE---" in raw_text and "---DESCRIPTION---" in raw_text and "---CONTENT---" in raw_text:
            try:
                parts = raw_text.split("---TITLE---")[1].split("---DESCRIPTION---")
                gen_title = parts[0].strip().replace("\n", " ")
                gen_title = re.sub(r'^(TITLE:|タイトル[:：]|【.*?】)\s*', '', gen_title).strip()
                gen_title = re.sub(r'\s+', ' ', gen_title)

                subparts = parts[1].split("---CONTENT---")
                gen_desc = subparts[0].strip()
                gen_desc = re.sub(r'^(DESCRIPTION:|ディスクリプション[:：])\s*', '', gen_desc).strip()

                gen_content = subparts[1].strip()
                gen_content = re.sub(r'^(CONTENT:|本文[:：])\s*', '', gen_content).strip()

                if len(gen_title) > 42:
                    for sep in ['！', '!', '？', '?', ' ', '　', '。']:
                        if sep in gen_title[:38]:
                            idx = gen_title[:38].rfind(sep)
                            if idx > 15:
                                gen_title = gen_title[:idx+1].strip()
                                break
                if not gen_title:
                    gen_title = f"{clean_title}の魅力と見逃せない注目ポイント"

                desc_html = f'<p class="entry-lead" style="font-size: 16px; line-height: 1.8; color: #333; margin-bottom: 24px;">{gen_desc}</p>'
                return gen_title, desc_html, gen_content
            except Exception as e:
                print(f"Error parsing LLM output: {e}. Falling back to default layout.")

        # フォールバック
        fallback_title = f"可愛さ満点！『{clean_title}』の魅力と見逃せない注目ポイント"
        fallback_desc = f'<p class="entry-lead" style="font-size: 16px; line-height: 1.8; color: #333; margin-bottom: 24px;">大注目の最新アイテム『{clean_title}』が登場！ファン必見の細部までこだわり抜かれた造形とデザインの魅力を徹底紹介。お部屋のインテリアやコレクションにぴったりの逸品です。</p>'
        fallback_content = f"""<h3>細部までこだわり抜かれた圧倒的な造形美と再現度</h3>
<p>キャラクターの魅力を余すところなく落とし込んだ細やかなディテールが魅力。お部屋のデスクや棚に飾るだけで、パッと空間が華やぎます。コレクションアイテムとしても非常に完成度が高く、ファンなら思わずニンマリしてしまう仕上がりです。</p>

<h3>集めて楽しい！開けてワクワクの特別感</h3>
<p>日常にちょっとした癒やしやワクワクをプラスしてくれるデザイン。プレゼントや自分へのご褒美としても選ばれており、実物を手にしたときの満足感はひとしおです。</p>

<h3>完売注意！在庫があるうちに今すぐチェック</h3>
<p><b>人気アイテムのため、早期に品切れ・予約終了となる可能性が非常に高いです！</b> 気になっている方は、在庫が揃っている今のうちに楽天市場公式ショップでぜひチェックしてみてください！</p>"""
        return fallback_title, fallback_desc, fallback_content

    def _generate_with_gemini(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        
        models = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-2.5-pro",
            "gemini-3.1-pro"
        ]
        headers = {"Content-Type": "application/json"}
        for model_name in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": "あなたはプロのホビーレビュー編集者です。指示された出力フォーマット（---TITLE---, ---DESCRIPTION---, ---CONTENT---）を厳格に守り日本語で出力してください。\n\n" + prompt
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 3000
                    }
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    candidate = data.get("candidates", [{}])[0]
                    parts = candidate.get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if p.get("text")).strip()
                    if text and len(text) > 200 and "---TITLE---" in text:
                        print(f"Successfully generated article via Gemini API ({model_name}).")
                        return text
            except Exception as e:
                print(f"Gemini API ({model_name}) error: {e}")
        return None

    def _generate_with_groq(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "あなたはプロのホビーレビュー編集者です。---TITLE---, ---DESCRIPTION---, ---CONTENT---の区切りを守り日本語で出力してください。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.8
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=20)
                if res.status_code == 200:
                    text = res.json()["choices"][0]["message"]["content"]
                    if text and len(text.strip()) > 200 and "---TITLE---" in text:
                        return text.strip()
            except Exception as e:
                print(f"Groq ({model}) error: {e}")
        return None

    def _generate_with_github_models(self, prompt: str) -> Optional[str]:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            return None
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "あなたはプロのホビーレビュー編集者です。---TITLE---, ---DESCRIPTION---, ---CONTENT---の区切りを守り日本語で出力してください。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None

    def _generate_with_openrouter(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "google/gemma-2-9b-it:free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None
