from unittest import TestCase

from src.leetcode import lc_588_file_system


class TestFileSystem(TestCase):
    def test_upper(self):
        fs = lc_588_file_system.FileSystem()
        fs.mkdir("/a/b/c")
        fs.addContentToFile("/a/b/c/d", "hello")
        self.assertEqual(['d'], fs.ls("/a/b/c"))
