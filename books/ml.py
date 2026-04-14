import json
import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder

retriever = SentenceTransformer('all-MiniLM-L6-v2')
ranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# In-memory index: loaded once at startup, reused for every search
_BOOK_IDS = []      # list of DB primary keys
_EMB_MATRIX = None  # numpy array shape (N, 384), L2-normalised

def _load_index():
    global _BOOK_IDS, _EMB_MATRIX
    # Import here to avoid circular import at module level
    from .models import Book
    print('[ml] Loading embedding index...')
    rows = list(Book.objects.exclude(embedding='').values('id', 'embedding'))
    if not rows:
        print('[ml] No embeddings found in DB.')
        _EMB_MATRIX = np.empty((0, 384), dtype=np.float32)
        return
    ids, vecs = [], []
    for r in rows:
        try:
            v = np.array(json.loads(r['embedding']), dtype=np.float32)
            ids.append(r['id'])
            vecs.append(v)
        except Exception:
            continue
    mat = np.vstack(vecs)                        # (N, 384)
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-10
    _BOOK_IDS = ids
    _EMB_MATRIX = mat / norms                    # pre-normalise rows once
    print(f'[ml] Index ready: {len(_BOOK_IDS)} books.')

def _ensure_index():
    if _EMB_MATRIX is None:
        _load_index()

def smart_search(query, username=None, mood=50, complexity=50):
    from .models import Book, Library
    _ensure_index()

    # Build vibe-adjusted query
    vibe = ''
    if mood < 30: vibe += ' lighthearted funny cheerful happy'
    elif mood > 70: vibe += ' dark serious grim intense'
    if complexity < 30: vibe += ' simple easy read short'
    elif complexity > 70: vibe += ' complex philosophical academic difficult'
    final_query = query + vibe

    # Exact title matches (pinned to top)
    exact_qs = Book.objects.filter(title__iexact=query)[:3]
    exact_titles = set()
    exact_books = []
    for b in exact_qs:
        exact_books.append({'title': b.title, 'description': b.description,
            'avg_rating': b.avg_rating, 'ratings_count': b.ratings_count,
            'url': b.url, 'image_url': b.image_url,
            'authors': b.authors, 'genres': b.genres, 'final_score': 2.0})
        exact_titles.add(b.title)

    # Encode + normalise query vector
    q_vec = retriever.encode(final_query).astype(np.float32)

    # Blend with user history (85/15)
    if username and _EMB_MATRIX.shape[0] > 0:
        saved_titles = list(Library.objects.filter(user_id=username).values_list('title', flat=True))
        if saved_titles:
            history = list(Book.objects.filter(title__in=saved_titles).exclude(embedding='').values('embedding'))
            user_vecs = []
            for h in history:
                try: user_vecs.append(np.array(json.loads(h['embedding']), dtype=np.float32))
                except: pass
            if user_vecs:
                user_vec = np.mean(user_vecs, axis=0)
                q_vec = (q_vec * 0.85) + (user_vec * 0.15)

    q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-10)

    # --- Single matrix multiply replaces the per-row loop ---
    # scores shape: (N,)  — dot product of normalised vecs = cosine similarity
    scores = _EMB_MATRIX @ q_norm

    # Pick top-40 indices (argpartition is faster than full sort for large N)
    k = min(40, len(scores))
    top_idx = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]  # sort descending

    top_ids = [_BOOK_IDS[i] for i in top_idx]
    top_books_qs = {b.id: b for b in Book.objects.filter(id__in=top_ids)}
    top40 = [top_books_qs[bid] for bid in top_ids if bid in top_books_qs]

    # CrossEncoder re-ranking on the top-40 candidates
    if top40:
        pairs = [[final_query, b.description or ''] for b in top40]
        ce_scores = ranker.predict(pairs)
        candidates = []
        for idx, b in enumerate(top40):
            pop = min((np.log1p(b.ratings_count or 0) * (b.avg_rating or 0)) / 50.0, 1.0)
            candidates.append({'title': b.title, 'description': b.description,
                'avg_rating': b.avg_rating, 'ratings_count': b.ratings_count,
                'url': b.url, 'image_url': b.image_url, 'authors': b.authors,
                'genres': b.genres,
                'final_score': float(ce_scores[idx]) * 0.70 + pop * 0.30})
        candidates.sort(key=lambda x: x['final_score'], reverse=True)
    else:
        candidates = []

    # Merge exact + vibe results, deduplicated
    results = list(exact_books)
    seen = set(exact_titles)
    for c in candidates:
        if c['title'] not in seen:
            results.append(c)
            seen.add(c['title'])
    return results
