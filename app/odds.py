import trueskill
import itertools
import math
from pprint import pprint

# source: https://github.com/sublee/trueskill/issues/1#issuecomment-149762508
def win_probability(team1, team2):
    # assume: first player in team plays offense, first skill in player is offensive skill
    delta_mu  = team1[0][0].mu - team2[0][0].mu
    sum_sigma = sum(r.sigma ** 2 for r in [team1[0][0], team2[0][0]])
    if len(team1) > 1:
        delta_mu  += team1[1][1].mu
        sum_sigma += team1[1][1].sigma ** 2
    else:
        delta_mu  += team1[0][1].mu
        sum_sigma += team1[0][1].sigma ** 2
    if len(team2) > 1:
        delta_mu  -= team2[1][1].mu
        sum_sigma += team2[1][1].sigma ** 2
    else:
        delta_mu  -= team2[0][1].mu
        sum_sigma += team2[0][1].sigma ** 2

    #delta_mu = sum(r.mu for r in team1) - sum(r.mu for r in team2)
    #sum_sigma = sum(r.sigma ** 2 for r in itertools.chain(team1, team2))
    size = len(team1) + len(team2)
    denom = math.sqrt(size * (trueskill.BETA * trueskill.BETA) + sum_sigma)
    ts = trueskill.global_env()
    return ts.cdf(delta_mu / denom)

odds_texts = [
            ("0:1", 0 / (0 + 1)),
            ("1:20", 1 / (1 + 20)),
            ("1:12", 1 / (1 + 12)),
            ("1:8", 1 / (1 + 8)),
            ("1:6", 1 / (1 + 6)),
            ("1:5", 1 / (1 + 5)),
            ("1:4", 1 / (1 + 4)),
            ("1:3", 1 / (1 + 3)),
            ("2:5", 2 / (2 + 5)),
            ("1:2", 1 / (1 + 2)),
            ("3:5", 3 / (3 + 5)),
            ("2:3", 2 / (2 + 3)),
            ("4:5", 4 / (4 + 5)),
            ("1:1", 1 / (1 + 1)),
            ("5:4", 5 / (5 + 4)),
            ("3:2", 3 / (3 + 2)),
            ("5:3", 5 / (5 + 3)),
            ("2:1", 2 / (2 + 1)),
            ("5:2", 5 / (5 + 2)),
            ("3:1", 3 / (3 + 1)),
            ("4:1", 4 / (4 + 1)),
            ("5:1", 5 / (5 + 1)),
            ("6:1", 6 / (6 + 1)),
            ("8:1", 8 / (8 + 1)),
            ("12:1", 12 / (12 + 1)),
            ("20:1", 20 / (20 + 1)),
            ("1:0", 1 / (1 + 0))]
