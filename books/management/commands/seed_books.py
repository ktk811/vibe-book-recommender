import csv, json
import numpy as np
from django.core.management.base import BaseCommand
from sentence_transformers import SentenceTransformer
from books.models import Book

CSV_PATH = r'C:\Users\Kartik\Downloads\book_data.csv'
BATCH_SIZE = 64

class Command(BaseCommand):
    help = 'Load books from CSV into MySQL and compute embeddings'

    def handle(self, *args, **kwargs):
        model = SentenceTransformer('all-MiniLM-L6-v2')
        self.stdout.write('Loading CSV...')
        rows = []
        with open(CSV_PATH, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                rows.append(row)
        self.stdout.write(f'Found {len(rows)} books. Computing embeddings in batches...')
        total = len(rows)
        for start in range(0, total, BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            texts = [r.get('book_desc') or r.get('book_title', '') for r in batch]
            embeddings = model.encode(texts, show_progress_bar=False)
            to_create = []
            for i, r in enumerate(batch):
                try: rating = float(r.get('book_rating') or 0)
                except: rating = 0.0
                try: count = int(str(r.get('book_rating_count') or '0').replace(',', ''))
                except: count = 0
                to_create.append(Book(
                    title=r.get('book_title', '')[:500],
                    authors=r.get('book_authors', '')[:500],
                    description=r.get('book_desc', ''),
                    avg_rating=rating,
                    ratings_count=count,
                    url=r.get('url', ''),
                    image_url=r.get('image_url', ''),
                    genres=r.get('genres', '')[:500],
                    embedding=json.dumps(embeddings[i].tolist()),
                ))
            Book.objects.bulk_create(to_create, ignore_conflicts=True)
            pct = min(start + BATCH_SIZE, total)
            self.stdout.write(f'  {pct}/{total} done')
        self.stdout.write(self.style.SUCCESS('Seeding complete!'))
