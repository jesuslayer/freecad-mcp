"""Request size and concurrency limits on the RPC server (hardened fork)."""

from collections.abc import Iterator
from contextlib import contextmanager
import http.client
import socket
import sys
import threading
import time
import xmlrpc.client

from test_rpc_concurrency import filtered_server_class


class Interface:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = threading.Event()
        self.entered = threading.Event()

    def ping(self) -> bool:
        self.calls.append("ping")
        return True

    def block(self) -> bool:
        self.entered.set()
        self.release.wait(timeout=10)
        return True


@contextmanager
def limited_server(**kwargs) -> Iterator[tuple[Interface, int]]:
    interface = Interface()
    server = filtered_server_class()(
        ("127.0.0.1", 0), auth_token="t", allow_none=True, logRequests=False, **kwargs
    )
    server.register_instance(interface)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        yield interface, server.server_address[1]
    finally:
        interface.release.set()
        server.shutdown()
        loop.join(timeout=5)
        server.server_close()


def raw_status(port: int, head: bytes) -> int:
    """Send only request headers and return the status code of the reply."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.sendall(head)
        reply = conn.makefile("rb").readline()
    return int(reply.split()[1])


def headers(extra: str) -> bytes:
    return (
        "POST /RPC2 HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: text/xml\r\n"
        f"Authorization: Bearer t\r\n{extra}\r\n"
    ).encode()


def test_oversized_body_is_rejected_before_reading() -> None:
    ip_filter = sys.modules[filtered_server_class().__module__]
    too_big = ip_filter.MAX_REQUEST_BYTES + 1
    with limited_server() as (interface, port):
        assert raw_status(port, headers(f"Content-Length: {too_big}\r\n")) == 413
    assert interface.calls == []


def test_missing_content_length_is_rejected() -> None:
    with limited_server() as (interface, port):
        assert raw_status(port, headers("")) == 411
    assert interface.calls == []


def test_normal_request_still_works() -> None:
    with limited_server() as (interface, port):
        body = xmlrpc.client.dumps((), "ping").encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(
                "POST", "/RPC2", body=body,
                headers={"Content-Type": "text/xml", "Authorization": "Bearer t"},
            )
            assert conn.getresponse().status == 200
        finally:
            conn.close()
    assert interface.calls == ["ping"]


def test_requests_over_the_concurrency_limit_get_503() -> None:
    with limited_server(max_concurrent_requests=1) as (interface, port):
        proxy = xmlrpc.client.ServerProxy(f"http://:t@127.0.0.1:{port}")
        busy = threading.Thread(target=proxy.block, daemon=True)
        busy.start()
        assert interface.entered.wait(timeout=5)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            reply = conn.makefile("rb").readline()
        assert reply.split()[1] == b"503"
        interface.release.set()
        busy.join(timeout=5)
        assert xmlrpc.client.ServerProxy(f"http://:t@127.0.0.1:{port}").ping() is True


def test_idle_connections_do_not_hold_slots_forever() -> None:
    """Silent sockets must time out so they cannot lock out the real client."""
    server_class = filtered_server_class()
    handler = sys.modules[server_class.__module__].TokenAuthRequestHandler

    class QuickTimeout(handler):
        timeout = 0.5

    with limited_server(max_concurrent_requests=2, requestHandler=QuickTimeout) as (_, port):
        idle = [socket.create_connection(("127.0.0.1", port)) for _ in range(2)]
        try:
            # Both slots are taken, so a third connection is refused.
            with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
                assert conn.makefile("rb").readline().split()[1] == b"503"
            # Once the idle sockets time out the slots come back.
            deadline = time.monotonic() + 5
            while True:
                try:
                    assert xmlrpc.client.ServerProxy(f"http://:t@127.0.0.1:{port}").ping() is True
                    break
                except xmlrpc.client.ProtocolError:
                    assert time.monotonic() < deadline, "slots were never released"
                    time.sleep(0.2)
        finally:
            for conn in idle:
                conn.close()


def test_default_idle_timeout_is_set() -> None:
    handler = sys.modules[filtered_server_class().__module__].TokenAuthRequestHandler
    assert handler.timeout is not None and 0 < handler.timeout <= 30
