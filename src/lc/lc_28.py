class Solution:
    def strStr(self, haystack: str, needle: str) -> int:
        if len(needle) > len(haystack):
            return -1
        ret = 0
        l, r = 0, 0
        for l in range(len(haystack)):
            r = l
            idx = 0
            while idx < len(needle):
                if haystack[r] == needle[idx]:
                    r += 1
                    idx += 1
            if idx == len(needle):
                return l
        return -1

if __name__ == "__main__":
    Solution.strStr("hello", "ll")
