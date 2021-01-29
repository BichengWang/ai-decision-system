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


if __name__ == "__main__":
    print()
