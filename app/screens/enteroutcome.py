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
        self.winButton1 = LcarsButton2(colours.ORANGE,   (328,452), (188, 92), "", partial(self.winHandler, 0))
        self.winButton2 = LcarsButton2(colours.ORANGE,   (520,452), (188, 92), "", partial(self.winHandler, 1))
        all_sprites.add(self.winButton1, layer=1)
        all_sprites.add(self.winButton2, layer=1)
        self.saveButton = LcarsButton2(colours.ORANGE,   (856,140), (164, 68), "Save Result", self.saveHandler)
        self.saveButton.setEnabled(False)
        all_sprites.add(self.saveButton, layer=1)
        
        # fixed text:
        all_sprites.add(LcarsText(colours.BLACK, pos(328, 416), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(520, 416), capwords(self.team2[0]), 20/19))
        if len(self.team1)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(328, 380), capwords(self.team1[1]), 20/19))
        if len(self.team2)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(520, 380), capwords(self.team2[1]), 20/19))


        all_sprites.add(LcarsText(colours.BLACK, pos(192, 140), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(192, 68), capwords(self.team2[0]), 20/19))
        if len(self.team2)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(192, 32), capwords(self.team2[1]), 20/19))
        if len(self.team1)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(192, 104), capwords(self.team1[1]), 20/19))

        all_sprites.add(LcarsText(colours.BLACK, pos(390, 497), "TEAM A", 25/19), layer=2)
        all_sprites.add(LcarsText(colours.BLACK, pos(400, 467), "WON  ", 25/19), layer=2)
        all_sprites.add(LcarsText(colours.BLACK, pos(582, 497), "TEAM B", 25/19), layer=2)
        all_sprites.add(LcarsText(colours.BLACK, pos(592, 467), "WON  ", 25/19), layer=2)

        # adjustable texts:
        xs = [384, 428, 532, 620, 664, 768]
        widths = [40, 100, 40, 40, 100, 40]
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
            self.textLabels[2][j].setText("{:d}".format(round(trueskill.expose(player))))
            
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
        
    def winHandler(self, team, item, event, clock):
        print("team {} won".format(team))

        self.winningteam = team
        # enable saving
        self.saveButton.setEnabled(True)
        #if team == 0:
        #    self.winButton1.setColor(colours.RED_BROWN)
        #    self.winButton2.setColor(colours.BEIGE)
        #else:
        #    self.winButton1.setColor(colours.BEIGE)
        #    self.winButton2.setColor(colours.RED_BROWN)

        # fill the columns with 'after' values
        players = shelve.open('playerdb')
        updated = dict(players.items()) # clone that does not write back

        # update scores:
        ranks = [1,1]
        ranks[team] = 0
        newratings = trueskill.rate([tuple((players[x] for x in self.team1)), tuple((players[x] for x in self.team2))], ranks=ranks)
        pprint(newratings)
        updated[self.team1[0]] = newratings[0][0]
        updated[self.team2[0]] = newratings[1][0]
        if len(self.team1) >= 2:
            updated[self.team1[1]] = newratings[0][1]
        if len(self.team2) >= 2:
            updated[self.team2[1]] = newratings[1][1]
        
        # update the text labels:
        for i in range(4):
            team = [self.team1, self.team2][math.floor(i/2)]
            if i%2 >= len(team):
                continue
            name = team[i%2]
            if name not in updated:
                continue
            player = updated[name]
            self.textLabels[3][i].setText(findRank(updated, name))
            self.textLabels[4][i].setText("{:.2f}/{:.2f}".format(player.mu, player.sigma))
            self.textLabels[5][i].setText("{:d}".format(round(trueskill.expose(player))))
            
        players.close()
        

    def saveHandler(self, item, event, clock):
        players = shelve.open('playerdb')

        # update scores:
        ranks = [1,1]
        ranks[self.winningteam] = 0
        newratings = trueskill.rate([tuple((players[x] for x in self.team1)), tuple((players[x] for x in self.team2))], ranks=ranks)
        players[self.team1[0]] = newratings[0][0]
        players[self.team2[0]] = newratings[1][0]
        if len(self.team1) >= 2:
            players[self.team1[1]] = newratings[0][1]
        if len(self.team2) >= 2:
            players[self.team2[1]] = newratings[1][1]
        
        players.close()

        # return to match screen:
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())
        
        
