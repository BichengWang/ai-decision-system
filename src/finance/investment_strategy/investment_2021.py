key_words = ["Trending", "Fact", "Reason", "Side Effect", "Index", "Stock"]
knowledge_graph_dict = {
    "Value Investing": {},
    "Risk Management": {},
    "Joe Biden": {
        "Tax Increase Policy": {
            "Tech Company": {
                "Trending": "Negative",
            },
            "Corporate Tax": {
                "Trending": "Negative",
            },
            "Capital Gain Tax": {
                "Trending": "Negative",
            }
        },
        "Economic Stimulus Package": {
            "Trending": "Positive",
            "Reason": "buy the rumor sell the news.",
            "Fact": "Negative",
            "Side Effect": {
                "Consumption Discretionary Sector": {
                    "Index": "",
                    "Trending": "Positive",
                    "Reason": "Covid recover and stimulus package delivered."
                }
            }
        },
    }
}


class Investment2021:
    def __init__(self):
        self.knowledge_graph_dict = knowledge_graph_dict


if __name__ == "__main__":
    print("Investment Jan. Plan")
