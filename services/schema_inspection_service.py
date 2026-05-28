import os
import re
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

@dataclass
class CollectionSchema:
    """Represents the schema, indexes, and sample keys of a MongoDB collection."""
    name: str
    fields: Dict[str, str] = field(default_factory=dict)
    indexes: List[str] = field(default_factory=list)
    sample_document_keys: List[str] = field(default_factory=list)

@dataclass
class FieldChange:
    """Represents a single field or collection-level schema modification compared to previous state."""
    collection: str
    change_type: str        # "added_field", "removed_field", "type_changed", "added_collection", "removed_collection"
    field_name: Optional[str] = None  # None for collection-level changes
    old_value: Optional[str] = None
    new_value: Optional[str] = None

@dataclass
class SchemaDelta:
    """Represents differences detected between two schema snapshots."""
    has_changes: bool
    changes: List[FieldChange] = field(default_factory=list)

@dataclass
class SchemaInspectionReport:
    """Contains schema state metadata collected during a backend-touching MR audit."""
    inspected_at: datetime
    triggered_by_files: List[str]
    triggered_by_content: List[str] = field(default_factory=list)
    confidence: str = "LOW"
    scoped: bool = False
    skipped_reason: str = ""
    collections: List[CollectionSchema] = field(default_factory=list)
    delta: Optional[SchemaDelta] = None


def parse_diff_by_file(diff_text: str) -> Dict[str, str]:
    """
    Parses unified diff text into a dictionary mapping file path to its diff lines.
    
    Args:
        diff_text: Raw unified diff string.
        
    Returns:
        Dict of file paths to raw diff segments.
    """
    file_diffs = {}
    current_file = None
    current_lines = []
    
    file_header_re = re.compile(r'^diff --git a/(.+?) b/(.+)$')
    
    for line in diff_text.splitlines():
        match = file_header_re.match(line)
        if match:
            if current_file and current_lines:
                file_diffs[current_file] = "\n".join(current_lines)
            current_file = match.group(2)
            current_lines = [line]
        else:
            if current_file is not None:
                current_lines.append(line)
                
    if current_file and current_lines:
        file_diffs[current_file] = "\n".join(current_lines)
        
    return file_diffs


def detect_backend_change(diff_text: str) -> Tuple[bool, List[str], List[str], str]:
    """
    Detects if the incoming MR diff is backend-touching.
    
    Checks both file path patterns and scans added lines (starting with "+") for MongoDB operation keywords.
    Resolves a confidence score:
      - "HIGH"   -> matches migrations/ folder or endings: .model.py, models.py, .schema.py, .schema.js, .schema.ts
      - "MEDIUM" -> matches db/, database/, db_config.py/database.py keywords OR keyword matching in diff body
      - "LOW"    -> config.py keyword match with exactly one occurrence
      
    Args:
        diff_text: Raw unified diff string.
        
    Returns:
        Tuple[is_backend_change, triggered_by_files, triggered_by_content, confidence]
    """
    if not diff_text:
        return False, [], [], "LOW"
        
    file_diffs = parse_diff_by_file(diff_text)
    triggered_by_files = []
    triggered_by_content = []
    
    sus_patterns = ["models/", "schemas/", "migrations/", "db/", "database/"]
    high_extensions = (".model.py", ".schema.py", ".schema.js", ".schema.ts", "schema.ts")
    sus_special_files = ("db_config.py", "database.py", "config.py")
    keywords = ["collection", "schema", "MongoClient", "connection_string"]
    
    # MongoDB operation keywords to scan added lines for
    mongo_keywords = [
        'db[', '.find(', '.insert_one(', '.insert_many(', '.update_one(', '.update_many(',
        '.delete_one(', '.delete_many(', '.aggregate(', '$set', '$push', '$pull', '$addToSet',
        '.collection(', 'MongoClient', 'pymongo', 'mongoose.model', 'Schema({'
    ]
    
    # Content-based scan on lines starting with '+' (excluding metadata lines)
    content_matches = {}  # file_path -> list of matching lines
    for file_path, file_content in file_diffs.items():
        added_lines = [
            line for line in file_content.splitlines() 
            if line.startswith("+") and not line.startswith("+++")
        ]
        
        matches = []
        for line in added_lines:
            if any(kw in line for kw in mongo_keywords):
                matches.append(line)
                
        if matches:
            content_matches[file_path] = matches
            
    high_match = False
    medium_match = False
    low_match = False
    
    for file_path, file_content in file_diffs.items():
        path_lower = file_path.lower()
        filename = path_lower.split("/")[-1]
        matched_file = False
        file_high = False
        file_medium = False
        file_low = False
        
        # 1. High Path Patterns
        if "migrations/" in path_lower or filename.endswith(high_extensions) or filename == "models.py":
            matched_file = True
            file_high = True
            
        # 2. Content scan matched keywords
        if file_path in content_matches:
            matched_file = True
            file_medium = True
            for line in content_matches[file_path]:
                if len(triggered_by_content) < 5:
                    triggered_by_content.append(line)
                    
        # 3. Soft Path Patterns (db/, database/)
        if "db/" in path_lower or "database/" in path_lower:
            matched_file = True
            if not file_high:
                file_medium = True
                
        # 4. Special file keyword match
        if filename in ("db_config.py", "database.py"):
            content_lower = file_content.lower()
            occurrences = sum(content_lower.count(kw.lower()) for kw in keywords)
            if occurrences > 0:
                matched_file = True
                if not file_high:
                    file_medium = True
                    
        # 5. Low confidence config.py check
        if filename == "config.py":
            content_lower = file_content.lower()
            occurrences = sum(content_lower.count(kw.lower()) for kw in keywords)
            if occurrences > 0:
                matched_file = True
                if occurrences == 1:
                    file_low = True
                else:
                    file_medium = True
                    
        if matched_file:
            triggered_by_files.append(file_path)
            if file_high:
                high_match = True
            elif file_medium:
                medium_match = True
            elif file_low:
                low_match = True
                
    is_backend_change = len(triggered_by_files) > 0
    if not is_backend_change:
        return False, [], [], "LOW"
        
    # Resolve confidence rank
    if high_match:
        confidence = "HIGH"
    elif medium_match:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
        
    return is_backend_change, triggered_by_files, triggered_by_content, confidence


def parse_mcp_json_response(res: Any) -> Optional[Any]:
    """
    Safely extracts and parses JSON payload from MongoDB MCP tool call results.
    Handles both direct structuredContent output and formatUntrustedData tags.
    """
    if not res:
        return None
        
    # Try direct structuredContent
    if hasattr(res, "structuredContent") and res.structuredContent:
        return res.structuredContent
    if hasattr(res, "model_extra") and res.model_extra and "structuredContent" in res.model_extra:
        return res.model_extra["structuredContent"]
        
    # Try parsing text content from blocks
    if hasattr(res, "content") and res.content:
        for block in res.content:
            text = getattr(block, "text", None)
            if not text and isinstance(block, dict):
                text = block.get("text")
            if text:
                tag_match = re.search(r'<untrusted-user-data-[^>]+>\s*(.*?)\s*</untrusted-user-data-[^>]+>', text, re.DOTALL)
                if tag_match:
                    try:
                        return json.loads(tag_match.group(1))
                    except Exception:
                        pass
                try:
                    return json.loads(text)
                except Exception:
                    pass
    return None


async def get_target_database(mongo_session) -> str:
    """
    Resolves the database name by checking environment configs or listing databases.
    Defaults to 'gatekeeper_dev'.
    """
    import urllib.parse
    uri = os.getenv("MDB_MCP_CONNECTION_STRING") or os.getenv("MONGO_URI")
    if uri:
        try:
            parsed = urllib.parse.urlparse(uri)
            db_path = parsed.path.split("?")[0].lstrip("/")
            if db_path:
                return db_path
        except Exception:
            pass
            
    try:
        res = await mongo_session.call_tool(name="list-databases", arguments={})
        parsed = parse_mcp_json_response(res)
        if parsed and isinstance(parsed, dict) and "databases" in parsed:
            dbs = parsed["databases"]
            names = [db["name"] for db in dbs if db.get("name") not in ("admin", "config", "local")]
            if names:
                return names[0]
    except Exception as e:
        print(f"[⚠️] list-databases tool call failed: {e}")
        
    return "gatekeeper_dev"


def extract_normalized_words(paths: List[str], content_lines: List[str]) -> set:
    """Extracts lowercase alphanumeric words from paths and diff content for scoping queries."""
    words = set()
    for item in paths + content_lines:
        found = re.findall(r'[a-zA-Z0-9_]+', item)
        for f in found:
            words.add(f.lower())
    return words


def compute_schema_delta(prev_collections_data: List[dict], curr_collections: List[CollectionSchema]) -> SchemaDelta:
    """
    Computes a SchemaDelta between a previous database schema snapshot and the current schema.
    
    Args:
        prev_collections_data: Collection dictionaries loaded from the database snapshot log.
        curr_collections: List of current CollectionSchema instances.
        
    Returns:
        SchemaDelta dataclass instance.
    """
    changes = []
    
    prev_map = {}
    for col in prev_collections_data:
        if isinstance(col, dict) and "name" in col:
            prev_map[col["name"]] = col.get("fields", {})
            
    curr_map = {col.name: col.fields for col in curr_collections}
    
    # 1. Check for removed collections
    for col_name in prev_map:
        if col_name not in curr_map:
            changes.append(FieldChange(
                collection=col_name,
                change_type="removed_collection"
            ))
            
    # 2. Check for added collections and field modifications
    for col_name, curr_fields in curr_map.items():
        if col_name not in prev_map:
            changes.append(FieldChange(
                collection=col_name,
                change_type="added_collection"
            ))
        else:
            prev_fields = prev_map[col_name]
            
            # Check added or changed fields
            for f_name, f_type in curr_fields.items():
                if f_name not in prev_fields:
                    changes.append(FieldChange(
                        collection=col_name,
                        change_type="added_field",
                        field_name=f_name,
                        new_value=f_type
                    ))
                elif prev_fields[f_name] != f_type:
                    changes.append(FieldChange(
                        collection=col_name,
                        change_type="type_changed",
                        field_name=f_name,
                        old_value=prev_fields[f_name],
                        new_value=f_type
                    ))
                    
            # Check removed fields
            for f_name, f_type in prev_fields.items():
                if f_name not in curr_fields:
                    changes.append(FieldChange(
                        collection=col_name,
                        change_type="removed_field",
                        field_name=f_name,
                        old_value=f_type
                    ))
                    
    has_changes = len(changes) > 0
    return SchemaDelta(has_changes=has_changes, changes=changes)


def extract_collections_from_diff(diff_text: str) -> List[str]:
    """
    Extracts MongoDB collection names from unified diff text using regex patterns,
    including file path indicators.
    """
    if not diff_text:
        return []
        
    collections = set()
    
    # 1. Parse file paths in diff header (e.g., a/models/users.py)
    file_diffs = parse_diff_by_file(diff_text)
    for path in file_diffs.keys():
        path_lower = path.lower()
        filename = path_lower.split("/")[-1]
        base_name = filename.split(".")[0]
        if any(folder in path_lower for folder in ("models/", "schemas/")):
            collections.add(base_name)
            if not base_name.endswith('s'):
                collections.add(base_name + 's')
                
    # 2. Parse database operations in diff text
    patterns = [
        r'db\.([a-zA-Z0-9_]+)\.[a-zA-Z0-9_]+',
        r'db\[[\'"]([a-zA-Z0-9_]+)[\'"]\]',
        r'db\.get_collection\([\'"]([a-zA-Z0-9_]+)[\'"]\)',
        r'\.collection\([\'"]([a-zA-Z0-9_]+)[\'"]\)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, diff_text)
        for m in matches:
            if m not in ('prototype', 'constructor', 'find', 'insert', 'update', 'delete', 'aggregate', 'get_database'):
                collections.add(m)
                
    return sorted(list(collections))


async def _get_target_mongodb_uri(project_id: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Fetches and decrypts the target MongoDB URI and Fivetran secrets for a repository.
    Returns (mongodb_uri, db_name, is_encrypted)
    """
    if not project_id:
        return None, None, False

    try:
        from services import mongo_client
        # Query connected_repositories for the project_id (which is a string)
        repo = await mongo_client.find_one(
            collection_name="connected_repositories",
            filter={"id": str(project_id)}
        )
        if not repo:
            # Try to match numeric project_id if it's passed as int or string
            repo = await mongo_client.find_one(
                collection_name="connected_repositories",
                filter={"id": project_id}
            )

        if repo and "mongodb_uri" in repo and repo["mongodb_uri"]:
            uri = repo["mongodb_uri"]
            is_encrypted = repo.get("credentials_encrypted", False)

            if is_encrypted:
                from services.encryption_service import decrypt_value
                uri = decrypt_value(uri)

            import urllib.parse
            parsed = urllib.parse.urlparse(uri)
            db_name = parsed.path.split("?")[0].lstrip("/") or "gatekeeper_target"
            return uri, db_name, is_encrypted
    except Exception as e:
        print(f"[⚠️] Failed to fetch target database credentials for project {project_id}: {e}")

    return None, None, False


def infer_mongo_type(val) -> str:
    if val is None:
        return "null"
    t_name = type(val).__name__
    if t_name == "ObjectId":
        return "objectId"
    if t_name == "str":
        return "string"
    if t_name == "int":
        return "number"
    if t_name == "float":
        return "number"
    if t_name == "bool":
        return "boolean"
    if t_name == "dict":
        return "object"
    if t_name == "list":
        return "array"
    if t_name == "datetime":
        return "date"
    return t_name


async def run_schema_inspection(diff_text: str, mongo_session=None, project_id: Optional[Any] = None) -> Optional[SchemaInspectionReport]:
    """
    Performs database schema discovery and computes changes compared to previous state.
    Uses dynamic direct Motor client to connect to the target database.

    Args:
        diff_text: The Git Merge Request diff text.
        mongo_session: Deprecated/unused (for backward compatibility).
        project_id: The project identifier from the GitLab webhook payload (optional).

    Returns:
        SchemaInspectionReport if a backend change was matched and inspected, else None.
    """
    is_backend_change, suspicious_files, triggered_by_content, confidence = detect_backend_change(diff_text)
    if not is_backend_change:
        return None

    print(f"[+] Backend change detected (Confidence: {confidence})")
    print(f"[+] Files: {suspicious_files}")
    if triggered_by_content:
        print(f"[+] Content lines: {triggered_by_content}")

    # Gating Logic (LOW confidence checks skip MCP calls entirely)
    if confidence == "LOW":
        return SchemaInspectionReport(
            inspected_at=datetime.now(timezone.utc),
            triggered_by_files=suspicious_files,
            triggered_by_content=triggered_by_content,
            confidence=confidence,
            scoped=False,
            skipped_reason="Low confidence backend change — target DB queries skipped",
            collections=[],
            delta=None
        )

    try:
        # 1. Retrieve dynamic credentials for project
        uri, db_name, is_encrypted = await _get_target_mongodb_uri(project_id)

        if not uri:
            print(f"[⚠️] No target database URI configured for project {project_id}; skipping target schema inspection.")
            return SchemaInspectionReport(
                inspected_at=datetime.now(timezone.utc),
                triggered_by_files=suspicious_files,
                triggered_by_content=triggered_by_content,
                confidence=confidence,
                scoped=False,
                skipped_reason="No target MongoDB URI onboarded",
                collections=[],
                delta=None
            )

        print(f"[*] Decoupled: connecting to target database '{db_name}' directly...")
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]

        # 2. Retrieve collection names directly from the target database
        try:
            db_collections = await db.list_collection_names()
            # Filter out system collections
            target_collections = [col for col in db_collections if not col.startswith("system.")]
            print(f"[+] Retrieved target collections from database: {target_collections}")
            scoped = False
        except Exception as list_err:
            print(f"[⚠️] Failed to list collections from database: {list_err}")
            # Fall back to extracted collections from diff
            extracted_collections = extract_collections_from_diff(diff_text)
            print(f"[+] Falling back to extracted collections from diff: {extracted_collections}")
            target_collections = extracted_collections
            scoped = True

        # 3. Query details for target collections directly from target database
        collection_schemas = []
        for col_name in target_collections:
            fields = {}
            indexes = []
            sample_keys = []

            # Query schema
            try:
                # Query up to 5 documents to infer schema
                cursor = db[col_name].find().limit(5)
                sample_docs = await cursor.to_list(length=5)

                for doc in sample_docs:
                    for k, v in doc.items():
                        if k not in fields:
                            fields[k] = infer_mongo_type(v)
                            sample_keys.append(k)
            except Exception as e:
                print(f"[⚠️] Failed to query schema/sample documents for '{col_name}': {e}")

            # Query indexes
            try:
                idx_info = await db[col_name].index_information()
                for idx_name in idx_info.keys():
                    indexes.append(idx_name)
            except Exception as e:
                print(f"[⚠️] Failed to query indexes for '{col_name}': {e}")

            collection_schemas.append(CollectionSchema(
                name=col_name,
                fields=fields,
                indexes=indexes,
                sample_document_keys=sample_keys
            ))

        # Close direct client connection
        client.close()

        # 4. Schema Delta Comparison
        delta = None
        if project_id:
            try:
                print(f"[*] Fetching previous snapshot from schema_snapshots collection for project: {project_id}...")
                from services import mongo_client
                prev_docs = await mongo_client.find(
                    collection_name="schema_snapshots",
                    filter={"project_id": str(project_id)},
                    limit=1,
                    sort=[("timestamp", -1)]
                )

                # Check with raw project_id (sometimes passed as int)
                if not prev_docs:
                    prev_docs = await mongo_client.find(
                        collection_name="schema_snapshots",
                        filter={"project_id": project_id},
                        limit=1,
                        sort=[("timestamp", -1)]
                    )

                if prev_docs and len(prev_docs) > 0:
                    last_snapshot = prev_docs[0]
                    prev_report = last_snapshot.get("report", {})
                    prev_collections_data = prev_report.get("collections", [])
                    delta = compute_schema_delta(prev_collections_data, collection_schemas)
                else:
                    print("[ℹ️] No previous schema snapshot found for this project.")
            except Exception as delta_err:
                print(f"[⚠️] Failed to compute schema delta: {delta_err}")

        return SchemaInspectionReport(
            inspected_at=datetime.now(timezone.utc),
            triggered_by_files=suspicious_files,
            triggered_by_content=triggered_by_content,
            confidence=confidence,
            scoped=scoped,
            collections=collection_schemas,
            delta=delta
        )
    except Exception as e:
        print(f"[x] Error executing schema inspection: {e}")
        return SchemaInspectionReport(
            inspected_at=datetime.now(timezone.utc),
            triggered_by_files=suspicious_files,
            triggered_by_content=triggered_by_content,
            confidence=confidence,
            scoped=False,
            collections=[]
        )



def format_schema_report_to_markdown(report: SchemaInspectionReport) -> str:
    """
    Formats the SchemaInspectionReport and SchemaDelta into a markdown representation suitable for Gemini context.
    
    Args:
        report: SchemaInspectionReport instance.
        
    Returns:
        Formatted markdown block string.
    """
    if not report:
        return ""
        
    lines = []
    
    # Delta Section
    if report.delta is None:
        lines.append("## Schema Delta")
        lines.append("ℹ️ No previous snapshot found for this project. This is the baseline.")
    else:
        lines.append("## Schema Delta (vs last snapshot)")
        if not report.delta.has_changes:
            lines.append("✅ No schema changes detected across any collections.")
        else:
            changed_cols = set(change.collection for change in report.delta.changes)
            all_cols = set(col.name for col in report.collections)
            
            for change in report.delta.changes:
                col = change.collection
                if change.change_type == "added_collection":
                    lines.append(f"⚠️ Collection `{col}`: ADDED collection detected")
                elif change.change_type == "removed_collection":
                    lines.append(f"⚠️ Collection `{col}`: REMOVED collection detected")
                elif change.change_type == "added_field":
                    lines.append(f"⚠️ Collection `{col}`: NEW field `{change.field_name}` ({change.new_value}) detected")
                elif change.change_type == "removed_field":
                    lines.append(f"⚠️ Collection `{col}`: REMOVED field `{change.field_name}`")
                elif change.change_type == "type_changed":
                    lines.append(f"⚠️ Collection `{col}`: TYPE CHANGED for field `{change.field_name}` from `{change.old_value}` to `{change.new_value}`")
                    
            for col in sorted(all_cols):
                if col not in changed_cols:
                    lines.append(f"✅ No changes detected in `{col}`")
                    
    lines.append("")
    
    # Full Schema Section
    lines.append("## Current MongoDB Schema State")
    triggered_files = ", ".join(f"`{f}`" for f in report.triggered_by_files)
    lines.append(f"**Triggered by files:** {triggered_files}")
    if report.triggered_by_content:
        triggered_content = ", ".join(f"`{c.strip()}`" for c in report.triggered_by_content)
        lines.append(f"**Triggered by content patterns:** {triggered_content}")
    lines.append("")
    
    if report.skipped_reason:
        lines.append(f"ℹ️ *{report.skipped_reason}*")
        lines.append("")
    elif not report.collections:
        lines.append("ℹ️ *No collections matched for inspection.*")
        lines.append("")
    else:
        for col in report.collections:
            lines.append(f"### Collection: {col.name}")
            lines.append("| Field | Type |")
            lines.append("|-------|------|")
            
            if col.fields:
                for field_name, field_type in col.fields.items():
                    lines.append(f"| {field_name} | {field_type} |")
            else:
                lines.append("| (No schema inferred) | - |")
                
            lines.append("")
            indexes_str = ", ".join(col.indexes) if col.indexes else "None"
            lines.append(f"**Indexes:** {indexes_str}")
            lines.append("")
            
    return "\n".join(lines)
