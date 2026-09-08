import pytest
import sqlite3
from data_pipeline.storage_provider import StorageProvider

def test_audit_trail_hash_chain_and_tamper_detection(tmp_path):
    test_db = str(tmp_path / "tamper_test.db")
    storage = StorageProvider(db_path=test_db)
    user_id = "test_auditor"

    # Step 1: Record 3 valid rebalances
    for i in range(1, 4):
        storage.record_rebalance_execution(
            user_id=user_id,
            old_weights={"fixed_income": 0.5, "thai_equity": 0.5},
            new_weights={"fixed_income": 0.6, "thai_equity": 0.4},
            score_before=50.0 + i,
            score_after=60.0 + i,
            reason=f"Legitimate Rebalance #{i}"
        )

    # Step 2: Verification on pristine database should be 100% valid
    audit_res = storage.verify_audit_integrity(user_id)
    assert audit_res["is_valid"] is True
    assert audit_res["total_entries"] == 3
    assert audit_res["tampered_count"] == 0

    # Step 3: Simulate unauthorized tampering in SQLite!
    conn = sqlite3.connect(test_db)
    # Alter score_before of entry #2 directly
    conn.execute("UPDATE rebalance_logs SET score_before = 99.9 WHERE rebalance_no = 2")
    conn.commit()
    conn.close()

    # Step 4: Verification must immediately detect the tamper!
    tampered_res = storage.verify_audit_integrity(user_id)
    assert tampered_res["is_valid"] is False
    assert tampered_res["tampered_count"] >= 1
    assert "Data alteration detected" in str(tampered_res["tampered_details"])
