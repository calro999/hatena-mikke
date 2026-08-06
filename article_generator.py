from typing import Dict, Any

def sanitize_llm_output(content, valid_affiliate_url=""):
    if not content:
        return ""
    import re
    url_pattern = r'https?://[^\s"<>\'\)]+'
    def replace_url(match):
        found_url = match.group(0)
        if "room.rakuten.co.jp" in found_url or "hb.afl.rakuten.co.jp" in found_url or ("rakuten.co.jp" in found_url and "affiliateId" in found_url) or "hatena.ne.jp" in found_url:
            return found_url
        return valid_affiliate_url if valid_affiliate_url else "https://room.rakuten.co.jp/jack555/items"
    
    sanitized = re.sub(url_pattern, replace_url, content)
    sanitized = sanitized.replace("Amazon", "楽天市場").replace("アマゾン", "楽天市場").replace("ヤフー", "楽天市場").replace("Yahoo!", "楽天市場")
    return sanitized

class ArticleGenerator:
    def __init__(self, model_id: str = ""):
        pass

    def load_model(self):
        print("ArticleGenerator: Initialized using online free API router (No local models loaded).")
        pass

    def translate_synopsis(self, text: str) -> str:
        return text

    def generate_review_article(self, item: Dict[str, Any]) -> str:
        title = item.get("title", "")
        clean_title = item.get("clean_title", title)
        price = item.get("price", "")
        url = item.get("affiliateUrl") or item.get("url", "")
        caption = item.get("caption", "")

        prompt = f"""あなたは「新作ホビー・ガチャ・食玩の最速予約・在庫復活」を伝えるプロの速報編集者です。
以下の楽天市場ホビー商品の情報を元に、読者（コレクター）に向けた速報ブログ記事を執筆してください。
自分語りやエッセイ風の書き出し、不自然なポエムは【絶対に禁止】です。

【商品名】: {title}
【価格】: {price}
【商品の説明】: {caption}
【アフィリエイトURL】: {url}

【出力の構成ルール（厳格遵守）】:
① 記事のタイトル（【速報】【在庫復活】などの煽り文句＋商品名）を <h2> タグで囲んで出力してください。
② どんなキャラクターのどんな商品なのか、一目でわかる簡潔な説明（2〜3行程度）を書いてください。
③ コレクター必見の魅力やおすすめポイントを、必ず <ul> と <li> タグを使った【3つの箇条書き】にしてください。
④ 最後に「人気キャラのため一瞬で売り切れる可能性があります！急いでチェックしてください！」という強い購入への誘導文を書いてください。

【執筆の厳格なルール】:
1. 出力はブログの【本文HTMLのみ】にしてください。余計な挨拶や解説は絶対に1文字も含めないでください。
2. スマホで読みやすいように、重要な部分やアピールポイントは適宜 <b> タグで囲んで太字に強調してください。
3. すべてHTMLタグを使用して整形した状態で出力してください（Markdown記法ではなく直接HTMLタグを使用すること）。
4. 【厳禁事項】: Amazon, Yahoo, 他社ECサイト, メーカー公式サイト等のURLや名称は絶対に含めないでください。商品リンクは提供したアフィリエイトURLのみを使用してください。
"""

        generators = [
            ("Groq API", self._generate_with_groq),
            ("Gemini API (Free Tier)", self._generate_with_gemini),
            ("GitHub Models API (Free for Actions/PAT)", self._generate_with_github_models),
            ("OpenRouter Free API", self._generate_with_openrouter),
            ("Hugging Face API (Free Tier)", self._generate_with_huggingface),

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
            print("WARNING: All free LLM APIs failed or are rate-limited. Generating dynamic high-quality HTML review article based on item metadata.")
            raw_article = f"""<h2>【速報】{clean_title} の予約受付がスタート！</h2>
<p>大注目の最新アイテム <b>{clean_title}</b> が楽天市場で予約開始されました！ファンにはたまらない魅力が詰まった大人気ホビーです。</p>
<ul>
  <li><b>圧倒的な造形美</b>：細部までこだわり抜かれたハイクオリティなクオリティを実現！</li>
  <li><b>豪華セット仕様</b>：ファン必見のコレクターズアイテム仕様！</li>
  <li><b>限定デザイン</b>：クオリティが高く満足度の高い完成度！</li>
</ul>
<p><b>人気キャラのため一瞬で売り切れる可能性があります！急いでチェックしてください！</b></p>"""

        # メタ文言のクリーニング
        raw_article = re.sub(r"^(はい、|承知いたしました。|以下が商品紹介記事です。|以下に記事を出力します。|以下が執筆した記事です。)\s*", "", raw_article)
        meta_markers = ["以上のように", "このように、", "アフィリエイトリンクへの"]
        for marker in meta_markers:
            if marker in raw_article:
                raw_article = raw_article.split(marker)[0].rstrip()

        # Step 2: 誤字脱字チェック & SEO / AI-SEO / GEO ブラッシュアップ工程
        polished_article = self.proofread_and_optimize(raw_article, title)
        if polished_article and len(polished_article.strip()) > 100:
            raw_article = polished_article

        # Step 3: 途中切れ・力尽き防止チェック & 完結補正
        raw_article = self.ensure_complete_article(raw_article)

        # すでにHTMLで出力されているため、Markdown変換は行わずそのまま返します
        # リンクの target="_blank" 付与処理のみ実行します
        def add_target_blank(match):
            tag = match.group(0)
            if 'target=' not in tag:
                tag = tag.replace('<a ', '<a target="_blank" rel="noopener noreferrer" ')
            return tag
            
        html_output = re.sub(r'<a\s+[^>]*>', add_target_blank, raw_article)
        return sanitize_llm_output(html_output, url)

    def proofread_and_optimize(self, content: str, title: str) -> str:
        """誤字脱字の最終チェックと、SEO, AI-SEO (AI検索対応), GEO (Generative Engine Optimization) 的なブラッシュアップを行う工程。"""
        proofread_prompt = f"""以下のホビー速報ブログ原稿（HTML形式）に対して、誤字脱字チェックとSEO・AI-SEO・GEO最適化を行い、最高品質の完成原稿にブラッシュアップしてください。

【対象商品名】: {title}

【原稿】:
{content}

【ブラッシュアップ要件（絶対遵守）】:
1. 誤字脱字・不自然なHTML構造・日本語の誤りを校正してください。
2. SEO & AI-SEO (GEO) 最適化:
   - 読者（コレクター）が知りたい商品の魅力・在庫情報をHTMLタグ（<h2>, <ul>, <li>, <b>）で明確に構造化してください。
   - 不要なポエムや挨拶文を排除し、ファクトと商品の価値を分かりやすく記述してください。
3. 途中で途切れることのないよう、完全に完結させてください。
4. HTML形式のまま、余計な前置き・解説なしで本文のみを出力してください。
"""
        generators = [
            ("Groq API", self._generate_with_groq),
            ("Gemini API (Proofread)", self._generate_with_gemini),
            ("GitHub Models API (Proofread)", self._generate_with_github_models),
            ("OpenRouter Free API (Proofread)", self._generate_with_openrouter),
        ]

        for name, gen_fn in generators:
            try:
                print(f"Attempting proofread and SEO/GEO optimization with {name}...")
                res = gen_fn(proofread_prompt)
                if res and len(res.strip()) > 100:
                    res_cleaned = re.sub(r"^(はい、|承知いたしました。|以下が校正後の記事です。|以下がブラッシュアップ後の原稿です。)\s*", "", res.strip())
                    print(f"Successfully proofread and optimized article with {name}!")
                    return res_cleaned
            except Exception as e:
                print(f"Proofread failed with {name}: {e}. Continuing with original.")

        return content

    def ensure_complete_article(self, content: str) -> str:
        """文章が途中で力尽きて切れている場合に、末尾をきれいに修復・完結させる。"""
        content = content.strip()
        valid_endings = ("。", "！", "？", "!", "?", "</p>", "</ul>", "</div>", "</b>", "</i>")
        
        if not content.endswith(valid_endings):
            print("WARNING: Article detected as truncated/incomplete at the end. Truncating incomplete part and closing tags properly.")
            last_period = max(content.rfind("。"), content.rfind("！"), content.rfind("</p>"), content.rfind("</ul>"))
            if last_period > len(content) * 0.5:
                content = content[:last_period + 1]
            else:
                content = content + "</p>"

        if "急いでチェックしてください" not in content and "ご覧ください" not in content:
            content += "<p><b>人気キャラのため一瞬で売り切れる可能性があります！急いでチェックしてください！</b></p>"

        return content

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
                "maxOutputTokens": 4000
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

    
    def _generate_with_groq(self, prompt: str) -> Optional[str]:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192"]
        for model in models:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    text = res.json()["choices"][0]["message"]["content"]
                    if text and len(text.strip()) > 30:
                        return text.strip()
            except Exception as e:
                print(f"Groq ({model}) error: {e}")
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
