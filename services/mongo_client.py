"""
MongoDB client for Gatekeeper.

Direct MongoDB connection using Motor (async driver).
Provides CRUD operations that bypass the limited MCP server.
"""

import os
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv()

# Global MongoDB client and database
_mongo_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None

# Configuration
DB_NAME = "gatekeeper"
CONNECTION_STRING = os.getenv("MDB_MCP_CONNECTION_STRING", "")


async def get_mongo_client() -> AsyncIOMotorClient:
    """
    Get or create the MongoDB client singleton.

    Returns:
        AsyncIOMotorClient: MongoDB client instance

    Raises:
        RuntimeError: If MDB_MCP_CONNECTION_STRING is not set
    """
    global _mongo_client

    if not CONNECTION_STRING:
        raise RuntimeError(
            "MDB_MCP_CONNECTION_STRING not set in environment variables. "
            "Please set it in your .env file."
        )

    if _mongo_client is None:
        print("[✅] Creating MongoDB Motor client...")
        _mongo_client = AsyncIOMotorClient(
            CONNECTION_STRING,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        # Test connection
        await _mongo_client.admin.command('ping')
        print("[✅] MongoDB connection successful (ping succeeded)")

    return _mongo_client


async def get_database() -> AsyncIOMotorDatabase:
    """
    Get the Gatekeeper database.

    Returns:
        AsyncIOMotorDatabase: MongoDB database instance
    """
    global _database

    if _database is None:
        client = await get_mongo_client()
        _database = client[DB_NAME]
        print(f"[✅] Using database: {DB_NAME}")

    return _database


async def close_mongo_connection():
    """Close the MongoDB connection."""
    global _mongo_client, _database

    if _mongo_client:
        _mongo_client.close()
        print("[✅] MongoDB connection closed")
        _mongo_client = None
        _database = None


async def insert_one(collection_name: str, document: Dict[str, Any]) -> str:
    """
    Insert a single document into a collection.

    Args:
        collection_name: Name of the collection
        document: Document to insert

    Returns:
        str: The inserted document's ID

    Raises:
        RuntimeError: If MongoDB connection fails
    """
    try:
        db = await get_database()
        collection = db[collection_name]
        result = await collection.insert_one(document)
        print(f"[✅] Document inserted into {collection_name} with ID: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        print(f"[❌] Failed to insert document: {e}")
        raise


async def find_one(collection_name: str, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Find a single document in a collection.

    Args:
        collection_name: Name of the collection
        filter: Query filter

    Returns:
        Dict if found, None otherwise
    """
    try:
        db = await get_database()
        collection = db[collection_name]
        document = await collection.find_one(filter)
        return document
    except Exception as e:
        print(f"[❌] Failed to find document: {e}")
        return None


async def find(collection_name: str, filter: Dict[str, Any], limit: Optional[int] = None, sort: Optional[List] = None) -> List[Dict[str, Any]]:
    """
    Find multiple documents in a collection.

    Args:
        collection_name: Name of the collection
        filter: Query filter
        limit: Optional limit on number of results
        sort: Optional sort specification as list of tuples [(field, direction)]

    Returns:
        List of documents
    """
    try:
        db = await get_database()
        collection = db[collection_name]

        cursor = collection.find(filter)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)

        documents = await cursor.to_list(length=limit or 1000)
        return documents
    except Exception as e:
        print(f"[❌] Failed to find documents: {e}")
        return []


async def update_one(collection_name: str, filter: Dict[str, Any], update: Dict[str, Any]) -> bool:
    """
    Update a single document in a collection.

    Args:
        collection_name: Name of the collection
        filter: Query filter
        update: Update operations

    Returns:
        bool: True if a document was modified
    """
    try:
        db = await get_database()
        collection = db[collection_name]
        result = await collection.update_one(filter, update)
        return result.modified_count > 0
    except Exception as e:
        print(f"[❌] Failed to update document: {e}")
        return False


async def delete_one(collection_name: str, filter: Dict[str, Any]) -> bool:
    """
    Delete a single document from a collection.

    Args:
        collection_name: Name of the collection
        filter: Query filter

    Returns:
        bool: True if a document was deleted
    """
    try:
        db = await get_database()
        collection = db[collection_name]
        result = await collection.delete_one(filter)
        return result.deleted_count > 0
    except Exception as e:
        print(f"[❌] Failed to delete document: {e}")
        return False


async def list_collections() -> List[str]:
    """
    List all collections in the database.

    Returns:
        List of collection names
    """
    try:
        db = await get_database()
        collections = await db.list_collection_names()
        return collections
    except Exception as e:
        print(f"[❌] Failed to list collections: {e}")
        return []


async def test_connection() -> Dict[str, Any]:
    """
    Test the MongoDB connection and return status.

    Returns:
        Dict with connection status and details
    """
    try:
        if not CONNECTION_STRING:
            return {
                "connected": False,
                "error": "MDB_MCP_CONNECTION_STRING not set",
                "details": "Set MDB_MCP_CONNECTION_STRING in .env file"
            }

        client = await get_mongo_client()
        # Ping the database
        await client.admin.command('ping')

        # Get database info
        db = await get_database()
        collections = await db.list_collection_names()

        return {
            "connected": True,
            "database": DB_NAME,
            "collections": collections,
            "message": "MongoDB connection successful"
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "details": "Failed to connect to MongoDB"
        }
