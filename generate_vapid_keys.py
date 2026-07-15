from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01

vapid = Vapid01()
vapid.generate_keys()

public_key = vapid.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)

private_key = vapid.private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

import base64

public_key_b64 = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("utf-8")

print()
print("=== Render Environment Variables ===")
print()
print(f"VAPID_PUBLIC_KEY={public_key_b64}")
print()
print("VAPID_PRIVATE_KEY=")
print(private_key.decode("utf-8"))
print()
print("VAPID_SUBJECT=mailto:admin@jitt.hu")