import json
import urllib.parse
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import User, Book, Library
from .ml import smart_search

def index(request):
    if not request.session.get('username'):
        return render(request, 'books/index.html', {'logged_in': False})
    library = list(Library.objects.filter(user_id=request.session['username']).values('title', 'url'))
    return render(request, 'books/index.html', {
        'logged_in': True,
        'username': request.session['username'],
        'library': library,
    })

@require_POST
def login_view(request):
    u = request.POST.get('username', '').strip()
    p = request.POST.get('password', '').strip()
    if User.objects.filter(username=u, password=p).exists():
        request.session['username'] = u
        return redirect('/')
    return render(request, 'books/index.html', {'logged_in': False, 'error': 'Invalid credentials'})

@require_POST
def register_view(request):
    u = request.POST.get('username', '').strip()
    p = request.POST.get('password', '').strip()
    if not u or not p:
        return render(request, 'books/index.html', {'logged_in': False, 'reg_error': 'Username and password required'})
    if User.objects.filter(username=u).exists():
        return render(request, 'books/index.html', {'logged_in': False, 'reg_error': 'Username already taken'})
    User.objects.create(username=u, password=p)
    return render(request, 'books/index.html', {'logged_in': False, 'reg_success': 'Account created! Please log in.'})

def logout_view(request):
    request.session.flush()
    return redirect('/')

# RESTful API endpoint — returns JSON results for AJAX calls
def search_api(request):
    if not request.session.get('username'):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'results': []})
    mood = int(request.GET.get('mood', 50))
    complexity = int(request.GET.get('complexity', 50))
    results = smart_search(query, request.session['username'], mood, complexity)
    # Sanitize for JSON
    safe = []
    for b in results[:20]:
        safe_title = urllib.parse.quote(b['title'])
        safe.append({
            'title': b['title'],
            'authors': b.get('authors', ''),
            'description': (b.get('description') or '')[:300] + '...' if len(b.get('description') or '') > 300 else (b.get('description') or ''),
            'avg_rating': round(b.get('avg_rating') or 0, 1),
            'ratings_count': b.get('ratings_count') or 0,
            'url': b.get('url') or f'https://www.google.com/search?q={safe_title}',
            'image_url': b.get('image_url') or '',
            'genres': b.get('genres', ''),
        })
    return JsonResponse({'results': safe})

@require_POST
def save_book_api(request):
    if not request.session.get('username'):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    data = json.loads(request.body)
    title = data.get('title', '')
    url = data.get('url', '')
    username = request.session['username']
    obj, created = Library.objects.get_or_create(user_id=username, title=title, defaults={'url': url})
    return JsonResponse({'saved': created})

@require_POST
def delete_book_api(request):
    if not request.session.get('username'):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    data = json.loads(request.body)
    Library.objects.filter(user_id=request.session['username'], title=data.get('title', '')).delete()
    return JsonResponse({'deleted': True})

@require_POST
def rate_book_api(request):
    if not request.session.get('username'):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    data = json.loads(request.body)
    title = data.get('title', '')
    rating = float(data.get('rating', 3))
    book = Book.objects.filter(title__iexact=title).first()
    if book:
        total = (book.avg_rating * book.ratings_count) + rating
        book.ratings_count += 1
        book.avg_rating = round(total / book.ratings_count, 2)
        book.save(update_fields=['avg_rating', 'ratings_count'])
    return JsonResponse({'rated': True})

def library_api(request):
    if not request.session.get('username'):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    items = list(Library.objects.filter(user_id=request.session['username']).values('title', 'url'))
    return JsonResponse({'library': items})
