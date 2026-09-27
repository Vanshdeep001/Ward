"""The RAG pipeline end to end: documents → index → retrieve → answer.

    inventory ──► build_documents (tags cleaned) ──► sync (only what changed) ──► store
    question ──► screen (action? injection?) ──► store.search (top k, reranked) ──► + account overview
             ──► answerer ──► off-topic? ──► numbers checked ──► answer + sources

Indexing is lazy and incremental. Every question rebuilds the documents (cheap, and it is the only way
to see the latest sweep), compares each one's fingerprint with what was last sent, and upserts only
those that changed, deleting any resource that disappeared. Document text uses whole days, so a quiet
account re-embeds almost nothing between questions.

Failure never means no answer. Pinecone unreachable → the local index answers; the model unreachable
→ the extractive answer. Either way the response says which ran, and why, in `notice`.
"""
import logging

from app.rag import answer as answers
from app.rag import guardrails
from app.rag.documents import OVERVIEW_ID, Doc
from app.rag.stores import Hit, LocalStore, StoreUnavailable

log = logging.getLogger('ward.rag')


class SearchService:
    def __init__(self, store=None, answerer: answers.LlmAnswerer | None = None, top_k: int = 6):
        self.local = store if isinstance(store, LocalStore) else LocalStore()
        self.store = store or self.local  # PineconeStore when configured
        self.answerer = answerer
        self.top_k = top_k
        self._sent: dict[tuple[str, str], dict[str, str]] = {}  # (store, namespace) → {doc id: fingerprint}

    # ─── Index ───────────────────────────────────────────────────────────────

    def sync(self, namespace: str, docs: list[Doc]) -> dict:
        """Bring each store's namespace in line with `docs`. Returns what was sent to the primary store."""
        stats = self._sync(self.local, namespace, docs)
        if self.store is not self.local:
            stats = self._sync(self.store, namespace, docs)
        return stats

    def _sync(self, store, namespace: str, docs: list[Doc]) -> dict:
        key = (store.name, namespace)
        first = key not in self._sent
        before = self._sent.get(key, {})
        now = {d.id: d.fingerprint for d in docs}
        changed = [d for d in docs if before.get(d.id) != d.fingerprint]
        removed = [i for i in before if i not in now]
        if first:
            # A fresh process can't know what an earlier one left in the namespace: start clean.
            store.delete(namespace)
        elif removed:
            store.delete(namespace, removed)
        if changed:
            store.upsert(namespace, changed)
        self._sent[key] = now
        return {'upserted': len(changed), 'deleted': len(removed), 'total': len(docs), 'fresh': first}

    def adopt(self, namespace: str, docs: list[Doc]) -> None:
        """Trust that the primary store already holds exactly `docs` (indexed by another service), so the
        first question doesn't empty and rewrite the namespace. Used by the evaluation."""
        self._sync(self.local, namespace, docs)
        self._sent[(self.store.name, namespace)] = {d.id: d.fingerprint for d in docs}

    def forget(self, namespace: str | None = None) -> None:
        """Force a full re-index next time (all namespaces when None)."""
        self._sent = {k: v for k, v in self._sent.items() if namespace is not None and k[1] != namespace}

    # ─── Ask ─────────────────────────────────────────────────────────────────

    def ask(self, question: str, namespace: str, docs: list[Doc], history: list[dict] | None = None) -> dict:
        verdict = guardrails.screen_question(question)
        if verdict.blocked:
            # Refused before anything is retrieved or any model is asked.
            return _blocked(verdict, retriever='none')

        notices = []
        retriever = self.store.name
        try:
            fresh = self.sync(namespace, docs).get('fresh')
            hits = self.store.search(namespace, question, self.top_k)
            if not hits and self.store is not self.local and fresh:
                # Pinecone makes new records searchable a few seconds after upsert; the first question
                # after indexing shouldn't come back empty because of it.
                hits, retriever = self.local.search(namespace, question, self.top_k), 'local'
                notices.append('Pinecone is still indexing this account, so the local index answered this one.')
        except StoreUnavailable as exc:
            log.warning('vector store unavailable: %s', exc)
            self._sync(self.local, namespace, docs)
            hits, retriever = self.local.search(namespace, question, self.top_k), 'local'
            notices.append(f'{exc} The local index answered instead.')

        context = self._with_overview(hits, docs)
        generator = 'extractive'
        text = None
        if self.answerer is not None:
            try:
                text = self.answerer.answer(question, context, history)
                generator = self.answerer.name
            except answers.AnswerUnavailable as exc:
                log.warning('answer model unavailable: %s', exc)
                notices.append(f'{exc} Showing the matches instead.')
        if text is None:
            text = answers.extractive(question, context)

        verdict = guardrails.off_topic(text)
        if verdict.blocked:
            return _blocked(verdict, retriever=retriever, generator=generator, retrieved=[h.id for h in hits])

        numbers = guardrails.check_numbers(text, [h.text for h in context], question)
        if not numbers.grounded:
            notices.append('Check these figures — they are not in Ward’s data: ' + ', '.join(numbers.unsupported) + '.')

        # Resources the answer names from the overview, beyond the top k, are real too: they become sources.
        in_context = {h.id for h in context}
        everything = context + [Hit(d.id, 0.0, d.text, d.fields) for d in docs if d.id not in in_context]
        cited = answers.cited(text, everything)
        retrieved = {h.id for h in hits}
        # Only for a model's answer: the extractive one quotes the overview, which names nearly everything.
        extra = [h for h in everything if h.id in cited and h.id not in retrieved] if generator != 'extractive' else []
        shown = hits + extra
        sources = [_source(h, h.id in cited) for h in shown if h.id != OVERVIEW_ID]
        # Cited first, in the order the answer mentions them; then the rest by relevance.
        sources.sort(key=lambda s: (not s['cited'], cited.index(s['id']) if s['cited'] else 0))
        return {
            'answer': text,
            'sources': sources,
            'retriever': retriever,
            'generator': generator,
            'notice': ' '.join(notices) or None,
            'retrieved': [h.id for h in hits],  # in ranked order, for evaluation and debugging
            'checks': {'blocked': None, 'numbersChecked': numbers.checked, 'unsupported': numbers.unsupported},
        }

    @staticmethod
    def _with_overview(hits: list[Hit], docs: list[Doc]) -> list[Hit]:
        """The totals always ride along, so "how many…" and "how much in all…" have something to read."""
        if any(h.id == OVERVIEW_ID for h in hits):
            return hits
        overview = next((d for d in docs if d.id == OVERVIEW_ID), None)
        return hits + ([Hit(id=overview.id, score=0.0, text=overview.text, fields=overview.fields)] if overview else [])

    def status(self) -> dict:
        return {
            'retriever': self.store.name,
            'generator': self.answerer.name if self.answerer else 'extractive',
            'indexed': {ns: len(ids) for (store, ns), ids in self._sent.items() if store == self.store.name},
        }


def _blocked(verdict: guardrails.Verdict, retriever: str, generator: str = 'guardrail', retrieved=()) -> dict:
    return {
        'answer': verdict.message, 'sources': [], 'retriever': retriever, 'generator': generator, 'notice': None,
        'retrieved': list(retrieved), 'checks': {'blocked': verdict.blocked, 'numbersChecked': 0, 'unsupported': []},
    }


def _source(h: Hit, is_cited: bool) -> dict:
    return {'id': h.id, 'score': h.score, 'cited': is_cited, 'snippet': h.text, **h.fields}
