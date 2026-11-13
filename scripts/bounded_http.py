"""Public HTTPS, explicit ranges, and a shared response-payload budget. No retries."""
from __future__ import annotations

import http.client
import ssl
from urllib.parse import urljoin, urlsplit


class TransferStopped(RuntimeError):
    pass


def safe_url(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def allowed_url(url):
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    return (p.scheme == "https" and not p.username and not p.password
            and p.port in (None, 443)
            and any(host == root or host.endswith('.' + root)
                    for root in ('huggingface.co', 'hf.co')))


class BoundedHTTP:
    """Counts all consumed HTTP body bytes, including redirects/errors.

    HTTP headers and TCP/TLS overhead are excluded. Unexpected, oversized
    responses are closed before consumption and mark measurement incomplete.
    Nothing silently retries or falls back to whole-object reads.
    """

    def __init__(self, limit=100 * 1024**2, connection_factory=None, *,
                 maximum_limit=100 * 1024**2, keep_alive=False):
        # Original pilot callers retain their 100 MiB ceiling. The text stage
        # explicitly opts into its separately approved 150 MiB ceiling.
        if not 0 < maximum_limit <= 150 * 1024**2 or not 0 < limit <= maximum_limit:
            raise ValueError('Budget exceeds the explicit ceiling (absolute maximum 150 MiB)')
        self.limit = limit
        self.used = 0
        self.ledger = []
        self.measurement_complete = True
        self.factory = connection_factory or self._connection
        self.keep_alive = keep_alive
        self._pool = {}

    def close(self):
        for connection in self._pool.values():
            connection.close()
        self._pool.clear()

    @staticmethod
    def _connection(host):
        return http.client.HTTPSConnection(host, timeout=45,
                                          context=ssl.create_default_context())

    def admit(self, count):
        if count < 0 or count > self.limit - self.used:
            raise TransferStopped('Planned payload exceeds remaining network budget')

    def _body(self, response, record, maximum):
        length = response.getheader('Content-Length')
        try:
            declared = int(length) if length is not None else None
        except ValueError:
            self.measurement_complete = False
            raise TransferStopped('Invalid HTTP Content-Length') from None
        if declared is not None and (declared < 0 or declared > maximum
                                     or declared > self.limit - self.used):
            self.measurement_complete = False
            raise TransferStopped('Unexpected oversized HTTP body; closed without consuming it')
        data = bytearray()
        while True:
            remaining = min(maximum - len(data), self.limit - self.used)
            if remaining <= 0:
                # A declared, fully consumed body needs no extra-byte probe.
                if declared == len(data):
                    break
                self.measurement_complete = False
                raise TransferStopped('Bound reached before HTTP body EOF')
            try:
                chunk = response.read(min(64 * 1024, remaining))
            except http.client.IncompleteRead as error:
                self.used += len(error.partial)
                record['payload_bytes'] += len(error.partial)
                raise TransferStopped('Truncated HTTP body') from None
            self.used += len(chunk)
            record['payload_bytes'] += len(chunk)
            data.extend(chunk)
            if not chunk:
                break
            if declared == len(data):
                break
        if declared is not None and len(data) != declared:
            raise TransferStopped('HTTP body length differs from declaration')
        return bytes(data)

    def request(self, url, *, method='GET', byte_range=None, object_size=None,
                maximum=1024**2):
        if method not in ('GET', 'HEAD'):
            raise ValueError('Only GET and HEAD are supported')
        if byte_range is not None:
            start, end = byte_range
            if method != 'GET' or not (0 <= start <= end < object_size):
                raise ValueError('Invalid explicit byte range')
            maximum = end - start + 1
            self.admit(maximum)
        for _ in range(6):
            if not allowed_url(url):
                raise TransferStopped('Non-allowlisted redirect or URL')
            p = urlsplit(url)
            target = p.path + ('?' + p.query if p.query else '')
            headers = {'Accept-Encoding': 'identity',
                       'User-Agent': 'SmartShop-AI-ID-only-coverage-pilot/1.0',
                       'Connection': 'keep-alive' if self.keep_alive else 'close'}
            if byte_range is not None:
                headers['Range'] = f'bytes={start}-{end}'
            record = {'url': safe_url(url), 'method': method,
                      'range': list(byte_range) if byte_range else None,
                      'payload_bytes': 0}
            self.ledger.append(record)
            # Re-admit after redirects as their bodies also consume budget.
            if byte_range is not None:
                self.admit(maximum)
            connection = self._pool.get(p.hostname)
            if connection is None:
                connection = self.factory(p.hostname)
            response = None
            try:
                connection.request(method, target, headers=headers)
                response = connection.getresponse()
                record['status'] = response.status
                if response.status in (301, 302, 303, 307, 308):
                    destination = response.getheader('Location')
                    if not destination:
                        raise TransferStopped('Redirect without Location')
                    if method != 'HEAD':
                        self._body(response, record, min(64 * 1024, self.limit-self.used))
                    url = urljoin(url, destination)
                    continue
                if response.status not in (200, 206):
                    if method != 'HEAD':
                        self._body(response, record, min(64 * 1024, self.limit-self.used))
                    raise TransferStopped(f'HTTP status {response.status}')
                if byte_range is not None:
                    expected = f'bytes {start}-{end}/{object_size}'
                    if (response.status != 206
                            or response.getheader('Content-Range') != expected
                            or response.getheader('Content-Length') != str(maximum)
                            or response.getheader('Content-Encoding', 'identity') != 'identity'):
                        self.measurement_complete = False
                        raise TransferStopped('Server did not honor exact identity range; no full-file fallback')
                body = b'' if method == 'HEAD' else self._body(response, record, maximum)
                if byte_range is not None and len(body) != maximum:
                    raise TransferStopped('Short byte range')
                return body, {k.lower(): v for k, v in response.getheaders()}, url
            except (OSError, http.client.HTTPException):
                record['transport_error'] = True
                raise TransferStopped('HTTPS transport failed; no automatic retry') from None
            finally:
                if (self.keep_alive and response is not None
                        and response.isclosed()):
                    self._pool[p.hostname] = connection
                else:
                    self._pool.pop(p.hostname, None)
                    connection.close()
        raise TransferStopped('Too many redirects')

    def summary(self):
        return {'budget_bytes': self.limit, 'response_payload_bytes': self.used,
                'remaining_bytes': self.limit-self.used,
                'request_attempts': len(self.ledger), 'automatic_retries': 0,
                'measurement_complete': self.measurement_complete,
                'excluded': 'HTTP headers, TCP/TLS overhead; approved package installation and browser research',
                'ledger': self.ledger}
