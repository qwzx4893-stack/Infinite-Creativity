"""HTTPS transport that connects to the public IPs it actually validated.

TLS still verifies the original hostname. No proxy environment, secondary DNS
lookup, automatic redirect, or source-provided connection address is used.
"""
import email.message
import http.client
import io
import ipaddress
import socket
import ssl
import threading
import time
from urllib.error import HTTPError

import httpx
from .request_scope import checkpoint


def public_addresses(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private or unresolved network content is prohibited')
    return addresses


class CheckpointReader(io.RawIOBase):
    """Check every socket read, including buffered HTTP header/chunk lines."""
    def __init__(self, raw):
        self.raw = raw

    def readable(self):
        return True

    def readinto(self, buffer):
        checkpoint()
        received = self.raw.readinto(buffer)
        checkpoint()
        return received

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class ScopedHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, **kwargs):
        class ScopedSocket:
            def makefile(self, mode):
                return io.BufferedReader(CheckpointReader(sock.makefile(mode, buffering=0)))
        super().__init__(ScopedSocket(), *args, **kwargs)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    response_class = ScopedHTTPResponse

    def connect(self):
        addresses = public_addresses(self.host, self.port)
        last = None
        for family, socktype, proto, _, address in addresses:
            checkpoint()
            raw = socket.socket(family, socktype, proto)
            try:
                raw.settimeout(self.timeout)
                raw.connect(address)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except (OSError, ValueError) as error:
                raw.close()
                last = error
        raise last or OSError('No public HTTPS address available')


class ResponseStream(httpx.SyncByteStream):
    def __init__(self, response, connection, release):
        self.response, self.connection = response, connection
        self.release=release;self.complete=False;self.closed=False

    def __iter__(self):
        while True:
            checkpoint()
            try:
                # read() waits for the entire buffer and lets a slow-drip peer
                # postpone cancellation indefinitely. read1() yields available
                # bytes after at most one socket read.
                body = self.response.read1(64 * 1024)
            except http.client.IncompleteRead as error:
                raise httpx.RemoteProtocolError('Provider closed an incomplete response body') from error
            checkpoint()
            if not body:
                if self.response.length:
                    raise httpx.RemoteProtocolError('Provider closed before the declared Content-Length was received')
                self.complete=True
                break
            yield body

    def close(self):
        if not self.closed:
            self.closed=True
            self.response.close()
            self.release(self.connection,self.complete and not self.response.will_close)


class PublicTransport(httpx.BaseTransport):
    def __init__(self):
        self.context=ssl.create_default_context();self.lock=threading.Lock()
        self.pool={};self.slots=threading.BoundedSemaphore(8);self.closed=False

    def close(self):
        with self.lock:
            self.closed=True;connections=[c for group in self.pool.values() for c in group];self.pool.clear()
        for connection in connections:connection.close()

    def handle_request(self, request):
        from .content import CONTENT_PORTS
        host, port = request.url.host, request.url.port or 443
        if request.url.scheme != 'https' or (port != 443 and (host, port) not in CONTENT_PORTS):
            raise ValueError('Only approved public HTTPS ports are allowed')
        if request.method not in {'GET', 'HEAD'}:
            raise ValueError('Original-content transport supports read methods only')
        timeout = request.extensions.get('timeout', {}).get('read', 12) or 12
        started=time.monotonic()
        while not self.slots.acquire(timeout=.05):
            checkpoint()
            if time.monotonic()-started>6:raise httpx.PoolTimeout('Original-content transport capacity exhausted')
        key=(host,port)
        with self.lock:
            group=self.pool.get(key,[]);connection=group.pop() if group else None
        connection=connection or PinnedHTTPSConnection(host,port,timeout=min(timeout,12),context=self.context)
        def release(conn,reusable):
            with self.lock:
                group=self.pool.setdefault(key,[])
                if reusable and not self.closed and len(group)<4:group.append(conn)
                else:conn.close()
            self.slots.release()
        try:
            if self.closed:raise ValueError('Original-content transport is closed')
            connection.putrequest(request.method, request.url.raw_path.decode('ascii'),
                                  skip_host=True, skip_accept_encoding=True)
            for name, value in request.headers.multi_items():
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            return httpx.Response(response.status, headers=response.getheaders(),
                                  stream=ResponseStream(response, connection,release))
        except BaseException:
            release(connection,False)
            raise


class ContentResponse:
    def __init__(self, response, client):
        self.response, self.client = response, client
        self.status = response.status_code
        self.headers = email.message.Message()
        for name, value in response.headers.multi_items():
            self.headers[name] = value
        self.blocks = response.iter_bytes(64 * 1024)
        self.buffer = bytearray()

    def read(self, length=-1):
        if length < 0:
            raise ValueError('Content reads require an explicit bounded length')
        while len(self.buffer) < length:
            checkpoint()
            try:
                block = next(self.blocks)
            except StopIteration:
                break
            checkpoint(received_bytes=len(block))
            self.buffer.extend(block)
        body = bytes(self.buffer[:length])
        del self.buffer[:length]
        return body

    def close(self):
        self.response.close()
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ContentOpener:
    def open(self, request, timeout=12):
        checkpoint(requests=1)
        client = httpx.Client(transport=PublicTransport(), follow_redirects=False,
                              trust_env=False, timeout=timeout)
        try:
            response = client.send(client.build_request('GET', request.full_url,
                                   headers=dict(request.header_items())), stream=True)
            result = ContentResponse(response, client)
            if response.status_code >= 300:
                headers = result.headers
                result.close()
                raise HTTPError(request.full_url, response.status_code,
                                'Provider HTTP response', headers, None)
            return result
        except BaseException:
            client.close()
            raise
