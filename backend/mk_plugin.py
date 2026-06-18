import os
import sys
import json
import shutil
import subprocess
import mk_logger
import mk_loader
import asyncio
import py_plugin

from shared_loop import SharedLoop
from py_http_api import app, db
from starlette.routing import Match

def submit_coro(scope, body, send):
    async def run():
        # Wrap the send function to ensure it's always awaitable
        async def async_send(message):
            # Call the original send function; it should now return a coroutine
            result = send(message)
            if result is not None:
                await result

        async def receive():
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        try:
            await app(scope, receive, async_send)
        except Exception as e:
            mk_logger.log_warn(f"FastAPI failed: {e}")
            # Send an error response
            await async_send({
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"text/plain")],
            })
            await async_send({
                "type": "http.response.body",
                "body": b"Internal Server Error",
                "more_body": False,
            })
    return asyncio.run_coroutine_threadsafe(run(), SharedLoop.get_loop())

def check_route(scope) -> bool:
    for route in app.routes:
        if hasattr(route, "matches"):
            match, _ = route.matches(scope)
            if match == Match.FULL:
                return True
    return False

def _resolve_ffmpeg_bin(configured: str) -> str:
    """
    Ensure the ffmpeg executable path is valid.
    1. If the configured path exists and is executable, return it directly.
    2. Otherwise use shutil.which to search in PATH (cross-platform).
    3. On Unix, additionally try whereis as a supplement.
    Return the path found, or an empty string if not found.
    """
    # 1. If the configured path is usable, return it directly
    if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
        mk_logger.log_info(f"[ffmpeg] Using configured path: {configured}")
        return configured

    if configured:
        mk_logger.log_warn(f"[ffmpeg] Configured path unusable: {configured}, trying auto-discovery")

    # 2. shutil.which (cross-platform; Windows auto-appends .exe)
    found = shutil.which("ffmpeg")
    if found:
        mk_logger.log_info(f"[ffmpeg] Found in PATH: {found}")
        return found

    # 3. Unix-specific: whereis ffmpeg
    if sys.platform != "win32":
        try:
            out = subprocess.check_output(
                ["whereis", "-b", "ffmpeg"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            # Output format: "ffmpeg: /usr/bin/ffmpeg ..."
            parts = out.split(":")
            if len(parts) >= 2:
                candidates = parts[1].split()
                for candidate in candidates:
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        mk_logger.log_info(f"[ffmpeg] whereis found: {candidate}")
                        return candidate
        except Exception as e:
            mk_logger.log_warn(f"[ffmpeg] whereis lookup failed: {e}")

    return ""


def on_start():
    # Load plugins and sync database bindings
    py_plugin.registry.load()
    # Import the sync function from py_http_api
    try:
        from py_http_api import _sync_bindings_from_db
        _sync_bindings_from_db()
    except Exception as e:
        mk_logger.log_warn(f"[on_start] Failed to sync plugin bindings: {e}")

    mk_logger.log_info(f"on_start, secret: {mk_loader.get_config('api.secret')}")
    # Set http.rootPath to the ../frontend directory relative to the current py file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_path = os.path.abspath(os.path.join(current_dir, '..', 'frontend'))
    mk_loader.set_config('http.rootPath', frontend_path)
    mk_logger.log_info(f"set http.rootPath to {frontend_path}")

    ffmpeg_bin = mk_loader.get_config('ffmpeg.bin')
    ffmpeg_bin = _resolve_ffmpeg_bin(ffmpeg_bin)
    if ffmpeg_bin:
        mk_loader.set_config('ffmpeg.bin', ffmpeg_bin)
        mk_logger.log_info(f"set ffmpeg.bin to {ffmpeg_bin}")
    else:
        mk_logger.log_warn("ffmpeg not found, ffmpeg.bin not set")

    mk_loader.update_config()
    mk_loader.set_fastapi(check_route, submit_coro)

    # Dispatch the on_start event to plugins (including pull_proxy_restore, etc.)
    py_plugin.registry.dispatch("on_start")



def _build_proxy_call_args(proxy: dict, url: str = "", url_params: dict = {}) -> tuple:
    """
    Parse the params required by add_stream_proxy from the database proxy record.
    url      is obtained by the caller from pull_proxy_urls.url and passed in.
    url_params is obtained by the caller from pull_proxy_urls.params and passed in (already deserialized to dict),
               containing address-level params such as schema, rtp_type, etc.
    Returns (vhost, app, stream, url, retry_count, timeout_sec, opt)
    """
    vhost  = proxy.get("vhost")  or "__defaultVhost__"
    app    = proxy.get("app",    "")
    stream = proxy.get("stream", "")

    custom_params_dict = {}
    raw_custom = proxy.get("custom_params") or "{}"
    try:
        custom_params_dict = json.loads(raw_custom) if isinstance(raw_custom, str) else raw_custom
        if not isinstance(custom_params_dict, dict):
            custom_params_dict = {}
    except Exception as e:
        mk_logger.log_warn(f"[build_proxy_call_args] Failed to parse custom_params id={proxy.get('id')}: {e}")

    retry_count = int(custom_params_dict.pop("retry_count",  -1))
    timeout_sec = float(custom_params_dict.pop("timeout_sec", 0.0))

    opt = {}
    raw_proto = proxy.get("protocol_params") or "{}"
    try:
        proto_dict = json.loads(raw_proto) if isinstance(raw_proto, str) else raw_proto
        if isinstance(proto_dict, dict):
            opt.update(proto_dict)
    except Exception as e:
        mk_logger.log_warn(f"[build_proxy_call_args] Failed to parse protocol_params id={proxy.get('id')}: {e}")
    opt.update(custom_params_dict)
    # Address-level params (schema, rtp_type, etc.) have the highest priority and override other same-name params
    if url_params:
        opt.update({k: v for k, v in url_params.items() if v != '' and v is not None})

    return vhost, app, stream, url, retry_count, timeout_sec, opt


def on_stream_not_found(args: dict, sender: dict, invoker) -> bool:
    mk_logger.log_info(f"on_stream_not_found, args: {args}, sender: {sender}")
    return py_plugin.registry.dispatch("on_stream_not_found", args=args, sender=sender, invoker=invoker)


def on_http_access(parser: mk_loader.Parser, path: str, file_path: str, is_dir: bool, invoker, sender: dict) -> bool:
    return py_plugin.registry.dispatch(
        "on_http_access",
        parser=parser, path=path, file_path=file_path,
        is_dir=is_dir, invoker=invoker, sender=sender,
    )

def on_player_proxy_failed(url: str, media_tuple: mk_loader.MediaTuple, ex: mk_loader.SockException) -> bool:
    mk_logger.log_info(f"on_player_proxy_failed: {url}, {media_tuple.shortUrl()}, {ex.what()}")
    return py_plugin.registry.dispatch(
        "on_player_proxy_failed", url=url, media_tuple=media_tuple, ex=ex
    )


# ══════════════════════════════════════════════════════════════════════
# Plugin system event dispatch
# The following event functions first try to dispatch to bound plugins; if a plugin returns True it takes over,
# otherwise the original built-in logic runs (if any), and finally returns False to hand back to ZLM.
# ══════════════════════════════════════════════════════════════════════

def on_publish(type: str, args: dict, invoker, sender: dict) -> bool:
    mk_logger.log_info(f"on_publish, type: {type}, args: {args}, sender: {sender}")
    return py_plugin.registry.dispatch("on_publish", type=type, args=args, invoker=invoker, sender=sender)

def on_play(args: dict, invoker, sender: dict) -> bool:
    mk_logger.log_info(f"on_play, args: {args}, sender: {sender}")
    return py_plugin.registry.dispatch("on_play", args=args, invoker=invoker, sender=sender)

def on_flow_report(args: dict, totalBytes: int, totalDuration: int, isPlayer: bool, sender: dict) -> bool:
    mk_logger.log_info(f"on_flow_report, args: {args}, totalBytes: {totalBytes}, totalDuration: {totalDuration}, isPlayer: {isPlayer}, sender: {sender}")
    return py_plugin.registry.dispatch(
        "on_flow_report",
        args=args, totalBytes=totalBytes, totalDuration=totalDuration,
        isPlayer=isPlayer, sender=sender,
    )

def on_media_changed(is_register: bool, sender: mk_loader.MediaSource) -> bool:
    mk_logger.log_info(f"on_media_changed, is_register: {is_register}, sender: {sender}")
    return py_plugin.registry.dispatch(
        "on_media_changed", is_register=is_register, sender=sender
    )

def on_record_mp4(info: dict) -> bool:
    mk_logger.log_info(f"on_record_mp4: {info.get('file_path')}")
    return py_plugin.registry.dispatch("on_record_mp4", info=info)

def on_record_ts(info: dict) -> bool:
    mk_logger.log_info(f"on_record_ts: {info.get('file_path')}")
    return py_plugin.registry.dispatch("on_record_ts", info=info)

def on_stream_none_reader(sender: mk_loader.MediaSource) -> bool:
    mk_logger.log_info(f"on_stream_none_reader: {sender.getUrl()}")
    return py_plugin.registry.dispatch("on_stream_none_reader", sender=sender)

def on_send_rtp_stopped(sender: mk_loader.MultiMediaSourceMuxer, ssrc: str, ex: mk_loader.SockException) -> bool:
    mk_logger.log_info(f"on_send_rtp_stopped: ssrc={ssrc}, ex={ex.what()}")
    return py_plugin.registry.dispatch(
        "on_send_rtp_stopped", sender=sender, ssrc=ssrc, ex=ex
    )

def on_rtp_server_timeout(local_port: int, tuple: mk_loader.MediaTuple, tcp_mode: int, re_use_port: bool, ssrc: int) -> bool:
    mk_logger.log_info(f"on_rtp_server_timeout: port={local_port}, ssrc={ssrc}")
    return py_plugin.registry.dispatch(
        "on_rtp_server_timeout",
        local_port=local_port, tuple=tuple, tcp_mode=tcp_mode,
        re_use_port=re_use_port, ssrc=ssrc,
    )

def on_reload_config():
    mk_logger.log_info("on_reload_config")
    py_plugin.registry.dispatch("on_reload_config")

def on_get_rtsp_realm(args: dict, invoker, sender: dict) -> bool:
    mk_logger.log_info(f"on_get_rtsp_realm, args: {args}, invoker: {invoker}, sender: {sender}")
    return py_plugin.registry.dispatch("on_get_rtsp_realm", args=args, invoker=invoker, sender=sender)

def on_rtsp_auth(args: dict, realm: str, user_name: str, must_no_encrypt: bool, invoker, sender: dict) -> bool:
    mk_logger.log_info(f"on_rtsp_auth, args: {args}, realm: {realm}, user_name: {user_name}, must_no_encrypt: {must_no_encrypt}, sender: {sender}")
    return py_plugin.registry.dispatch(
        "on_rtsp_auth",
        args=args, realm=realm, user_name=user_name,
        must_no_encrypt=must_no_encrypt, invoker=invoker, sender=sender,
    )

def on_exit():
    mk_logger.log_info("on_exit")