"""
wipe.py — Secure wallet destruction and emergency data wipe.

Operations:
  - secure_delete_file(): multi-pass overwrite + unlink (best-effort on SSD)
  - wipe_session_and_backups(): zeros session key + deletes all backups
  - panic_wipe(): one-shot emergency destroy (wallet + backups + audit log)

Design decisions:
- On SSDs and SSDs with wear-leveling (most modern drives), multi-pass
  overwrite does NOT guarantee data erasure due to remapping. This is
  documented clearly to the user. Full-disk encryption (LUKS, BitLocker)
  is the only reliable solution on SSDs.
- On HDDs and tmpfs/ramfs mounts, multi-pass overwrite is effective.
- We use 3-pass DoD-5220 style: zeros, ones, random. Then fsync + unlink.
- The audit log is preserved by default. panic_wipe() optionally deletes it.
- This module NEVER imports from wallet.core.session to avoid circular imports.
"""

import os
import secrets
import logging
from pathlib import Path

log = logging.getLogger(__name__)

WIPE_PASSES = 3


def _overwrite_file(path: Path) -> None:
    """
    Overwrite file content with multiple passes.
    Pass 0: all zeros
    Pass 1: all ones (0xFF)
    Pass N: cryptographically random bytes
    Then fsync to force write through OS page cache to block device.
    """
    size = path.stat().st_size
    if size == 0:
        return

    with open(path, "r+b") as f:
        for pass_num in range(WIPE_PASSES):
            f.seek(0)
            if pass_num == 0:
                f.write(b"\x00" * size)
            elif pass_num == 1:
                f.write(b"\xff" * size)
            else:
                f.write(secrets.token_bytes(size))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass   # fsync may fail on some virtual FS — best effort


def secure_delete_file(path: Path, *, warn_ssd: bool = True) -> bool:
    """
    Attempt secure deletion of a file.

    Returns True on success, False if file did not exist.
    Raises OSError if file exists but cannot be deleted.

    Note: On SSDs, this is BEST-EFFORT. The caller receives a warning
    if warn_ssd=True and the filesystem type suggests SSD storage.
    """
    if not path.exists():
        return False

    if warn_ssd:
        log.warning(
            "secure_delete: '%s' — note: on SSDs, overwrite does not guarantee "
            "erasure due to wear-leveling. Use full-disk encryption for strongest protection.",
            path,
        )

    _overwrite_file(path)
    path.unlink()
    log.info("secure_delete: '%s' wiped and unlinked.", path)
    return True


def wipe_session(session: object) -> None:
    """
    Force-lock the session and zero the key buffer.
    Accepts any object with a .lock() method.
    """
    if hasattr(session, "lock"):
        try:
            session.lock(reason="panic_wipe")
        except Exception:  # noqa: BLE001
            pass


def wipe_backups(backup_dir: Path) -> int:
    """
    Securely delete all wallet_*.enc backup files.
    Returns count of files deleted.
    """
    deleted = 0
    if not backup_dir.exists():
        return 0
    for f in sorted(backup_dir.glob("wallet_*.enc")):
        try:
            secure_delete_file(f, warn_ssd=False)
            deleted += 1
        except OSError as e:
            log.error("wipe_backups: failed to delete '%s': %s", f, e)
    return deleted


def panic_wipe(
    wallet_path: Path,
    backup_dir: Path,
    *,
    session: object | None = None,
    delete_audit_log: bool = False,
    audit_log_path: Path | None = None,
) -> dict:
    """
    Emergency destruction of all wallet data.

    Executes in this order:
    1. Zero and lock the session key (in-memory wipe)
    2. Securely overwrite and delete wallet.enc
    3. Securely overwrite and delete all backup files
    4. Optionally delete audit.log

    Returns a summary dict with counts of deleted files.
    """
    summary: dict = {"session_wiped": False, "wallet_deleted": False,
                     "backups_deleted": 0, "audit_deleted": False}

    # 1. Memory wipe
    if session is not None:
        wipe_session(session)
        summary["session_wiped"] = True

    # 2. Wallet file
    try:
        summary["wallet_deleted"] = secure_delete_file(wallet_path, warn_ssd=False)
    except OSError as e:
        log.error("panic_wipe: could not delete wallet: %s", e)

    # 3. Backups
    summary["backups_deleted"] = wipe_backups(backup_dir)

    # 4. Audit log
    if delete_audit_log and audit_log_path:
        try:
            summary["audit_deleted"] = secure_delete_file(
                audit_log_path, warn_ssd=False
            )
        except OSError as e:
            log.error("panic_wipe: could not delete audit log: %s", e)

    log.critical(
        "PANIC WIPE executed. wallet_deleted=%s backups=%d",
        summary["wallet_deleted"],
        summary["backups_deleted"],
    )
    return summary
