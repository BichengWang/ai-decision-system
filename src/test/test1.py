def find_first(list, tgt, end_i):
    start = 0
    end = end_i

    while start < end:
        mid = (start + end) // 2
        if list[mid] < tgt:
            start = mid + 1
        else:
            end = mid
    return start


def compress(chars):
    ret = []
    prev = ""
    cnt = 0
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch == prev:
            cnt += 1
            if cnt > 2:
                del chars[i]
                i -= 1
        else:
            if cnt > 1:
                chars[i - 1] = str(cnt)
            prev, cnt = ch, 1
        i += 1
    if cnt > 1:
        chars[i - 1] = str(cnt)
    print(chars)
    return len(chars)


def bruceforcesong(time):
    n = len(time)
    prev_list = [0]
    for i in range(n):
        cur = time[i]
        cur_list = []
        cur_list.extend(prev_list)
        for prev in prev_list:
            cur_list.append(prev + cur)
        prev_list = cur_list
    cnt = 0
    print(prev_list)
    for prev in prev_list:
        if prev % 60 == 0:
            cnt += 1
    return cnt


if __name__ == '__main__':
    print(find_first([3, 5, 6, 9, 10], 6, 4))
    print(find_first([1, 3, 5, 7, 9], 3, 4))

    print(compress(['a', 'b', 'b', 'b', 'c', 'c', 'c', 'c']))
    print(bruceforcesong([30,20,150,100,40]))
