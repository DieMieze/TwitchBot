from __future__ import annotations

import re
import subprocess
from typing import Any

from .logger import get_logger

logger = get_logger(__name__)

_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


class TunnelManager:
    """Starts and stops a cloudflared Quick Tunnel pointing at the local
    EventSub webhook port.

    ``start`` spawns ``cloudflared tunnel --url http://localhost:<port>`` and
    parses the random ``https://<random>.trycloudflare.com`` URL from the
    process stdout/stderr. ``stop`` terminates the subprocess.

    Only meaningful in production mode; silent/test modes do not need a
    public callback URL.
    """

    # --- Member variables ---
    binary: str  # path/name of the cloudflared executable to invoke
    _process: Any  # running subprocess.Popen handle (None when not started)
    _public_url: str  # parsed trycloudflare URL, empty until established

    def __init__(self, binary: str = "cloudflared") -> None:
        """
        @brief Construct a tunnel manager for a cloudflared executable.

        @param binary: name or path of the cloudflared binary to run;
            defaults to ``"cloudflared"`` on PATH.
        @return: None
        """
        self.binary = binary
        self._process: Any = None
        self._public_url: str = ""

    def start(self, local_port: int = 5002, timeout: float = 30.0) -> str:
        """
        @brief Spawn the cloudflared Quick Tunnel and return its public URL.

        When a tunnel is already running with a known URL the cached value
        is returned without spawning again. Otherwise spawns the subprocess,
        reads its output for the trycloudflare URL, and stops the process
        again if no URL appears within the timeout.

        @param local_port: local port the tunnel should point at.
        @param timeout: maximum seconds to wait for the public URL.
        @return: the parsed ``https://<random>.trycloudflare.com`` URL.
        """
        if self._process is not None and self._public_url:
            return self._public_url

        cmd = [self.binary, "tunnel", "--url", f"http://localhost:{local_port}"]
        logger.info("Starting cloudflared tunnel: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._public_url = self._read_public_url(timeout)
        if not self._public_url:
            self.stop()
            raise RuntimeError("cloudflared did not return a trycloudflare URL in time")
        logger.info("Tunnel public URL: %s", self._public_url)
        return self._public_url

    def _read_public_url(self, timeout: float) -> str:
        """
        @brief Read cloudflared output until a trycloudflare URL appears.

        Polls the subprocess stdout line-by-line until the deadline; stops
        early if the process exits before emitting a URL.

        @param timeout: maximum seconds to wait for the URL.
        @return: the matched URL, or ``""`` when none is found in time.
        """
        if self._process is None or self._process.stdout is None:
            return ""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self._process.stdout.readline()
            if not line:
                if self._process.poll() is not None:
                    break
                continue
            match = _TUNNEL_URL_RE.search(line)
            if match:
                return match.group(0)
        return ""

    @property
    def public_url(self) -> str:
        """
        @brief The currently established public tunnel URL.

        @return: the trycloudflare URL, or ``""`` when no tunnel is active.
        """
        return self._public_url

    def stop(self) -> None:
        """
        @brief Terminate the cloudflared subprocess if running.

        Terminates the process and waits briefly; escalates to ``kill`` if
        termination does not complete, then clears the cached process and
        URL regardless of outcome.

        @return: None
        """
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
        except Exception:
            logger.exception("Failed to stop cloudflared tunnel")
        finally:
            self._process = None
            self._public_url = ""
