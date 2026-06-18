from sys import version
import os
import sys
import importlib
import importlib.util
import inspect
import threading

import mk_logger

# ── All ZLM-supported event types ──────────────────────────────────────────
SUPPORTED_EVENTS = [
    "on_start",
    "on_publish",
    "on_play",
    "on_stream_not_found",
    "on_stream_none_reader",
    "on_record_mp4",
    "on_record_ts",
    "on_media_changed",
    "on_flow_report",
    "on_http_access",
    "on_player_proxy_failed",
    "on_send_rtp_stopped",
    "on_rtp_server_timeout",
    "on_get_rtsp_realm",
    "on_rtsp_auth",
]


class PluginBase:
    name = "base"
    version = "0.0.1"
    description = "Base plugin class"
    # type must be one of SUPPORTED_EVENTS
    type = "base"
    # interruptible=True  → intercepting type: after run() returns True, immediately stop dispatching to subsequent plugins
    #                        for scenarios requiring exclusive event control, such as authentication (e.g. TokenAuth calls invoker)
    # interruptible=False → listening type: regardless of what run() returns, continue executing subsequent plugins
    #                        for side-channel handling that doesn't affect the business flow, such as logging and DB writes
    interruptible = True
    # abstract=True means this class is an intermediate abstract base and won't be registered as an actual plugin.
    # The plugin loader skips all abstract=True classes and registers only concrete abstract=False plugins.
    abstract = False
    # multi_binding=True means this plugin may be bound to the same event multiple times (e.g. an auth plugin that supports stream filtering).
    # Default False, i.e. each event can bind the same plugin only once.
    multi_binding = False

    def get_url_params(self, **kwargs) -> dict:
        """
        Optional method, called before the playback URL is generated; returns a dict of query params to append to the playback URL.
        For example, an auth plugin returns {"token": "xxx"}, and the frontend appends it to the playback URL.
        Returns an empty dict by default; subclasses override as needed.
        """
        return {}

    def run(self, **kwargs):
        return False
    
    def params(self) -> dict:
        """
        Optional method; returns a dict defining the schema structure of the plugin binding params.
        For example:
        {
            "push_url": {
                "type": "string",
                "default": "https://default.example.com",
                "description": "push URL"
            },
            ...
        }
        """
        return {}

class PluginRegistry:
    """
    Global plugin registry, responsible for:
    - Scan and load plugins under the plugins/ directory (supports hot-reload)
    - Maintain the event_type → [{"name": ..., "params": {...}}, ...] binding relationship
    - Thread-safely dispatch events to the bound plugins
    """
    _lock = threading.RLock()

    def __init__(self):
        # name → PluginBase instance
        self._plugins: dict[str, PluginBase] = {}
        # event_type → list[{"name": str, "params": dict}](enabled bindings, ordered)
        self._bindings: dict[str, list[dict]] = {}

    # ── Load / hot-reload ─────────────────────────────────────────────

    def load(self, plugin_dir: str = "plugins") -> dict:
        """
        Scan the plugin_dir directory and load (or reload) all plugin modules.
        Clear already-registered plugins before hot-reloading to avoid leftover deleted or renamed plugins.
        Returns the {name: instance} dict loaded this time.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_path = os.path.join(current_dir, plugin_dir)
        loaded = {}

        if not os.path.isdir(plugin_path):
            mk_logger.log_warn(f"[PluginRegistry] Plugin directory does not exist: {plugin_path}")
            return loaded

        # Clear the plugin registry before hot-reloading
        with self._lock:
            self._plugins.clear()
            mk_logger.log_info("[PluginRegistry] Plugin registry cleared, starting reload...")

        for filename in sorted(os.listdir(plugin_path)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            module_name = f"{plugin_dir}.{filename[:-3]}"
            try:
                # if already loaded then reload, otherwise import
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                    mk_logger.log_info(f"[PluginRegistry] Hot-reloading module: {module_name}")
                else:
                    module = importlib.import_module(module_name)
                    mk_logger.log_info(f"[PluginRegistry] Loading module: {module_name}")

                for cls_name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, PluginBase) and obj is not PluginBase and not obj.abstract:
                        instance = obj()
                        with self._lock:
                            self._plugins[instance.name] = instance
                        loaded[instance.name] = instance
                        mk_logger.log_info(
                            f"[PluginRegistry] Registered plugin: {instance.name} "
                            f"v{instance.version} type={instance.type}"
                        )
            except Exception as e:
                mk_logger.log_warn(f"[PluginRegistry] Failed to load {module_name}: {e}")

        return loaded

    # ── Query ──────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Return the info list of all loaded plugins (including param schema)"""
        with self._lock:
            result = []
            for p in self._plugins.values():
                try:
                    schema = p.params() if callable(getattr(p, 'params', None)) else {}
                except Exception:
                    schema = {}
                result.append({
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "type": p.type,
                    "interruptible": p.interruptible,
                    "multi_binding": p.multi_binding,
                    "params_schema": schema,
                })
            return result

    def get(self, name: str) -> "PluginBase | None":
        with self._lock:
            return self._plugins.get(name)

    # ── Binding management ──────────────────────────────────────────────────

    def set_bindings(self, event_type: str, bindings: list):
        """
        Set the enabled binding list for an event type (full replacement).

        bindings format (both supported):
          - old format: ["plugin_name1", "plugin_name2"]
          - new format: [{"name": "plugin_name1", "params": {...}}, ...]

        Invalid plugin names (nonexistent or type-mismatched) are skipped and a warning is logged.
        """
        with self._lock:
            valid = []
            for item in bindings:
                # Compatible with old str format
                if isinstance(item, str):
                    item = {"name": item, "params": {}}
                n = item.get("name", "")
                params = item.get("params") or {}
                if n not in self._plugins:
                    mk_logger.log_warn(f"[PluginRegistry] Plugin does not exist when binding: {n}")
                    continue
                p = self._plugins[n]
                if p.type != event_type:
                    mk_logger.log_warn(
                        f"[PluginRegistry] Plugin type mismatch: {n}.type={p.type} != {event_type}"
                    )
                    continue
                valid.append({"name": n, "params": params, "id": item.get("id")})
            self._bindings[event_type] = valid
            mk_logger.log_info(
                f"[PluginRegistry] Binding updated: {event_type} → "
                f"{[v['name'] for v in valid]}"
            )

    def get_bindings(self) -> dict:
        with self._lock:
            return dict(self._bindings)

    # ── Event dispatch ──────────────────────────────────────────────────

    def collect_url_params(self, event_type: str, **kwargs) -> dict:
        """
        Collect the playback URL extra params of all plugins bound to event_type.

        Iterate over all enabled plugins under this event and call get_url_params() in turn,
        Merge the returned dict and return it (later plugins may override an earlier same-name key).
        Skip plugins that don't implement get_url_params or return empty.
        """
        with self._lock:
            items = list(self._bindings.get(event_type, []))

        merged: dict = {}
        for item in items:
            name   = item.get("name", "")
            params = item.get("params") or {}
            with self._lock:
                plugin = self._plugins.get(name)
            if plugin is None:
                continue
            try:
                extra = plugin.get_url_params(**kwargs, binding_params=params)
                if isinstance(extra, dict) and extra:
                    merged.update(extra)
            except Exception as e:
                mk_logger.log_warn(
                    f"[PluginRegistry] Plugin [{name}] collect_url_params exception: {e}"
                )
        return merged

    def dispatch(self, event_type: str, **kwargs) -> bool:
        """
        Dispatch the event to all enabled plugins bound to event_type, executed in list order (priority high to low).

        Intercepting plugins (interruptible=True):
          run() returns True → immediately stop all subsequent plugins and return True (take over the event)
          run() returns False → continue to the next plugin

        Listening plugins (interruptible=False):
          regardless of what run() returns → always continue executing subsequent plugins; this plugin doesn't affect the final takeover result

        after all plugins have executed, if no intercepting plugin took over → return False
        """
        with self._lock:
            items = list(self._bindings.get(event_type, []))

        intercepted = False
        for item in items:
            name      = item.get("name", "")
            params    = item.get("params") or {}
            binding_id = item.get("id")
            with self._lock:
                plugin = self._plugins.get(name)
            if plugin is None:
                continue
            try:
                result = plugin.run(**kwargs, binding_params=params)
                # Update hit count
                if binding_id is not None:
                    try:
                        from py_http_api import db as _db
                        _db.increment_hit_count(binding_id)
                    except Exception:
                        pass
                if plugin.interruptible:
                    if result:
                        mk_logger.log_info(
                            f"[PluginRegistry] Event {event_type} taken over by intercepting plugin [{name}]"
                        )
                        intercepted = True
                        break   # intercepted and took over, terminate the rest
                else:
                    mk_logger.log_info(
                        f"[PluginRegistry] Listening plugin [{name}] finished handling {event_type}"
                    )
            except Exception as e:
                mk_logger.log_warn(
                    f"[PluginRegistry] Plugin [{name}] handling {event_type} exception: {e}"
                )
        return intercepted


# ── Global singleton ─────────────────────────────────────────────────────
registry = PluginRegistry()


# ── Legacy-interface compatibility ───────────────────────────────────────────────────
def load_plugins(plugin_dir: str = "plugins") -> dict:
    """Compatible with the legacy call style, delegates to the global registry"""
    return registry.load(plugin_dir)