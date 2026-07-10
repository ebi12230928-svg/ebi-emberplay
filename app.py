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
    """
    from sqlalchemy import inspect, text

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
