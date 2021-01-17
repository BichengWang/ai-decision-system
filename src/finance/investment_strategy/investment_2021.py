key_words = ["Trending", "Fact", "Reason", "Side Effect", "Index", "Stock", "ETF"]
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
                    "ETF": [
                        "PEJ Leisure & entertainment etf",
                        "XLY Consumer discretionary select sector SPDR fund",
                    ],
                    "Trending": "Positive",
                    "Reason": "Covid recover and stimulus package delivered."
                }
            }
        },
    }
}


investment_principle = {
    "principle1": {
        "Principle": "Other investors haven't go into the underlying but will plan to.",
        "Trending": "Positive",
        "Reason": "Newly long position crowd would push the price to go high and squeeze short."
    },
    "principle2": {
        "Principle": "Does all the potential investors go into the trading? Yes, then leave it",
        "Trending": "Negative",
        "Reason": "Picked like leek",
    },
}


class Investment2021:
    def __init__(self):
        self.knowledge_graph_dict = knowledge_graph_dict


if __name__ == "__main__":
    print("Investment Jan. Plan")
