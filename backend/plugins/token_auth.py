"""
Token authentication plugin (play + publish)
- PlayTokenAuth  : handles on_play, verifies the token before playback
- PublishTokenAuth: handles on_publish, verifies the token before publishing

Both plugins share the TokenAuthBase base class; all token generation/verification/expiry logic is implemented in the base class.
"""

import time
import secrets
import string
import fnmatch

import mk_loader
import mk_logger
from py_plugin import PluginBase
from urllib.parse import parse_qs


# ── Common base class ─────────────────────────────────────────────────────────────────

class TokenAuthBase(PluginBase):
    """
    Token authentication base class.
    Subclasses only need to declare name/description/type and implement the two methods _allow(invoker) / _deny(invoker).
    The auth plugin calls invoker (publish_auth_invoker_do / play_auth_invoker_do),
    After consuming the event, no other plugin is allowed to continue processing, hence interruptible=True.
    """
    abstract = True   # intermediate base class, not registered as an actual plugin
    interruptible = True  # auth plugin: terminates subsequent plugins after consuming
    _token: dict = {}

    # ── Parameter schema ──────────────────────────────────────────────────────────
    def params(self) -> dict:
        return {
            "vhost_filter": {
                "type": "str",
                "description": "vhost filter rule; wildcard * supported; default * matches all",
                "default": "*",
            },
            "app_filter": {
                "type": "str",
                "description": "app filter rule; wildcard * supported; default * matches all",
                "default": "*",
            },
            "stream_filter": {
                "type": "str",
                "description": "stream filter rule; wildcard * supported; default * matches all; e.g. test* matches all streams starting with test",
                "default": "*",
            },
            "expire_seconds": {
                "type": "int",
                "description": "token expiry time (seconds), default 300 seconds",
                "default": 300,
            },
            "token_length": {
                "type": "int",
                "description": "token random string length, default 16",
                "default": 16,
            },
            "token_usage_count": {
                "type": "int",
                "description": "token max use count; -1 means unlimited; default -1",
                "default": -1,
            },
            "allow_localhost": {
                "type": "bool",
                "description": "whether to allow localhost access to bypass authentication, default true",
                "default": True,
            },
        }

    # ── Hooks subclasses must implement ────────────────────────────────────────────────────
    def _allow(self, invoker, extra: dict | None = None):
        raise NotImplementedError

    def _deny(self, invoker, reason: str = "token error"):
        raise NotImplementedError

    # ── Core logic ──────────────────────────────────────────────────────────────
    def run(self, **kwargs) -> bool:
        args           = kwargs.get("args", {})
        invoker        = kwargs.get("invoker")
        binding_params = kwargs.get("binding_params", {})

        vhost  = args.get("vhost", "__defaultVhost__")
        app    = args.get("app", "")
        stream = args.get("stream", "")
        # Get the client IP from sender, IPv6 supported
        client_ip = ""
        sender = kwargs.get("sender")
        if isinstance(sender, dict) and "peer_ip" in sender:
            client_ip = sender.get("peer_ip", "")

        # Wildcard filtering: skip if no match, don't consume the event
        vhost_filter  = binding_params.get("vhost_filter",  "*") or "*"
        app_filter    = binding_params.get("app_filter",    "*") or "*"
        stream_filter = binding_params.get("stream_filter", "*") or "*"
        if not (fnmatch.fnmatch(vhost, vhost_filter)
                and fnmatch.fnmatch(app, app_filter)
                and fnmatch.fnmatch(stream, stream_filter)):
            mk_logger.log_info(
                f"[{self.name}] skip {vhost}/{app}/{stream} "
                f"(filter: {vhost_filter}/{app_filter}/{stream_filter})"
            )
            return False

        # Check whether it's localhost access
        allow_localhost = binding_params.get("allow_localhost", True)
        if isinstance(allow_localhost, str):
            allow_localhost = allow_localhost.lower() not in ('false', '0', '')
        if allow_localhost and client_ip in ('127.0.0.1', '::1', 'localhost'):
            mk_logger.log_info(f"[{self.name}] allow localhost access {vhost}/{app}/{stream}")
            self._allow(invoker, extra=binding_params)
            return True

        expire_seconds    = int(binding_params.get("expire_seconds", 300))
        token_length      = int(binding_params.get("token_length", 16))
        token_usage_count = int(binding_params.get("token_usage_count", -1))

        vhost  = args.get("vhost", "__defaultVhost__")
        app    = args.get("app", "")
        stream = args.get("stream", "")

        expected = self.get_token(vhost, app, stream,
                                  expire_seconds=expire_seconds,
                                  token_length=token_length,
                                  token_usage_count=token_usage_count)
        given = parse_qs(args.get("params", "")).get("token", [""])[0]

        if given != expected:
            mk_logger.log_info(f"[{self.name}] token mismatch {vhost}/{app}/{stream}")
            self._deny(invoker)
        else:
            if token_usage_count > 0:
                self._decr_usage(vhost, app, stream)
            # Pass binding_params through to _allow for subclasses to use as needed (e.g. PublishTokenAuth's protocol config)
            self._allow(invoker, extra=binding_params)
        return True

    def get_url_params(self, **kwargs) -> dict:
        vhost  = kwargs.get("vhost", "__defaultVhost__")
        app    = kwargs.get("app", "")
        stream = kwargs.get("stream", "")
        binding_params    = kwargs.get("binding_params", {})

        # If not within the filter scope, don't append the token parameter
        vhost_filter  = binding_params.get("vhost_filter",  "*") or "*"
        app_filter    = binding_params.get("app_filter",    "*") or "*"
        stream_filter = binding_params.get("stream_filter", "*") or "*"
        if not (fnmatch.fnmatch(vhost, vhost_filter)
                and fnmatch.fnmatch(app, app_filter)
                and fnmatch.fnmatch(stream, stream_filter)):
            return {}

        expire_seconds    = int(binding_params.get("expire_seconds", 300))
        token_length      = int(binding_params.get("token_length", 16))
        token_usage_count = int(binding_params.get("token_usage_count", -1))
        token = self.get_token(vhost, app, stream,
                               expire_seconds=expire_seconds,
                               token_length=token_length,
                               token_usage_count=token_usage_count)
        return {"token": token}

    # ── Token management ────────────────────────────────────────────────────────────
    @staticmethod
    def _random_string(length: int = 16) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    def get_token(self, vhost, app, stream,
                  expire_seconds=300, token_length=16, token_usage_count=-1) -> str:
        key  = (vhost, app, stream)
        item = self._token.get(key)
        need_new = (
            not item
            or time.time() > item[1] + expire_seconds
            or (token_usage_count > 0 and item[2] <= 0)
        )
        if need_new:
            return self._new_token(key, token_length, token_usage_count)
        return item[0]

    def _new_token(self, key: tuple, token_length: int, token_usage_count: int) -> str:
        token = self._random_string(token_length)
        self._token[key] = (token, time.time(), token_usage_count)
        return token

    def _decr_usage(self, vhost, app, stream):
        key  = (vhost, app, stream)
        item = self._token.get(key)
        if item and item[2] > 0:
            self._token[key] = (item[0], item[1], item[2] - 1)

    def cleanup(self, expire_seconds: int = 300):
        now     = time.time()
        expired = [k for k, (_, ts, _u) in self._token.items() if now > ts + expire_seconds]
        for k in expired:
            del self._token[k]


# ── Play authentication ──────────────────────────────────────────────────────────────────

class PlayTokenAuth(TokenAuthBase):
    name        = "play_token_auth"
    version     = "1.0.0"
    description = "Play authentication plugin; rejects the play request when authentication fails. Supports vhost/app/stream wildcard filtering; can bind multiple times for different streams."
    type        = "on_play"
    interruptible = True
    multi_binding = True
    abstract    = False

    _token: dict = {}   # independent from PublishTokenAuth

    def _allow(self, invoker, extra: dict | None = None):
        mk_loader.play_auth_invoker_do(invoker, "")

    def _deny(self, invoker, reason: str = "token error"):
        mk_loader.play_auth_invoker_do(invoker, reason)


# ── Publish authentication ──────────────────────────────────────────────────────────────────

class PublishTokenAuth(TokenAuthBase):
    name        = "publish_token_auth"
    version     = "1.0.0"
    description = "Publish authentication plugin; rejects the publish request when authentication fails. Supports vhost/app/stream wildcard filtering; can bind multiple times for different streams. Protocol options can be configured and are applied automatically after authentication passes."
    type        = "on_publish"
    interruptible = True
    multi_binding = True
    abstract    = False

    _token: dict = {}   # independent from PlayTokenAuth

    def params(self) -> dict:
        # Inherit the base class token params and append auth-toggle and protocol-config selection params
        base = super().params()
        base["enable_auth"] = {
            "type": "bool",
            "description": "whether to enable token authentication; when off, only the protocol config is applied and the token is not verified",
            "default": True,
        }
        base["protocol_option"] = {
            "type": "protocol_option",
            "description": "protocol config applied after publish authentication passes (or auth is off) (optional)",
            "default": {},
        }
        return base

    def run(self, **kwargs) -> bool:
        binding_params = kwargs.get("binding_params", {})
        enable_auth = binding_params.get("enable_auth", True)
        if isinstance(enable_auth, str):
            enable_auth = enable_auth.lower() not in ('false', '0', '')
        if not enable_auth:
            # Auth off: allow directly, apply only the protocol config
            invoker = kwargs.get("invoker")
            args    = kwargs.get("args", {})
            vhost   = args.get("vhost", "__defaultVhost__")
            app     = args.get("app", "")
            stream  = args.get("stream", "")
            mk_logger.log_info(f"[publish_token_auth] auth disabled, allow {vhost}/{app}/{stream}")
            self._allow(invoker, extra=binding_params)
            return True
        return super().run(**kwargs)

    def get_url_params(self, **kwargs) -> dict:
        binding_params = kwargs.get("binding_params", {})
        enable_auth = binding_params.get("enable_auth", True)
        if isinstance(enable_auth, str):
            enable_auth = enable_auth.lower() not in ('false', '0', '')
        if not enable_auth:
            return {}
        return super().get_url_params(**kwargs)

    def _allow(self, invoker, extra: dict | None = None):
        # Take protocol_option out of binding_params and pass it in directly (only protocol fields are stored when saved to the database)
        protocol_opt: dict = {}
        if extra:
            raw = extra.get("protocol_option")
            if isinstance(raw, dict):
                protocol_opt = raw
        mk_logger.log_info(f"[publish_token_auth] allow, protocol_option={protocol_opt}")
        mk_loader.publish_auth_invoker_do(invoker, "", protocol_opt)

    def _deny(self, invoker, reason: str = "token error"):
        mk_loader.publish_auth_invoker_do(invoker, reason, {})
