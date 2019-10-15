from string import capwords
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
import shelve
from string import capwords
from functools import partial
from pprint import pprint
import math
import trueskill
import time
from odds import win_probability, odds_texts

def pos(x,y):
    return (768-y-32+4, x+4)

def findRank(players, player):
    ranked = sorted(players.items(), key=lambda kv:trueskill.expose(kv[1]), reverse=True)
    minindex = len(ranked)
    maxindex = 0
    i = 1
    for name,skill in ranked:
        if round(trueskill.expose(players[player])) == round(trueskill.expose(skill)): # since we only display rounded skill it is only fair to group by whole numbers
            minindex = min(minindex, i)
            maxindex = max(maxindex, i)
        i += 1
    if minindex==maxindex:
        return "{}".format(minindex)
    else:
        return "{}-{}".format(minindex,maxindex)
        

class ScreenEnterOutcome(LcarsScreen):
    def __init__(self, team1, team2):
        self.team1 = list(team1)
        self.team2 = list(team2)
        super().__init__()
        
    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars-kickers-resultscreen.png"), layer=0)

        print("drawing labels: {} against {}".format(self.team1, self.team2))


        # buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4,708), (140, 40), "Cancel", self.cancelHandler), layer=1)
        self.scorebuttons1 = []
        self.scorebuttons2 = []
        for i in range(1,6):
            b1 = LcarsButton2((127,127,127), (400,372+36*i), (96,32), str(i), partial(self.scoreHandler, 0, i))
            b2 = LcarsButton2((127,127,127), (500,372+36*i), (96,32), str(i), partial(self.scoreHandler, 1, i))
            self.scorebuttons1.append(b1)
            self.scorebuttons2.append(b2)
            all_sprites.add(b1, layer=1)
            all_sprites.add(b2, layer=1)
            
        self.saveButton = LcarsButton2(colours.ORANGE,   (740,520), (120, 68), "Save Result", self.saveHandler)
        self.saveButton.setEnabled(False)
        all_sprites.add(self.saveButton, layer=1)
        
        # fixed text:
        all_sprites.add(LcarsText(colours.BLACK, pos(316, 372), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(508, 372), capwords(self.team2[0]), 20/19))
        if len(self.team1)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(316, 336), capwords(self.team1[1]), 20/19))
        if len(self.team2)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(508, 336), capwords(self.team2[1]), 20/19))


        all_sprites.add(LcarsText(colours.BLACK, pos(200, 140), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(200, 68), capwords(self.team2[0]), 20/19))
        if len(self.team2) > 1:
            all_sprites.add(LcarsText(colours.BLACK, pos(200, 32), capwords(self.team2[1]), 20/19))
        if len(self.team1) > 1:
            all_sprites.add(LcarsText(colours.BLACK, pos(200, 104), capwords(self.team1[1]), 20/19))

        # game odds
        # add a text object for the odds:
        team1ratings = []
        team2ratings = []
        players = shelve.open('playerdb')
        team1ratings.append(players[self.team1[0]])
        team2ratings.append(players[self.team2[0]])
        if len(self.team1) > 1:
            team1ratings.append(players[self.team1[1]])
        if len(self.team2) > 1:
            team2ratings.append(players[self.team2[1]])
        players.close()
        p = win_probability(team1ratings, team2ratings)
        print("win probability: {}%".format(p * 100))

        ratio = sorted(odds_texts, key=lambda x: abs(x[1] - p))[0][0]
        print("selected ratio: {}".format(ratio))
        all_sprites.add(LcarsText(colours.BLACK, pos(160, 480), str(ratio.split(':')[0]), 20/19, alignright=True))
        all_sprites.add(LcarsText(colours.BLACK, pos(180, 480), str(ratio.split(':')[1]), 20/19))

        # add placeholders for likelihood
        self.lhtext1 = LcarsText(colours.BLACK, pos(160, 408), '', 20/19, alignright=True)
        self.lhtext2 = LcarsText(colours.BLACK, pos(180, 408), '', 20/19)
        all_sprites.add(self.lhtext1)
        all_sprites.add(self.lhtext2)
        
            
        # adjustable texts:
        xs = [384, 428, 532, 636, 724, 768, 872, 976]
        widths = [40, 100, 100, 40, 40, 100, 100, 40]
        ys = [140, 104, 68, 32]

        self.textLabels = [[None for y in ys] for x in xs]
        
        # now accessible as self.textLabels[x][y]
        for i,x in enumerate(xs):
            for j,y in enumerate(ys):
                self.textLabels[i][j] = LcarsText(colours.BLACK, pos(x,y), "?", 20/19)
                all_sprites.add(self.textLabels[i][j])

        # prefill the labels with 'before' values
        players = shelve.open('playerdb')
        for j,y in enumerate(ys):
            team = [self.team1, self.team2][math.floor(j/2)]
            if j%2 >= len(team):
                continue
            name = team[j%2]
            if name not in players:
                continue
            player = players[name]
            self.textLabels[0][j].setText(findRank(players, name))
            self.textLabels[1][j].setText("{:.2f}/{:.2f}".format(player.mu, player.sigma))
            self.textLabels[2][j].setText("{:.2f}/{:.2f}".format(player.mu, player.sigma))
            self.textLabels[3][j].setText("{:d}".format(round(trueskill.expose(player))))
            
            
        players.close()
        
        
        

    def update(self, screenSurface, clock):
        LcarsScreen.update(self, screenSurface, clock)

    def handleEvents(self, event, clock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            #self.beep1.play()
            pass
        if event.type == pygame.MOUSEBUTTONUP:
            return False

    def cancelHandler(self, item, event, clock):
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())

    def scoreHandler(self, team, score, item, event, clock):
        # enable save button
        self.saveButton.setEnabled(True)
        # highlight score
        self.team1score = score if team==0 else 5-score
        self.team2score = score if team==1 else 5-score
        for i in range(1,6):
            self.scorebuttons1[i-1].setColor(colours.RED_BROWN if i<= self.team1score else (127,127,127))
            self.scorebuttons2[i-1].setColor(colours.BLUE      if i<= self.team2score else (127,127,127))
        

        players = shelve.open('playerdb')
        
        newratings = [tuple((players[x] for x in self.team1)), tuple((players[x] for x in self.team2))]
        numdraws = 2 * min(self.team1score, self.team2score)
        numwins = 5 - numdraws
        for i in range(numdraws):
            newratings = trueskill.rate(newratings, ranks=[1,1])
            print(newratings)
        for i in range(numwins):
            newratings = trueskill.rate(newratings, ranks=[0,1] if self.team1score > self.team2score else [1,0])
            print(newratings)
        

        updated = dict(players.items()) # clone that does not write back
        updated[self.team1[0]] = newratings[0][0]
        updated[self.team2[0]] = newratings[1][0]
        if len(self.team1)>1:
            updated[self.team1[1]] = newratings[0][1]
            updated[self.team2[1]] = newratings[1][1]

        self.ratingupdate = newratings
        for i in range(4):
            team = [self.team1, self.team2][math.floor(i/2)]
            if i%2 >= len(team):
                continue
            name = team[i%2]
            player = updated[name]
            self.textLabels[4][i].setText(findRank(updated, name))
            self.textLabels[5][i].setText("{:.2f}/{:.2f}".format(player.mu, player.sigma))
            self.textLabels[6][i].setText("{:.2f}/{:.2f}".format(player.mu, player.sigma))
            self.textLabels[7][i].setText("{:d}".format(round(trueskill.expose(player))))
            
        players.close()
        

    def saveHandler(self, item, event, clock):
        players = shelve.open('playerdb')

        winningteam = self.team1 if self.team1score > self.team2score else self.team2
        with open('logfile.log', 'a') as log:
            log.write("{}: match played between {} and {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), self.team1, self.team2))
            log.write("                   : won by {}\n".format(winningteam))
            log.write("                   : skill before: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]].mu, players[self.team1[0]].sigma))
            log.write("                   : skill before: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]].mu, players[self.team2[0]].sigma))
            if len(self.team1)>=2:
                log.write("                   : skill before: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]].mu, players[self.team1[1]].sigma))
            if len(self.team2)>=2:
                log.write("                   : skill before: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]].mu, players[self.team2[1]].sigma))

            #self.updatedskills
            players[self.team1[0]] = self.ratingupdate[0][0]
            players[self.team2[0]] = self.ratingupdate[1][0]
            if len(self.team1) >= 2:
                players[self.team1[1]] = self.ratingupdate[0][1]
                if len(self.team2) >= 2:
                    players[self.team2[1]] = self.ratingupdate[1][1]
        
            log.write("                   : skill after: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]].mu, players[self.team1[0]].sigma))
            log.write("                   : skill after: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]].mu, players[self.team2[0]].sigma))
            if len(self.team1)>=2:
                log.write("                   : skill after: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]].mu, players[self.team1[1]].sigma))
            if len(self.team2)>=2:
                log.write("                   : skill after: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]].mu, players[self.team2[1]].sigma))
            
        players.close()
        # return to match screen:
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())
        
        
