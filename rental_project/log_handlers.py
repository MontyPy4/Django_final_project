import logging
import time
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None


class MongoLogHandler(logging.Handler):
    """Logging handler that writes records into a MongoDB collection.

    Designed to never crash the app: failures to connect/insert are silently
    suppressed (logged via handleError) and the handler backs off for
    RETRY_AFTER_SECONDS before trying to reconnect.
    """

    RETRY_AFTER_SECONDS = 30

    def __init__(
        self,
        uri='mongodb://localhost:27017',
        db_name='rental_logs',
        collection='app_logs',
        timeout_ms=1500,
        level=logging.NOTSET,
    ):
        super().__init__(level)
        self._uri = uri
        self._db_name = db_name
        self._collection_name = collection
        self._timeout_ms = timeout_ms
        self._client = None
        self._collection = None
        self._failed_at = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        if MongoClient is None:
            return None
        if self._failed_at and (time.monotonic() - self._failed_at) < self.RETRY_AFTER_SECONDS:
            return None
        try:
            self._client = MongoClient(self._uri, serverSelectionTimeoutMS=self._timeout_ms)
            self._client.admin.command('ping')
            self._collection = self._client[self._db_name][self._collection_name]
            self._failed_at = None
            return self._collection
        except Exception:
            self._failed_at = time.monotonic()
            return None

    def emit(self, record):
        collection = self._get_collection()
        if collection is None:
            return
        try:
            doc = {
                'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'func': record.funcName,
                'line': record.lineno,
                'process': record.process,
                'thread': record.thread,
            }
            if record.exc_info:
                doc['exception'] = self.format(record)
            collection.insert_one(doc)
        except Exception:
            self._collection = None
            self._failed_at = time.monotonic()
            self.handleError(record)
