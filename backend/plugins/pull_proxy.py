"""
Pull Proxy built-in plugins
Contains two plugins enabled by default:
  - pull_proxy_on_demand   : handles on_stream_not_found, implementing on-demand pull
  - pull_proxy_failover    : handles on_player_proxy_failed, implementing multi-address failover
Both plugins automatically insert default binding records on database initialization (INSERT OR IGNORE).
"""

import mk_loader
import mk_logger
from py_plugin import PluginBase


class PullProxyOnDemand(PluginBase):
    """
    On-demand pull plugin (on_stream_not_found)
    When the stream requested by the player doesn't exist, query the matching on_demand=1 proxy in the database,
    trigger the pull and let ZLM wait for the stream to come online before pushing it to the player.
    """
    name = "pull_proxy_on_demand"
    version = "1.0.0"
    description = "On-demand pull plugin; automatically triggers the pull proxy when the stream doesn't exist (on_demand=1). Enabled by default; disabling is not recommended."
    type = "on_stream_not_found"
    interruptible = True

    def run(self, **kwargs) -> bool:
        from py_http_api import db
        import mk_plugin as _mk

        args = kwargs.get("args", {})
        vhost  = args.get("vhost")  or "__defaultVhost__"
        app    = args.get("app",    "")
        stream = args.get("stream", "")

        try:
            db.cursor.execute(
                "SELECT * FROM pull_proxies WHERE vhost=? AND app=? AND stream=? AND on_demand=1",
                (vhost, app, stream)
            )
            row = db.cursor.fetchone()
            proxy = dict(row) if row else None
        except Exception as e:
            mk_logger.log_warn(f"[pull_proxy_on_demand] Failed to query the database: {e}")
            proxy = None

        if not proxy:
            return False

        pid = proxy.get("id")
        proxy_urls = db.get_proxy_urls(pid)
        first_url  = proxy_urls[0] if proxy_urls else {}
        url        = first_url.get("url", "")
        url_params = first_url.get("params", {})

        if not url:
            mk_logger.log_warn(f"[pull_proxy_on_demand] On-demand proxy has no valid address id={pid}")
            return False

        vhost, app, stream, url, retry_count, timeout_sec, opt = _mk._build_proxy_call_args(
            proxy, url, url_params
        )
        mk_logger.log_info(
            f"[pull_proxy_on_demand] Triggering on-demand pull id={pid} {vhost}/{app}/{stream} url={url}"
        )

        def cb(err, key):
            if err:
                mk_logger.log_warn(
                    f"[pull_proxy_on_demand] On-demand pull failed id={pid} {vhost}/{app}/{stream}: {err}"
                )
            else:
                mk_logger.log_info(
                    f"[pull_proxy_on_demand] On-demand pull succeeded id={pid} {vhost}/{app}/{stream}"
                )

        opt['auto_close'] = True
        mk_loader.add_stream_proxy(
            vhost, app, stream, url, cb,
            retry_count=len(proxy_urls) - 1,
            force=True,
            timeout_sec=timeout_sec,
            opt=opt,
        )
        return True


class PullProxyFailover(PluginBase):
    """
    Multi-address failover plugin (on_player_proxy_failed)
    When the pull proxy fails, automatically switch to the next backup address (cyclically).
    """
    name = "pull_proxy_failover"
    version = "1.0.0"
    description = "Pull Proxy multi-address failover plugin; automatically switches to a backup address when the pull fails. Enabled by default; disabling is not recommended."
    type = "on_player_proxy_failed"
    interruptible = True

    def run(self, **kwargs) -> bool:
        from py_http_api import db

        url         = kwargs.get("url", "")
        media_tuple = kwargs.get("media_tuple")

        try:
            vhost  = media_tuple.vhost  if hasattr(media_tuple, 'vhost')  else '__defaultVhost__'
            app    = media_tuple.app    if hasattr(media_tuple, 'app')    else ''
            stream = media_tuple.stream if hasattr(media_tuple, 'stream') else ''

            if not app or not stream:
                return False

            db.cursor.execute(
                "SELECT * FROM pull_proxies WHERE vhost=? AND app=? AND stream=?",
                (vhost, app, stream)
            )
            row = db.cursor.fetchone()
            if not row:
                return False

            proxy = dict(row)
            pid   = proxy.get("id")
            if not pid:
                return False

            proxy_urls = db.get_proxy_urls(int(pid))
            if len(proxy_urls) <= 1:
                return False

            current_idx = next(
                (i for i, pu in enumerate(proxy_urls) if pu.get("url", "") == url),
                0
            )
            next_idx = (current_idx + 1) % len(proxy_urls)
            if next_idx == current_idx:
                return False

            next_url_item = proxy_urls[next_idx]
            next_url      = next_url_item.get("url", "")
            next_params   = next_url_item.get("params", {})

            if not next_url:
                return False

            mk_logger.log_info(
                f"[pull_proxy_failover] Switching to backup address id={pid} {vhost}/{app}/{stream} "
                f"[{current_idx}→{next_idx}] {url} → {next_url}"
            )
            mk_loader.update_stream_proxy(vhost, app, stream, next_url, next_params)
            return True

        except Exception as e:
            mk_logger.log_warn(f"[pull_proxy_failover] Multi-address switch exception: {e}")

        return False


class PullProxyRestore(PluginBase):
    """
    Startup-restore plugin (on_start)
    When ZLMediaKit starts, read all on_demand=0 pull proxies from the database,
    call mk_loader.add_stream_proxy to re-register, restoring the previous run state.
    Non-exclusive; allows other on_start plugins to run simultaneously.
    """
    name = "pull_proxy_restore"
    version = "1.0.0"
    description = "Automatically restores non-on-demand pull proxies at startup. Enabled by default; disabling is not recommended."
    type = "on_start"
    interruptible = False

    def run(self, **kwargs) -> bool:
        import mk_plugin as _mk
        from py_http_api import db

        try:
            proxies = db.get_all_pull_proxies()
        except Exception as e:
            mk_logger.log_warn(f"[pull_proxy_restore] Failed to read the database: {e}")
            return False

        count = 0
        for proxy in proxies:
            if proxy.get("on_demand", 0):
                continue

            proxy_id = proxy.get("id")
            vhost  = proxy.get("vhost")  or "__defaultVhost__"
            app    = proxy.get("app",    "")
            stream = proxy.get("stream", "")

            proxy_urls = db.get_proxy_urls(proxy_id)
            first_url  = proxy_urls[0] if proxy_urls else {}
            url        = first_url.get("url", "")
            url_params = first_url.get("params", {})

            if not app or not stream or not url:
                mk_logger.log_warn(f"[pull_proxy_restore] Skipping invalid record id={proxy_id}")
                continue

            vhost, app, stream, url, retry_count, timeout_sec, opt = _mk._build_proxy_call_args(
                proxy, url, url_params
            )

            def make_cb(pid, v, a, s, u):
                def cb(err, key):
                    if err:
                        mk_logger.log_warn(
                            f"[pull_proxy_restore] Restore failed id={pid} {v}/{a}/{s}: {err}"
                        )
                    else:
                        mk_logger.log_info(
                            f"[pull_proxy_restore] Restore succeeded id={pid} {v}/{a}/{s} url={u}"
                        )
                return cb

            mk_logger.log_info(
                f"[pull_proxy_restore] Restoring pull proxy id={proxy_id} {vhost}/{app}/{stream} url={url} "
                f"retry_count={retry_count} timeout_sec={timeout_sec}"
            )
            mk_loader.add_stream_proxy(
                vhost, app, stream, url,
                make_cb(proxy_id, vhost, app, stream, url),
                retry_count=retry_count,
                force=True,
                timeout_sec=timeout_sec,
                opt=opt,
            )
            count += 1

        mk_logger.log_info(f"[pull_proxy_restore] Restored {count} pull proxies in total")
        return False  # non-exclusive; always returns False to let other on_start plugins continue
