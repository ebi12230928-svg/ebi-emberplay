import os

from flask import Flask
from flask_login import current_user

from config import Config
from extensions import db, login_manager
from models import User


def _auto_migrate(app):
    """
    新しいテーブル・列を自動的に追加する簡易マイグレーション。
    (列の削除やリネームには対応しないが、「追加」だけなら安全に自動対応できる。
    これにより、モデルに新しい列を増やすたびにデータベースを作り直す必要がなくなる)

    起動のたびに全テーブルをスキャンすると、テーブル数が増えるにつれて起動が遅くなっていくため、
    「モデル定義に変更が無ければスキャン自体をスキップする」キャッシュを設けている。
    これにより、モデルを変更しない限り、2回目以降の起動はほぼ瞬時になる。
    """
    import hashlib
    from sqlalchemy import inspect, text

    # 現在のモデル定義(テーブル名・列名・型)からハッシュ値を計算する
    schema_fingerprint_parts = []
    for table in sorted(db.metadata.sorted_tables, key=lambda t: t.name):
        col_sig = ",".join(f"{c.name}:{c.type}" for c in table.columns)
        schema_fingerprint_parts.append(f"{table.name}[{col_sig}]")
    schema_fingerprint = hashlib.sha256("|".join(schema_fingerprint_parts).encode()).hexdigest()

    marker_path = os.path.join(app.instance_path, ".schema_fingerprint")
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        if os.path.exists(marker_path):
            with open(marker_path, "r", encoding="utf-8") as f:
                if f.read().strip() == schema_fingerprint:
                    return  # 前回起動時からモデル定義が変わっていないため、スキャンを省略する
    except OSError:
        pass  # 書き込み不可な環境では、キャッシュを使わず毎回スキャンする(安全側に倒す)

    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        db.create_all()  # 存在しないテーブルはここで新規作成される

        inspector = inspect(db.engine)  # create_all後に取り直す
        for table in db.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # 今回新規作成されたテーブルは、既に最新の状態なのでスキップ

            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(db.engine.dialect)
                default_clause = ""
                if column.default is not None and not column.default.is_callable:
                    val = column.default.arg
                    if isinstance(val, bool):
                        val = 1 if val else 0
                    default_clause = f" DEFAULT '{val}'" if isinstance(val, str) else f" DEFAULT {val}"

                try:
                    db.session.execute(text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_clause}'
                    ))
                    db.session.commit()
                    print(f"[auto-migrate] {table.name}.{column.name} を追加しました。")
                except Exception as e:
                    db.session.rollback()
                    print(f"[auto-migrate] {table.name}.{column.name} の追加に失敗しました: {e}")

    try:
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write(schema_fingerprint)
    except OSError:
        pass


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from auth import auth_bp
    from lobby import lobby_bp
    from rewards import rewards_bp
    from admin import admin_bp
    from games import games_bp
    from notifications import notifications_bp
    from leaderboard import leaderboard_bp
    from sportsbook import sportsbook_bp
    from vip import vip_bp
    from chat import chat_bp
    from giveaway import giveaway_bp
    from events import events_bp
    from player_profile import profile_bp
    from support import support_bp
    from demo import demo_bp
    from stream import stream_bp
    from challenges import challenges_bp
    from friends import friends_bp
    from gacha import gacha_bp
    from collection import collection_bp
    from towerdefense import towerdefense_bp
    from squad import squad_bp
    from rpgboss import rpgboss_bp
    from seasons import seasons_bp
    from polls import polls_bp
    from cardroom import cardroom_bp
    from pets import pets_bp
    from trade import trade_bp
    from fishing import fishing_bp
    from rhythm import rhythm_bp
    from fortune import fortune_bp
    from guild import guild_bp
    from titles import titles_bp
    from tournament import tournament_bp
    from dm import dm_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(lobby_bp)
    app.register_blueprint(rewards_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(games_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(sportsbook_bp)
    app.register_blueprint(vip_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(giveaway_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(gacha_bp)
    app.register_blueprint(collection_bp)
    app.register_blueprint(towerdefense_bp)
    app.register_blueprint(squad_bp)
    app.register_blueprint(rpgboss_bp)
    app.register_blueprint(seasons_bp)
    app.register_blueprint(polls_bp)
    app.register_blueprint(cardroom_bp)
    app.register_blueprint(pets_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(fishing_bp)
    app.register_blueprint(rhythm_bp)
    app.register_blueprint(fortune_bp)
    app.register_blueprint(guild_bp)
    app.register_blueprint(titles_bp)
    app.register_blueprint(tournament_bp)
    app.register_blueprint(dm_bp)

    @app.context_processor
    def inject_user():
        unread_count = 0
        if current_user.is_authenticated:
            from models import Notification
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"nav_user": current_user, "unread_notifications": unread_count}

    _auto_migrate(app)

    with app.app_context():
        # 初回だけ、指定したユーザー名を自動的に管理者にする(コンソールが使えない環境向けの措置)
        initial_admin_username = os.environ.get("INITIAL_ADMIN_USERNAME", "ebi1223")
        if initial_admin_username:
            u = User.query.filter_by(username=initial_admin_username).first()
            if u and not u.is_admin:
                u.is_admin = True
                db.session.commit()
                print(f"[emberplay] '{initial_admin_username}' を管理者に設定しました。")
            elif not u:
                print(f"[emberplay] 管理者にしようとしたユーザー '{initial_admin_username}' が見つかりません(先に新規登録が必要です)。")

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("HOST", "0.0.0.0")
    # ArkHost/Pterodactyl系パネルは SERVER_PORT でポートを指定してくることが多いため、
    # 複数の環境変数名に対応する(見つかった最初のものを使用)
    port = int(
        os.environ.get("SERVER_PORT")
        or os.environ.get("PORT")
        or "5000"
    )
    print(f"[emberplay] listening on {host}:{port}")
    app.run(debug=os.environ.get("DEBUG", "false").lower() == "true", host=host, port=port)
