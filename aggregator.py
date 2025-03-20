#!/usr/bin/env python3

# --- Automatic Dependency Installation ---
import sys
import subprocess
import os
import logging
import sqlite3
import re
from datetime import datetime

def check_and_install_dependencies():
    """Install missing Python libraries."""
    required_libraries = [
        "beautifulsoup4", "fastapi", "uvicorn", "feedparser", "requests", "python-dotenv", "typer", "streamlit"
    ]
    for library in required_libraries:
        try:
            __import__(library.split('-')[0])
        except ImportError:
            print(f"Installing missing library: {library}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", library])

check_and_install_dependencies()

# Now that we've ensured all dependencies are installed, we can import them
import streamlit as st
from streamlit import runtime
import requests
from bs4 import BeautifulSoup
import feedparser
from dotenv import load_dotenv

# Configuration
load_dotenv()
DB_FILE = os.getenv("DB_FILE", "podcasts.db")
MAX_FEED_SIZE = 15000000  # 15MB max feed size

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database Initialization
def init_db():
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

# RSS Feed Search Function
def find_podcast_rss(url: str):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        rss_links = soup.find_all('link', type=re.compile(r'(rss|xml|atom)'))
        potential_feeds = [link['href'] for link in rss_links]
        
        common_paths = ['/feed', '/rss', '/podcast.xml', '/episodes.xml']
        for path in common_paths:
            potential_feeds.append(url.rstrip('/') + path)
        
        valid_podcast_feeds = []
        for feed_url in potential_feeds:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries and any('enclosures' in entry for entry in feed.entries):
                    valid_podcast_feeds.append(feed_url)
            except:
                continue
        
        return valid_podcast_feeds
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")
        return []

# Fetch and Store Podcasts
def fetch_and_store_podcasts(feed_url: str):
    try:
        feed = feedparser.parse(feed_url)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for entry in feed.entries:
                guid = entry.get('id') or entry.get('guid')
                if not guid:
                    logger.warning(f"Skipping entry without GUID in feed {feed_url}")
                    continue
                
                audio_url = next((enc.href for enc in entry.get('enclosures', []) 
                                  if enc.type.startswith('audio/')), None)
                if not audio_url:
                    logger.warning(f"Skipping entry without audio enclosure: {guid}")
                    continue
                
                pub_date = entry.get('published', datetime.now().isoformat())
                
                cursor.execute('''
                    INSERT OR REPLACE INTO podcasts 
                    (title, description, audio_url, guid, feed_url, pub_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (entry.get('title'), entry.get('summary'), audio_url, guid, feed_url, pub_date))
            
            conn.execute("INSERT OR REPLACE INTO rss_sources (url, last_updated) VALUES (?, ?)", 
                         (feed_url, datetime.now().isoformat()))
            conn.commit()
        logger.info(f"Successfully updated feed: {feed_url}")
    except Exception as e:
        logger.error(f"Error processing feed {feed_url}: {str(e)}")
        raise

# Streamlit GUI
def run_gui():
    st.title("Podcast Aggregator")
    
    st.sidebar.header("Actions")
    action = st.sidebar.selectbox("Choose an action:", ["Search RSS Feeds", "View Podcasts", "Update Feeds"])
    
    if action == "Search RSS Feeds":
        st.subheader("Search for Podcast RSS Feeds")
        url = st.text_input("Enter a webpage URL:")
        
        if st.button("Search"):
            feeds = find_podcast_rss(url)
            if feeds:
                st.success(f"Found {len(feeds)} RSS feeds!")
                for feed in feeds:
                    st.write(feed)
                    if st.button(f"Add Feed: {feed}", key=feed):
                        try:
                            fetch_and_store_podcasts(feed)
                            st.success(f"Feed added successfully: {feed}")
                        except Exception as e:
                            st.error(f"Failed to add feed: {str(e)}")
            else:
                st.error("No valid RSS feeds found.")
    
    elif action == "View Podcasts":
        st.subheader("View Podcasts")
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, description, audio_url FROM podcasts ORDER BY pub_date DESC LIMIT 10")
            podcasts = cursor.fetchall()
        
        if podcasts:
            for podcast in podcasts:
                title, description, audio_url = podcast
                st.write(f"**Title:** {title}")
                st.write(f"**Description:** {description}")
                st.audio(audio_url)
                st.write("---")
        else:
            st.warning("No podcasts found.")
    
    elif action == "Update Feeds":
        st.subheader("Update All Feeds")
        
        with sqlite3.connect(DB_FILE) as conn:
            feeds = conn.execute("SELECT url FROM rss_sources").fetchall()
        
        if feeds:
            for (feed,) in feeds:
                try:
                    fetch_and_store_podcasts(feed)
                    st.success(f"Updated: {feed}")
                except Exception as e:
                    st.error(f"Failed to update {feed}: {str(e)}")
        else:
            st.warning("No feeds found.")

# Main Execution
if __name__ == "__main__":
    from streamlit.web import cli as stcli

    def run_streamlit():
        init_db()
        run_gui()

    if runtime.exists():
        run_streamlit()
    else:
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())

