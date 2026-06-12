import os
import re
import requests
import json
import time
import urllib.parse
from typing import Dict, Any, Optional, List

class ArticleGenerator:
    def __init__(self, model_id: str = ""):
        pass

    def load_model(self):
        print("ArticleGenerator: Initialized using online free API router (No local models loaded).")
        pass

    def translate_synopsis(self, text: str) -> str:
        # 呼び出しは不要となりましたが、互換性のためにメソッドは残しておきます
        return text

    def generate_review_article(self, item: Dict[str, Any]) -> str:
        title = item.get("title", "")
        clean_title = item.get("clean_title", title)
        price = item.get("price", "")
        url = item.get("url", "")
        caption = item.get("caption", "")

        prompt = f"""あなたは「新作ホビー・ガチャ・食玩の最速予約・在庫復活」を伝えるプロの速報編集者です。
以下の楽天市場ホビー商品の情報を元に、読者（コレクター）に向けた速報ブログ記事を執筆してください。
自分語りやエッセイ風の書き出し、不自然なポエムは【絶対に禁止】です。

【商品名】: {title}
【価格】: {price}
【商品の説明】: {caption}

【出力の構成ルール（厳格遵守）】:
① 記事のタイトル（【速報】【在庫復活】などの煽り文句＋商品名）を <h2> タグで囲んで出力してください。
② どんなキャラクターのどんな商品なのか、一目でわかる簡潔な説明（2〜3行程度）を書いてください。
③ コレクター必見の魅力やおすすめポイントを、必ず <ul> と <li> タグを使った【3つの箇条書き】にしてください。
④ 最後に「人気キャラのため一瞬で売り切れる可能性があります！急いでチェックしてください！」という強い購入への誘導文を書いてください。

【執筆の厳格なルール】:
1. 出力はブログの【本文HTMLのみ】にしてください。余計な挨拶や解説（「はい、以下が記事です」など）は絶対に1文字も含めないでください。
2. スマホで読みやすいように、重要な部分やアピールポイントは適宜 <b> タグで囲んで太字に強調してください。
3. すべてHTMLタグを使用して整形した状態で出力してください（Markdown記法ではなく直接HTMLタグを使用すること）。
"""

        generators = [
            ("Gemini API (Free Tier)", self._generate_with_gemini),
            ("GitHub Models API (Free for Actions/PAT)", self._generate_with_github_models),
            ("OpenRouter Free API", self._generate_with_openrouter),
            ("Hugging Face API (Free Tier)", self._generate_with_huggingface),
            ("Pollinations AI Free (No Key Required)", self._generate_with_pollinations),
        ]

        raw_article = None
        for name, gen_fn in generators:
            try:
                print(f"Attempting article generation with {name}...")
                res = gen_fn(prompt)
                if res and len(res.strip()) > 100:
                    raw_article = res.strip()
                    print(f"Successfully generated article using {name}!")
                    break
                else:
                    print(f"{name} returned empty or too short response. Trying next fallback...")
            except Exception as e:
                print(f"Error calling {name}: {e}. Trying next fallback...")

        if not raw_article:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                raise RuntimeError("All free LLM APIs failed to generate a valid review article in GitHub Actions.")
            else:
                print("WARNING: All free LLM APIs failed or are rate-limited. Since this is a local dry-run, generating dummy review text.")
                raw_article = f"""<h2>【速報】{clean_title} の予約受付がスタート！</h2>
<p>大注目の最新アイテム <b>{clean_title}</b> が楽天市場で予約開始されました！ファンにはたまらない魅力が詰まった大人気ホビーです。</p>
<ul>
  <li><b>圧倒的な造形美</b>：細部までこだわり抜かれたハイクオリティなクオリティを実現！</li>
  <li><b>豪華セット仕様</b>：全種類コンプリート可能なファン必見のパッケージ構成！</li>
  <li><b>限定デザイン</b>：ここでしか手に入らないプレミアムなコレクターズアイテム！</li>
</ul>
<p><b>人気キャラのため一瞬で売り切れる可能性があります！急いでチェックしてください！</b></p>"""

        # メタ文言のクリーニング
        raw_article = re.sub(r"^(はい、|承知いたしました。|以下が商品紹介記事です。|以下に記事を出力します。|以下が執筆した記事です。)\s*", "", raw_article)
        meta_markers = ["以上のように", "このように、", "アフィリエイトリンクへの"]
        for marker in meta_markers:
            if marker in raw_article:
                raw_article = raw_article.split(marker)[0].rstrip()

        # すでにHTMLで出力されているため、Markdown変換は行わずそのまま返します
        # リンクの target="_blank" 付与処理のみ実行します
        def add_target_blank(match):
            tag = match.group(0)
            if 'target=' not in tag:
                tag = tag.replace('<a ', '<a target="_blank" rel="noopener noreferrer" ')
            return tag
            
        html_output = re.sub(r'<a\s+[^>]*>', add_target_blank, raw_article)
        return html_output

    def _generate_with_gemini(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": "あなたはホビー速報ブログのプロ編集者です。指示された厳格なルールを遵守し、余計な挨拶や解説を一切含まないHTML本文のみを出力します。\n\n" + prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2000
            }
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except KeyError:
                return None
        return None

    def _generate_with_github_models(self, prompt: str) -> Optional[str]:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            return None
        
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "あなたはホビー速報ブログのプロ編集者です。指示されたルールを厳格に守り、日本語で前置き・後書きなしでHTML本文のみを出力してください。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            try:
                return resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                return None
        return None

    def _generate_with_openrouter(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemma-2-9b-it:free",
            "messages": [
                {"role": "system", "content": "あなたはホビー速報ブログのプロ編集者です。指示された厳格なルールを守り、余計な解説を一切含まない日本語のHTML本文のみを出力します。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except KeyError:
                return None
        return None

    def _generate_with_huggingface(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("HF_API_KEY") or os.environ.get("HF_TOKEN")
        if not api_key:
            return None
        
        model_id = "Qwen/Qwen2.5-72B-Instruct"
        url = f"https://api-inference.huggingface.co/models/{model_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": f"<|im_start|>system\nあなたはホビー速報ブログのプロ編集者です。日本語で余計な前置きや後書きなしに、HTML本文のみを出力します。<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
            "parameters": {
                "max_new_tokens": 1500,
                "temperature": 0.7
            }
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        if resp.status_code == 200:
            data = resp.json()
            try:
                text = data[0]["generated_text"]
                if "assistant\n" in text:
                    return text.split("assistant\n")[-1]
                return text
            except (KeyError, IndexError):
                return None
        return None

    def _generate_with_pollinations(self, prompt: str) -> Optional[str]:
        url = "https://text.pollinations.ai/"
        models = ["openai", "qwen", "mistral"]
        
        for attempt, model in enumerate(models):
            payload = {
                "messages": [
                    {"role": "system", "content": "あなたはホビー速報ブログのプロ編集者です。指示されたルールを厳格に守り、日本語で前置き・後書きなしでHTML本文のみを出力してください。"},
                    {"role": "user", "content": prompt}
                ],
                "model": model
            }
            try:
                resp = requests.post(url, json=payload, timeout=25)
                if resp.status_code == 200 and len(resp.text.strip()) > 100:
                    return resp.text
                elif resp.status_code == 429:
                    time.sleep(attempt+2)
            except Exception:
                pass
            
        return None
