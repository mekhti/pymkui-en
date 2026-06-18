"""
HTTP access-control built-in plugin
- http_access_frontend: handles on_http_access, restricting access to the frontend directory only.
Enabled by default; disabling is not recommended (after disabling, ZLM uses its own default path strategy).
"""

import os
import mk_loader
import mk_logger
from py_plugin import PluginBase


class HttpAccessFrontend(PluginBase):
    """
    HTTP access-control plugin (on_http_access)
    Only allows access to files under the frontend directory; rejects out-of-bounds access.
    Exclusive type: returns directly after handling, no longer continuing to other plugins.
    """
    name = "http_access_frontend"
    version = "1.0.0"
    description = "HTTP access control, restricting access to the frontend directory only. Enabled by default; disabling is not recommended."
    type = "on_http_access"
    interruptible = True

    def run(self, **kwargs) -> bool:
        file_path = kwargs.get("file_path", "")
        path      = kwargs.get("path", "")
        invoker   = kwargs.get("invoker")

        current_dir   = os.path.dirname(os.path.abspath(__file__))
        frontend_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'frontend'))

        if not file_path.startswith(frontend_path):
            mk_logger.log_warn(f"[http_access_frontend] Access denied: '{file_path}' is outside frontend directory")
            mk_loader.http_access_invoker_do(invoker, "Access denied by pymkui", path, 60 * 60)
            return True

        mk_loader.http_access_invoker_do(invoker, "", path, 60 * 60)
        return True
