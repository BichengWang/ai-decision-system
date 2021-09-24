from unittest import TestCase

from src.leetcode.interviews import facebook_interview_prepare
from src.leetcode.interviews.facebook_interview_prepare import lowestCommonAncestor


class Test(TestCase):
    def test_exact_match(self):
        self.assertEqual(
            (['FB,B,0100,UUID1'], ['FB,S,0100,UUID1']),
            facebook_interview_prepare.delete1([
                "AAPL,B,0100,UUID1",
                "FB,B,0100,UUID1",
            ], [
                "AAPL,B,0100,UUID1",
                "FB,S,0100,UUID1",
            ]),
        )

    def test_lowest_common_ancestor(self):
        class Node:
            def __init__(self, val):
                self.val = val
                self.left = None
                self.right = None
                self.parent = None

        root1 = Node(1)
        root2 = Node(2)
        root3 = Node(3)
        root4 = Node(4)
        root1.left = root2
        root2.parent = root1
        root1.right = root3
        root3.parent = root1
        root2.right = root4
        root4.parent = root2

        root = lowestCommonAncestor(root4, root3)
        print(root.val)
