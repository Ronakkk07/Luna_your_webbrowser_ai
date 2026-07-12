"""Lightweight retrieval for page RAG (the ``ask_website`` upgrade).

Splits page text into passages and ranks them against the question, so we feed the
LLM only the most relevant chunks instead of the whole page — cheaper on tokens and
more accurate on long pages. Uses a dependency-free TF-IDF-ish keyword score; the
interface (``top_passages``) can be swapped for vector embeddings later without
touching callers.
"""
import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    """a an the of to in on for and or is are was were be been being at by with as
    that this these those it its from into your you i we they he she them his her
    do does did has have had will would can could should may might not no yes but if
    then than so such about over under out up down off""".split()
)


def _tokens(text):
    return [w for w in _WORD.findall((text or "").lower()) if len(w) > 1 and w not in _STOP]


def _split_passages(text, target=600):
    """Break text into ~``target``-char passages along paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n+", text or "") if p.strip()]
    passages, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 <= target:
            cur = (cur + "\n" + p).strip()
        else:
            if cur:
                passages.append(cur)
                cur = ""
            if len(p) <= target:
                cur = p
            else:  # a single huge paragraph: window it
                for i in range(0, len(p), target):
                    passages.append(p[i : i + target])
    if cur:
        passages.append(cur)
    return passages


def top_passages(text, query, k=6, max_chars=6000):
    """Return the passages most relevant to ``query``, in original order.

    With no usable query signal, returns the head of the document (bounded).
    """
    passages = _split_passages(text)
    if not passages:
        return ""

    q = Counter(_tokens(query))
    if not q:
        out = []
        total = 0
        for p in passages:
            if total + len(p) > max_chars:
                break
            out.append(p)
            total += len(p)
        return "\n\n".join(out)

    tokenized = [_tokens(p) for p in passages]
    df = Counter()
    for toks in tokenized:
        for w in set(toks):
            df[w] += 1
    n = len(passages)

    def score(toks):
        if not toks:
            return 0.0
        tf = Counter(toks)
        s = 0.0
        for w, qc in q.items():
            c = tf.get(w)
            if c:
                idf = math.log(1 + n / (1 + df[w]))
                s += qc * idf * (c / (len(toks) + 1))
        return s

    ranked = sorted(range(n), key=lambda i: score(tokenized[i]), reverse=True)
    keep = sorted(ranked[:k])  # top-k, restored to reading order

    out, total = [], 0
    for i in keep:
        if total + len(passages[i]) > max_chars:
            continue
        out.append(passages[i])
        total += len(passages[i])
    return "\n\n".join(out)
