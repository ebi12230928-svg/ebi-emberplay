"""
プッシュ通知に必要な「VAPIDキー」(公開鍵・秘密鍵のペア)を生成するスクリプト。
一度だけ実行して、出力された値をlocal_secrets.pyに保存してください。

実行方法:
    python3 generate_vapid_keys.py
"""
import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_vapid_keys():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_numbers = private_key.private_numbers()
    private_value = private_numbers.private_value
    private_bytes = private_value.to_bytes(32, byteorder="big")

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    return _b64url(public_bytes), _b64url(private_bytes)


if __name__ == "__main__":
    public_key, private_key = generate_vapid_keys()
    print("以下の3行を local_secrets.py に追記してください:\n")
    print(f'VAPID_PUBLIC_KEY = "{public_key}"')
    print(f'VAPID_PRIVATE_KEY = "{private_key}"')
    print('VAPID_CONTACT_EMAIL = "mailto:your-email@example.com"  # ご自身の連絡先メールアドレスに変更してください')
