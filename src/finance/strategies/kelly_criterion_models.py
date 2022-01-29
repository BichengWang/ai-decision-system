import argparse


class KellyGeneralModel(object):
    def __init__(self, win_possible=0.0, win_reward=0.0):
        self.win_possible = win_possible
        self.win_reward = win_reward
        self.optimal_investment_percentage = None

    def fit(self):
        result = (self.win_possible * self.win_reward + self.win_possible - 1) / self.win_reward
        self.optimal_investment_percentage = result

    def get_investment_ratio(self):
        if self.optimal_investment_percentage is None:
            self.fit()
        return self.optimal_investment_percentage


parser = argparse.ArgumentParser()
parser.add_argument('-p', '--win_possible', type=float, help='win possible')
parser.add_argument('-r', '--win_reward', type=float, help='win gain')
args_dict = vars(parser.parse_args())
print(args_dict)
print("best investment ratio: %.3f" % KellyGeneralModel(**args_dict).get_investment_ratio())

