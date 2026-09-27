"""Steps 2 and 3 of the pipeline: store the documents, and find the ones that answer a question.

Two stores behind one interface:

PineconeStore — the real vector database. It uses an *integrated* index: Pinecone runs the embedding
  model itself (llama-text-embed-v2 by default), so Ward sends plain text in and gets ranked text out,
  and nothing is embedded on this machine. A hosted reranker then re-orders the candidates, which puts
  the best match first more reliably than vector similarity alone. Spoken to over its REST API with
  httpx, like the compiler model, so tests can fake it with a MockTransport.

LocalStore — BM25 keyword ranking in memory. It needs no key and no network, so search works before
  Pinecone is configured, in tests, and whenever Pinecone can't be reached.

Each account's documents live in their own namespace, so one index serves every connected account.
"""
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass

import httpx

from app.rag.documents import Doc

API_VERSION = '2025-04'
CONTROL = 'https://api.pinecone.io'
BATCH = 96  # Pinecone's limit on records per upsert when it embeds them itself


@dataclass(frozen=True)
class Hit:
    id: str
    score: float
    text: str
    fields: dict


class StoreUnavailable(Exception):
    """The vector database could not be reached or refused the request. Carries advice fit to show."""


# ─── Pinecone ────────────────────────────────────────────────────────────────

class PineconeStore:
    name = 'pinecone'

    def __init__(self, api_key: str, index: str, cloud: str = 'aws', region: str = 'us-east-1',
                 embed_model: str = 'llama-text-embed-v2', rerank_model: str | None = 'bge-reranker-v2-m3',
                 transport: httpx.BaseTransport | None = None, ready_timeout: float = 90.0):
        self.index, self.cloud, self.region = index, cloud, region
        self.embed_model, self.rerank_model = embed_model, rerank_model
        self.ready_timeout = ready_timeout
        self._client = httpx.Client(
            timeout=30.0, transport=transport,
            headers={'Api-Key': api_key, 'X-Pinecone-API-Version': API_VERSION},
        )
        self._host: str | None = None

    # The index is created on first use, with the embedding model attached. Creating takes a few seconds.
    def host(self) -> str:
        if self._host:
            return self._host
        response = self._call('GET', f'{CONTROL}/indexes/{self.index}', allow=(404,))
        if response.status_code == 404:
            self._call('POST', f'{CONTROL}/indexes/create-for-model', json={
                'name': self.index, 'cloud': self.cloud, 'region': self.region,
                'embed': {'model': self.embed_model, 'field_map': {'text': 'text'}},
            }, allow=(409,))  # 409: another worker created it first, which is fine
            response = self._wait_until_ready()
        described = response.json()
        if not described.get('host'):
            raise StoreUnavailable(f'Pinecone index {self.index!r} has no host yet; try again in a minute.')
        self._host = f"https://{described['host']}"
        return self._host

    def _wait_until_ready(self) -> httpx.Response:
        deadline = time.monotonic() + self.ready_timeout
        while True:
            response = self._call('GET', f'{CONTROL}/indexes/{self.index}')
            if response.json().get('status', {}).get('ready') or time.monotonic() > deadline:
                return response
            time.sleep(2)

    def upsert(self, namespace: str, docs: list[Doc]) -> None:
        for start in range(0, len(docs), BATCH):
            lines = '\n'.join(json.dumps({'_id': d.id, 'text': d.text, **d.fields}) for d in docs[start:start + BATCH])
            self._call('POST', f'{self.host()}/records/namespaces/{namespace}/upsert', content=lines.encode(),
                       headers={'Content-Type': 'application/x-ndjson'})

    def delete(self, namespace: str, ids: list[str] | None = None) -> None:
        """ids=None empties the namespace."""
        body = {'namespace': namespace, **({'ids': ids} if ids else {'deleteAll': True})}
        self._call('POST', f'{self.host()}/vectors/delete', json=body, allow=(404,))  # 404: namespace never existed

    def count(self, namespace: str) -> int:
        """Records Pinecone reports in the namespace. Writes become visible a few seconds after upsert."""
        stats = self._call('POST', f'{self.host()}/describe_index_stats', json={}).json()
        return int(stats.get('namespaces', {}).get(namespace, {}).get('vectorCount', 0))

    def search(self, namespace: str, query: str, top_k: int) -> list[Hit]:
        body = {'query': {'inputs': {'text': query}, 'top_k': top_k * 2 if self.rerank_model else top_k}}
        if self.rerank_model:
            # Retrieve wide, then let the reranker read question and document together and keep the best.
            body['rerank'] = {'model': self.rerank_model, 'top_n': top_k, 'rank_fields': ['text']}
        response = self._call('POST', f'{self.host()}/records/namespaces/{namespace}/search', json=body)
        hits = []
        for h in response.json().get('result', {}).get('hits', []):
            fields = dict(h.get('fields', {}))
            hits.append(Hit(id=h['_id'], score=round(float(h.get('_score', 0)), 4), text=fields.pop('text', ''), fields=fields))
        return hits

    def _call(self, method: str, url: str, allow: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise StoreUnavailable(f'Could not reach Pinecone: {exc}') from exc
        if response.status_code in allow or response.is_success:
            return response
        if response.status_code in (401, 403):
            raise StoreUnavailable('Pinecone rejected the API key. Check WARD_PINECONE_API_KEY in backend/.env.')
        raise StoreUnavailable(f'Pinecone answered {response.status_code}: {response.text[:300]}')


# ─── Local fallback ──────────────────────────────────────────────────────────

TOKEN = re.compile(r'[a-z0-9₹]+(?:[.-][a-z0-9]+)*')
STOP = frozenset('a an the is are was were of to in on for and or with my me i do does which what who how any all '
                 'that this it its be by as at from there have has show list find tell about'.split())


def tokens(text: str) -> list[str]:
    """Words, plus the pieces of dotted and hyphenated ones: "t3.micro" also yields "t3" and "micro"."""
    out = []
    for word in TOKEN.findall(text.lower()):
        if word in STOP:
            continue
        out.append(word)
        if '.' in word or '-' in word:
            out.extend(p for p in re.split(r'[.-]', word) if p and p not in STOP)
    return out


class LocalStore:
    """BM25 over the same documents. Not semantic — "server" only finds servers because the documents
    say "virtual server" — but honest, instant, and always available."""

    name = 'local'
    k1, b = 1.4, 0.75

    def __init__(self):
        self._spaces: dict[str, dict[str, Doc]] = {}

    def upsert(self, namespace: str, docs: list[Doc]) -> None:
        self._spaces.setdefault(namespace, {}).update({d.id: d for d in docs})

    def delete(self, namespace: str, ids: list[str] | None = None) -> None:
        if ids is None:
            self._spaces.pop(namespace, None)
        else:
            for i in ids:
                self._spaces.get(namespace, {}).pop(i, None)

    def count(self, namespace: str) -> int:
        return len(self._spaces.get(namespace, {}))

    def search(self, namespace: str, query: str, top_k: int) -> list[Hit]:
        docs = list(self._spaces.get(namespace, {}).values())
        terms = set(tokens(query))
        if not docs or not terms:
            return []
        bags = [Counter(tokens(d.text)) for d in docs]
        avg = sum(sum(b.values()) for b in bags) / len(bags)
        df = Counter(t for b in bags for t in set(b))
        scored = []
        for d, bag in zip(docs, bags):
            length = sum(bag.values())
            score = 0.0
            for t in terms:
                if t not in bag:
                    continue
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * bag[t] * (self.k1 + 1) / (bag[t] + self.k1 * (1 - self.b + self.b * length / avg))
            if score > 0:
                scored.append(Hit(id=d.id, score=round(score, 4), text=d.text, fields=d.fields))
        return sorted(scored, key=lambda h: -h.score)[:top_k]
