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
from odds import win_probability, odds_texts, findRank, playerLevel

def pos(x,y):
    return (768-y-32+4, x+4)


class ScreenEnterOutcome(LcarsScreen):
    def __init__(self, team1, team2):
        self.team1 = list(team1)
        self.team2 = list(team2)
        self.team1score = None
        self.team2score = None
        super().__init__()
        
    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars-kickers-resultscreen.png"), layer=0)

        print("drawing labels: {} against {}".format(self.team1, self.team2))


        # buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4,708), (140, 40), "Cancel", self.cancelHandler), layer=1)
        self.scorebuttons1 = []
        self.scorebuttons2 = []
        for i in range(6):
            b1 = LcarsButton2((127,127,127), (400,388+36*i), (96,32), str(i), partial(self.scoreHandler, 0, i))
            b2 = LcarsButton2((127,127,127), (500,388+36*i), (96,32), str(i), partial(self.scoreHandler, 1, i))
            self.scorebuttons1.append(b1)
            self.scorebuttons2.append(b2)
            all_sprites.add(b1, layer=1)
            all_sprites.add(b2, layer=1)
            
        self.saveButton = LcarsButton2(colours.ORANGE,   (740,520), (120, 68), "Save Result", self.saveHandler)
        self.saveButton.setEnabled(False)
        all_sprites.add(self.saveButton, layer=1)
        
        # fixed text:
        all_sprites.add(LcarsText(colours.BLACK, pos(316, 352), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(508, 352), capwords(self.team2[0]), 20/19))
        if len(self.team1)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(316, 316), capwords(self.team1[1]), 20/19))
        if len(self.team2)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(508, 316), capwords(self.team2[1]), 20/19))


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
        all_sprites.add(LcarsText(colours.BLACK, pos(160, 460), str(ratio.split(':')[0]), 20/19, alignright=True))
        all_sprites.add(LcarsText(colours.BLACK, pos(180, 460), str(ratio.split(':')[1]), 20/19))

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
            self.textLabels[1][j].setText("{:.2f}/{:.2f}".format(player[0].mu, player[0].sigma))
            self.textLabels[2][j].setText("{:.2f}/{:.2f}".format(player[1].mu, player[1].sigma))
            self.textLabels[3][j].setText("{:d}".format(round(playerLevel(player))))
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
        #self.saveButton.setEnabled(True)
        # highlight score
        if team==0:
            self.team1score = score
            for i in range(6):
                self.scorebuttons1[i].setColor(colours.RED_BROWN if i<= self.team1score else (127,127,127))
        else:
            self.team2score = score
            for i in range(6):
                self.scorebuttons2[i].setColor(colours.BLUE      if i<= self.team2score else (127,127,127))
        

        
        if self.team1score != None and self.team2score != None:
            minscore = min(self.team1score, self.team2score)
            maxscore = max(self.team1score, self.team2score)
            self.saveButton.setEnabled(maxscore==5 and minscore!=5)
            players = shelve.open('playerdb')
        
            #newratings = [tuple((players[x] for x in self.team1)), tuple((players[x] for x in self.team2))]
            # start with offensive players
            newratings = [[players[self.team1[0]][0]], [players[self.team2[0]][0]]]
            # depending on 1v1 or 2v2 add the other or the same as defense
            if len(self.team1) > 1:
                newratings[0].append(players[self.team1[1]][1])
            else:
                newratings[0].append(players[self.team1[0]][1])
            if len(self.team2) > 1:
                newratings[1].append(players[self.team2[1]][1])
            else:
                newratings[1].append(players[self.team2[0]][1])
            newratings[0] = tuple(newratings[0])
            newratings[1] = tuple(newratings[1])
            print('initial ratings: ', newratings)

            numdraws = minscore
            numwins = maxscore - minscore
            for i in range(numdraws):
                newratings = trueskill.rate(newratings, ranks=[1,1])
                print(newratings)
            for i in range(numwins):
                newratings = trueskill.rate(newratings, ranks=[0,1] if self.team1score > self.team2score else [1,0])
            print(newratings)
            

            updated = dict(players.items()) # clone that does not write back
            updated[self.team1[0]] = (newratings[0][0], updated[self.team1[0]][1])
            updated[self.team2[0]] = (newratings[1][0], updated[self.team2[0]][1])
            if len(self.team1)>1:
                updated[self.team1[1]] = (updated[self.team1[1]][0], newratings[0][1])
            else:
                updated[self.team1[0]] = (updated[self.team1[0]][0], newratings[0][1])
            if len(self.team2)>1:
                updated[self.team2[1]] = (updated[self.team2[1]][0], newratings[1][1])
            else:
                updated[self.team2[0]] = (updated[self.team2[0]][0], newratings[1][1])

            self.ratingupdate = updated
            for i in range(4):
                team = [self.team1, self.team2][math.floor(i/2)]
                if i%2 >= len(team):
                    continue
                name = team[i%2]
                player = updated[name]
                self.textLabels[4][i].setText(findRank(updated, name))
                self.textLabels[5][i].setText("{:.2f}/{:.2f}".format(player[0].mu, player[0].sigma))
                self.textLabels[6][i].setText("{:.2f}/{:.2f}".format(player[1].mu, player[1].sigma))
                self.textLabels[7][i].setText("{:d}".format(round(playerLevel(player))))
            
            players.close()
        

    def saveHandler(self, item, event, clock):
        players = shelve.open('playerdb')

        winningteam = self.team1 if self.team1score > self.team2score else self.team2
        with open('logfile.log', 'a') as log:
            log.write("{}: match played between {} and {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), self.team1, self.team2))
            log.write("                   : won by {}\n".format(winningteam))
            log.write("                   : offensive skill before: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]][0].mu, players[self.team1[0]][0].sigma))
            log.write("                   : defensive skill before: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]][1].mu, players[self.team1[0]][1].sigma))
            log.write("                   : offensive skill before: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]][0].mu, players[self.team2[0]][0].sigma))
            log.write("                   : defensive skill before: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]][1].mu, players[self.team2[0]][1].sigma))
            if len(self.team1)>=2:
                log.write("                   : offensive skill before: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]][0].mu, players[self.team1[1]][0].sigma))
                log.write("                   : defensive skill before: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]][1].mu, players[self.team1[1]][1].sigma))
            if len(self.team2)>=2:
                log.write("                   : offensive skill before: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]][0].mu, players[self.team2[1]][0].sigma))
                log.write("                   : defensive skill before: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]][1].mu, players[self.team2[1]][1].sigma))

            #self.updatedskills
            # update offensive skills
            players[self.team1[0]] = self.ratingupdate[self.team1[0]]
            players[self.team2[0]] = self.ratingupdate[self.team2[0]]
            if len(self.team1) >= 2:
                players[self.team1[1]] = self.ratingupdate[self.team1[1]]
            if len(self.team2) >= 2:
                players[self.team2[1]] = self.ratingupdate[self.team2[1]]

            log.write("                   : offensive skill after: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]][0].mu, players[self.team1[0]][0].sigma))
            log.write("                   : defensive skill after: {}: {}/{}\n".format(self.team1[0], players[self.team1[0]][1].mu, players[self.team1[0]][1].sigma))
            log.write("                   : offensive skill after: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]][0].mu, players[self.team2[0]][0].sigma))
            log.write("                   : defensive skill after: {}: {}/{}\n".format(self.team2[0], players[self.team2[0]][1].mu, players[self.team2[0]][1].sigma))
            if len(self.team1)>=2:
                log.write("                   : offensive skill after: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]][0].mu, players[self.team1[1]][0].sigma))
                log.write("                   : defensive skill after: {}: {}/{}\n".format(self.team1[1], players[self.team1[1]][1].mu, players[self.team1[1]][1].sigma))
            if len(self.team2)>=2:
                log.write("                   : offensive skill after: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]][0].mu, players[self.team2[1]][0].sigma))
                log.write("                   : defensive skill after: {}: {}/{}\n".format(self.team2[1], players[self.team2[1]][1].mu, players[self.team2[1]][1].sigma))

                    
        players.close()
        # return to match screen:
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())
        
        
