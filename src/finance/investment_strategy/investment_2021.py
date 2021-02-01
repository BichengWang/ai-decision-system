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
            },
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
                    "Reason": "Covid recover and stimulus package delivered.",
                },
            },
        },
    },
    "New Type of Inflation": {
        "Phenomenon": "Fed release money -> core CPI not increasing fast, but asset bull",
        "Result": "New Type of Inflation, fool people and rich richest all the time",
        "Reason": "This is so call new type of inflation. "
                  "Traditional CPI index already out of style, because the necessity in the modern world is not food but asset."
                  "Fed blindly or intend to blindly use old world index as CPI to fool people."
                  "Then, the asset increase fast, and the gap between rich and poor split more."
                  "The side effect would show the result sooner or later.",
    },
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
    "principle3": {
        "Principle": "Find the frontier and the edger of the world who being laughed at.",
        "Trending": "Positive",
        "Reason": "Margin cost lowest but margin reward highest in the uncultivated land to lead the world."
                  "Being laughed at by the crowd means less people realize the real value and underestimated but already obtain attention."
                  "Truth is in the hands of a few",
    },
    "principle4": {
        "Principle": "The highest risk is not long the position but is sell then buy again risk.",
        "Reason": "long time experience",
    }
}

target_assets = [
    {
        "Name": "Asana",
        "Symbol": "ASAN",
        "Type": "Equity",
        "Positive": [],
        "Negative": [],
    },
    {
        "Name": "Nano Dimension",
        "Symbol": "NNDM",
        "Type": "Equity",
        "Positive": [],
        "Negative": [],
    },
    {
        "Name": "Lockheed",
        "Symbol": "LMT",
        "Type": "Equity",
        "Positive": [],
        "Negative": [],
    },
    {
        "Name": "Lockheed",
        "Symbol": "LMT",
        "Type": "Equity",
        "Positive": [],
        "Negative": [],
    },
    {
        "Name": "Bitcoin",
        "Symbol": "BTC",
        "Type": "Cryptocurrencies",
        "Positive": [],
        "Negative": [],
    },

]

todo_list = ["https://en.wikipedia.org/wiki/Ronald_S._Baron"]


class Investment2021:
    def __init__(self):
        self.knowledge_graph_dict = knowledge_graph_dict


if __name__ == "__main__":
    print("Investment Jan. Plan")
