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

    HOURLY_REWARD = 100
    DAILY_REWARD = 650
    WEEKLY_REWARD = 2600
    MONTHLY_REWARD = 10000

    RELOAD_THRESHOLD = 100       # 残高がこれ以下のときだけリロード可能
    RELOAD_AMOUNT = 900
    RELOAD_COOLDOWN_HOURS = 12

    RAKEBACK_RATE = 0.03          # プレイ料の3%がレーキバックとして積み立てられる

    LOAN_AMOUNT = 3000            # 「借金する」ボタンで借りられる指定額

    # ログインストリークボーナス(連続ログイン日数に応じて増える。1日空けるとリセット)
    LOGIN_STREAK_REWARDS = [200, 300, 400, 500, 700, 900, 1500]  # 1〜7日目、以降は7日目の額をループ
