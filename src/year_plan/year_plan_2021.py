import sys

key_words = ["Name", "Target", "Principle"]
monthly_plans = [
    {
        "Name": "Jan. Plan",
        "Target": [
            {
                "Name": "Build a website",
                "Result": "",
            },
            {
                "Name": "Write first blog",
                "Result": "",
            },
        ],
        "Principle": [
            {
                "Name": "Don't rule they, let them go. They will pay well.",
                "Reason": "Too many rules introduce many unnecessary conflicts, slow down cooperate. Inspirit them better than rule them.",
            }
        ],
    },
    {
        "Name": "Feb. Plan",
        "Targets": [

        ],
    },

]


class YearPlan:
    def __init__(self):
        self.monthly_plans = monthly_plans


def monthly_plan():
    print("Jan. Monthly plan.")


class Solution(object):
    def minDifficulty(self, jobDifficulty, d):
        """
        :type jobDifficulty: List[int]
        :type d: int
        :rtype: int
        """
        maxSelectJob = len(jobDifficulty) - d + 1
        row = d + 1
        col = len(jobDifficulty) + 1
        dp = [[-1]*col for i in range(row)]
        diff_max = self._gen_diff_sum(jobDifficulty)
        dp[0][0] = 0
        for i in range(1, row):
            for j in range(1, col):
                cur = sys.maxsize
                for k in range(0, j):
                    if dp[i - 1][k] == -1:
                        continue
                    cur = min(cur, dp[i - 1][k] + diff_max[k][j])
                dp[i][j] = cur
        print(dp)
        return dp[row - 1][col - 1]

    def _gen_diff_sum(self, jobs):
        row = len(jobs) + 1
        col = len(jobs) + 1
        ret = [[0]*col for i in range(row)]
        for i in range(row):
            ret[i][i] = 0
            for j in range(i + 1, col):
                ret[i][j] = max(ret[i][j - 1], jobs[j - 1])
        print(ret)
        return ret

if __name__ == "__main__":
    print()
    Solution().minDifficulty([6,5,4,3,2,1],2)
