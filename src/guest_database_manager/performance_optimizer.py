"""Performance optimization utilities for the Guest Database Manager.

This module provides caching, indexing, and query optimization features
to dramatically improve application responsiveness.
"""

import functools
import logging
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class QueryCache:
    """In-memory cache for frequently accessed database queries."""
    
    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache with time-to-live in seconds."""
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                logger.debug(f"Cache hit for key: {key}")
                return value
            else:
                logger.debug(f"Cache expired for key: {key}")
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Store value in cache with current timestamp."""
        self._cache[key] = (value, time.time())
        logger.debug(f"Cached value for key: {key}")
    
    def invalidate(self, pattern: Optional[str] = None) -> None:
        """Invalidate cache entries matching pattern, or all if pattern is None."""
        if pattern is None:
            self._cache.clear()
            logger.info("Cache cleared completely")
        else:
            keys_to_delete = [k for k in self._cache if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self.invalidate()


# Global cache instance
_global_cache = QueryCache(ttl_seconds=300)


def cached_query(cache_key_prefix: str, ttl_seconds: int = 300):
    """Decorator to cache query results with automatic key generation."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [cache_key_prefix, func.__name__]
            for arg in args[1:]:  # Skip 'self'
                key_parts.append(str(arg))
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            cache_key = ":".join(key_parts)
            
            # Check cache
            cached_result = _global_cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute query and cache result
            result = func(*args, **kwargs)
            _global_cache.set(cache_key, result)
            return result
        
        return wrapper
    return decorator


def invalidate_cache(pattern: Optional[str] = None) -> None:
    """Invalidate cached queries matching pattern."""
    _global_cache.invalidate(pattern)


class DatabaseOptimizer:
    """Utilities for optimizing SQLite database performance."""
    
    @staticmethod
    def create_indexes(db_path: str) -> None:
        """Create indexes on frequently queried columns for faster lookups."""
        indexes = [
            # Guest table indexes
            ("idx_guests_email", "guests", "email"),
            ("idx_guests_full_name", "guests", "full_name"),
            ("idx_guests_is_processed", "guests", "is_processed"),
            ("idx_guests_email_status", "guests", "email_status"),
            ("idx_guests_date_added", "guests", "date_added"),
            ("idx_guests_booking_token", "guests", "booking_token"),
            # Composite indexes for common filter combinations
            ("idx_guests_processed_date", "guests", "is_processed, date_added"),
            ("idx_guests_status_date", "guests", "email_status, date_added"),
            # Interview table indexes
            ("idx_interviews_guest_id", "interviews", "guest_id"),
            ("idx_interviews_calendar_event", "interviews", "calendar_event_id"),
            ("idx_interviews_scheduled_for", "interviews", "scheduled_for"),
            ("idx_interviews_status", "interviews", "status"),
            # Episode table indexes
            ("idx_episodes_guest_id", "episodes", "guest_id"),
            ("idx_episodes_release_date", "episodes", "release_date"),
            ("idx_episodes_release_status", "episodes", "release_status"),
        ]
        
        with sqlite3.connect(db_path) as conn:
            for index_name, table_name, columns in indexes:
                try:
                    conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})")
                    logger.info(f"Created/verified index: {index_name}")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not create index {index_name}: {e}")
            conn.commit()
    
    @staticmethod
    def optimize_database(db_path: str) -> None:
        """Run VACUUM and ANALYZE to optimize database performance."""
        with sqlite3.connect(db_path) as conn:
            logger.info("Running ANALYZE to update query planner statistics...")
            conn.execute("ANALYZE")
            logger.info("Optimization complete")
    
    @staticmethod
    def configure_connection(conn: sqlite3.Connection) -> None:
        """Configure connection for optimal performance."""
        # Enable Write-Ahead Logging for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        # Increase cache size (default is 2MB, set to 20MB)
        conn.execute("PRAGMA cache_size=-20000")
        # Set synchronous to NORMAL for better performance (still safe)
        conn.execute("PRAGMA synchronous=NORMAL")
        # Enable memory-mapped I/O (30MB)
        conn.execute("PRAGMA mmap_size=30000000")
        logger.debug("Connection configured for optimal performance")


class BatchProcessor:
    """Utilities for batch processing database operations."""
    
    @staticmethod
    def batch_insert_guests(conn: sqlite3.Connection, guests_data: List[Dict[str, Any]]) -> int:
        """Insert multiple guests in a single transaction for better performance."""
        if not guests_data:
            return 0
        
        inserted_count = 0
        cursor = conn.cursor()
        
        insert_sql = """
            INSERT OR IGNORE INTO guests (
                name, full_name, email, website, social_media_handles, 
                background, profession, motivation, life_experiences, core_values, 
                faith_practice, beliefs_align, favorite_quote, passionate_topics, message_takeaway,
                podcast_experience, additional_info, following_us, is_processed,
                original_file_name, original_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        for guest in guests_data:
            values = (
                guest.get('full_name'), guest.get('full_name'), guest.get('email'), 
                guest.get('website'), guest.get('social_handles'),
                guest.get('background'), guest.get('profession'), guest.get('motivation'), 
                guest.get('life_experiences'), guest.get('core_values'), guest.get('faith'), 
                guest.get('alignment'), guest.get('favorite_quote'), guest.get('passionate_topics'), 
                guest.get('message'), guest.get('experience'), guest.get('additional_info'), 
                guest.get('has_social_media'), guest.get('is_processed', False),
                guest.get('original_file_name'), guest.get('original_data'),
            )
            cursor.execute(insert_sql, values)
            if cursor.rowcount > 0:
                inserted_count += 1
        
        conn.commit()
        logger.info(f"Batch inserted {inserted_count} guests")
        return inserted_count


class PaginatedQuery:
    """Helper for efficient pagination of large result sets."""
    
    @staticmethod
    def paginate_guests(
        conn: sqlite3.Connection,
        page: int = 1,
        page_size: int = 25,
        status_filter: Optional[str] = None,
        search_term: Optional[str] = None,
        order_by: str = "date_added DESC"
    ) -> Dict[str, Any]:
        """
        Fetch paginated guests with efficient SQL-level filtering and sorting.
        
        Returns dict with 'guests', 'total_count', 'page', 'page_size', 'total_pages'
        """
        conn.row_factory = sqlite3.Row
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if status_filter == "Processed":
            where_conditions.append("is_processed = 1")
        elif status_filter == "Unprocessed":
            where_conditions.append("is_processed = 0")
        
        if search_term:
            search_conditions = [
                "full_name LIKE ?",
                "email LIKE ?",
                "profession LIKE ?",
                "background LIKE ?",
                "passionate_topics LIKE ?",
                "additional_info LIKE ?",
                "social_media_handles LIKE ?",
                "website LIKE ?"
            ]
            where_conditions.append(f"({' OR '.join(search_conditions)})")
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern] * len(search_conditions))
        
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM guests {where_clause}"
        total_count = conn.execute(count_query, params).fetchone()['total']
        
        # Calculate pagination
        total_pages = (total_count - 1) // page_size + 1 if total_count > 0 else 1
        offset = (page - 1) * page_size
        
        # Fetch page of results
        query = f"""
            SELECT * FROM guests
            {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])
        guests = [dict(row) for row in conn.execute(query, params).fetchall()]
        
        return {
            'guests': guests,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages
        }


class PerformanceMonitor:
    """Monitor and log database query performance."""
    
    def __init__(self, threshold_ms: float = 100):
        """Initialize monitor with slow query threshold in milliseconds."""
        self.threshold_ms = threshold_ms
    
    def monitor_query(self, query_name: str):
        """Decorator to monitor query execution time."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    elapsed_ms = (time.time() - start_time) * 1000
                    if elapsed_ms > self.threshold_ms:
                        logger.warning(f"Slow query '{query_name}': {elapsed_ms:.2f}ms")
                    else:
                        logger.debug(f"Query '{query_name}': {elapsed_ms:.2f}ms")
            return wrapper
        return decorator


# Convenience function to initialize all optimizations
def initialize_performance_optimizations(db_path: str) -> None:
    """Initialize all performance optimizations for the database."""
    logger.info("Initializing performance optimizations...")
    DatabaseOptimizer.create_indexes(db_path)
    DatabaseOptimizer.optimize_database(db_path)
    logger.info("Performance optimizations complete!")
