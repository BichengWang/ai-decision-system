import argparse


class KellyModel:
    def __init__(self, win_ratio=0.0, win_possible=0.0):
        self.win_ratio = win_ratio
        self.win_possible = win_possible
        self.optimal_investment_percentage = None
        
    def fit(self):
        result = (self.win_possible * self.win_ratio + self.win_possible - 1) / self.win_ratio
        self.optimal_investment_percentage = result
        return result


class KellyGeneralModel:
    # https://www.investopedia.com/articles/trading/04/091504.asp
    def __init__(self, win_possible=0.0, win_reward=0.0, target_reward=None, target_loss=0.0, current_price=1.0):
        self.win_possible = win_possible
        self.win_ratio = win_reward
        self.target_reward = target_reward - current_price
        self.target_loss = current_price - target_loss
        if target_reward:
            self.win_ratio = self.target_reward / self.target_loss
        self.optimal_investment_percentage = None

    def fit(self):
        result = (self.win_possible * self.win_ratio + self.win_possible - 1) / self.win_ratio
        self.optimal_investment_percentage = result

    def get_investment_ratio(self):
        if self.optimal_investment_percentage is None:
            self.fit()
        return self.optimal_investment_percentage


# -p 0.8 -r 2.0
# ratio = reward/loss
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('-p', '--win_possible', type=float, help='win possible')
#     parser.add_argument('-r', '--win_ratio', type=float, help='win ratio')
#     parser.add_argument('-t', '--target_reward', type=float, help='target reward')
#     parser.add_argument('-l', '--target_loss', type=float, help='target loss')
#     parser.add_argument('-c', '--current_price', type=float, help='current price')
#     args_dict = vars(parser.parse_args())
#     print(args_dict)
#     print("best investment ratio: %.3f" % KellyGeneralModel(**args_dict).get_investment_ratio())
