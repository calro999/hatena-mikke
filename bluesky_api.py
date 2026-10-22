import os
import re
import json
import random
import datetime
import requests
from typing import Dict, Any, Optional, List

class BlueskyAPI:
    """Bluesky (AT Protocol) 投稿クライアント"""
    
    def __init__(self, handle: Optional[str] = None, app_password: Optional[str] = None, pds_url: str = "https://bsky.social"):
        self.handle = (handle or os.environ.get("BLUESKY_HANDLE") or os.environ.get("BSKY_HANDLE") or "mikke-hobby.bsky.social").strip()
        if self.handle.startswith("@"):
            self.handle = self.handle[1:]
            
        self.app_password = (app_password or os.environ.get("BLUESKY_APP_PASSWORD") or os.environ.get("BSKY_APP_PASSWORD") or os.environ.get("BLUESKY_PASSWORD") or "").strip()
        self.pds_url = pds_url.rstrip("/")
        self.access_jwt = None
        self.did = None

    def authenticate(self) -> bool:
        """Bluesky AT Protocol セッションを作成してJWTトークンを取得"""
        if not self.app_password:
            print("Bluesky: BLUESKY_APP_PASSWORD が設定されていません。投稿をスキップします。")
            return False

        url = f"{self.pds_url}/xrpc/com.atproto.server.createSession"
        payload = {
            "identifier": self.handle,
            "password": self.app_password
        }

        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                self.access_jwt = data.get("accessJwt")
                self.did = data.get("did")
                print(f"Bluesky: 認証成功 (DID: {self.did}, Handle: {self.handle})")
                return True
            else:
                print(f"Bluesky: 認証失敗 HTTP {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"Bluesky: 認証例外発生: {e}")
            return False

    def shorten_url(self, url: str) -> str:
        """長いアフィリエイトURL等をTinyURLで安全に短縮（Blueskyの300 grapheme制限対策）"""
        if not url or len(url) < 35:
            return url
        try:
            resp = requests.get(f"https://tinyurl.com/api-create.php?url={url}", timeout=6)
            if resp.status_code == 200 and resp.text.startswith("http"):
                shortened = resp.text.strip()
                print(f"Bluesky: URLを短縮しました ({len(url)}文字 -> {len(shortened)}文字)")
                return shortened
        except Exception as e:
            print(f"Bluesky: URL短縮スキップ (元URLを使用): {e}")
        return url

    def _extract_facets(self, text: str) -> List[Dict[str, Any]]:
        """
        投稿テキストからURLを検出してUTF-8バイトオフセット基準のfacets（リンク情報）を生成。
        """
        facets = []
        url_pattern = re.compile(r'https?://[^\s]+')
        
        for match in url_pattern.finditer(text):
            url = match.group(0)
            byte_start = len(text[:match.start()].encode("utf-8"))
            byte_end = len(text[:match.end()].encode("utf-8"))
            
            facets.append({
                "index": {
                    "byteStart": byte_start,
                    "byteEnd": byte_end
                },
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url
                    }
                ]
            })
        return facets

    def generate_post_text(self, item: Dict[str, Any], blog_url: str, genre: str = "gadget") -> str:
        """
        Gemini等の利用可能LLMを使って、毎回変化する高CTAなBluesky投稿文を生成。
        300文字制限を厳守するため、URLを短縮し全体を安全な長さに収める。
        """
        clean_title = item.get("clean_title") or item.get("title") or "話題のアイテム"
        price = item.get("price", "")
        raw_product_url = item.get("url") or item.get("affiliateUrl") or ""

        # 長いURLは短縮して文字数を圧縮
        short_blog_url = self.shorten_url(blog_url)
        short_product_url = self.shorten_url(raw_product_url)

        # LLMによる動的生成
        generated_text = self._generate_with_llm(clean_title, price, short_blog_url, short_product_url, genre)
        if generated_text:
            cleaned = self._ensure_length_and_links(generated_text, short_blog_url, short_product_url)
            if cleaned:
                return cleaned

        # フォールバック
        fallback_text = self._generate_fallback_text(clean_title, price, short_blog_url, short_product_url, genre)
        return self._ensure_length_and_links(fallback_text, short_blog_url, short_product_url)

    def _ensure_length_and_links(self, text: str, blog_url: str, product_url: str) -> str:
        """Blueskyの300 grapheme (文字数) 制限を絶対に超えないよう整形・調整"""
        # リンクが含まれているか確認
        if blog_url and blog_url not in text:
            text += f"\n📝詳細: {blog_url}"
        if product_url and product_url not in text:
            text += f"\n🛒楽天: {product_url}"

        # 280文字以内に収めるための安全トリミング
        if len(text) > 280:
            lines = text.split("\n")
            # リンク行以外を削る
            kept_lines = []
            for line in lines:
                if blog_url in line or product_url in line:
                    kept_lines.append(line)
                elif len("\n".join(kept_lines + [line])) < 190:
                    kept_lines.append(line)
            text = "\n".join(kept_lines)

        return text.strip()

    def _generate_with_llm(self, clean_title: str, price: str, blog_url: str, product_url: str, genre: str) -> Optional[str]:
        """最新Geminiモデル（2.5/3.x）等を活用して高CTA投稿文を動的生成"""
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if gemini_api_key:
            gemini_models = [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-3.5-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-3-flash",
                "gemini-2.0-flash",
                "gemini-2.5-pro"
            ]
            
            angle_hints = [
                "「想像以上に良かった」「迷ってるなら買い」という熱い興奮を伝える切り口",
                "「気になってた人必見」「この使い心地は沼」という本音レビューを伝える切り口",
                "「在庫あるうちに急いで！」「完売前に要チェック」という緊急感を煽る切り口",
                "「生活やデスク周りが劇的に変わった」というベネフィットの切り口",
                "「可愛すぎて即確保」「手に入るうちに急いで」というファン目線の切り口"
            ]
            chosen_angle = random.choice(angle_hints)

            prompt = f"""あなたはSNSで大人気のインフルエンサー兼レビュアーです。
Bluesky向けに、読者が思わずブログ記事と商品リンクをタップしたくなる【超高CTAな投稿文】を1つ作成してください。

【対象商品】: {clean_title}
【価格】: {price}
【ジャンル】: {genre}
【今回の切り口】: {chosen_angle}
【ブログ記事URL】: {blog_url}
【商品ページURL】: {product_url}

====================
【厳格な文字数ルール】
====================
※Blueskyは300文字上限のため、【URLを含めて全体で200文字以内】で簡潔かつ強烈に作成してください！
構成案：
1行目：思わず手が止まるインパクトある一言
2行目：おすすめポイント・熱量
3行目：本音レビュー記事👉 {blog_url}
4行目：楽天公式・在庫を見る🛒 {product_url}
5行目：#ハッシュタグ（1〜2個）

余計な解説・前置き・引用符は一切出力せず、投稿テキストのみを日本語で出力してください。
"""

            headers = {"Content-Type": "application/json"}
            for model_name in gemini_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.85,
                            "maxOutputTokens": 200
                        }
                    }
                    if any(v in model_name for v in ["2.5", "3.", "3-"]):
                        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
                    resp = requests.post(url, headers=headers, json=payload, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts if p.get("text")).strip()
                        text = text.strip('"\'`')
                        if text and len(text) > 30:
                            print(f"Bluesky: Gemini API ({model_name}) により魅力的な投稿文を生成しました")
                            return text
                except Exception:
                    continue

        # Groq API フォールバック
        groq_api_key = os.environ.get("GROQ_API_KEY")
        if groq_api_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "あなたはBlueskyで反響を呼ぶプロのレビュアーです。URLを含めて全体で200文字以内の高CTAな投稿本文のみを前置きなしで出力してください。"},
                        {"role": "user", "content": f"商品「{clean_title}」({price})の紹介ポストを作ってください。\nブログURL: {blog_url}\n商品URL: {product_url}\n両方のURLを必ず含めてください。"}
                    ],
                    "temperature": 0.8
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'`')
                    if text and len(text) > 30:
                        print("Bluesky: Groq API により投稿文を生成しました")
                        return text
            except Exception:
                pass

        return None

    def _generate_fallback_text(self, clean_title: str, price: str, blog_url: str, product_url: str, genre: str) -> str:
        """LLM呼び出し失敗時のランダム高CTAテンプレート群（250文字以内）"""
        price_str = f"（{price}）" if price else ""
        
        patterns = [
            (
                f"気になってた「{clean_title}」{price_str}、実際に使ったら想像以上によかった…！✨\n\n"
                f"📝本音レビュー検証:\n{blog_url}\n\n"
                f"🛒楽天の在庫・最安値:\n{product_url}\n\n"
                f"#おすすめ #楽天市場"
            ),
            (
                f"「{clean_title}」って実際のところ買い？\n"
                f"メリットも気になる点もぜんぶ本音でまとめました💡\n\n"
                f"📝詳細レビューはこちら👇\n{blog_url}\n\n"
                f"🛒セール・口コミを見る👇\n{product_url}\n\n"
                f"#買ってよかった #楽天お買い物マラソン"
            ),
            (
                f"話題の「{clean_title}」✨\n"
                f"手に入るうちに急いで！🏃💨\n\n"
                f"📝検証記事はこちら:\n{blog_url}\n\n"
                f"🛒楽天市場公式ページ:\n{product_url}\n\n"
                f"#人気アイテム #注目"
            )
        ]
        return random.choice(patterns)

    def post(self, text: str) -> bool:
        """Blueskyに投稿（テキスト＋facetsによるハイパーリンク）"""
        if not self.access_jwt or not self.did:
            if not self.authenticate():
                print("Bluesky: 認証されていないため投稿を中止します。")
                return False

        facets = self._extract_facets(text)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now_iso,
        }
        if facets:
            record["facets"] = facets

        url = f"{self.pds_url}/xrpc/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {self.access_jwt}",
            "Content-Type": "application/json"
        }
        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.post",
            "record": record
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                post_data = resp.json()
                print(f"🎉 Blueskyへの投稿に成功しました！ URI: {post_data.get('uri')}")
                return True
            else:
                print(f"Bluesky投稿失敗 HTTP {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"Bluesky投稿例外発生: {e}")
            return False
