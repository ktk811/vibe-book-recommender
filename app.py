import streamlit as st
import pymongo
from sentence_transformers import SentenceTransformer, CrossEncoder
import urllib.parse
import requests
import numpy as np
import certifi

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vibe", layout="wide", page_icon="📚")

# --- CUSTOM CSS (VISUAL FIXES) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* 1. Global App Styling */
    .stApp { 
        background-color: #F1F5F9 !important; 
        font-family: 'Inter', sans-serif; 
        color: #0F172A !important; 
    }
    
    /* 2. Sidebar & Toggle Button Fix */
    [data-testid="stSidebar"] { 
        background-color: #E2E8F0 !important; 
        border-right: 1px solid #CBD5E1 !important; 
    }
    
    /* This makes the collapse arrow visible (Dark Slate color) */
    [data-testid="stSidebarCollapsedControl"], 
    [data-testid="stSidebarNav"] > button,
    button[kind="header"] {
        color: #0F172A !important;
        background-color: transparent !important;
    }

    /* 3. Text Visibility */
    h1, h2, h3, h4, h5, h6, [data-testid="stHeader"] { 
        color: #0F172A !important; 
        font-weight: 700 !important; 
    }
    p, span, div, label, li { 
        color: #334155 !important; 
    }

    /* 4. UNIFIED BUTTON ARCHITECTURE (The Fix) */
    /* We target <a> (links) and <button> (actions) to share EXACT styling */
    
    .stButton > button, 
    a[data-testid="stLinkButton"], 
    [data-testid="stBaseButton-secondary"],
    div[data-testid="stPopover"] > button {
        background-color: #0F172A !important; /* Unified Dark Color */
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        
        /* Force identical geometry */
        min-height: 3rem !important; 
        height: auto !important;
        width: 100% !important;
        padding: 0px 16px !important;
        
        /* Centering Content */
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        
        /* Typography */
        font-weight: 600 !important;
        text-decoration: none !important;
        line-height: 1.5 !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* Force Internal Text Colors to White */
    .stButton > button p, 
    .stButton > button span,
    a[data-testid="stLinkButton"], 
    div[data-testid="stPopover"] > button p {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    /* Primary Search Button Highlight (Indigo) */
    div.stButton > button[kind="primary"] {
        background-color: #4338CA !important;
    }

    /* Hover States */
    .stButton > button:hover, 
    a[data-testid="stLinkButton"]:hover, 
    div[data-testid="stPopover"] > button:hover {
        background-color: #334155 !important; /* Lighter Slate on hover */
        transform: translateY(-1px);
        color: #FFFFFF !important;
    }

    /* 5. Book Card Styling */
    .book-card {
        background-color: #FFFFFF !important; 
        border: 1px solid #E2E8F0 !important; 
        border-radius: 12px;
        padding: 24px; 
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }

    /* 6. Input Field Styling */
    .stTextInput input { 
        background-color: #FFFFFF !important; 
        border: 1px solid #CBD5E1 !important; 
        border-radius: 8px; 
        color: #0F172A !important; 
    }
</style>
""", unsafe_allow_html=True)

# --- DATABASE ---
@st.cache_resource
def init_connection():
    try: return pymongo.MongoClient(st.secrets["MONGO_URI"], tlsCAFile=certifi.where())
    except: return pymongo.MongoClient("mongodb+srv://YOUR_USER:YOUR_PASS@cluster0.mongodb.net/?retryWrites=true&w=majority", tlsCAFile=certifi.where())

def get_db(): return init_connection().vibebooks_db

# --- AI MODELS ---
@st.cache_resource
def load_models():
    retriever = SentenceTransformer('all-MiniLM-L6-v2')
    ranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return retriever, ranker

retriever, ranker = load_models()

# --- SMART SEARCH (STRICT TITLE + VIBE) ---
def smart_search(query, username=None, mood=50, complexity=50):
    db = get_db()
    
    # 1. EXACT TITLE MATCH (Strict Mode ^...$)
    # Using ^ and $ ensures "Malice" matches exactly "Malice" and not "Without MAlice"
    exact_matches = list(db.books_collection.find(
        {"title": {"$regex": f"^{query}$", "$options": "i"}},
        {"_id": 0, "title": 1, "description": 1, "ratings_count": 1, "avg_rating": 1, "url": 1, "image_url": 1}
    ).limit(3))
    
    # Force high score for exact matches
    for book in exact_matches:
        book['final_score'] = 2.0 

    # 2. VIBE SEARCH
    vibe_context = ""
    if mood < 30: vibe_context += " lighthearted funny cheerful happy"
    elif mood > 70: vibe_context += " dark serious grim intense"
    if complexity < 30: vibe_context += " simple easy read short"
    elif complexity > 70: vibe_context += " complex philosophical academic difficult"
    
    final_query = query + vibe_context
    query_vec = retriever.encode(final_query)
    
    # Personalization
    if username:
        saved = list(db.library.find({"username": username}))
        if saved:
            titles = [b['title'] for b in saved]
            history = list(db.books_collection.find({"title": {"$in": titles}}, {"embedding": 1}))
            if history:
                user_vec = np.mean([d['embedding'] for d in history], axis=0)
                query_vec = (query_vec * 0.85) + (user_vec * 0.15)

    pipeline = [
        {"$vectorSearch": {"index": "default", "path": "embedding", "queryVector": query_vec.tolist(), "numCandidates": 100, "limit": 40}},
        {"$project": {"_id": 0, "title": 1, "description": 1, "ratings_count": 1, "avg_rating": 1, "url": 1, "image_url": 1}}
    ]
    vibe_candidates = list(db.books_collection.aggregate(pipeline))

    # 3. RE-RANKING (CrossEncoder)
    if vibe_candidates:
        pairs = [[final_query, doc.get('description', '')] for doc in vibe_candidates]
        scores = ranker.predict(pairs)
        
        for idx, doc in enumerate(vibe_candidates):
            relevance = scores[idx]
            count = doc.get('ratings_count', 0) or 0
            rating = doc.get('avg_rating', 0) or 0
            pop_score = min((np.log1p(count) * rating) / 50.0, 1.0)
            doc['final_score'] = (relevance * 0.70) + (pop_score * 0.30)

    # 4. MERGE
    seen_titles = set()
    final_results = []
    
    for book in exact_matches:
        if book['title'] not in seen_titles:
            final_results.append(book); seen_titles.add(book['title'])
            
    vibe_candidates.sort(key=lambda x: x['final_score'], reverse=True)
    for book in vibe_candidates:
        if book['title'] not in seen_titles:
            final_results.append(book); seen_titles.add(book['title'])

    return final_results

# --- ACTIONS ---
def submit_rating(title, rating):
    get_db().books_collection.update_one({"title": title}, {"$set": {"avg_rating": rating}, "$inc": {"ratings_count": 1}})

def save_book(u, t, url):
    db = get_db()
    if not db.library.find_one({"username": u, "title": t}):
        db.library.insert_one({"username": u, "title": t, "url": url})
        return True
    return False

def get_library(u): return list(get_db().library.find({"username": u}))
def delete_book(u, t): get_db().library.delete_one({"username": u, "title": t})
def login_user(u, p): return get_db().users.find_one({"username": u, "password": p}) is not None
def register_user(u, p):
    db = get_db()
    if db.users.find_one({"username": u}): return False
    db.users.insert_one({"username": u, "password": p})
    return True

@st.cache_data(ttl=3600)
def fetch_cover(title):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{urllib.parse.quote(title)}&maxResults=1"
        data = requests.get(url).json()
        if "items" in data: return data["items"][0]["volumeInfo"]["imageLinks"].get("thumbnail")
    except: pass
    return None

# --- UI ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = ""
if 'results' not in st.session_state: st.session_state.results = []

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center;'>Vibe</h1>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["Login", "Sign Up"])
        with t1:
            u, p = st.text_input("User", key="l_u"), st.text_input("Pass", type="password", key="l_p")
            if st.button("Login", type="primary", use_container_width=True):
                if login_user(u, p): st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Invalid")
        with t2:
            u, p = st.text_input("User", key="r_u"), st.text_input("Pass", type="password", key="r_p")
            if st.button("Create", type="primary", use_container_width=True):
                if register_user(u, p): st.success("Created!")
                else: st.error("Taken")
else:
    with st.sidebar:
        st.markdown(f"### {st.session_state.username}")
        if st.button("Sign Out", type="secondary", use_container_width=True): 
            st.session_state.logged_in = False; st.rerun()
        
        st.divider()
        st.markdown("### 🎛️ Vibe Meter")
        mood = st.slider("Mood (Light ↔ Dark)", 0, 100, 50, help="0=Happy, 100=Dark")
        complex = st.slider("Complexity (Simple ↔ Deep)", 0, 100, 50, help="0=Easy, 100=Academic")
        
        st.divider()
        st.subheader("My Library")
        for item in get_library(st.session_state.username):
            c1, c2 = st.columns([4,1])
            c1.markdown(f"[{item['title']}]({item['url']})")
            if c2.button("x", key=f"del_{item['title']}"): delete_book(st.session_state.username, item['title']); st.rerun()

    st.markdown("<h1 style='text-align: center;'>Vibe</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #64748B;'>Searching <b>{53128:,}</b> books</p>", unsafe_allow_html=True)

    c1, c2 = st.columns([5, 1]) 
    with c1: 
        query = st.text_input("Search", placeholder="Describe the vibe...", label_visibility="collapsed")
    with c2: 
        if st.button("Search", type="primary", use_container_width=True) and query:
            with st.spinner("Analyzing..."):
                st.session_state.results = smart_search(query, st.session_state.username, mood, complex)

    if st.session_state.results:
        for idx, book in enumerate(st.session_state.results):
            with st.container():
                st.markdown('<div class="book-card">', unsafe_allow_html=True)
                col_img, col_txt = st.columns([1, 4])
                
                with col_img:
                    img = book.get('image_url')
                    if not img or len(str(img)) < 10: img = fetch_cover(book['title'])
                    if not img: img = "https://placehold.co/400x600/E2E8F0/475569?text=No+Cover"
                    st.image(img, use_container_width=True)

                with col_txt:
                    st.markdown(f"### {book['title']}")
                    if book.get('avg_rating'): st.caption(f"{book['avg_rating']:.1f} / 5.0  •  {book.get('ratings_count',0):,} ratings")
                    
                    desc = book.get('description', 'No description.')
                    st.write(desc[:280] + "..." if len(desc) > 280 else desc)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
                    
                    safe_title = urllib.parse.quote(book['title'])
                    google_link = f"https://www.google.com/search?q={safe_title}"
                    ocean_link = f"https://oceanofpdf.com/?s={safe_title}"
                    
                    b1.link_button("Read Info", book.get('url', google_link), use_container_width=True)
                    b2.link_button("PDF Search", ocean_link, use_container_width=True)
                    
                    if b3.button("Save", key=f"save_{idx}_{book['title']}", use_container_width=True):
                        save_book(st.session_state.username, book['title'], google_link)
                        st.toast("Saved!")

                    with b4.popover("Rate"):
                        st.write(f"Rate **{book['title'][:20]}...**")
                        user_score = st.slider("Stars", 1, 5, 5, key=f"sl_{idx}_{book['title']}")
                        if st.button("Submit", key=f"btn_{idx}_{book['title']}", type="primary"):
                            submit_rating(book['title'], user_score)
                            st.toast("Rated!")

                st.markdown('</div>', unsafe_allow_html=True)
