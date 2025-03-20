
Go to MAIN branch ...

# Podcast Aggregator

## Description
This Podcast Aggregator is a Streamlit-based web application that allows users to search for, add, and manage podcast RSS feeds. It provides a simple interface to discover new podcasts, view their episodes, and keep track of updates.

## Features
- Search for podcast RSS feeds by URL
- Add discovered feeds to a local database
- View the latest episodes from added podcasts
- Update all stored podcast feeds

## Installation
1. Clone this repository:

git clone https://github.com/your-username/podcast-aggregator.git

text
2. Navigate to the project directory:

cd podcast-aggregator

text
3. Install the required dependencies:

pip install -r requirements.txt

text

## Usage
1. Run the application:

streamlit run aggregator.py

text
2. Open your web browser and go to the URL provided by Streamlit (usually `http://localhost:8501`).

3. Use the sidebar to navigate between different actions:
- **Search RSS Feeds**: Enter a website URL to find podcast RSS feeds.
- **View Podcasts**: See the latest episodes from your added podcasts.
- **Update Feeds**: Refresh all stored podcast feeds.

## Dependencies
- streamlit
- beautifulsoup4
- feedparser
- requests
- python-dotenv

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is open source and available under the [MIT License](LICENSE).

