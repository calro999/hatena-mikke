# -*- coding: utf-8 -*-
"""
外部特化メディア（クラカジ、旅宿クラウド、チー牛メンズ、Qualia Navi）への
親和性スコアリングおよび自然な内部・外部リンク自動生成モジュール
"""
import re
from typing import Dict, Any, Optional

EXTERNAL_TARGETS = [
    {
        "domain": "kurakaji.vercel.app",
        "url": "https://kurakaji.vercel.app/articles/cluster/panel-heater-vs-ceramic.html",
        "anchor_title": "【徹底比較】パネルヒーター vs セラミックファンヒーター！電気代と暖まり方の違い検証（クラカジ）",
        "keywords": ["ヒーター", "暖房", "こたつ", "加湿器", "電気代", "サーキュレーター", "乾燥", "温風", "電気毛布", "ストーブ"],
        "callout_title": "⚡ 家電の電気代・暖房器具の賢い選び方",
        "desc": "デスクワークや冬の部屋全体の暖房コストを抑えるなら、家電の比較検証メディア「クラカジ」による詳細な実測テストも非常に参考になります。"
    },
    {
        "domain": "croud-travel.pages.dev",
        "url": "https://croud-travel.pages.dev/winter-kanagawa-hakone-yumoto-ashinoko-shrine-fuji-stay/",
        "anchor_title": "【冬の箱根湯本＆芦ノ湖・名湯宿ガイド】澄み渡る白雪富士の絶景と温泉（旅宿クラウド）",
        "keywords": ["トラベル", "旅行", "出張", "ポーチ", "圧縮", "スーツケース", "ホテル", "温泉", "宿泊", "パッキング", "移動", "キャリー"],
        "callout_title": "✈️ 旅・出張を快適にするおすすめ宿・滞在情報",
        "desc": "荷物をスマートにパッキングして出かける冬の温泉旅行やワーケーション。滞在先の空間や名湯選びには、宿泊特化メディア「旅宿クラウド」の厳選ガイドが役立ちます。"
    },
    {
        "domain": "tigyu-mens.vercel.app",
        "url": "https://tigyu-mens.vercel.app/posts/mens-cleansing-oil-blackhead-pore",
        "anchor_title": "洗顔じゃ無理！小鼻の黒ずみを溶かす男のクレンジングオイル徹底攻略（チー牛メンズ）",
        "keywords": ["シェーバー", "髭剃り", "ヒゲ", "メンズ", "洗顔", "毛穴", "男", "グルーミング", "身だしなみ", "カミソリ", "脱毛器", "バリカン"],
        "callout_title": "💈 男の清潔感を劇的に引き上げる身だしなみ攻略",
        "desc": "シェーバーや身だしなみギアを整えたら、日々の洗顔や毛穴ケアも見直すのが垢抜けの近道。メンズケアメディア「チー牛メンズ」の実践記事もぜひチェックしてみてください。"
    },
    {
        "domain": "qualia-navi.vercel.app",
        "url": "https://qualia-navi.vercel.app/articles/art-winter-b76-wip-10-ue10000165",
        "anchor_title": "【クリニーク クラリファイング ローション】角質ケア効果と本音レビュー（Qualia Navi）",
        "keywords": ["コスメ", "スキンケア", "化粧水", "美容液", "パック", "フェイスマスク", "保湿", "乾燥肌", "毛穴ケア", "リップ", "アイシャドウ", "チーク", "ファンデーション"],
        "callout_title": "💄 美肌をキープする実力派スキンケア＆コスメ検証",
        "desc": "日々の肌コンディションを底上げするなら、コスメ専門アナリストによる徹底検証メディア「Qualia Navi」の成分・使用感レビューが頼りになります。"
    }
]

def find_best_external_link(item_title: str, item_caption: str = "") -> Optional[Dict[str, Any]]:
    """商材情報から最も親和性の高い外部メディアを1つだけ選定（親和性が低い場合はNone）"""
    text = (item_title + " " + item_caption).lower()
    best_target = None
    max_score = 0
    for target in EXTERNAL_TARGETS:
        score = sum(1 for kw in target["keywords"] if kw.lower() in text)
        if score > max_score:
            max_score = score
            best_target = target
    
    # 最低でもキーワードが1つ以上合致した場合のみ返す（無理なこじつけは完全排除）
    return best_target if max_score >= 1 else None

def generate_external_link_html(target: Optional[Dict[str, Any]]) -> str:
    """デザイン性の高いブログ埋め込み用HTMLを生成"""
    if not target:
        return ""
    return f'''
<div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 5px solid #475569; border-radius: 8px; padding: 18px 20px; margin: 35px 0;">
    <div style="font-weight: bold; color: #1e293b; font-size: 15px; margin-bottom: 8px;">
        {target["callout_title"]}
    </div>
    <p style="margin: 0 0 10px 0; font-size: 14px; color: #475569; line-height: 1.7;">
        {target["desc"]}
    </p>
    <p style="margin: 0; font-size: 14px;">
        👉 関連おすすめ記事：<a href="{target["url"]}" target="_blank" rel="noopener noreferrer" style="color: #0284c7; font-weight: bold; text-decoration: underline;">{target["anchor_title"]}</a>
    </p>
</div>
'''
