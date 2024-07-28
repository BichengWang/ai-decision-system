import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import logging
import requests


CHROMEDRIVER_PATH = 'C:/Program Files/Google/chromedriver-win64/chromedriver.exe'
DOWNLOAD_DIR = 'D:/Downloads/'
logging.basicConfig(level=logging.INFO)


# Setup Selenium WebDriver
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
    return driver


# Scrape the webpage to get torrent links
def get_torrent_links(url, num_pages):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    links = []
    for page in range(1, num_pages+1):
        
        url = f"{base_url}?page={page}"
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")
        for a in soup.find_all("a", href=True):
            if "torrent" in a["href"]:  # Adjust this condition based on actual link structure
                links.append("https://onejav.com"+a["href"])
    return links


# Download torrents using Selenium
def download_torrents(links):
    driver = setup_driver()
    for link in links[:1]:
        logging.info(f"Attempting download: {link}")

        response = requests.get(link)
        
        if response.status_code != 200:
            print(f"Failed to download torrent: {link}")
            continue
        
        filename = os.path.join(DOWNLOAD_DIR, link.split('/')[-1])
        with open(filename, 'wb') as f:
            f.write(response.content)
        logging.info(f"Successfully downloaded: {filename}")
    driver.quit()


if __name__ == "__main__":
    base_url = "https://onejav.com/new"
    num_pages = 5  # Number of pages to scrape
    torrent_links = get_torrent_links(base_url, num_pages)
    download_torrents(torrent_links)
