import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _resolve_database_uri():
    # RailwayなどのPaaSは環境変数 DATABASE_URL でPostgresの接続先を渡してくる。
    # SQLAlchemy 1.4+は "postgres://" ではなく "postgresql://" を要求するため変換する。
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    # ローカル開発時はSQLiteにフォールバック
    return "sqlite:///" + os.path.join(BASE_DIR, "emberplay.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── ポイント経済(エンタメ専用・換金/購入は一切不可) ──
    SIGNUP_BONUS = 1000

    REFERRAL_BONUS_NEW = 500        # 紹介経由で登録した新規ユーザーへの追加ボーナス
    REFERRAL_BONUS_REFERRER = 1000  # 紹介した側が受け取るボーナス

    # ── Discord連携(OAuth2。パスワードは一切受け取らず、Discord公式の認可画面のみを使う) ──
    # 設定の優先順位:
    #   1. サーバーの環境変数(有料プランで「Environment variables」が使える場合はこちらを推奨)
    #   2. local_secrets.py(無料プランなど、環境変数が使えない場合。GitHubには一切上げず、
    #      PythonAnywhereのサーバー上で直接作成すること。.gitignoreに登録済み)
    try:
        import local_secrets as _local_secrets
    except ImportError:
        _local_secrets = None

    DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID") or getattr(_local_secrets, "DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET") or getattr(_local_secrets, "DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI") or getattr(_local_secrets, "DISCORD_REDIRECT_URI", "")

    SPIN_PRIZES = [100, 150, 200, 300, 500, 1000, 2500]         # デイリースピンの候補
    SPIN_WEIGHTS = [30, 25, 20, 12, 8, 4, 1]                    # 各候補の出やすさ(合計比率)

    HOURLY_REWARD = 100
    DAILY_REWARD = 650
    WEEKLY_REWARD = 2600
    MONTHLY_REWARD = 10000

    RELOAD_THRESHOLD = 100       # 残高がこれ以下のときだけリロード可能
    RELOAD_AMOUNT = 900
    RELOAD_COOLDOWN_HOURS = 12

    RAKEBACK_RATE = 0.03           # 通常のレーキバック率(プレイ料の3%)
    VIP_RAKEBACK_RATE = 0.06       # VIP(Bronze)のレーキバック率(2倍・後方互換用デフォルト)

    LOAN_AMOUNT = 3000             # 「借金する」ボタンで借りられる指定額(通常)
    VIP_LOAN_AMOUNT = 8000         # VIP(Bronze)が借りられる指定額(後方互換用デフォルト)

    XP_MULTIPLIER = 1.0            # 通常のXP倍率
    VIP_XP_MULTIPLIER = 1.5        # VIP(Bronze)のXP倍率(後方互換用デフォルト)

    HOURLY_COOLDOWN_HOURS = 1.0    # 通常のアワリー報酬クールダウン
    VIP_HOURLY_COOLDOWN_HOURS = 0.5  # VIP(Bronze)は30分ごとに受け取り可能(後方互換用デフォルト)

    VIP_SPIN_PRIZES = [300, 500, 800, 1200, 2000, 3500, 6000]   # VIP(Bronze)専用デイリースピンの候補
    VIP_SPIN_WEIGHTS = [30, 25, 20, 12, 8, 4, 1]

    # ── VIPティア制(1=Bronze, 2=Silver, 3=Gold, 4=Diamond)。数字が大きいほど特典が手厚くなる ──
    VIP_TIER_NAMES = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Diamond"}
    VIP_TIER_RAKEBACK = {1: 0.06, 2: 0.08, 3: 0.11, 4: 0.15}
    VIP_TIER_HOURLY_COOLDOWN = {1: 0.5, 2: 0.5, 3: 0.25, 4: 0.1}
    VIP_TIER_XP_MULTIPLIER = {1: 1.5, 2: 1.75, 3: 2.0, 4: 2.5}
    VIP_TIER_LOAN = {1: 8000, 2: 12000, 3: 20000, 4: 35000}
    VIP_TIER_SPIN_PRIZES = {
        1: [300, 500, 800, 1200, 2000, 3500, 6000],
        2: [500, 800, 1200, 2000, 3200, 5000, 9000],
        3: [800, 1200, 2000, 3200, 5000, 8000, 15000],
        4: [1500, 2500, 4000, 6000, 10000, 16000, 30000],
    }
    VIP_TIER_SPIN_WEIGHTS = [30, 25, 20, 12, 8, 4, 1]

    # ログインストリークボーナス(連続ログイン日数に応じて増える。1日空けるとリセット)
    LOGIN_STREAK_REWARDS = [200, 300, 400, 500, 700, 900, 1500]  # 1〜7日目、以降は7日目の額をループ
