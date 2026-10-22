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
        # もし @ から始まっていたら除去
        if self.handle.startswith("@"):
            self.handle = self.handle[1:]
            
        self.app_password = (app_password or os.environ.get("BLUESKY_APP_PASSWORD") or os.environ.get("BSKY_APP_PASSWORD") or os.environ.get("BLUESKY_PASSWORD") or "").strip()
        self.pds_url = pds_url.rstrip("/")
        self.access_jwt = None
        self.did = None

    def authenticate(self) -> bool:
        """Bluesky AT Protocol セッションを作成してJWTトークンを取得"""
        if not self.app_password:
            print("Bluesky: BLUESKY_APP_PASSWORD (または BSKY_APP_PASSWORD) が設定されていません。投稿をスキップします。")
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

    def _extract_facets(self, text: str) -> List[Dict[str, Any]]:
        """
        投稿テキストからURLを検出してUTF-8バイトオフセット基準のfacets（リンク情報）を生成。
        Blueskyではリンクをクリック可能にするためにfacetの指定が必要。
        """
        facets = []
        text_bytes = text.encode("utf-8")
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
        Gemini/Groq/GitHub Models 等の利用可能LLMを使って、毎回変化する高CTAなBluesky投稿文を生成。
        万一のフォールバック用テンプレートも複数用意。
        """
        clean_title = item.get("clean_title") or item.get("title") or "話題のアイテム"
        price = item.get("price", "")
        product_url = item.get("url") or item.get("affiliateUrl") or ""

        # LLMによる動的生成を試みる
        generated_text = self._generate_with_llm(clean_title, price, blog_url, product_url, genre)
        if generated_text:
            return generated_text

        # フォールバック：バラエティ豊かな高CTA文面テンプレート
        return self._generate_fallback_text(clean_title, price, blog_url, product_url, genre)

    def _generate_with_llm(self, clean_title: str, price: str, blog_url: str, product_url: str, genre: str) -> Optional[str]:
        """最新Geminiモデル（2.5/3.x）やGroq等を活用して高CTA投稿文を動的生成"""
        # 1. Gemini API (ユーザー規則に準拠した最新モデル群)
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
                "「想像以上に良かった」「迷ってるなら買い」という熱い愛用者の興奮・発見を伝える切り口",
                "「気になってた人必見」「この使い心地はヤバい」という本音検証・リアル体験を強調する切り口",
                "「セールやポイント還元中」「売り切れ前にチェック」というタイムリーなお得感を煽る切り口",
                "「デスク周りや生活が劇的に激変した」「神アイテム認定」というライフハック的ベネフィットの切り口",
                "「かわいすぎて即確保」「手に入るうちに急いで」というファン目線の熱狂的な切り口"
            ]
            chosen_angle = random.choice(angle_hints)

            prompt = f"""あなたはSNSで絶大な支持を集めるインフルエンサー兼レビュアーです。
Bluesky（ブルースカイ）向けに、読者が思わずブログ記事と商品リンクをタップしたくなる【超高CTA・魅力的な投稿文】を1つ作成してください。

【対象商品】: {clean_title}
【価格】: {price}
【ジャンル】: {genre}（ガジェット/ホビー/便利グッズなど）
【今回の切り口】: {chosen_angle}
【ブログ記事URL】: {blog_url}
【商品ページURL】: {product_url}

====================
【投稿作成ルール】
====================
1. 文字数制限: 全体で260文字以内（URLを含む）。長すぎずスマホで一瞬で読める構成に。
2. 構成:
   - 1〜2行の強烈なフック（思わず手が止まる導入）
   - このアイテムの凄さ・おすすめポイント（1〜2行、箇条書きや絵文字活用）
   - 「本音レビュー・詳細はこちら👇」＋ブログURL
   - 「楽天市場で在庫・セールを見る🛒」＋商品URL
   - 関連ハッシュタグ 2〜3個
3. 毎回同じテンプレートにならず、切り口や言葉遣いを生き生きと変えてください。AI臭い定型文（「今回はご紹介します」「いかがでしたでしょうか」等）は一切使わないこと。
4. 出力はBlueskyの投稿テキストのみ。余計な解説・前置き・クォーテーションは絶対に出力しないでください。
"""

            headers = {"Content-Type": "application/json"}
            for model_name in gemini_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.85,
                            "maxOutputTokens": 300
                        }
                    }
                    if any(v in model_name for v in ["2.5", "3.", "3-"]):
                        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
                    resp = requests.post(url, headers=headers, json=payload, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts if p.get("text")).strip()
                        # クォーテーションなどのトリミング
                        text = text.strip('"\'`')
                        if text and len(text) > 30 and (blog_url in text or product_url in text):
                            # URLが欠けていたら補完
                            if blog_url and blog_url not in text:
                                text += f"\n📝詳細レビュー: {blog_url}"
                            if product_url and product_url not in text:
                                text += f"\n🛒楽天でチェック: {product_url}"
                            print(f"Bluesky: Gemini API ({model_name}) により魅力的な投稿文を生成しました")
                            return text
                except Exception as e:
                    continue

        # 2. Groq API フォールバック
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
                        {"role": "system", "content": "あなたはBlueskyで反響を呼ぶプロのレビュアーです。日本語で高CTAな投稿本文のみを前置きなしで出力してください。"},
                        {"role": "user", "content": f"商品「{clean_title}」({price})の紹介ポストを作ってください。\nブログURL: {blog_url}\n商品URL: {product_url}\n両方のURLを必ず含め、熱量ある語り口で260文字以内で作成してください。"}
                    ],
                    "temperature": 0.8
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'`')
                    if text and len(text) > 30:
                        if blog_url and blog_url not in text:
                            text += f"\n📝詳細レビュー: {blog_url}"
                        if product_url and product_url not in text:
                            text += f"\n🛒楽天でチェック: {product_url}"
                        print("Bluesky: Groq API により投稿文を生成しました")
                        return text
            except Exception:
                pass

        return None

    def _generate_fallback_text(self, clean_title: str, price: str, blog_url: str, product_url: str, genre: str) -> str:
        """LLM呼び出し失敗時のランダム高CTAテンプレート群"""
        price_str = f"（{price}）" if price else ""
        
        patterns = [
            # パターン1: 結論ファースト・興奮型
            (
                f"【本音レビュー更新】\n"
                f"気になってた「{clean_title}」{price_str}、実際に使ってみたら想像以上のクオリティでした…！✨\n\n"
                f"リアルな使い勝手＆注意点を徹底検証しました👇\n"
                f"📝ブログで詳しく見る:\n{blog_url}\n\n"
                f"🛒楽天市場の在庫・最安値はこちら:\n{product_url}\n\n"
                f"#おすすめ #楽天市場 #買ってよかった"
            ),
            # パターン2: 疑問解決・お悩み解消型
            (
                f"「{clean_title}」って実際のところ買い？\n"
                f"迷ってる人向けに、メリットも惜しい点もぜんぶ本音でまとめました💡\n\n"
                f"失敗したくない人は購入前にぜひチェックを！👇\n"
                f"📝本音レビュー記事:\n{blog_url}\n\n"
                f"🛒セール情報・口コミを見る:\n{product_url}\n\n"
                f"#注目アイテム #ポイ活 #楽天お買い物マラソン"
            ),
            # パターン3: タイムリー・在庫注意型
            (
                f"SNSやランキングで今話題の「{clean_title}」✨\n"
                f"この使い心地は一度使うと手放せないやつです…！{price_str}\n\n"
                f"リアルな使用感レビューを公開しました👇\n"
                f"📝検証ブログを見る:\n{blog_url}\n\n"
                f"売り切れ前にチェック👇\n"
                f"🛒楽天公式ページ:\n{product_url}\n\n"
                f"#人気商品 #トレンド #新生活"
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
