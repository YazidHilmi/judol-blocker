"""
Utility enkripsi — dipakai buat nyimpen streamKey Saweria di DB, biar gak
kesimpen plaintext. Pakai Fernet (symmetric encryption) dari library
`cryptography`.

PENTING: ENCRYPTION_KEY harus di-set di .env dan JANGAN BERUBAH setelah
ada data tersimpan, karena data lama gak akan bisa di-decrypt lagi kalau
key-nya ganti. Generate key baru dengan:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger("crypto-utils")

_key = os.environ.get("ENCRYPTION_KEY")

if not _key:
    # Fallback buat development doang — key random tiap restart server.
    # JANGAN dipakai buat production/demo yang butuh data persisten,
    # karena data yang udah dienkripsi sebelumnya gak akan bisa dibaca lagi
    # setelah server restart (key-nya beda).
    _key = Fernet.generate_key().decode()
    logger.warning(
        "ENCRYPTION_KEY tidak di-set di .env — pakai key sementara (hilang pas restart). "
        "Generate key permanen dengan: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        "lalu taruh di .env sebagai ENCRYPTION_KEY=..."
    )

_fernet = Fernet(_key.encode() if isinstance(_key, str) else _key)


def encrypt_value(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
