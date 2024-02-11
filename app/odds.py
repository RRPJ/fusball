import trueskill
import itertools
import math
from pprint import pprint

# Compute win probability between two teams
def win_probability(team1, team2):
    # Assume: first player in team plays offense, first skill in player is offensive skill
    delta_mu  = team1[0][0].mu - team2[0][0].mu
    sum_sigma = sum(r.sigma ** 2 for r in [team1[0][0], team2[0][0]])
    
    # Adjust delta_mu and sum_sigma based on team composition
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

    # Calculate win probability using TrueSkill algorithm
    size = len(team1) + len(team2)
    denom = math.sqrt(size * (trueskill.BETA * trueskill.BETA) + sum_sigma)
    ts = trueskill.global_env()
    return ts.cdf(delta_mu / denom)

# Pre-defined odds texts and corresponding probabilities
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
    ("1:0", 1 / (1 + 0))
]

# Compute player level based on TrueSkill ratings
def playerLevel(player):
    return trueskill.expose(player[0]) + trueskill.expose(player[1])

# Find rank of a player among others
def findRank(players, player):
    ranked = sorted(players.items(), key=lambda kv:playerLevel(kv[1]), reverse=True)
    minindex = len(ranked)
    maxindex = 0
    i = 1
    for name,skill in ranked:
        # Group players by whole numbers since only rounded skill is displayed
        if round(playerLevel(players[player])) == round(playerLevel(skill)):
            minindex = min(minindex, i)
            maxindex = max(maxindex, i)
        i += 1
    if minindex == maxindex:
        return "{}".format(minindex)
    else:
        return "{}-{}".format(minindex, maxindex)
