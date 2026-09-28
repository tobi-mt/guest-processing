from unittest.mock import patch
import time

from guest_database_manager.accounts import AccountError, AccountStore, hash_password, verify_password
from guest_database_manager.database import GuestDatabase


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("Correct horse 42")
    second = hash_password("Correct horse 42")
    assert first != second
    assert verify_password("Correct horse 42", first)
    assert not verify_password("wrong password 42", first)


def test_mt_admin_bootstraps_as_super_admin_and_recovery_is_one_time(temp_db):
    GuestDatabase(temp_db.db_path)
    accounts = AccountStore(temp_db.db_path)
    accounts.bootstrap("mt_admin", "legacy-secret", role="admin")
    authenticated = accounts.authenticate("mt_admin", "legacy-secret")
    assert authenticated["role"] == "super_admin"

    member = accounts.create(
        {"username": "producer", "email": "producer@example.com", "role": "operator"},
        actor="mt_admin",
    )
    assert member["must_set_password"] == 1
    assert accounts.authenticate("producer", "anything") is None
    token = accounts.create_recovery_token(member["id"], actor="mt_admin")
    accounts.recover(token, "Replacement pass 84")
    assert accounts.authenticate("producer", "Replacement pass 84")
    try:
        accounts.recover(token, "Another password 96")
    except AccountError as exc:
        assert "invalid or has expired" in str(exc)
    else:
        raise AssertionError("recovery token was reusable")


def test_invalid_recovery_token_is_rejected_before_expensive_hashing(temp_db):
    GuestDatabase(temp_db.db_path)
    accounts = AccountStore(temp_db.db_path)
    with patch("guest_database_manager.accounts.hash_password") as password_hash:
        try:
            accounts.recover("invalid-token", "Strong unrelated pass 42")
        except AccountError as exc:
            assert "invalid or has expired" in str(exc)
        else:
            raise AssertionError("invalid token was accepted")
    password_hash.assert_not_called()


def test_last_super_admin_cannot_remove_own_access(temp_db):
    GuestDatabase(temp_db.db_path)
    accounts = AccountStore(temp_db.db_path)
    accounts.bootstrap("mt_admin", "legacy-secret", role="admin")
    admin = accounts.authenticate("mt_admin", "legacy-secret")
    try:
        accounts.update(admin["id"], {"role": "admin"}, actor="mt_admin", actor_id=admin["id"])
    except AccountError as exc:
        assert "own account" in str(exc)
    else:
        raise AssertionError("super administrator removed own access")


def test_totp_is_encrypted_and_replay_protected(temp_db):
    GuestDatabase(temp_db.db_path)
    accounts = AccountStore(temp_db.db_path, encryption_secret="stable-test-secret")
    accounts.bootstrap("mt_admin", "legacy-secret", role="admin")
    admin = accounts.authenticate("mt_admin", "legacy-secret")
    enrollment = accounts.begin_mfa(admin["id"], actor="mt_admin")
    code = accounts._totp(enrollment["secret"], int(time.time()) // 30)
    accounts.confirm_mfa(admin["id"], code, actor="mt_admin")

    challenge = accounts.authenticate("mt_admin", "legacy-secret")
    assert challenge["mfa_required"] is True
    assert accounts.authenticate("mt_admin", "legacy-secret", otp=code)
    assert accounts.authenticate("mt_admin", "legacy-secret", otp=code) is None

    with accounts._connect() as conn:
        row = conn.execute("SELECT mfa_secret_ciphertext FROM dashboard_accounts WHERE id=?", (admin["id"],)).fetchone()
    assert enrollment["secret"] not in row["mfa_secret_ciphertext"]
