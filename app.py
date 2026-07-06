import os

from flask import Flask
from flask_login import current_user

from config import Config
from extensions import db, login_manager
from models import User


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

    app.register_blueprint(auth_bp)
    app.register_blueprint(lobby_bp)
    app.register_blueprint(rewards_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(games_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(leaderboard_bp)

    @app.context_processor
    def inject_user():
        unread_count = 0
        if current_user.is_authenticated:
            from models import Notification
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"nav_user": current_user, "unread_notifications": unread_count}

    with app.app_context():
        db.create_all()

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
