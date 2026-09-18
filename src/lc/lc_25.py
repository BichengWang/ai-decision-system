class ListNode:
    def __init__(self, val, next=None):
        self.val = val
        self.next = next


def reverseKGroup(h, k):
    """
    :type head: ListNode
    :type k: int
    :rtype: ListNode
    """
    dummy = ListNode(0, h)
    prev = dummy
    cur = h
    cnt = 0
    while cur:
        head = prev
        tail = cur
        while cnt < k:
            if not cur:
                break
            cnt += 1
            next = cur.next
            cur.next = prev
            prev, cur = cur, next
        tail.next = cur
        if cnt == k:
            head.next = prev
            prev = tail
            cnt = 0
        else:
            cur, prev = prev, cur
            while cnt > 0:
                cnt -= 1
                next = cur.next
                cur.next = prev
                prev, cur = cur, next
    h = dummy.next
    del dummy
    return h


if __name__ == "__main__":
    h = ListNode(1, ListNode(2, ListNode(3, ListNode(4, ListNode(5)))))
    h = reverseKGroup(h, 3)
