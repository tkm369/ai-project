"""
pdca_analyzer.py - posts_log.jsonのパフォーマンスデータをGeminiで分析し
                   strategy.jsonを更新する（PDCA の Check → Act）

GitHub Actionsから定期実行される。
PDCA完了後にDiscordに結果を通知する（DISCORD_WEBHOOK_URL 環境変数が必要）。
"""
import os
import sys
import json
import urllib.request
from datetime import datetime, timedelta

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
DISCORD_WEBHOOK   = os.environ.get("DISCORD_WEBHOOK_URL", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

BASE_DIR              = os.path.dirname(os.path.abspath(__file__))
POSTS_LOG             = os.path.join(BASE_DIR, "posts_log.json")
STRATEGY_FILE         = os.path.join(BASE_DIR, "strategy.json")
ACCOUNT_ANALYTICS_FILE = os.path.join(BASE_DIR, "account_analytics.json")

CATEGORIES    = [
    "片思い", "失恋", "復縁", "恋愛あるある",
    "元カレ元カノ", "好きな人", "寂しい夜", "恋愛名言",
]
TONES         = ["共感型", "励まし型", "あるある型"]
FORMATS       = ["独白", "問いかけ", "ストーリー", "qa", "dialogue", "list"]
CARD_STYLES   = ["xdark", "gradient", "poem", "light", "line_chat", "notebook", "list_card"]
VOICE_FORMATS = ["fortune", "psychology", "advice"]   # 音声投稿フォーマット


# ------------------------------------------------------------------ #
#  データ読み込み
# ------------------------------------------------------------------ #

def load_posts_log() -> list:
    if not os.path.exists(POSTS_LOG):
        return []
    with open(POSTS_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def load_strategy() -> dict:
    if os.path.exists(STRATEGY_FILE):
        with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_strategy(s: dict):
    with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def load_account_analytics() -> list:
    """account_analytics.json を読み込む（存在しない場合は空リスト）"""
    if not os.path.exists(ACCOUNT_ANALYTICS_FILE):
        return []
    try:
        with open(ACCOUNT_ANALYTICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def compute_account_metrics(history: list) -> dict:
    """
    account_analytics.json の履歴からアカウントレベルの指標を計算する。
    最新エントリと直近7件の平均を返す。

    Returns:
        {
            "latest": { profile_views, reach, new_followers, avg_watch_time, video_views },
            "avg_7d": { profile_views, reach, new_followers, avg_watch_time },
            "profile_visit_rate_pct": 数値（プロフィール遷移率 %）,
        }
    """
    if not history:
        return {}

    latest = history[-1]
    recent = history[-7:]  # 直近7件

    def _avg_field(records, key):
        vals = [r.get(key) for r in records if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    avg_7d = {
        "profile_views": _avg_field(recent, "profile_views"),
        "reach":         _avg_field(recent, "reach"),
        "new_followers": _avg_field(recent, "new_followers"),
        "avg_watch_time": _avg_field(recent, "avg_watch_time"),
        "video_views":   _avg_field(recent, "video_views"),
    }

    # プロフィール遷移率 = profile_views / video_views * 100
    pv  = avg_7d.get("profile_views")
    vv  = avg_7d.get("video_views")
    rate = round(pv / vv * 100, 2) if (pv and vv and vv > 0) else None

    return {
        "latest":                 latest,
        "avg_7d":                 avg_7d,
        "profile_visit_rate_pct": rate,
    }


# ------------------------------------------------------------------ #
#  Discord 通知
# ------------------------------------------------------------------ #

def _send_discord(payload: dict):
    """Discord Webhook に embed を送信する"""
    if not DISCORD_WEBHOOK:
        return
    try:
        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.status not in (200, 204):
                print(f"Discord送信失敗: {res.status}")
    except Exception as e:
        print(f"Discord送信エラー: {e}")


def notify_pdca_report(stats: dict, strategy: dict, account: dict, insights: str):
    """PDCA 分析結果を Discord に通知する"""
    if not DISCORD_WEBHOOK:
        return

    total    = stats.get("total_measured", 0)
    card_cnt = stats.get("card_posts", 0)
    voi_cnt  = stats.get("voice_posts", 0)

    # カテゴリ別トップ3
    by_cat   = stats.get("by_category", {})
    top_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = "\n".join(f"　{i+1}. {c}（{v:.1f}）" for i, (c, v) in enumerate(top_cats)) or "データなし"

    # カードスタイル別トップ
    by_style  = stats.get("by_card_style", {})
    best_style = max(by_style, key=by_style.get) if by_style else "不明"

    # 音声フォーマット別
    by_voice  = stats.get("by_voice_format", {})
    best_voice = max(by_voice, key=by_voice.get) if by_voice else "不明"

    # アカウントレベルメトリクス
    acc_7d   = account.get("avg_7d", {})
    visit_rt = account.get("profile_visit_rate_pct")
    visit_rt_str = f"{visit_rt:.2f}%" if visit_rt is not None else "取得中"
    pv_str   = str(int(acc_7d["profile_views"])) if acc_7d.get("profile_views") else "取得中"
    reach_str = str(int(acc_7d["reach"])) if acc_7d.get("reach") else "取得中"
    watch_str = f"{acc_7d['avg_watch_time']:.1f}秒" if acc_7d.get("avg_watch_time") else "取得中"
    follower_str = f"+{int(acc_7d['new_followers'])}" if acc_7d.get("new_followers") else "取得中"

    # Thompson Sampling トップ
    ts_top = {
        k: max(
            strategy.get(f"ts_{k}", {}).items(),
            key=lambda x: x[1].get("alpha", 1) / max(x[1].get("alpha", 1) + x[1].get("beta", 1), 1),
            default=("?", {}),
        )[0]
        for k in ("category", "card_style", "format")
    }

    payload = {
        "embeds": [{
            "title": "📊 TikTok PDCA レポート",
            "color": 0x5B8DEF,
            "description": f"💡 {insights[:200]}" if insights else "分析完了",
            "fields": [
                {
                    "name": "📹 投稿実績",
                    "value": (
                        f"計測済み: {total}件\n"
                        f"カード: {card_cnt}件 / 音声: {voi_cnt}件"
                    ),
                    "inline": True,
                },
                {
                    "name": "👤 アカウント指標（7日平均）",
                    "value": (
                        f"プロフィール閲覧: {pv_str}\n"
                        f"プロフィール遷移率: **{visit_rt_str}**\n"
                        f"リーチ: {reach_str}\n"
                        f"平均視聴時間: {watch_str}\n"
                        f"フォロワー増加: {follower_str}"
                    ),
                    "inline": True,
                },
                {
                    "name": "🏆 カテゴリ TOP3（エンゲージメント）",
                    "value": top_cats_str,
                    "inline": False,
                },
                {
                    "name": "🎨 推奨スタイル（Thompson Sampling）",
                    "value": (
                        f"カテゴリ: **{ts_top['category']}**\n"
                        f"カードスタイル: **{ts_top['card_style']}**\n"
                        f"フォーマット: **{ts_top['format']}**\n"
                        f"音声フォーマット: **{best_voice}**"
                    ),
                    "inline": False,
                },
            ],
            "footer": {
                "text": f"更新: {datetime.now().strftime('%Y-%m-%d %H:%M JST')}",
            },
        }]
    }
    _send_discord(payload)
    print("Discord通知送信完了")


# ------------------------------------------------------------------ #
#  統計集計（Gemini不要な部分）
# ------------------------------------------------------------------ #

def compute_stats(posts: list) -> dict:
    """カテゴリ・トーン・フォーマット別の平均を計算
    エンゲージメントスコア = いいね×1 + 保存×3 + コメント×5（TikTokアルゴリズム重み付け）
    いいね等が取れない場合は views を代替指標として使用"""
    measured = [p for p in posts if p.get("views") is not None or p.get("likes") is not None]
    if not measured:
        return {}

    def engagement_score(p):
        """TikTokアルゴリズムに近い重み付きエンゲージメントスコア
        保存・コメントはいいねより拡散への影響が大きい"""
        likes    = p.get("likes")    or 0
        saves    = p.get("saves")    or 0
        comments = p.get("comments") or 0
        if likes == 0 and saves == 0 and comments == 0:
            # エンゲージメントが全部0なら再生数を代替指標
            return p.get("views", 0) * 0.01  # viewsはスケール調整
        return likes * 1 + saves * 3 + comments * 5

    def avg_by(key, choices):
        result = {}
        for val in choices:
            group = [engagement_score(p) for p in measured if p.get(key) == val]
            if group:
                result[val] = round(sum(group) / len(group), 2)
        return result

    def avg_metric_by(metric_key, key, choices):
        """特定指標の平均をカテゴリ別に集計"""
        result = {}
        for val in choices:
            group = [p.get(metric_key) for p in measured
                     if p.get(key) == val and p.get(metric_key) is not None]
            if group:
                result[val] = round(sum(group) / len(group), 1)
        return result

    # コンテンツタイプ別の分離
    card_posts  = [p for p in measured if p.get("content_type", "card") == "card"]
    voice_posts = [p for p in measured if p.get("content_type") == "voice"]

    result = {
        "total_measured":  len(measured),
        "card_posts":      len(card_posts),
        "voice_posts":     len(voice_posts),
        # カード投稿のエンゲージメントスコア
        "by_category":    avg_by("category",   CATEGORIES),
        "by_tone":        avg_by("tone",        TONES),
        "by_format":      avg_by("format",      FORMATS),
        "by_card_style":  avg_by("card_style",  CARD_STYLES),
        # 音声投稿フォーマット別スコア
        "by_voice_format": {
            vf: round(
                sum(engagement_score(p) for p in voice_posts if p.get("voice_format") == vf)
                / max(1, len([p for p in voice_posts if p.get("voice_format") == vf])),
                2,
            )
            for vf in VOICE_FORMATS
            if any(p.get("voice_format") == vf for p in voice_posts)
        },
        # コンテンツタイプ別平均スコア
        "content_type_avg": {
            "card":  round(sum(engagement_score(p) for p in card_posts)  / max(1, len(card_posts)),  2),
            "voice": round(sum(engagement_score(p) for p in voice_posts) / max(1, len(voice_posts)), 2),
        } if voice_posts else {},
        # 個別指標の平均（Geminiが詳細分析できるように）
        "avg_views_by_category":    avg_metric_by("views",    "category", CATEGORIES),
        "avg_likes_by_category":    avg_metric_by("likes",    "category", CATEGORIES),
        "avg_saves_by_category":    avg_metric_by("saves",    "category", CATEGORIES),
        "avg_comments_by_category": avg_metric_by("comments", "category", CATEGORIES),
        "by_hour": {
            h: round(sum(engagement_score(p) for p in measured if p.get("posting_hour") == h)
                     / len([p for p in measured if p.get("posting_hour") == h]), 2)
            for h in range(24)
            if any(p.get("posting_hour") == h for p in measured)
        },
        "recent_posts": [
            {
                "text":         p.get("text", "")[:40],
                "content_type": p.get("content_type", "card"),
                "voice_format": p.get("voice_format"),
                "category":     p.get("category"),
                "tone":         p.get("tone"),
                "format":       p.get("format"),
                "views":        p.get("views"),
                "likes":        p.get("likes"),
                "saves":        p.get("saves"),
                "comments":     p.get("comments"),
                "eng_score":    round(engagement_score(p), 1),
                "posted_at":    p.get("posted_at", "")[:10],
            }
            for p in sorted(measured, key=lambda x: engagement_score(x), reverse=True)[:20]
        ],
    }
    return result


# ------------------------------------------------------------------ #
#  Gemini 分析
# ------------------------------------------------------------------ #

def _call_gemini(prompt: str) -> str:
    from gemini_client import call_gemini
    return call_gemini(prompt, max_tokens=1024, temperature=0.3, response_json=True)


def analyze_with_gemini(stats: dict, current_strategy: dict,
                        account_metrics: dict = None) -> dict:
    """Geminiがパフォーマンスを分析して次の戦略を提案"""

    account_section = ""
    if account_metrics:
        visit_rt = account_metrics.get("profile_visit_rate_pct")
        avg_7d   = account_metrics.get("avg_7d", {})
        account_section = f"""
【アカウントレベル指標（直近7日平均）】
- プロフィール閲覧数: {avg_7d.get('profile_views', '不明')}
- リーチ（ユニーク視聴者）: {avg_7d.get('reach', '不明')}
- 平均視聴時間: {avg_7d.get('avg_watch_time', '不明')}秒
- フォロワー獲得数: {avg_7d.get('new_followers', '不明')}
- プロフィール遷移率: {f"{visit_rt:.2f}%" if visit_rt is not None else '不明'}
  （プロフィール遷移率が高い → プロフィール誘導コンテンツが効果的）
  （2〜5%が一般的、5%以上は優秀）

"""

    prompt = f"""あなたはTikTokコンテンツの戦略アナリストです。
以下のパフォーマンスデータを分析し、次の投稿戦略をJSONで出力してください。

【重要】エンゲージメントスコアの算出方法:
  スコア = いいね×1 + 保存数×3 + コメント数×5
  ※保存・コメントはTikTokの拡散アルゴリズムへの影響が特に大きい
{account_section}
【パフォーマンスデータ】
{json.dumps(stats, ensure_ascii=False, indent=2)}

【現在の戦略】
{json.dumps(current_strategy.get("generation_params", {}), ensure_ascii=False)}

以下の点を重点的に分析してください：
- by_categoryのエンゲージメントスコアが高いカテゴリ（伸ばすべき）
- avg_saves_by_categoryが高いカテゴリ（保存されやすい＝バズりやすい）
- avg_comments_by_categoryが高いカテゴリ（共感・反応されやすい）
- by_card_styleのスコアが高いスタイル（視覚的に止まるデザイン）
- by_formatのスコアが高いフォーマット（読み切られやすい形式）
- by_voice_formatのスコアが高い音声フォーマット（占い/心理解説/アドバイスのどれが伸びるか）
- content_type_avgでcardとvoiceのどちらが高いか（両者の比較）
- recent_postsのeng_scoreが高い投稿のtone/format/card_styleの傾向
- プロフィール遷移率が高い場合 → プロフィール誘導（「プロフで詳細」等）を増やすべきか
- 平均視聴時間が短い場合 → 冒頭1秒のフック強化が必要か

分析して以下のJSONを出力してください：
{{
  "insights": "1〜2文で何が伸びているかの要約（保存・コメント・スタイルの傾向も含める）",
  "category_weights": {{
    "片思い": 数値(0.1〜3.0),
    "失恋": 数値,
    "復縁": 数値,
    "恋愛あるある": 数値,
    "元カレ元カノ": 数値,
    "好きな人": 数値,
    "寂しい夜": 数値,
    "恋愛名言": 数値
  }},
  "card_style_weights": {{
    "xdark": 数値(0.1〜3.0),
    "gradient": 数値,
    "poem": 数値,
    "light": 数値,
    "line_chat": 数値,
    "notebook": 数値
  }},
  "format_weights": {{
    "独白": 数値(0.1〜3.0),
    "問いかけ": 数値,
    "ストーリー": 数値,
    "qa": 数値,
    "dialogue": 数値
  }},
  "voice_format_weights": {{
    "fortune": 数値(0.1〜3.0),
    "psychology": 数値,
    "advice": 数値
  }},
  "generation_params": {{
    "tone": "共感型 or 励まし型 or あるある型",
    "length_range": [最小文字数, 最大文字数]
  }}
}}

データが少ない場合は全カテゴリweight=1.0・現状維持を推奨してください。
JSONのみ出力してください。"""

    raw = _call_gemini(prompt)
    # JSON抽出
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


# ------------------------------------------------------------------ #
#  Thompson Sampling データ更新（⑦）
# ------------------------------------------------------------------ #

def _update_ts_data(strategy: dict, posts: list):
    """
    個別投稿の実績からThompson Samplingのalpha/betaを更新。
    エンゲージメントスコアが全体中央値以上なら「成功」、未満なら「失敗」。
    alpha/betaは累積加算（リセットしない）。
    """
    measured = [p for p in posts
                if p.get("views") is not None or p.get("likes") is not None]
    if len(measured) < 5:
        return

    def eng(p):
        return ((p.get("likes") or 0) * 1
                + (p.get("saves") or 0) * 3
                + (p.get("comments") or 0) * 5)

    scores = sorted(eng(p) for p in measured)
    median_score = scores[len(scores) // 2]

    def update_for(field, options, ts_key):
        ts = strategy.setdefault(ts_key, {})
        for opt in options:
            group = [p for p in measured if p.get(field) == opt]
            if not group:
                ts.setdefault(opt, {"alpha": 1.0, "beta": 1.0})
                continue
            successes = sum(1 for p in group if eng(p) >= median_score)
            failures  = len(group) - successes
            prev = ts.get(opt, {"alpha": 1.0, "beta": 1.0})
            ts[opt] = {
                "alpha": round(prev["alpha"] + successes, 2),
                "beta":  round(prev["beta"]  + failures,  2),
            }

    update_for("category",     CATEGORIES,    "ts_category")
    update_for("card_style",   CARD_STYLES,   "ts_card_style")
    update_for("format",       FORMATS,       "ts_format")
    update_for("voice_format", VOICE_FORMATS, "ts_voice_format")

    print(f"TS更新: median_eng={median_score}, "
          f"measured={len(measured)}件")


# ------------------------------------------------------------------ #
#  メイン
# ------------------------------------------------------------------ #

def run():
    print("=== PDCA分析開始 ===")
    posts    = load_posts_log()
    strategy = load_strategy()

    # アカウントレベルのメトリクスを読み込む
    acc_history = load_account_analytics()
    account_metrics = compute_account_metrics(acc_history)
    if account_metrics:
        visit_rt = account_metrics.get("profile_visit_rate_pct")
        avg_7d   = account_metrics.get("avg_7d", {})
        print(f"プロフィール閲覧数（7日平均）: {avg_7d.get('profile_views', '不明')}")
        print(f"リーチ（7日平均）: {avg_7d.get('reach', '不明')}")
        print(f"平均視聴時間: {avg_7d.get('avg_watch_time', '不明')}秒")
        print(f"フォロワー獲得（7日平均）: {avg_7d.get('new_followers', '不明')}")
        print(f"プロフィール遷移率: {f'{visit_rt:.2f}%' if visit_rt is not None else '不明'}")
    else:
        print("アカウントレベルのメトリクスなし（まだ収集されていない）")

    print(f"総投稿数: {len(posts)}")
    stats = compute_stats(posts)

    if not stats:
        print("メトリクスデータなし（投稿後24時間待機中）→ strategy.json更新スキップ")
        # データなしでも Discord に通知（アカウント指標だけ表示）
        if account_metrics:
            notify_pdca_report(
                stats={}, strategy=strategy,
                account=account_metrics, insights="動画計測データなし（収集中）",
            )
        return

    print(f"計測済み投稿: {stats['total_measured']}件")
    print(f"カテゴリ別平均いいね: {stats.get('by_category', {})}")

    # カテゴリ統計を先に更新（Gemini失敗でも反映させる）
    by_cat = stats.get("by_category", {})
    for cat in CATEGORIES:
        if cat in strategy.get("categories", {}):
            if cat in by_cat:
                strategy["categories"][cat]["avg_likes"] = by_cat[cat]
            cnt = sum(1 for p in posts
                      if p.get("category") == cat and
                      (p.get("views") is not None or p.get("likes") is not None))
            strategy["categories"][cat]["post_count"] = cnt

    # Geminiで分析（失敗時はルールベースフォールバック）
    print("Gemini分析中...")
    result = None
    try:
        result = analyze_with_gemini(stats, strategy, account_metrics)
    except Exception as e:
        print(f"Gemini分析エラー（フォールバック使用）: {e}")

    if result is None:
        # ルールベース: 平均スコアが高い項目のweightを上げる
        if by_cat:
            max_score = max(by_cat.values()) or 1
            new_weights = {cat: round(1.0 + (by_cat.get(cat, max_score/2) / max_score), 2)
                           for cat in CATEGORIES}
            top_cat = max(by_cat, key=by_cat.get)

            # カードスタイル・フォーマットもルールベースで更新
            by_style = stats.get("by_card_style", {})
            by_fmt   = stats.get("by_format", {})
            style_weights = {s: round(1.0 + (by_style.get(s, 0) / (max(by_style.values()) or 1)), 2)
                             for s in CARD_STYLES} if by_style else {s: 1.0 for s in CARD_STYLES}
            fmt_weights   = {f: round(1.0 + (by_fmt.get(f, 0) / (max(by_fmt.values()) or 1)), 2)
                             for f in FORMATS}   if by_fmt   else {f: 1.0 for f in FORMATS}

            result = {
                "insights": f"計測中（{stats['total_measured']}件）。{top_cat}が最高eng {by_cat[top_cat]:.1f}",
                "category_weights":   new_weights,
                "card_style_weights": style_weights,
                "format_weights":     fmt_weights,
                "generation_params":  strategy.get("generation_params", {}),
            }
            print(f"フォールバック結果: {top_cat}が最高（eng {by_cat[top_cat]:.1f}）")

    # strategy.jsonを更新
    strategy["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    strategy["insights"] = result.get("insights", strategy.get("insights", ""))

    # カテゴリweightを更新
    new_weights = result.get("category_weights", {})
    for cat in CATEGORIES:
        if cat in new_weights and cat in strategy.get("categories", {}):
            strategy["categories"][cat]["weight"] = float(new_weights[cat])

    # カードスタイルweightを更新
    new_style_weights = result.get("card_style_weights", {})
    if new_style_weights:
        if "card_style_weights" not in strategy:
            strategy["card_style_weights"] = {s: 1.0 for s in CARD_STYLES}
        for s in CARD_STYLES:
            if s in new_style_weights:
                strategy["card_style_weights"][s] = float(new_style_weights[s])

    # フォーマットweightを更新
    new_format_weights = result.get("format_weights", {})
    if new_format_weights:
        if "format_weights" not in strategy:
            strategy["format_weights"] = {f: 1.0 for f in FORMATS}
        for f in FORMATS:
            if f in new_format_weights:
                strategy["format_weights"][f] = float(new_format_weights[f])

    # 音声フォーマットweightを更新
    new_voice_fmt_weights = result.get("voice_format_weights", {})
    if new_voice_fmt_weights:
        if "voice_format_weights" not in strategy:
            strategy["voice_format_weights"] = {vf: 1.0 for vf in VOICE_FORMATS}
        for vf in VOICE_FORMATS:
            if vf in new_voice_fmt_weights:
                strategy["voice_format_weights"][vf] = float(new_voice_fmt_weights[vf])

    # 生成パラメータを更新
    new_params = result.get("generation_params", {})
    if new_params:
        strategy["generation_params"] = new_params

    # ⑦ Thompson Sampling の alpha/beta パラメータを更新
    _update_ts_data(strategy, posts)

    save_strategy(strategy)
    print(f"strategy.json更新完了")
    print(f"insights: {strategy['insights']}")
    print(f"best tone: {strategy['generation_params'].get('tone')}")
    ts_top = {k: max(strategy.get(f"ts_{k}", {}).items(),
                     key=lambda x: x[1].get("alpha", 1) / max(x[1].get("alpha", 1) + x[1].get("beta", 1), 1),
                     default=("?", {}))[0]
              for k in ("category", "card_style", "format")}
    print(f"TS推奨: category={ts_top['category']} style={ts_top['card_style']} format={ts_top['format']}")

    # Discord に PDCA レポートを送信
    notify_pdca_report(
        stats    = stats,
        strategy = strategy,
        account  = account_metrics,
        insights = strategy.get("insights", ""),
    )

    print("=== PDCA分析完了 ===")


if __name__ == "__main__":
    run()
