"""Synthetic responses only: no network access in tests."""
import http.client
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_http import BoundedHTTP, TransferStopped, allowed_url


class Response:
    def __init__(self, body=b'', status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers if headers is not None else {'Content-Length': str(len(body))}
        self.reads = 0

    def getheader(self, name, default=None):
        return next((v for k, v in self.headers.items() if k.lower()==name.lower()), default)

    def getheaders(self):
        return list(self.headers.items())

    def read(self, size):
        self.reads += 1
        return self.body.read(size)

    def isclosed(self):
        return self.body.tell()==len(self.body.getvalue())


class Factory:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = 0

    def __call__(self, host):
        owner = self
        class Connection:
            def request(self, method, target, headers):
                owner.requests.append((host, method, target, headers))
            def getresponse(self):
                return next(owner.responses)
            def close(self):
                owner.closed += 1
        return Connection()


class HTTPTests(unittest.TestCase):
    def test_ranges_are_exact_and_payload_metered(self):
        factory = Factory([Response(b'abcd', 206, {'Content-Length': '4', 'Content-Range': 'bytes 4-7/20'})])
        client = BoundedHTTP(4, factory)
        body, _, _ = client.request('https://huggingface.co/a', byte_range=(4,7), object_size=20)
        self.assertEqual(body, b'abcd')
        self.assertEqual(client.used, 4)
        self.assertEqual(factory.requests[0][3]['Range'], 'bytes=4-7')
        self.assertEqual(factory.requests[0][3]['Accept-Encoding'], 'identity')
        self.assertEqual(factory.closed, 1)

    def test_budget_admission_before_network(self):
        factory = Factory([])
        client = BoundedHTTP(3, factory)
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a', byte_range=(4,7), object_size=20)
        self.assertEqual(factory.requests, [])

    def test_no_whole_object_fallback(self):
        response = Response(b'whole file', 200)
        client = BoundedHTTP(100, Factory([response]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a', byte_range=(0,3), object_size=20)
        self.assertEqual(response.reads, 0)
        self.assertFalse(client.measurement_complete)

    def test_mismatched_range_rejected(self):
        response = Response(b'abcd', 206, {'Content-Length':'4', 'Content-Range':'bytes 1-4/20'})
        client = BoundedHTTP(100, Factory([response]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a', byte_range=(0,3), object_size=20)
        self.assertEqual(response.reads, 0)

    def test_redirects_and_error_bodies_are_counted_and_signed_queries_redacted(self):
        factory = Factory([Response(b'go', 302, {'Content-Length':'2','Location':'https://cdn-lfs.hf.co/file?secret=value'}),
                           Response(b'error', 403)])
        client = BoundedHTTP(100, factory)
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a')
        self.assertEqual(client.used, 7)
        self.assertNotIn('secret', str(client.summary()))
        self.assertEqual(client.summary()['automatic_retries'], 0)

    def test_oversized_body_closed_unread(self):
        response = Response(b'12345')
        client = BoundedHTTP(4, Factory([response]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a')
        self.assertEqual(client.used, 0)
        self.assertEqual(response.reads, 0)
        self.assertFalse(client.measurement_complete)

    def test_unknown_length_response_remains_bounded(self):
        client = BoundedHTTP(4, Factory([Response(b'123456', headers={})]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/api/a')
        self.assertEqual(client.used, 4)
        self.assertFalse(client.measurement_complete)

    def test_short_response_is_metered(self):
        client = BoundedHTTP(10, Factory([Response(b'ab', headers={'Content-Length':'4'})]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a')
        self.assertEqual(client.used, 2)

    def test_head_transfers_no_body(self):
        response = Response(b'unread', headers={'Content-Length':'6000'})
        client = BoundedHTTP(1, Factory([response]))
        client.request('https://huggingface.co/a', method='HEAD')
        self.assertEqual(client.used, 0)
        self.assertEqual(response.reads, 0)

    def test_untrusted_hosts_and_budget_over_100mib_rejected(self):
        for url in ('http://huggingface.co/a','https://huggingface.co.evil/a',
                    'https://user@huggingface.co/a','https://huggingface.co:8000/a'):
            self.assertFalse(allowed_url(url))
        with self.assertRaises(ValueError):
            BoundedHTTP(100*1024**2+1)

    def test_explicit_text_ceiling_preserves_original_default(self):
        client = BoundedHTTP(150*1024**2,maximum_limit=150*1024**2)
        self.assertEqual(client.limit,150*1024**2)
        with self.assertRaises(ValueError):
            BoundedHTTP(151*1024**2,maximum_limit=151*1024**2)

    def test_redirect_consumption_readmits_range_budget(self):
        factory = Factory([Response(b'go',302,{'Content-Length':'2','Location':'https://cdn-lfs.hf.co/file'})])
        client = BoundedHTTP(5,factory)
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a',byte_range=(0,3),object_size=20)
        self.assertEqual(client.used,2)
        self.assertEqual(len(factory.requests),1)

    def test_persistent_connection_reused_only_after_complete_body(self):
        factory = Factory([Response(b'ab'),Response(b'cd')])
        creations = []
        def create(host):
            creations.append(host)
            return factory(host)
        client = BoundedHTTP(10,create,keep_alive=True)
        client.request('https://huggingface.co/a')
        client.request('https://huggingface.co/b')
        self.assertEqual(len(creations),1)
        self.assertEqual(client.used,4)
        self.assertEqual(factory.requests[0][3]['Connection'],'keep-alive')
        self.assertEqual(factory.closed,0)
        client.close()
        self.assertEqual(factory.closed,1)

    def test_rejected_range_discards_persistent_connection(self):
        factory = Factory([Response(b'abcd',200)])
        client = BoundedHTTP(10,factory,keep_alive=True)
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a',byte_range=(0,3),object_size=20)
        self.assertEqual(factory.closed,1)
        client.close()
        self.assertEqual(factory.closed,1)

    def test_invalid_length_is_unaccountable_and_stops(self):
        client=BoundedHTTP(10,Factory([Response(b'a',headers={'Content-Length':'bad'})]))
        with self.assertRaises(TransferStopped):
            client.request('https://huggingface.co/a')
        self.assertFalse(client.measurement_complete)


if __name__ == '__main__':
    unittest.main()
