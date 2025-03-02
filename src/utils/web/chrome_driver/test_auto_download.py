import unittest
from unittest.mock import patch, MagicMock
from selenium.webdriver.common.by import By
from auto_download import download_torrents


class TestDownloadTorrents(unittest.TestCase):

    @patch('auto_download.setup_driver')
    @patch('time.sleep', return_value=None)
    def test_download_torrents_empty_list(self, mock_sleep, mock_setup_driver):
        mock_driver = MagicMock()
        mock_setup_driver.return_value = mock_driver
        
        download_torrents([])
        
        mock_driver.get.assert_not_called()
        mock_driver.find_element.assert_not_called()
        mock_driver.quit.assert_called_once()

    @patch('auto_download.setup_driver')
    @patch('time.sleep', return_value=None)
    def test_download_torrents_element_not_found(self, mock_sleep, mock_setup_driver):
        mock_driver = MagicMock()
        mock_setup_driver.return_value = mock_driver
        mock_driver.find_element.side_effect = Exception("Element not found")
        
        test_links = ['http://example.com/torrent3']
        
        with self.assertRaises(Exception):
            download_torrents(test_links)
        
        mock_driver.get.assert_called_once_with(test_links[0])
        mock_driver.find_element.assert_called_once_with(By.CLASS_NAME, "download-button")
        mock_driver.quit.assert_called_once()

    @patch('auto_download.setup_driver')
    @patch('time.sleep', return_value=None)
    def test_download_torrents_multiple_links(self, mock_sleep, mock_setup_driver):
        mock_driver = MagicMock()
        mock_setup_driver.return_value = mock_driver
        mock_download_button = MagicMock()
        mock_driver.find_element.return_value = mock_download_button
        
        test_links = ['http://example.com/torrent4', 'http://example.com/torrent5', 'http://example.com/torrent6']
        
        download_torrents(test_links)
        
        self.assertEqual(mock_driver.get.call_count, len(test_links))
        self.assertEqual(mock_driver.find_element.call_count, len(test_links))
        self.assertEqual(mock_download_button.click.call_count, len(test_links))
        self.assertEqual(mock_sleep.call_count, len(test_links))
        mock_driver.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
