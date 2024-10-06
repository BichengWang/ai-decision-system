import unittest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from unittest.mock import patch, MagicMock
from auto_download import download_torrents


# Update the path to your chromedriver executable
CHROMEDRIVER_PATH = 'C:/Program Files/Google/chromedriver-win64/chromedriver.exe'


class TestChromeDriverSetup(unittest.TestCase):

    def setUp(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        self.driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

    def test_open_google(self):
        self.driver.get("https://www.google.com")
        self.assertIn("Google", self.driver.title)
        
        # Optionally, you can find an element to ensure the page has fully loaded
        search_box = self.driver.find_element(By.NAME, "q")
        self.assertIsNotNone(search_box)
        
    @patch('auto_download.setup_driver')
    @patch('time.sleep', return_value=None)
    def test_download_torrents(self, mock_sleep, mock_setup_driver):
        # Create a mock driver
        mock_driver = MagicMock()
        mock_setup_driver.return_value = mock_driver

        # Create a mock download button
        mock_download_button = MagicMock()
        mock_driver.find_element.return_value = mock_download_button

        # List of test links
        test_links = ['http://example.com/torrent1', 'http://example.com/torrent2']

        # Call the function with the test links
        download_torrents(test_links)

        # Check if the driver.get method was called with the correct links
        calls = [unittest.mock.call(link) for link in test_links]
        mock_driver.get.assert_has_calls(calls, any_order=False)

        # Check if the download button was clicked for each link
        self.assertEqual(mock_download_button.click.call_count, len(test_links))

        # Check if the driver.quit method was called
        mock_driver.quit.assert_called_once()

    def tearDown(self):
        self.driver.quit()
        


if __name__ == "__main__":
    unittest.main()
