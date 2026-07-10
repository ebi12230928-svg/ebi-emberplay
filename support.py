from flask import Blueprint, render_template
from flask_login import login_required

support_bp = Blueprint("support", __name__)

FAQ = [
    ("Embersって何ですか?現金化できますか?", "Embersはこのサイト専用の遊び用ポイントです。無料の報酬でのみ手に入り、現金・ギフトカード・暗号資産などへの交換は一切できません。"),
    ("残高が0になってしまいました。", "ウォレット画面から、アワリー・デイリー・ウィークリー・マンスリー・デイリースピン・借りるなどの方法でEmbersを補充できます。"),
    ("VIPになるにはどうすればいいですか?", "VIPは管理者が手動で認定します。気になる方は管理者にチャットやプレゼント企画などで直接聞いてみてください。"),
    ("パスワードを忘れてしまいました。", "現在パスワード再発行機能はありません。管理者に直接連絡してください。"),
    ("不具合を見つけました。", "チャット、または管理者に直接連絡してください。"),
]


@support_bp.route("/support")
@login_required
def index():
    return render_template("support.html", faq=FAQ)
