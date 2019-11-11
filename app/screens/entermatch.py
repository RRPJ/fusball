from datetime import datetime
from functools import partial
import random
from string import capwords
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from datasources.network import get_ip_address_string
import shelve
from fuzzywuzzy import process
import trueskill
import math
import re
from pprint import pprint
import itertools
import time
from odds import win_probability, odds_texts



def pos(x,y):
    return (768-y-32+4, x+4)


class ScreenEnterMatch(LcarsScreen):

    def setup(self, all_sprites):

        # load the most recently used player layout
        recentplayers = shelve.open('recentplayers')
        if 'names' not in recentplayers:
            recentplayers['names'] = []
        recentplayers.close()
        
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_match.png"), layer=0)

        # large interface buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 708),
                                     (140, 40), "Back", self.backHandler), layer=1)
        self.startMatchButton = LcarsButton2(
            colours.ORANGE, (928, 528), (92, 60), "Start Match", self.startHandler)
        all_sprites.add(self.startMatchButton, layer=1)

        
        all_sprites.add(LcarsButton2(colours.BEIGE, (928, 392),
                                     (92, 32), "Auto", self.autoHandler))

        # the small buttons for rearranging players:
        all_sprites.add(LcarsButton2(colours.BEIGE, (244, 330), (32, 32),
                                     "bottomrow", glyph=True, handler=self.swapHandler, glyphoffset=(0, 5)))
        all_sprites.add(LcarsButton2(colours.BEIGE, (208, 330), (32, 32),
                                     "toprow", glyph=True, handler=self.swapHandler, glyphoffset=(0, -5)))
        all_sprites.add(LcarsButton2(colours.BLUE, (172, 330),
                                     (32, 32), "diag1", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BLUE, (136, 330),
                                     (32, 32), "diag2", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (100, 330), (32, 32),
                                     "rotateleft", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (64, 330), (32, 32),
                                     "rotateright", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (280, 330), (32, 32),
                                     "leftcol", glyph=True, glyphoffset=(-5,0), handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (316, 330), (32, 32),
                                     "rightcol", glyph=True, glyphoffset=(5,0), handler=self.swapHandler))

        # add a keyboard:
        all_sprites.add(LcarsKeyboard((572, 280), self.keyboardHandler))
        # add a clear input button
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (616, 216),
                                     (28, 28), "clear", glyph=True, handler=self.keyboardHandler))
        # add the text already input
        self.searchText = LcarsText(
            colours.WHITE, (768 - 216 - 26, 284), "", 20 / 19)
        all_sprites.add(self.searchText)
        # add the placeholder text
        self.placeholder = LcarsText(
            (127, 127, 127), (768 - 216 - 26, 292), "Search by name...", 20 / 19)
        all_sprites.add(self.placeholder)
        # add a carret:
        self.carret = LcarsButton2(colours.WHITE, (284, 216), (4, 28), "")
        all_sprites.add(self.carret)

        # add a text object for the odds:
        self.oddsText = LcarsText(
            colours.WHITE, pos(648, 336), "1:1", 20/19)
        all_sprites.add(self.oddsText)

        # placeholders for names:
        self.matchedNames = []
        for i in range(6):
            newbutton = LcarsButton2((127, 127, 127), (52, 200 - 36 * i),
                                     (188, 32), '', handler=partial(self.playerClicked, i))
            newbutton.addPlayer = False
            self.matchedNames.append(newbutton)
            all_sprites.add(newbutton)

        # texts for selected players
        #prefill = shelve.open('latestmatch')
        self.selectedPlayers = [
            LcarsText(colours.BLACK, (768-502-32+4, 216+4), '', 20/19, placeholder='Defense...', placeholdercolor=(120,60,60)),
            LcarsText(colours.BLACK, (768-430-32+4, 216+4), '', 20/19, placeholder='Offense...', placeholdercolor=(120,60,60)),
            LcarsText(colours.BLACK, (768-466-32+4, 600+4), '', 20/19, placeholder='Offense...', placeholdercolor=(97,118,142)),
            LcarsText(colours.BLACK, (768-394-32+4, 600+4), '', 20/19, placeholder='Defense...', placeholdercolor=(97,118,142))
        ]
        #prefill.close()
        #self.updateOdds()

        all_sprites.add(LcarsButton2(colours.RED_BROWN, (408, 502),
                                     (32, 32), "clear", glyph=True, handler=partial(self.clearSingleHandler, 0)))
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (408, 430),
                                     (32, 32), "clear", glyph=True, handler=partial(self.clearSingleHandler, 1)))
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (564, 466),
                                     (32, 32), "clear", glyph=True, handler=partial(self.clearSingleHandler, 2)))
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (564, 394),
                                     (32, 32), "clear", glyph=True, handler=partial(self.clearSingleHandler, 3)))
        
        
        all_sprites.add(self.selectedPlayers[0], layer=1)
        all_sprites.add(self.selectedPlayers[1], layer=1)
        all_sprites.add(self.selectedPlayers[2], layer=1)
        all_sprites.add(self.selectedPlayers[3], layer=1)

        # sprites for highlighting/playerfocus
        self.inputfocus = [
            LcarsInputFocus((768 - 502 - 32, 216), False, False,
                            handler=partial(self.inputFocusHandler, 0)),
            LcarsInputFocus((768 - 430 - 32, 216), False, True,
                            handler=partial(self.inputFocusHandler, 1)),
            LcarsInputFocus((768 - 466 - 32, 600), True, True,
                            handler=partial(self.inputFocusHandler, 2)),
            LcarsInputFocus((768 - 394 - 32, 600), True, True,
                            handler=partial(self.inputFocusHandler, 3))
        ]
        all_sprites.add(self.inputfocus[0], layer=2)
        all_sprites.add(self.inputfocus[1], layer=2)
        all_sprites.add(self.inputfocus[2], layer=2)
        all_sprites.add(self.inputfocus[3], layer=2)
        self.currentFocus = 0
        self.searchString = ""
        self.updatePlayerSelection()
        
        self.validate()
        self.searchString = ""

    def update(self, screenSurface, fpsClock):
        # if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
        #    self.stardate.setText(datetime.now().strftime("%d%m.%y %H:%M:%S"))
        #    self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)

    def validate(self):
        p0 = self.selectedPlayers[0].message.lower()
        p1 = self.selectedPlayers[1].message.lower()
        p2 = self.selectedPlayers[2].message.lower()
        p3 = self.selectedPlayers[3].message.lower()
        
        team1 = set()  # makes unique
        team2 = set()
        if p0 != '':
            team1.add(p0)
        if p1 != '':
            team1.add(p1)
        if p2 != '':
            team2.add(p2)
        if p3 != '':
            team2.add(p3)
        if (len(team1) == len(team2) and
            len(team1) >= 1 and
            len(team1) <= 2 and
                len(team1.intersection(team2)) == 0):

            self.startMatchButton.setEnabled(True)
        else:
            self.startMatchButton.setEnabled(False)

    def handleEvents(self, event, fpsClock):
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            # self.beep1.play()
            pass

        if event.type == pygame.MOUSEBUTTONUP:
            return False

        if event.type == pygame.USEREVENT:
            with shelve.open('tagdb') as tagdb:
                if event.tagid in tagdb:
                    tagname = tagdb[event.tagid]
                    print('key presented for: ', tagname)
                    with shelve.open("playerdb") as playerdb:
                        if tagname not in playerdb:
                            print('player does not exist!')
                            return
                    
                    for i in range(4):
                        if self.selectedPlayers[i].message == capwords(tagname):
                            self.selectedPlayers[i].setText('')
                    self.selectedPlayers[self.currentFocus].setText(capwords(tagname))
                    self.updatePlayerSelection()
            
                    # rotate focus
                    self.currentFocus = (self.currentFocus + 1) % 4
                    for i in range(4):
                        self.inputfocus[i].setTransparent(i != self.currentFocus)
                    self.updateOdds()
                    self.validate()
                else:
                    print('tag ', event.tagid, ' not registered')
            

    def inputFocusHandler(self, which, item, event, clock):
        print("input focus on {}".format(which))
        self.currentFocus = which
        for i in range(4):
            self.inputfocus[i].setTransparent(i != which)

    def updateOdds(self):
        p0 = self.selectedPlayers[0].message.lower()
        p1 = self.selectedPlayers[1].message.lower()
        p2 = self.selectedPlayers[2].message.lower()
        p3 = self.selectedPlayers[3].message.lower()
        team1 = []
        team2 = []
        players = shelve.open('playerdb')
        # offense first, defense second (1 and 2 are offense)
        if p1 in players:
            team1.append(players[p1])
        if p0 in players:
            team1.append(players[p0])
        if p2 in players:
            team2.append(players[p2])
        if p3 in players:
            team2.append(players[p3])
        players.close()
        p = 0.5
        if len(team1) > 0 and len(team2) > 0:
            p = win_probability(team1, team2)
        print("win probability: {}%".format(p * 100))

        ratio = sorted(odds_texts, key=lambda x: abs(x[1] - p))[0][0]
        print("selected ratio: {}".format(ratio))
        self.oddsText.setText(ratio)

    def resetPlayerInput(self):
        self.searchString = ""
        self.placeholder.visible = True
        self.searchText.setText(capwords("", " "))
        self.carret.rect.left = 284
        self.updatePlayerSelection()



    def uniq_list(self, inp):
        out = []
        for x in inp:
            if x not in out:
                out.append(x)
        return out
        

    def playerClicked(self, index, item, event, clock):
        print("player {} clicked: {}".format(index, item.text))
        name = item.text
        if item.addPlayer:
            item.addPlayer = False # clear add field
            name = self.searchString
            print("adding")
            with open('logfile.log', 'a') as log:
                log.write("{}: new player created '{}'\n".format(
                    time.strftime("%Y-%m-%d %H:%M:%S"), self.searchString))
            players = shelve.open("playerdb")
            players[self.searchString] = (trueskill.Rating(), trueskill.Rating())
            players.close()
            #self.updatePlayerSelection()
        
        print("choosing")
        self.selectedPlayers[self.currentFocus].setText(capwords(name))
        recentplayers = shelve.open('recentplayers')
        newnames = self.uniq_list([name.lower()] + recentplayers['names'])
        recentplayers['names'] = newnames
        recentplayers.close()
        self.updatePlayerSelection()
            
        # rotate focus
        self.currentFocus = (self.currentFocus + 1) % 4
        for i in range(4):
            self.inputfocus[i].setTransparent(i != self.currentFocus)
        self.updateOdds()
        self.validate()

        # clear player input field after clicking player
        self.resetPlayerInput()

    def updatePlayerSelection(self):
        players = shelve.open('playerdb')
        recentplayers = shelve.open('recentplayers')['names']
        candidates = []
        if len(players) > 0:
            candidates = process.extractBests(
                self.searchString, players.keys(), score_cutoff=50, limit=6)
        players.close()
        # remove candicates from recent to prevent double listing
        for c in candidates:
            print('c[0]:', c[0])
            if c[0] in recentplayers:
                recentplayers.remove(c[0])

        # remove already selected players
        for i in range(4):
            p = self.selectedPlayers[i].message.lower()
            # recent players is easy
            if p in recentplayers:
                recentplayers.remove(p)
            # candidates are harder because they are tuples
            candidates = [c for c in candidates if c[0] != p]
                
        # remove already chosen players from suggestions
        for i in range(4):
            s = self.selectedPlayers[i].message.lower()
            if s in recentplayers:
                recentplayers.remove(s)
        print('recentplayers: ', recentplayers)
        print('candidates: ', candidates)
        
        
        for i in range(6):
            print('i: ', i)
            # skip the add player button
            if self.matchedNames[i].addPlayer:
                continue
            if i >= len(candidates):
                # fill up remaining fields with recent selections:
                if i-len(candidates) < len(recentplayers):
                    self.matchedNames[i].setText(capwords(recentplayers[i-len(candidates)]))
                    self.matchedNames[i].setColor(colours.BEIGE, colours.WHITE)
                else:
                    # keep empty if there are none
                    self.matchedNames[i].setText('')
                    self.matchedNames[i].setColor((127,127,127), (127,127,127))
            else:
                # add fields
                print(candidates[i])
                self.matchedNames[i].setText(capwords(candidates[i][0]))
                self.matchedNames[i].setColor(colours.BEIGE, colours.WHITE)

    def keyboardHandler(self, item, event, clock):
        print("keyboard event forwarded to match screen: {}".format(event))
        # update the input field with the new text:
        if type(event) == str:
            if event == 'bkspc':
                match = re.search('0x[0-9][0-9]$', self.searchString)
                if match != None:
                    self.searchString = self.searchString[:-
                                                          4] + chr(int(match.group(), 16))
                else:
                    self.searchString = self.searchString[:-1]
            elif event == 'enter':
                # todo: figure out what this does
                pass
            else:
                self.searchString = self.searchString + event
        else:
            if item.text == "clear":
                self.searchString = ""

        players = shelve.open('playerdb')
        if self.searchString not in players.keys() and len(self.searchString.strip()) > 3:
            self.matchedNames[-1].setText("Add " + capwords(self.searchString))
            self.matchedNames[-1].setColor(colours.RED_BROWN)
            self.matchedNames[-1].addPlayer = True
        else:
            self.matchedNames[-1].addPlayer = False
        players.close()

        # update list of selectable players
        self.updatePlayerSelection()

        # reset player input field
        self.placeholder.visible = len(self.searchString) == 0
        self.searchText.setText(capwords(self.searchString, " "))
        self.carret.rect.left = 284 + self.searchText.image.get_size()[0]

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

    def startHandler(self, item, event, clock):
        from screens.enteroutcome import ScreenEnterOutcome
        p0 = self.selectedPlayers[0].message.lower()
        p1 = self.selectedPlayers[1].message.lower()
        p2 = self.selectedPlayers[2].message.lower()
        p3 = self.selectedPlayers[3].message.lower()
        team1 = []
        team2 = []
        # because of the input validator it is already impossible that there are 2 identical players
        if p1 != '':
            team1.append(p1)
        if p0 != '':
            team1.append(p0)
        if p2 != '':
            team2.append(p2)
        if p3 != '':
            team2.append(p3)
        self.loadScreen(ScreenEnterOutcome(team1, team2))
        print("starting match")

    def clearSingleHandler(self, index, item, event, clock):
        self.selectedPlayers[index].setText('')
        self.validate()
        self.updatePlayerSelection()
        self.updateOdds()
        
    def swapHandler(self, item, event, clock):
        print("swapping " + item.text)
        if item.text == 'clear':
            self.selectedPlayers[0].setText('')
            self.selectedPlayers[1].setText('')
            self.selectedPlayers[2].setText('')
            self.selectedPlayers[3].setText('')
            self.validate()
        if item.text == 'rotateright':
            tmp = self.selectedPlayers[0].message
            self.selectedPlayers[0].setText(self.selectedPlayers[1].message)
            self.selectedPlayers[1].setText(self.selectedPlayers[3].message)
            self.selectedPlayers[3].setText(self.selectedPlayers[2].message)
            self.selectedPlayers[2].setText(tmp)
        if item.text == 'rotateleft':
            tmp = self.selectedPlayers[0].message
            self.selectedPlayers[0].setText(self.selectedPlayers[2].message)
            self.selectedPlayers[2].setText(self.selectedPlayers[3].message)
            self.selectedPlayers[3].setText(self.selectedPlayers[1].message)
            self.selectedPlayers[1].setText(tmp)
        if item.text == 'diag1':
            tmp = self.selectedPlayers[0].message
            self.selectedPlayers[0].setText(self.selectedPlayers[3].message)
            self.selectedPlayers[3].setText(tmp)
        if item.text == 'diag2':
            tmp = self.selectedPlayers[1].message
            self.selectedPlayers[1].setText(self.selectedPlayers[2].message)
            self.selectedPlayers[2].setText(tmp)
        if item.text == 'toprow':
            tmp = self.selectedPlayers[0].message
            self.selectedPlayers[0].setText(self.selectedPlayers[2].message)
            self.selectedPlayers[2].setText(tmp)
        if item.text == 'bottomrow':
            tmp = self.selectedPlayers[1].message
            self.selectedPlayers[1].setText(self.selectedPlayers[3].message)
            self.selectedPlayers[3].setText(tmp)
        if item.text == 'leftcol':
            tmp = self.selectedPlayers[0].message
            self.selectedPlayers[0].setText(self.selectedPlayers[1].message)
            self.selectedPlayers[1].setText(tmp)
        if item.text == 'rightcol':
            tmp = self.selectedPlayers[2].message
            self.selectedPlayers[2].setText(self.selectedPlayers[3].message)
            self.selectedPlayers[3].setText(tmp)
        self.updateOdds()

    def autoHandler(self, item, event, clock):
        # there are really only 3 combinations that teams can be assigned
        # there are 4 combinations of offense/defense for each.
        p0 = self.selectedPlayers[0].message.lower() # defense team A
        p1 = self.selectedPlayers[1].message.lower() # offense team A
        p2 = self.selectedPlayers[2].message.lower() # offense team B
        p3 = self.selectedPlayers[3].message.lower() # defense team B
            
        players = shelve.open('playerdb')
        if p0 not in players or p1 not in players or p2 not in players or p3 not in players:
            # nothing to do
            return
        match1a = [(players[p0][0], players[p1][1]), (players[p2][0], players[p3][1])]
        match1b = [(players[p0][0], players[p1][1]), (players[p3][0], players[p2][1])]
        match1c = [(players[p1][0], players[p0][1]), (players[p2][0], players[p3][1])]
        match1d = [(players[p1][0], players[p0][1]), (players[p3][0], players[p2][1])]
        match2a = [(players[p0][0], players[p2][1]), (players[p1][0], players[p3][1])]
        match2b = [(players[p0][0], players[p2][1]), (players[p3][0], players[p1][1])]
        match2c = [(players[p2][0], players[p0][1]), (players[p1][0], players[p3][1])]
        match2d = [(players[p2][0], players[p0][1]), (players[p3][0], players[p1][1])]
        match3a = [(players[p0][0], players[p3][1]), (players[p1][0], players[p2][1])]
        match3b = [(players[p0][0], players[p3][1]), (players[p2][0], players[p1][1])]
        match3c = [(players[p3][0], players[p0][1]), (players[p1][0], players[p2][1])]
        match3d = [(players[p3][0], players[p0][1]), (players[p2][0], players[p1][1])]
        q1a = trueskill.quality(match1a)
        q1b = trueskill.quality(match1b)
        q1c = trueskill.quality(match1c)
        q1d = trueskill.quality(match1d)
        q2a = trueskill.quality(match2a)
        q2b = trueskill.quality(match2b)
        q2c = trueskill.quality(match2c)
        q2d = trueskill.quality(match2d)
        q3a = trueskill.quality(match3a)
        q3b = trueskill.quality(match3b)
        q3c = trueskill.quality(match3c)
        q3d = trueskill.quality(match3d)
        #match = None
        maxscore = max(q1a,q1b,q1c,q1d, q2a,q2b,q2c,q2d,q3a,q3b,q3c,q3d)
        names = [p1,p0,p2,p3] if q1a==maxscore else (
            [p1,p0,p3,p2] if q1b==maxscore else (
            [p0,p1,p2,p3] if q1c==maxscore else (
            [p0,p1,p3,p2] if q1d==maxscore else (
            [p2,p0,p1,p3] if q2a==maxscore else (
            [p2,p0,p3,p1] if q2b==maxscore else (
            [p0,p2,p1,p3] if q2c==maxscore else (
            [p0,p2,p3,p1] if q2d==maxscore else (
            [p3,p0,p1,p2] if q3a==maxscore else (
            [p3,p0,p2,p1] if q3b==maxscore else (
            [p0,p3,p1,p2] if q3c==maxscore else (
            [p0,p3,p2,p1] )))))))))))
        self.selectedPlayers[0].setText(capwords(names[0]))
        self.selectedPlayers[1].setText(capwords(names[1]))
        self.selectedPlayers[2].setText(capwords(names[2]))
        self.selectedPlayers[3].setText(capwords(names[3]))
        players.close()

        self.updateOdds()
    
