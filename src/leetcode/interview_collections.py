from collections import Counter

"""
Robinhood Phone Interview
"""


def match(house, street):
    house, street = delete1(house, street)
    house, street = delete2(house, street)
    house, street = delete3(house, street)
    return sorted(house + street)


def delete1(house, street):
    return list((Counter(house) - Counter(street)).elements()), list((Counter(street) - Counter(house)).elements())


def helper(house):
    h_dict = {}
    for h in house:
        h_l = h.split(',')
        h_k = ",".join(h_l[:3])
        id = h_l[3]
        if h_k not in h_dict:
            h_dict[h_k] = {}
        h_dict[h_k][id] = h_dict[h_k].get(id, 0) + 1
    return h_dict


def rebuild(s_dict):
    house, street = [], []
    for s_k, user_d in s_dict.items():
        for user, cnt in user_d.items():
            if cnt > 0:
                street.extend([s_k + "," + user] * cnt)
            elif cnt < 0:
                house.extend([s_k + "," + user] * (-cnt))
    return house, street


def delete2(house, street):
    h_dict = helper(house)
    s_dict = helper(street)
    for h_k, user_d in h_dict.items():
        cnt_sum = sum(user_d.values())
        cnt_s_sum = sum(s_dict.get(h_k, {}).values())
        cnt = cnt_s_sum - cnt_sum
        new_s_v = {}
        if cnt > 0:
            s_v = s_dict.get(h_k, {})
            for k, v in s_v.items():
                if v >= cnt:
                    new_s_v[k] = cnt
                    break
                cnt -= v
                new_s_v[k] = v
        elif cnt < 0:
            cnt = -cnt
            h_v = h_dict.get(h_k, {})
            for k, v in h_v.items():
                if v >= cnt:
                    new_s_v[k] = -cnt
                    break
                cnt -= v
                new_s_v[k] = -v
        s_dict[h_k] = new_s_v
    return rebuild(s_dict)


def delete3(house, street):
    h_dict = helper(house)
    s_dict = helper(street)
    for h_k, user_d in h_dict.items():
        h_l = h_k.split(',')
        s_k = h_l[0] + (",S," if h_l[1] == "B" else ",B,") + h_l[2]
        cnt_sum = sum(user_d.values())
        cnt_s_sum = sum(s_dict.get(s_k, {}).values())
        cnt = cnt_s_sum - cnt_sum
        new_s_v = {}
        if cnt > 0:
            s_v = s_dict.get(s_k, {})
            for k, v in s_v.items():
                if v >= cnt:
                    new_s_v[k] = cnt
                    break
                cnt -= v
                new_s_v[k] = v
        elif cnt < 0:
            cnt = -cnt
            h_v = h_dict.get(h_k, {})
            for k, v in h_v.items():
                if v >= cnt:
                    new_s_v[k] = -cnt
                    break
                cnt -= v
                new_s_v[k] = -v
        s_dict[s_k] = new_s_v
    print(s_dict)
    return rebuild(s_dict)

