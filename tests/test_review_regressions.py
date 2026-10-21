import hashlib
import http.client
import io
import unittest

import httpx

from infinite_creativity import request_scope
from infinite_creativity.live_quality import inspect_source_bundle
from infinite_creativity.live_registry import public_registry
from infinite_creativity.public_transport import ResponseStream, ScopedHTTPResponse
import test_author_routes as author_fixture


class TransportCompletionTests(unittest.TestCase):
    def response(self, wire, method='GET'):
        class Socket:
            def makefile(self, *args):
                return io.BytesIO(wire)
        response = http.client.HTTPResponse(Socket(), method=method)
        response.begin()
        return response

    def test_truncated_content_length_is_rejected_and_connection_not_reused(self):
        response = self.response(b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc')
        released = []
        stream = ResponseStream(response, object(), lambda conn, reusable: released.append(reusable))
        with self.assertRaisesRegex(httpx.RemoteProtocolError, 'Content-Length'):
            list(stream)
        stream.close()
        self.assertFalse(stream.complete)
        self.assertEqual(released, [False])

    def test_truncated_chunked_response_is_rejected_and_connection_not_reused(self):
        response = self.response(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabc')
        released = []
        stream = ResponseStream(response, object(), lambda conn, reusable: released.append(reusable))
        with self.assertRaises(httpx.RemoteProtocolError):
            list(stream)
        stream.close()
        self.assertEqual(released, [False])

    def test_complete_body_and_bodyless_head_are_accepted(self):
        for method, expected in [('GET', b'abc'), ('HEAD', b'')]:
            with self.subTest(method=method):
                response = self.response(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc', method)
                released = []
                stream = ResponseStream(response, object(), lambda conn, reusable: released.append(reusable))
                self.assertEqual(b''.join(stream), expected)
                stream.close()
                self.assertEqual(released, [True])

    def test_stream_uses_single_socket_reads_and_checks_cancellation_before_yielding(self):
        scope = request_scope.RequestScope()
        class Response:
            def read1(self, length):
                scope.cancelled.set()
                return b'first available bytes'
            def read(self, length):
                raise AssertionError('A buffering read can hide slow-drip cancellation')
        token = request_scope.CURRENT.set(scope)
        try:
            with self.assertRaises(request_scope.RequestCancelled):
                next(iter(ResponseStream(Response(), object(), lambda *args: None)))
        finally:
            request_scope.CURRENT.reset(token)

    def test_slow_status_header_and_chunk_lines_cannot_hide_cancellation(self):
        for prefix, operation in [
            (b'HTTP/1.1 200', 'headers'),
            (b'HTTP/1.1 200 OK\r\nX-Slow: ', 'headers'),
            (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n', 'chunks'),
        ]:
            with self.subTest(stage=operation, prefix=prefix):
                scope = request_scope.RequestScope()
                class Raw(io.RawIOBase):
                    def __init__(self):
                        self.position = 0
                    def readable(self):
                        return True
                    def readinto(self, buffer):
                        if self.position < len(prefix):
                            buffer[0] = prefix[self.position]
                            self.position += 1
                            return 1
                        scope.cancelled.set()
                        buffer[0] = ord('1')
                        return 1
                class Socket:
                    def makefile(self, mode, buffering):
                        self.buffering = buffering
                        return Raw()
                token = request_scope.CURRENT.set(scope)
                response = ScopedHTTPResponse(Socket())
                try:
                    with self.assertRaises(request_scope.RequestCancelled):
                        response.begin()
                        if operation == 'chunks':
                            response.read1(1024)
                finally:
                    response.close()
                    request_scope.CURRENT.reset(token)


class BundleFingerprintTests(unittest.TestCase):
    def fingerprint(self, records):
        return inspect_source_bundle(records)['normalized_source_sha256']

    def test_json_configuration_changes_are_distinct_but_formatting_is_ignored(self):
        base = {'component.tsx': {'_text': 'export const Card=()=> <div>Hello</div>;'}}
        def bundle(text):
            return {**base, 'config.json': {'_text': text}}
        red = self.fingerprint(bundle('{"color":"red","size":2}'))
        self.assertNotEqual(red, self.fingerprint(bundle('{"color":"blue","size":2}')))
        self.assertEqual(red, self.fingerprint(bundle('{ "size": 2, "color": "red" }')))

    def test_file_paths_and_root_roles_remain_part_of_bundle_identity(self):
        first = {'alpha.tsx': {'_text': 'export default 1'}, 'beta.tsx': {'_text': 'export default 2'}}
        swapped = {'alpha.tsx': first['beta.tsx'], 'beta.tsx': first['alpha.tsx']}
        self.assertNotEqual(self.fingerprint(first), self.fingerprint(swapped))
        self.assertNotEqual(self.fingerprint({'a.tsx': {'_text': 'export default 1', '_root': True}}),
                            self.fingerprint({'a.tsx': {'_text': 'export default 1', '_root': False}}))


class OriginalByteIdentityTests(unittest.TestCase):
    def test_raw_author_files_preserve_bom_in_download_checksum_and_byte_count(self):
        http = author_fixture.OriginalHTTP()
        original_read = http.read
        body = b'\xef\xbb\xbfexport const Signature=()=> <button>Sign</button>;'
        def read(url, max_bytes, *args):
            if url.endswith('/signature.tsx'):
                return body
            return original_read(url, max_bytes, *args)
        http.read = read
        asset = public_registry(http, author_fixture.AuthorRoutes().source(), {}, '', 1, key='signature')
        file = next(f for f in asset['files'] if f['filename'] == 'signature.tsx')
        self.assertEqual(file['sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(file['bytes'], len(body))
        self.assertEqual(asset['features']['source_quality']['state'], 'syntax-checked')


if __name__ == '__main__':
    unittest.main()
