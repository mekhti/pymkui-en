"""
Database management module for PyMKUI
"""
import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import config
import mk_logger

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path if db_path else config.DATABASE_PATH
        self.connection: sqlite3.Connection
        self.cursor: sqlite3.Cursor
        self.init_db()
    
    def init_db(self):
        """Initialize database connection"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        # SQLite does not enable foreign key constraints by default; must enable them manually after each connection
        self.cursor.execute("PRAGMA foreign_keys = ON")

        self._create_tables()
    
    def _get_local_timezone(self):
        """Get the local timezone"""
        import datetime
        try:
            return datetime.datetime.now().astimezone().tzinfo
        except Exception:
            return None
    
    def _date_to_timestamp_range(self, date_str):
        """Convert a date string to the timestamp range of that day"""
        import datetime
        import time
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            # Try to use the local timezone
            local_tz = self._get_local_timezone()
            if local_tz:
                local_date = date_obj.replace(tzinfo=local_tz)
                start_of_day = int(local_date.timestamp())
            else:
                # If the local timezone can't be obtained, use the default method
                start_of_day = int(time.mktime(date_obj.timetuple()))
            end_of_day = start_of_day + 86399  # 23:59:59 of that day
            return start_of_day, end_of_day
        except ValueError:
            return None, None
    
    def _month_to_timestamp_range(self, year, month):
        """Convert a year-month to the timestamp range of that month"""
        import datetime
        import time
        try:
            start_date = datetime.datetime(year, month, 1)
            if month == 12:
                end_date = datetime.datetime(year + 1, 1, 1)
            else:
                end_date = datetime.datetime(year, month + 1, 1)
            
            # Try to use the local timezone
            local_tz = self._get_local_timezone()
            if local_tz:
                start_date_local = start_date.replace(tzinfo=local_tz)
                end_date_local = end_date.replace(tzinfo=local_tz)
                start_ts = int(start_date_local.timestamp())
                end_ts = int(end_date_local.timestamp()) - 1  # last second of the month
            else:
                # If the local timezone can't be obtained, use the default method
                start_ts = int(time.mktime(start_date.timetuple()))
                end_ts = int(time.mktime(end_date.timetuple())) - 1
            return start_ts, end_ts
        except Exception:
            return None, None

    def _cursor(self) -> sqlite3.Cursor:
        """Return a new independent cursor on each call to avoid errors from recursively reusing the same cursor"""
        cur = self.connection.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        return cur
    
    def _create_tables(self):
        """Create necessary tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pull_proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vhost TEXT NOT NULL DEFAULT '__defaultVhost__',
                app TEXT NOT NULL,
                stream TEXT NOT NULL,
                remark TEXT DEFAULT '',
                custom_params TEXT,
                protocol_params TEXT,
                on_demand INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT current_timestamp,
                updated_at TIMESTAMP DEFAULT current_timestamp,
                UNIQUE(vhost, app, stream)
            )
        ''')

        # Multi-address table: each proxy can have multiple pull URLs; smaller priority means higher precedence
        # params field (JSON) stores params specific to this address, e.g. schema, rtp_type, etc.
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pull_proxy_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                params TEXT DEFAULT '{}',
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT current_timestamp,
                FOREIGN KEY(proxy_id) REFERENCES pull_proxies(id) ON DELETE CASCADE
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS push_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                app TEXT not NULL,
                stream TEXT,
                url TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT current_timestamp,
                updated_at TIMESTAMP DEFAULT current_timestamp
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vhost       TEXT NOT NULL DEFAULT '__defaultVhost__',
                app         TEXT NOT NULL,
                stream      TEXT NOT NULL,
                file_name   TEXT,
                file_path   TEXT,
                file_size   INTEGER,
                url         TEXT NOT NULL,
                start_time  INTEGER,
                time_len    REAL,
                created_at  TIMESTAMP DEFAULT current_timestamp,
                UNIQUE(file_path)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS protocol_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                modify_stamp TEXT,
                enable_audio TEXT,
                add_mute_audio TEXT,
                auto_close TEXT,
                continue_push_ms TEXT,
                paced_sender_ms TEXT,
                enable_hls TEXT,
                enable_hls_fmp4 TEXT,
                enable_mp4 TEXT,
                enable_rtsp TEXT,
                enable_rtmp TEXT,
                enable_ts TEXT,
                enable_fmp4 TEXT,
                mp4_as_player TEXT,
                mp4_max_second TEXT,
                mp4_save_path TEXT,
                hls_save_path TEXT,
                hls_demand TEXT,
                rtsp_demand TEXT,
                rtmp_demand TEXT,
                ts_demand TEXT,
                fmp4_demand TEXT,
                created_at TIMESTAMP DEFAULT current_timestamp,
                updated_at TIMESTAMP DEFAULT current_timestamp
            )
        ''')

        # Plugin event binding table: each record = one event type + one plugin binding, with params and priority
        # priority the smaller it is, the earlier it executes; params is a JSON object storing this binding's custom params
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS plugin_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                priority INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                hit_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT current_timestamp
            )
        ''')

        self.connection.commit()

        # Insert default bindings only when the plugin_bindings table is empty (first DB creation)
        self.cursor.execute("SELECT COUNT(*) FROM plugin_bindings")
        if self.cursor.fetchone()[0] == 0:
            self._init_default_plugin_bindings()

        mk_logger.log_info(f"Database initialized at {self.db_path}")

    def _init_default_plugin_bindings(self):
        """Insert default binding records for built-in plugins (called only on first DB creation when the table is empty)"""
        defaults = [
            ("on_stream_not_found",    "pull_proxy_on_demand",  "{}", 0, 1),
            ("on_player_proxy_failed", "pull_proxy_failover",   "{}", 0, 1),
            ("on_start",               "pull_proxy_restore",    "{}", 0, 1),
            ("on_start",               "record_cleanup",        '{}', 10, 1),
            ("on_http_access",         "http_access_frontend",  "{}", 0, 1),
            ("on_record_mp4",          "record_mp4_logger",     "{}", 0, 1),
        ]
        for event_type, plugin_name, params, priority, enabled in defaults:
            self.cursor.execute(
                """
                INSERT INTO plugin_bindings
                    (event_type, plugin_name, params, priority, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, plugin_name, params, priority, enabled),
            )
        self.connection.commit()
        mk_logger.log_info("[Database] Default plugin bindings initialized")
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()
    
    def add_proxy(self, app: str, stream: str, url: str, enabled: bool = True) -> Optional[Dict[str, Any]]:
        """Add a proxy configuration"""
        try:
            cur = self._cursor()
            cur.execute(
                'INSERT INTO pull_proxies (app, stream, url, enabled) VALUES (?, ?, ?, ?)',
                (app, stream, url, enabled)
            )
            self.connection.commit()
            proxy_id = cur.lastrowid
            return {
                'id': proxy_id,
                'app': app,
                'stream': stream,
                'url': url,
                'enabled': enabled,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except sqlite3.IntegrityError as e:
            self.connection.rollback()
            raise Exception(f"Failed to add proxy: {e}")
    
    def get_proxy(self, proxy_id: int) -> Optional[Dict[str, Any]]:
        """Get proxy configuration by ID"""
        try:
            cur = self._cursor()
            cur.execute(
                'SELECT * FROM pull_proxies WHERE id = ?',
                (proxy_id,)
            )
            row = cur.fetchone()
            if row:
                return dict(row)
            return None
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to get proxy: {e}")
            return None
    
    def get_all_proxies(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all proxy configurations"""
        try:
            cur = self._cursor()
            if enabled_only:
                cur.execute(
                    'SELECT * FROM pull_proxies WHERE enabled = 1 ORDER BY created_at DESC'
                )
            else:
                cur.execute(
                    'SELECT * FROM pull_proxies ORDER BY created_at DESC'
                )
            
            proxies = []
            for row in cur.fetchall():
                proxies.append(dict(row))
            return proxies
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to get all proxies: {e}")
            return []
    
    def update_proxy(self, proxy_id: int, **kwargs) -> bool:
        """Update proxy configuration"""
        try:
            cur = self._cursor()
            set_clause = []
            values = []
            
            for key, value in kwargs.items():
                set_clause.append(f"{key} = ?")
                values.append(value)
            
            if set_clause:
                set_clause.append("updated_at = ?")
                values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                
                query = f"UPDATE pull_proxies SET {', '.join(set_clause)} WHERE id = ?"
                values.append(proxy_id)
                cur.execute(query, values)
                self.connection.commit()
                return True
            return False
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to update proxy: {e}")
            return False
    
    def delete_proxy(self, proxy_id: int) -> bool:
        """Delete proxy configuration"""
        try:
            cur = self._cursor()
            cur.execute('DELETE FROM pull_proxies WHERE id = ?', (proxy_id,))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to delete proxy: {e}")
            return False
    
    def add_recording(self, info: dict) -> Optional[int]:
        """Write an on_record_mp4 recording record; ignore if file_path is the same"""
        try:
            cur = self._cursor()
            cur.execute(
                '''INSERT OR IGNORE INTO recordings
                   (vhost, app, stream, file_name, file_path, file_size, url, start_time, time_len)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    info.get("vhost", "__defaultVhost__"),
                    info.get("app", ""),
                    info.get("stream", ""),
                    info.get("file_name", ""),
                    info.get("file_path", ""),
                    int(info.get("file_size", 0) or 0),
                    info.get("url", ""),
                    int(info.get("start_time", 0) or 0),
                    float(info.get("time_len", 0.0) or 0.0),
                ),
            )
            self.connection.commit()
            return cur.lastrowid
        except Exception as e:
            mk_logger.log_warn(f"add_recording error: {e}")
            return None

    def get_recordings(self, app: str = "", stream: str = "", vhost: str = "",
                       date: str = "", limit: int = 500, offset: int = 0,
                       start_ts: int = 0, end_ts: int = 0) -> List[Dict[str, Any]]:
        """Query the recordings list; supports filtering by app/stream/vhost/date/timestamp-range"""
        try:
            clauses, params = [], []
            if vhost:
                clauses.append("vhost = ?"); params.append(vhost)
            if app:
                clauses.append("app = ?"); params.append(app)
            if stream:
                clauses.append("stream = ?"); params.append(stream)
            if date:
                # Use the abstracted method to convert the date to a timestamp range
                start_of_day, end_of_day = self._date_to_timestamp_range(date)
                if start_of_day and end_of_day:
                    clauses.append("start_time >= ?"); params.append(start_of_day)
                    clauses.append("start_time <= ?"); params.append(end_of_day)
            if start_ts:
                clauses.append("start_time >= ?"); params.append(start_ts)
            if end_ts:
                clauses.append("start_time <= ?"); params.append(end_ts)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params += [limit, offset]
            cur = self._cursor()
            cur.execute(
                f"SELECT * FROM recordings {where} ORDER BY start_time DESC LIMIT ? OFFSET ?",
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            mk_logger.log_warn(f"get_recordings error: {e}")
            return []

    def get_recording_streams(self) -> List[Dict[str, Any]]:
        """Return all vhost/app/stream combinations that have recordings (deduplicated)"""
        try:
            cur = self._cursor()
            cur.execute(
                "SELECT DISTINCT vhost, app, stream FROM recordings ORDER BY app, stream"
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            mk_logger.log_warn(f"get_recording_streams error: {e}")
            return []

    def _remove_file_and_empty_parents(self, file_path: Optional[str]):
        """Delete the file, then remove empty directories level by level upward"""
        if not file_path or not os.path.isfile(file_path):
            return
        try:
            os.remove(file_path)
        except Exception as e:
            mk_logger.log_warn(f"[Database] Failed to delete file {file_path}: {e}")
            return
        # Clean up empty directories level by level upward
        parent = os.path.dirname(file_path)
        while parent and os.path.isdir(parent):
            try:
                if os.listdir(parent):  # not empty, stop
                    break
                os.rmdir(parent)
                mk_logger.log_info(f"[Database] Removed empty directory {parent}")
                parent = os.path.dirname(parent)
            except Exception:
                break

    def delete_recording(self, recording_id: int) -> bool:
        """Delete a recording record, and also delete the file and empty parent directories"""
        try:
            cur = self._cursor()
            cur.execute("SELECT file_path FROM recordings WHERE id = ?", (recording_id,))
            row = cur.fetchone()
            if row:
                self._remove_file_and_empty_parents(row["file_path"])
            cur.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
            self.connection.commit()
            return True
        except Exception as e:
            mk_logger.log_warn(f"delete_recording error: {e}")
            return False

    def get_recording(self, app: str, stream: str, file_path: str) -> Optional[Dict[str, Any]]:
        """Query a single recording by file_path"""
        try:
            cur = self._cursor()
            cur.execute(
                "SELECT * FROM recordings WHERE app = ? AND stream = ? AND file_path = ?",
                (app, stream, file_path),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            mk_logger.log_warn(f"get_recording error: {e}")
            return None

    def get_recording_by_id(self, rec_id: int) -> Optional[Dict[str, Any]]:
        """Query a single recording by primary key id"""
        try:
            cur = self._cursor()
            cur.execute("SELECT * FROM recordings WHERE id = ?", (rec_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            mk_logger.log_warn(f"get_recording_by_id error: {e}")
            return None

    def delete_recordings_by_stream(self, vhost: str, app: str, stream: str) -> int:
        """Delete all recording records of a given stream; return the number deleted"""
        try:
            cur = self._cursor()
            cur.execute(
                "SELECT id, file_path FROM recordings WHERE vhost=? AND app=? AND stream=?",
                (vhost, app, stream)
            )
            rows = cur.fetchall()
            for r in rows:
                self._remove_file_and_empty_parents(r["file_path"] if "file_path" in r.keys() else None)
            cur.execute(
                "DELETE FROM recordings WHERE vhost=? AND app=? AND stream=?",
                (vhost, app, stream)
            )
            self.connection.commit()
            return len(rows)
        except Exception as e:
            mk_logger.log_warn(f"delete_recordings_by_stream error: {e}")
            return 0

    def delete_recordings_by_stream_date(self, vhost: str, app: str, stream: str, date: str) -> int:
        """Delete all recording records of a given stream on a given day (date: YYYY-MM-DD); return the number deleted"""
        try:
            # Use the abstracted method to convert the date to a timestamp range
            start_of_day, end_of_day = self._date_to_timestamp_range(date)
            if not start_of_day or not end_of_day:
                return 0  # invalid date format, return 0
            
            cur = self._cursor()
            cur.execute(
                "SELECT id, file_path FROM recordings WHERE vhost=? AND app=? AND stream=? AND start_time >= ? AND start_time <= ?",
                (vhost, app, stream, start_of_day, end_of_day)
            )
            rows = cur.fetchall()
            for r in rows:
                self._remove_file_and_empty_parents(r["file_path"] if "file_path" in r.keys() else None)
            cur.execute(
                "DELETE FROM recordings WHERE vhost=? AND app=? AND stream=? AND start_time >= ? AND start_time <= ?",
                (vhost, app, stream, start_of_day, end_of_day)
            )
            self.connection.commit()
            return len(rows)
        except Exception as e:
            mk_logger.log_warn(f"delete_recordings_by_stream_date error: {e}")
            return 0

    def get_recording_dates(self, year: int, month: int,
                            app: str = "", stream: str = "", vhost: str = "") -> list:
        """Return the list of dates that have recordings in the given year-month (YYYY-MM-DD string list)"""
        try:
            import datetime
            # Use the abstracted method to convert the year-month to a timestamp range
            start_ts, end_ts = self._month_to_timestamp_range(year, month)
            if not start_ts or not end_ts:
                return []  # if conversion fails, return an empty list
            
            clauses = ["start_time >= ?", "start_time <= ?"]
            params: list = [start_ts, end_ts]
            if vhost:
                clauses.append("vhost = ?"); params.append(vhost)
            if app:
                clauses.append("app = ?"); params.append(app)
            if stream:
                clauses.append("stream = ?"); params.append(stream)
            where = "WHERE " + " AND ".join(clauses)
            
            cur = self._cursor()
            # Query all recording records within that month
            cur.execute(
                f"SELECT start_time FROM recordings {where}",
                params,
            )
            
            # Convert timestamps to date strings and deduplicate
            dates = set()
            for row in cur.fetchall():
                try:
                    ts = row["start_time"]
                    if ts:
                        # Convert to the date in the local timezone
                        date_obj = datetime.datetime.fromtimestamp(ts)
                        date_str = date_obj.strftime("%Y-%m-%d")
                        dates.add(date_str)
                except Exception:
                    pass
            
            # Sort and return
            return sorted(list(dates))
        except Exception as e:
            mk_logger.log_warn(f"get_recording_dates error: {e}")
            return []
    
    def add_protocol_option(self, name: str, **kwargs) -> Optional[int]:
        """Add a protocol option preset"""
        try:
            cur = self._cursor()
            fields = ['name']
            values = [name]
            placeholders = ['?']
            
            for key, value in kwargs.items():
                if key in ['modify_stamp', 'enable_audio', 'add_mute_audio', 'auto_close', 
                          'continue_push_ms', 'paced_sender_ms', 'enable_hls', 'enable_hls_fmp4',
                          'enable_mp4', 'enable_rtsp', 'enable_rtmp', 'enable_ts', 'enable_fmp4',
                          'mp4_as_player', 'mp4_max_second', 'mp4_save_path', 'hls_save_path',
                          'hls_demand', 'rtsp_demand', 'rtmp_demand', 'ts_demand', 'fmp4_demand']:
                    fields.append(key)
                    values.append(value)
                    placeholders.append('?')
            
            query = f"INSERT INTO protocol_options ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cur.execute(query, values)
            self.connection.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            print(f"Failed to add protocol option: {e}")
            return None
    
    def get_protocol_option(self, option_id: int) -> Optional[Dict[str, Any]]:
        """Get protocol option by ID"""
        try:
            cur = self._cursor()
            cur.execute('SELECT * FROM protocol_options WHERE id = ?', (option_id,))
            row = cur.fetchone()
            if row:
                columns = [description[0] for description in cur.description]
                return dict(zip(columns, row))
            return None
        except sqlite3.Error as e:
            print(f"Failed to get protocol option: {e}")
            return None
    
    def get_all_protocol_options(self) -> List[Dict[str, Any]]:
        """Get all protocol options (only basic info)"""
        try:
            cur = self._cursor()
            cur.execute('SELECT id, name, created_at FROM protocol_options ORDER BY created_at DESC')
            rows = cur.fetchall()
            columns = [description[0] for description in cur.description]
            return [dict(zip(columns, row)) for row in rows]
        except sqlite3.Error as e:
            print(f"Failed to get all protocol options: {e}")
            return []
    
    def update_protocol_option(self, option_id: int, **kwargs) -> bool:
        """Update protocol option"""
        try:
            cur = self._cursor()
            set_clause = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['name', 'modify_stamp', 'enable_audio', 'add_mute_audio', 'auto_close',
                          'continue_push_ms', 'paced_sender_ms', 'enable_hls', 'enable_hls_fmp4',
                          'enable_mp4', 'enable_rtsp', 'enable_rtmp', 'enable_ts', 'enable_fmp4',
                          'mp4_as_player', 'mp4_max_second', 'mp4_save_path', 'hls_save_path',
                          'hls_demand', 'rtsp_demand', 'rtmp_demand', 'ts_demand', 'fmp4_demand']:
                    set_clause.append(f"{key} = ?")
                    values.append(value)
            
            if set_clause:
                set_clause.append("updated_at = ?")
                values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                values.append(option_id)
                
                query = f"UPDATE protocol_options SET {', '.join(set_clause)} WHERE id = ?"
                cur.execute(query, values)
                self.connection.commit()
                return True
            return False
        except sqlite3.Error as e:
            print(f"Failed to update protocol option: {e}")
            return False
    
    def delete_protocol_option(self, option_id: int) -> bool:
        """Delete protocol option"""
        try:
            cur = self._cursor()
            cur.execute('DELETE FROM protocol_options WHERE id = ?', (option_id,))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            print(f"Failed to delete protocol option: {e}")
            return False
    
    def add_pull_proxy(self, proxy_data: Dict[str, Any]) -> Optional[int]:
        """Add a pull proxy"""
        try:
            cur = self._cursor()
            cur.execute(
                'INSERT INTO pull_proxies (vhost, app, stream, remark, custom_params, protocol_params, on_demand) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (proxy_data.get('vhost', '__defaultVhost__'),
                 proxy_data.get('app'),
                 proxy_data.get('stream'),
                 proxy_data.get('remark', ''),
                 proxy_data.get('custom_params', '{}'),
                 proxy_data.get('protocol_params', '{}'),
                 int(bool(proxy_data.get('on_demand', 0))))
            )
            self.connection.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            mk_logger.log_warn(f"Failed to add pull proxy: {e}")
            return None
    
    def get_pull_proxy(self, proxy_id: int) -> Optional[Dict[str, Any]]:
        """Get pull proxy by ID"""
        try:
            cur = self._cursor()
            cur.execute('SELECT * FROM pull_proxies WHERE id = ?', (proxy_id,))
            row = cur.fetchone()
            if row:
                columns = [description[0] for description in cur.description]
                return dict(zip(columns, row))
            return None
        except sqlite3.Error as e:
            print(f"Failed to get pull proxy: {e}")
            return None
    
    def get_all_pull_proxies(self) -> List[Dict[str, Any]]:
        """Get all pull proxies"""
        try:
            cur = self._cursor()
            cur.execute('SELECT * FROM pull_proxies ORDER BY created_at DESC')
            rows = cur.fetchall()
            columns = [description[0] for description in cur.description]
            return [dict(zip(columns, row)) for row in rows]
        except sqlite3.Error as e:
            print(f"Failed to get all pull proxies: {e}")
            return []
    
    def update_pull_proxy(self, proxy_id: int, **kwargs) -> bool:
        """Update pull proxy"""
        try:
            cur = self._cursor()
            set_clause = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['vhost', 'app', 'stream', 'remark', 'custom_params', 'protocol_params', 'on_demand']:
                    set_clause.append(f"{key} = ?")
                    values.append(value)
            
            if set_clause:
                set_clause.append("updated_at = ?")
                values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                values.append(proxy_id)
                
                query = f"UPDATE pull_proxies SET {', '.join(set_clause)} WHERE id = ?"
                cur.execute(query, values)
                self.connection.commit()
                return True
            return False
        except sqlite3.Error as e:
            print(f"Failed to update pull proxy: {e}")
            return False
    
    def delete_pull_proxy(self, vhost: str, app: str, stream: str) -> bool:
        """Delete pull proxy by vhost, app, stream"""
        try:
            cur = self._cursor()
            cur.execute('DELETE FROM pull_proxies WHERE vhost = ? AND app = ? AND stream = ?', 
                              (vhost, app, stream))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            print(f"Failed to delete pull proxy: {e}")
            return False

    # ==================== Multi-address management ====================

    def get_proxy_urls(self, proxy_id: int) -> List[Dict[str, Any]]:
        """Get all addresses of a proxy, ordered by priority ascending; the params field is automatically deserialized to dict"""
        try:
            cur = self._cursor()
            cur.execute(
                'SELECT * FROM pull_proxy_urls WHERE proxy_id = ? ORDER BY priority ASC, id ASC',
                (proxy_id,)
            )
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description]
            result = []
            for row in rows:
                item = dict(zip(columns, row))
                try:
                    item['params'] = json.loads(item.get('params') or '{}')
                except Exception:
                    item['params'] = {}
                result.append(item)
            return result
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to get proxy urls: {e}")
            return []

    def set_proxy_urls(self, proxy_id: int, urls: List[Dict[str, Any]]) -> bool:
        """
        Fully replace the address list of a proxy.
        urls format: [{"url": "...", "params": {"schema": "hls", "rtp_type": "0", ...}}, ...]
        """
        try:
            cur = self._cursor()
            cur.execute('DELETE FROM pull_proxy_urls WHERE proxy_id = ?', (proxy_id,))
            for i, item in enumerate(urls):
                params = item.get('params', {})
                if not isinstance(params, dict):
                    params = {}
                cur.execute(
                    'INSERT INTO pull_proxy_urls (proxy_id, url, params, priority) VALUES (?, ?, ?, ?)',
                    (proxy_id, item.get('url', ''), json.dumps(params, ensure_ascii=False), i)
                )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"Failed to set proxy urls: {e}")
            self.connection.rollback()
            return False

    def get_pull_proxy_with_urls(self, proxy_id: int) -> Optional[Dict[str, Any]]:
        """Get proxy detail, including the urls list"""
        proxy = self.get_pull_proxy(proxy_id)
        if proxy:
            proxy['urls'] = self.get_proxy_urls(proxy_id)
        return proxy

    def get_all_pull_proxies_with_urls(self) -> List[Dict[str, Any]]:
        """Get all proxies, each including its urls list"""
        proxies = self.get_all_pull_proxies()
        for proxy in proxies:
            proxy['urls'] = self.get_proxy_urls(proxy['id'])
        return proxies

    # ══════════════════════════════════════════════════════════════
    # Plugin event binding CRUD
    # ══════════════════════════════════════════════════════════════

    def get_all_plugin_bindings(self) -> List[Dict[str, Any]]:
        """
        Get all event binding records (new table plugin_bindings).
        Return format:
        [
          {
            "event_type": "on_publish",
            "bindings": [
              {"id": 1, "plugin_name": "my_plugin", "params": {...}, "priority": 0, "enabled": 1},
              ...
            ]
          },
          ...
        ]
        Grouped by event_type, sorted within each group by priority ASC.
        """
        try:
            cur = self._cursor()
            cur.execute(
                'SELECT * FROM plugin_bindings ORDER BY event_type, priority ASC, id ASC'
            )
            rows = cur.fetchall()
            from collections import OrderedDict
            groups: OrderedDict = OrderedDict()
            for row in rows:
                d = dict(row)
                try:
                    d['params'] = json.loads(d.get('params') or '{}')
                except Exception:
                    d['params'] = {}
                et = d['event_type']
                if et not in groups:
                    groups[et] = []
                groups[et].append(d)
            return [{"event_type": et, "bindings": binds} for et, binds in groups.items()]
        except sqlite3.Error as e:
            mk_logger.log_warn(f"get_all_plugin_bindings error: {e}")
            return []

    def get_plugin_bindings_for_event(self, event_type: str) -> List[Dict[str, Any]]:
        """
        Get all bindings of an event type (new table), sorted by priority ASC.
        Return [{"id":..., "plugin_name":..., "params":{...}, "priority":..., "enabled":...}, ...]
        """
        try:
            cur = self._cursor()
            cur.execute(
                'SELECT * FROM plugin_bindings WHERE event_type=? ORDER BY priority ASC, id ASC',
                (event_type,)
            )
            result = []
            for row in cur.fetchall():
                d = dict(row)
                try:
                    d['params'] = json.loads(d.get('params') or '{}')
                except Exception:
                    d['params'] = {}
                result.append(d)
            return result
        except sqlite3.Error as e:
            mk_logger.log_warn(f"get_plugin_bindings_for_event error: {e}")
            return []

    def upsert_plugin_binding_item(
        self, event_type: str, plugin_name: str,
        params: Optional[dict] = None, priority: int = 0, enabled: int = 1
    ) -> bool:
        """
        Insert a single binding.
        Note: after removing the UNIQUE constraint, it no longer does ON CONFLICT UPSERT and INSERTs directly.
        params is a dict storing this binding's custom params.
        """
        try:
            params_json = json.dumps(params or {}, ensure_ascii=False)
            cur = self._cursor()
            cur.execute(
                '''
                INSERT INTO plugin_bindings (event_type, plugin_name, params, priority, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, current_timestamp)
                ''',
                (event_type, plugin_name, params_json, priority, enabled),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"upsert_plugin_binding_item error: {e}")
            self.connection.rollback()
            return False

    def delete_plugin_binding_item(self, event_type: str, plugin_name: str, row_id: Optional[int] = None) -> bool:
        """Delete a single event-plugin binding. If row_id is provided, delete exactly by id; otherwise delete all same-name bindings under that event"""
        try:
            cur = self._cursor()
            if row_id is not None:
                cur.execute(
                    'DELETE FROM plugin_bindings WHERE id=?', (row_id,)
                )
            else:
                cur.execute(
                    'DELETE FROM plugin_bindings WHERE event_type=? AND plugin_name=?',
                    (event_type, plugin_name)
                )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"delete_plugin_binding_item error: {e}")
            return False

    def delete_plugin_bindings_for_event(self, event_type: str) -> bool:
        """Delete all bindings under a given event type"""
        try:
            cur = self._cursor()
            cur.execute(
                'DELETE FROM plugin_bindings WHERE event_type=?',
                (event_type,)
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"delete_plugin_bindings_for_event error: {e}")
            return False

    def save_plugin_bindings_for_event(
        self, event_type: str,
        bindings: List[Dict[str, Any]],
        enabled: int = 1
    ) -> bool:
        """
        Fully save the binding list for an event type (delete then insert).
        bindings format: [{"plugin_name": ..., "params": {...}}, ...]
        The list order is the execution priority (index=priority).
        enabled controls the enabled state of the whole binding group.
        """
        try:
            cur = self._cursor()
            cur.execute(
                'DELETE FROM plugin_bindings WHERE event_type=?', (event_type,)
            )
            for idx, item in enumerate(bindings):
                plugin_name = item.get('plugin_name') or item.get('name', '')
                params = item.get('params') or {}
                params_json = json.dumps(params, ensure_ascii=False)
                cur.execute(
                    '''
                    INSERT INTO plugin_bindings (event_type, plugin_name, params, priority, enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, current_timestamp)
                    ''',
                    (event_type, plugin_name, params_json, idx, enabled),
                )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"save_plugin_bindings_for_event error: {e}")
            self.connection.rollback()
            return False

    def increment_hit_count(self, binding_id: int) -> bool:
        """Increment the hit_count of the given binding record by 1"""
        try:
            cur = self._cursor()
            cur.execute(
                'UPDATE plugin_bindings SET hit_count = hit_count + 1 WHERE id = ?',
                (binding_id,)
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            mk_logger.log_warn(f"increment_hit_count error: {e}")
            return False

