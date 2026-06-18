"""
MP4 recording-to-DB plugin (on_record_mp4)
Non-exclusive; after recording completes, write the file info into the recordings table.
"""

import mk_logger
from py_plugin import PluginBase


class RecordMp4Logger(PluginBase):
    name        = "record_mp4_logger"
    version     = "1.0.0"
    description = "After MP4 recording completes, automatically writes the recording info into the database for querying on the recordings management page."
    type        = "on_record_mp4"
    interruptible = False  # listening type: after writing to DB, continue executing other plugins

    def run(self, **kwargs) -> bool:
        info = kwargs.get("info", {})
        if not isinstance(info, dict):
            return False
        try:
            from py_http_api import db
            db.add_recording(info)
            mk_logger.log_info(
                f"[record_mp4_logger] DB write succeeded: {info.get('app')}/{info.get('stream')} "
                f"{info.get('file_name')} size={info.get('file_size')}"
            )
        except Exception as e:
            mk_logger.log_warn(f"[record_mp4_logger] DB write failed: {e}")
        return False  # non-exclusive; continue dispatching to subsequent plugins
