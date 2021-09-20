from collections import Counter


def people_know_secret(people_conn, source):
    """
    https://leetcode.com/discuss/interview-question/1469368/One-onsite-question-from-Facebook
    Question 1
    Args:
        people_conn:
        source: leak secret source
    Returns:
        Who will know secret
    """
    people_conn.sort(key=lambda x: x[2])
    return people_know_secret_helper(people_conn, source)


def people_know_secret_helper(people_conn, source):
    """
    Assume people_conn sorted
    """
    ret = [source]
    visited = set(source)
    for p1, p2, time in people_conn:
        if p1 not in visited and p2 in visited:
            ret.append(p1)
            visited.add(p1)
        elif p1 in visited and p2 not in visited:
            ret.append(p1)
            visited.add(p1)
    return ret


def get_source_of_secret(people_conn, secret_holder):
    """
    https://leetcode.com/discuss/interview-question/1469368/One-onsite-question-from-Facebook
    Follow up 1
    Args:
        people_conn:
        secret_holder:
    Returns:
        who possible leak the secret
    """
    secret_holder = set(secret_holder)
    secret_dict = {}
    people = set()
    for p1, p2, _ in people_conn:
        people.add(p1)
        people.add(p2)
    people_conn.sort(key=lambda x: x[2])
    for p in people:
        secret_dict[p] = set(people_know_secret_helper(people_conn, p))
    ret = set()
    for k, v in secret_holder:
        if not v.difference(secret_holder):
            ret.add(k)
    valid_set = set()
    for p in ret:
        valid_set += secret_dict[p]
    return list(ret) if valid_set == secret_holder else []


def square_three_sum_possible(nums):
    """
    https://leetcode.com/discuss/interview-question/1467470/Facebook-phone-interview
    Question 1
    Args:
        nums: sorted nums
    Returns: bool possible three sum to zero
    """
    sq_nums = [num * num for num in sorted(nums)]
    c_nums = Counter(sq_nums)
    for i in range(len(nums) - 2):
        for j in range(i + 1, len(nums) - 1):
            total = nums[i] + nums[j]
            if total > nums[-1]:
                break
            if total in c_nums:
                if not Counter([nums[i], nums[j], total]) - c_nums:
                    return True
    return False


def tree_right_side_view(root):
    """
    https://leetcode.com/discuss/interview-question/1467470/Facebook-phone-interview
    Question 2
    Args:
        root:

    Returns:
        right side view
    """
    ret = []
    if not root: return ret
    q = [root]
    while q:
        ret.append(0)
        for _ in range(len(q)):
            cur = q.pop(0)
            ret[-1] = cur.val
            if cur.left: q.append(cur.left)
            if cur.right: q.append(cur.right)
    return ret


