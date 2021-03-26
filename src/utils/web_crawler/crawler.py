import time

import requests
import re
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
}


class SwiftCrawler:
    def __init__(self, url, headers):
        self.url = url
        self.headers = headers

    def crawl_content(self):
        response = requests.get(self.url, headers=self.headers)
        self.parse_content(response.text)
        return

    def parse_content(self, content):
        urls = re.findall(
            r'<img class="image" src="(.*?)" onerror="reloadImage\(event\)" referrerpolicy="same-origin">',
            content)
        for url in urls:
            time.sleep(1)
            strs = url.split('/')
            file_name = "\\".join(strs[-1])
            response = requests.get(url, headers=self.headers)
            with open(file_name, 'wb') as f:
                f.write(response.content)
        return urls


if __name__ == "__main__":
    sc = SwiftCrawler(
        url="?page={page}".format(page=1),
        headers=HEADERS,
    )
    sc.crawl_content()
