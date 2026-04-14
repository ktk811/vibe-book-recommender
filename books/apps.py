from django.apps import AppConfig

class BooksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'books'

    def ready(self):
        # Pre-load the embedding matrix into RAM when the server starts
        # so the first search request isn't slow
        import threading
        def _load():
            try:
                from .ml import _load_index
                _load_index()
            except Exception as e:
                print(f'[ml] Index preload failed: {e}')
        threading.Thread(target=_load, daemon=True).start()
