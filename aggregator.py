#!/usr/bin/env python3

import sys
import subprocess
import importlib.util
import os
import logging
import sqlite3
import re
from datetime import datetime
from urllib.parse import urljoin

# --- Configuration ---
DB_FILE = "podcasts.db"
MAX_FEED_SIZE = 15000000  # 15MB max feed size

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Dependency Management ---
def is_library_installed(library_name):
    return importlib.util.find_spec(library_name) is not None

def install_library(library):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", library, "--no-cache-dir"])
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {library}: {e}")
        sys.exit(1)

def check_and_install_dependencies():
    required_libraries = [
        ("beautifulsoup4", "bs4"),
        ("feedparser", "feedparser"),
        ("requests", "requests"),
        ("streamlit", "streamlit")
    ]
    for library, import_name in required_libraries:
        if not is_library_installed(import_name):
            print(f"Installing missing library: {library}")
            install_library(library)
        else:
            print(f"{library} is already installed")

# --- Database Operations ---
def init_db():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS podcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    description TEXT,
                    audio_url TEXT,
                    guid TEXT UNIQUE,
                    feed_url TEXT,
                    pub_date TEXT
                );
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    last_updated TIMESTAMP
                );
            ''')
            logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

def fetch_and_store_podcasts(feed_url: str) -> bool:
    import feedparser
    import requests
    try:
        # Fetch feed content
        response = requests.get(feed_url, timeout=10)
        response.raise_for_status()
        
        # Check feed size
        if len(response.content) > MAX_FEED_SIZE:
            logger.error(f"Feed {feed_url} exceeds size limit of {MAX_FEED_SIZE} bytes")
            return False
        
        feed = feedparser.parse(response.content)
        if feed.bozo:
            logger.error(f"Feed {feed_url} has parsing errors: {feed.bozo_exception}")
            return False
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for entry in feed.entries:
                guid = entry.get('id') or entry.get('guid')
                if not guid:
                    logger.warning(f"Skipping entry without GUID in feed {feed_url}")
                    continue
                
                # Find audio enclosure
                audio_url = None
                for enc in entry.get('enclosures', []):
                    if enc.get('type', '').startswith('audio/'):
                        audio_url = enc.href
                        break
                if not audio_url:
                    logger.warning(f"Skipping entry without audio enclosure: {guid}")
                    continue
                
                # Parse publication date
                if hasattr(entry, 'published_parsed'):
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat()
                else:
                    pub_date = datetime.now().isoformat()
                
                # Insert into database
                cursor.execute('''
                    INSERT OR REPLACE INTO podcasts 
                    (title, description, audio_url, guid, feed_url, pub_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    entry.get('title', 'No Title'),
                    entry.get('summary', ''),
                    audio_url,
                    guid,
                    feed_url,
                    pub_date
                ))
            
            # Update rss_sources
            cursor.execute('''
                INSERT OR REPLACE INTO rss_sources (url, last_updated)
                VALUES (?, ?)
            ''', (feed_url, datetime.now().isoformat()))
            conn.commit()
        
        logger.info(f"Successfully updated feed: {feed_url}")
        return True
    except Exception as e:
        logger.error(f"Error processing feed {feed_url}: {str(e)}")
        return False

# --- RSS Feed Operations ---
def find_podcast_rss(url: str):
    import requests
    from bs4 import BeautifulSoup
    import feedparser
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all RSS feed links
        rss_links = soup.find_all('link', type=re.compile(r'(rss|xml|atom)'))
        potential_feeds = [urljoin(url, link['href']) for link in rss_links]
        
        # Add common podcast feed paths
        common_paths = ['/feed', '/rss', '/podcast.xml', '/episodes.xml']
        for path in common_paths:
            potential_feeds.append(urljoin(url, path))
        
        # Validate feeds
        valid_podcast_feeds = []
        for feed_url in potential_feeds:
            try:
                response = requests.get(feed_url, timeout=10)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if not feed.bozo and feed.entries:
                    has_audio = any(
                        any(enc.get('type', '').startswith('audio/') 
                        for entry in feed.entries 
                        for enc in entry.get('enclosures', []))
                    )
                    if has_audio:
                        valid_podcast_feeds.append(feed_url)
            except Exception as e:
                logger.debug(f"Skipping invalid feed {feed_url}: {str(e)}")
                continue
        
        return valid_podcast_feeds
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")
        return []

# --- Streamlit GUI ---
def run_gui():
    import streamlit as st
    
    st.title("Podcast Aggregator")
    
    st.sidebar.header("Actions")
    action = st.sidebar.selectbox("Choose an action:", 
                                 ["Search RSS Feeds", "View Podcasts", "Update Feeds"])
    
    if action == "Search RSS Feeds":
        search_rss_feeds()
    elif action == "View Podcasts":
        view_podcasts()
    elif action == "Update Feeds":
        update_feeds()

def search_rss_feeds():
    import streamlit as st
    
    st.subheader("Search for Podcast RSS Feeds")
    url = st.text_input("Enter a webpage URL:", "https://example.com")
    
    if st.button("Search"):
        with st.spinner("Searching for podcast feeds..."):
            feeds = find_podcast_rss(url)
            if feeds:
                st.success(f"Found {len(feeds)} RSS feeds!")
                for feed in feeds:
                    st.write(feed)
                    if st.button(f"Add Feed: {feed}", key=f"add_{feed}"):
                        with sqlite3.connect(DB_FILE) as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT url FROM rss_sources WHERE url = ?", (feed,))
                            exists = cursor.fetchone()
                        if exists:
                            st.warning(f"Feed already exists: {feed}")
                        else:
                            success = fetch_and_store_podcasts(feed)
                            if success:
                                st.success(f"Feed added successfully: {feed}")
                            else:
                                st.error(f"Failed to add feed: {feed}")
            else:
                st.error("No valid RSS feeds found.")

def view_podcasts():
    import streamlit as st
    
    st.subheader("View Podcasts")
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT title, description, audio_url, pub_date 
            FROM podcasts 
            ORDER BY datetime(pub_date) DESC 
            LIMIT 50
        ''')
        podcasts = cursor.fetchall()
    
    if podcasts:
        for title, description, audio_url, pub_date in podcasts:
            st.subheader(title)
            st.caption(f"Published: {pub_date}")
            st.write(description)
            st.audio(audio_url)
            st.write("---")
    else:
        st.warning("No podcasts found.")

def update_feeds():
    import streamlit as st
    
    st.subheader("Update All Feeds")
    
    with sqlite3.connect(DB_FILE) as conn:
        feeds = conn.execute("SELECT url FROM rss_sources").fetchall()
    
    if not feeds:
        st.warning("No feeds found.")
        return
    
    progress_bar = st.progress(0)
    total_feeds = len(feeds)
    for i, (feed_url,) in enumerate(feeds):
        try:
            st.write(f"Updating: {feed_url}")
            success = fetch_and_store_podcasts(feed_url)
            if success:
                st.success(f"Updated successfully: {feed_url}")
            else:
                st.error(f"Failed to update: {feed_url}")
            progress_bar.progress((i + 1) / total_feeds)
        except Exception as e:
            st.error(f"Error updating {feed_url}: {str(e)}")
    st.success("All feeds updated!")

# --- Main Execution ---
if __name__ == "__main__":
    check_and_install_dependencies()
    init_db()

    if len(sys.argv) > 1 and sys.argv[1] == "streamlit":
        # Running with Streamlit
        import streamlit as st
        run_gui()
    else:
        # Running directly with Python
        print("To view this Streamlit app in your browser, run:")
        print(f"streamlit run {__file__}")
        
        # Automatically start Streamlit
        if "streamlit" not in sys.argv:
            subprocess.run([sys.executable, "-m", "streamlit", "run", __file__, "streamlit"])
            
            