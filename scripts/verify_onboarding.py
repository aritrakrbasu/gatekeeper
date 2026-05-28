import asyncio
import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

from services import repository_service
from services import schema_inspection_service
from services.encryption_service import encrypt_value, decrypt_value
from services import mongo_client

async def test_onboarding_flow():
    print("=" * 60)
    print("Starting Onboarding & Credential Security Verification")
    print("=" * 60)
    
    # 1. Test Encryption/Decryption Directly
    print("\n[1/4] Testing Encryption Service...")
    original_uri = "mongodb+srv://user:secretpass@cluster.mongodb.net/test_target_db"
    encrypted_uri = encrypt_value(original_uri)
    decrypted_uri = decrypt_value(encrypted_uri)
    
    print(f"  Original:  {original_uri[:25]}...")
    print(f"  Encrypted: {encrypted_uri[:25]}...")
    print(f"  Decrypted: {decrypted_uri[:25]}...")
    
    assert encrypted_uri != original_uri, "Encryption failed: cipher text is identical to plain text!"
    assert decrypted_uri == original_uri, "Decryption failed: decrypted value doesn't match original!"
    print("  Encryption/Decryption verification: ✅ PASS")
    
    # 2. Test Onboarding storage
    print("\n[2/4] Testing Onboard Repository Storage...")
    test_repo_id = "test_onboard_12345"
    onboard_data = {
        "mongodb_uri": original_uri,
        "fivetran_api_key": "ft_key_123",
        "fivetran_api_secret": "ft_secret_456",
        "encrypt_credentials": True
    }
    
    # We will onboard the repository for a dummy user
    dummy_user_id = "user_test_99"
    
    # Call onboard_repository
    result = await repository_service.onboard_repository(
        user_id=dummy_user_id,
        repo_id=test_repo_id,
        data=onboard_data
    )
    
    print(f"  Onboard Result: {result}")
    assert result["onboarded"] is True, "Onboarding method should return onboarded=True"
    
    # Query MongoDB directly to verify encryption at rest
    db_repo = await mongo_client.find_one(
        collection_name="connected_repositories",
        filter={"id": test_repo_id, "user_id": dummy_user_id}
    )
    
    assert db_repo is not None, "Failed to retrieve onboarded repository from MongoDB!"
    print("  Repository saved to MongoDB: ✅ SUCCESS")
    print(f"  Stored mongodb_uri: {db_repo['mongodb_uri'][:25]}...")
    assert db_repo["mongodb_uri"] != original_uri, "Credentials stored in plain text instead of encrypted!"
    assert db_repo["credentials_encrypted"] is True, "credentials_encrypted flag should be True"
    print("  Credentials encrypted at rest in MongoDB: ✅ PASS")
    
    # 3. Test Decrypted Schema Inspection Loading
    print("\n[3/4] Testing Decoupled Target Credentials Extraction...")
    from services.schema_inspection_service import _get_target_mongodb_uri
    uri, db_name, is_encrypted = await _get_target_mongodb_uri(test_repo_id)
    
    print(f"  Retrieved URI: {uri[:25]}...")
    print(f"  Database Name: {db_name}")
    print(f"  Is Encrypted:  {is_encrypted}")
    
    assert uri == original_uri, "Failed to retrieve and decrypt stored connection URI!"
    assert db_name == "test_target_db", f"Expected db_name 'test_target_db', got '{db_name}'"
    print("  Onboarding credentials load & decryption: ✅ PASS")
    
    # 4. Clean up test repository from DB
    print("\n[4/4] Cleaning Up Test Data...")
    deleted = await mongo_client.delete_one(
        collection_name="connected_repositories",
        filter={"id": test_repo_id, "user_id": dummy_user_id}
    )
    print(f"  Cleanup deletion status: {deleted}")
    
    print("\n" + "=" * 60)
    print("All Onboarding & Credential Security Verification Tests PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_onboarding_flow())
