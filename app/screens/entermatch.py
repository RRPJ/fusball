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
import itertools

# source: https://github.com/sublee/trueskill/issues/1#issuecomment-149762508
def win_probability(team1, team2):
    delta_mu = sum(r.mu for r in team1) - sum(r.mu for r in team2)
    sum_sigma = sum(r.sigma ** 2 for r in itertools.chain(team1, team2))
    size = len(team1) + len(team2)
    denom = math.sqrt(size * (trueskill.BETA * trueskill.BETA) + sum_sigma)
    ts = trueskill.global_env()
    return ts.cdf(delta_mu / denom)




class ScreenEnterMatch(LcarsScreen):


    def setup(self, all_sprites):

        # load the most recently used player layout
        prefill = shelve.open('latestmatch')
        for i in range(4):
            if str(i) not in prefill:
                prefill[str(i)] = ''
        prefill.close()
        
        
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_match.png"), layer=0)

        # large interface buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 708), (140,40), "Back",       self.backHandler), layer=1)
        self.startMatchButton = LcarsButton2(colours.ORANGE, (928, 528), (92, 60), "Start Match", self.startHandler)
        all_sprites.add(self.startMatchButton, layer=1)
        all_sprites.add(LcarsButton2(colours.BEIGE, (64,348), (40,32), "Auto", self.swapHandler))

        # the small buttons for rearranging players:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (324, 348), (32,32), "clear", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (288, 348), (32,32), "bottomrow", glyph=True, handler=self.swapHandler, glyphoffset=(0,5)))
        all_sprites.add(LcarsButton2(colours.BEIGE, (252, 348), (32,32), "toprow", glyph=True, handler=self.swapHandler, glyphoffset=(0,-5)))
        all_sprites.add(LcarsButton2(colours.BLUE, (216, 348), (32,32), "diag1", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BLUE, (180, 348), (32,32), "diag2", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (144, 348), (32,32), "rotateleft", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (108, 348), (32,32), "rotateright", glyph=True, handler=self.swapHandler))
        

        # add a keyboard:
        all_sprites.add(LcarsKeyboard((572,280), self.keyboardHandler))
        # add a clear input button
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (616, 216), (28,28), "clear", glyph=True, handler=self.keyboardHandler))
        # add the text already input
        self.searchText = LcarsText(colours.WHITE, (768-216-26, 284), "", 20/19)
        all_sprites.add(self.searchText)
        # add the placeholder text
        self.placeholder = LcarsText((127,127,127), (768-216-26, 292), "Search by name...", 20/19)
        all_sprites.add(self.placeholder)
        # add a carret:
        self.carret = LcarsButton2(colours.WHITE, (284, 216), (4, 28), "")
        all_sprites.add(self.carret)

        # add a text object for the odds:
        self.oddsText = LcarsText(colours.WHITE, (768-360-16-3, 648+1), "1:1", 1)
        all_sprites.add(self.oddsText)
        
        # placeholders for names:
        self.matchedNames = []
        for i in range(6):
            newbutton = LcarsButton2((127,127,127), (52, 200-36*i), (188, 32), '', handler=partial(self.playerClicked, i))
            newbutton.addPlayer = False
            self.matchedNames.append(newbutton)
            all_sprites.add(newbutton)


        # texts for selected players
        prefill = shelve.open('latestmatch')
        self.selectedPlayers = [
            LcarsText(colours.BLACK, (768-484-32+4, 216+4), capwords(prefill['0']), 20/19),
            LcarsText(colours.BLACK, (768-412-32+4, 216+4), capwords(prefill['1']), 20/19),
            LcarsText(colours.BLACK, (768-484-32+4, 600+4), capwords(prefill['2']), 20/19),
            LcarsText(colours.BLACK, (768-412-32+4, 600+4), capwords(prefill['3']), 20/19)
        ]
        prefill.close()
        all_sprites.add(self.selectedPlayers[0], layer=1)
        all_sprites.add(self.selectedPlayers[1], layer=1)
        all_sprites.add(self.selectedPlayers[2], layer=1)
        all_sprites.add(self.selectedPlayers[3], layer=1)

        # sprites for highlighting/playerfocus
        self.inputfocus = [
            LcarsInputFocus((768-484-32 , 216), False, False, handler=partial(self.inputFocusHandler, 0)),
            LcarsInputFocus((768-412-32 , 216), False, True, handler=partial(self.inputFocusHandler, 1)),
            LcarsInputFocus((768-484-32 , 600), True, True, handler=partial(self.inputFocusHandler, 2)),
            LcarsInputFocus((768-412-32 , 600), True, True, handler=partial(self.inputFocusHandler, 3))
            ]
        all_sprites.add(self.inputfocus[0], layer=2)
        all_sprites.add(self.inputfocus[1], layer=2)
        all_sprites.add(self.inputfocus[2], layer=2)
        all_sprites.add(self.inputfocus[3], layer=2)
        self.currentFocus = 0
            
        self.searchString = ""
        self.validate()
        
        
    def update(self, screenSurface, fpsClock):
        #if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
        #    self.stardate.setText(datetime.now().strftime("%d%m.%y %H:%M:%S"))
        #    self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)


    def validate(self):
        p0 = self.selectedPlayers[0].message.lower()
        p1 = self.selectedPlayers[1].message.lower()
        p2 = self.selectedPlayers[2].message.lower()
        p3 = self.selectedPlayers[3].message.lower()
        team1 = set() # makes unique
        team2 = set()
        if p0 != '':
            team1.add(p0)
        if p1 != '':
            team1.add(p1)
        if p2 != '':
            team2.add(p2)
        if p3 != '':
            team2.add(p3)
        if ( len(team1) == len(team2) and
             len(team1) >= 1 and
             len(team1) <= 2 and
             len(team1.intersection(team2)) == 0):

            self.startMatchButton.setEnabled(True)
        else:
            self.startMatchButton.setEnabled(False)
    
        
    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            #self.beep1.play()
            pass

        if event.type == pygame.MOUSEBUTTONUP:
            return False

    def inputFocusHandler(self, which, item, event, clock):
        print("input focus on {}".format(which))
        self.currentFocus = which
        for i in range(4):
            self.inputfocus[i].setTransparent(i!=which)

    def updateOdds(self):
        p0 = self.selectedPlayers[0].message.lower()
        p1 = self.selectedPlayers[1].message.lower()
        p2 = self.selectedPlayers[2].message.lower()
        p3 = self.selectedPlayers[3].message.lower()
        team1 = []
        team2 = []
        players = shelve.open('playerdb')
        if p0 in players:
            team1.append(players[p0])
        if p1 in players:
            team1.append(players[p1])
        if p2 in players:
            team2.append(players[p2])
        if p3 in players:
            team2.append(players[p3])
        players.close()
        p = 0.5
        if len(team1) > 0 and len(team2) > 0:
            p = win_probability(team1, team2)
        print("win probability: {}%".format(p*100))
        
        ratios = [
            ("0:1", 0/(0+1)),
            ("1:20", 1/(1+20)),
            ("1:12", 1/(1+12)),
            ("1:8", 1/(1+8)),
            ("1:6", 1/(1+6)),
            ("1:5", 1/(1+5)),
            ("1:4", 1/(1+4)),
            ("1:3", 1/(1+3)),
            ("2:5", 2/(2+5)),
            ("1:2", 1/(1+2)),
            ("3:5", 3/(3+5)),
            ("2:3", 2/(2+3)),
            ("4:5", 4/(4+5)),
            ("1:1", 1/(1+1)),
            ("5:4", 5/(5+4)),
            ("3:2", 3/(3+2)),
            ("5:3", 5/(5+3)),
            ("2:1", 2/(2+1)),
            ("5:2", 5/(5+2)),
            ("3:1", 3/(3+1)),
            ("4:1", 4/(4+1)),
            ("5:1", 5/(5+1)),
            ("6:1", 6/(6+1)),
            ("8:1", 8/(8+1)),
            ("12:1", 12/(12+1)),
            ("20:1", 20/(20+1)),
            ("1:0", 1/(1+0)) ]
        ratio = sorted(ratios, key=lambda x: abs(x[1]-p))[0][0]
        print("selected ratio: {}".format(ratio))
        self.oddsText.setText(ratio)

        

            
        
    def playerClicked(self, index, item, event, clock):
        print("player {} clicked: {}".format(index, item.text))
        if item.addPlayer:
            print("adding")
            players = shelve.open("playerdb")
            players[self.searchString] = trueskill.Rating()
            players.close()
            self.updatePlayerSelection()
        else:
            print("choosing")
            self.selectedPlayers[self.currentFocus].setText(item.text)
            # save in shelve
            prefill = shelve.open('latestmatch')
            prefill[str(self.currentFocus)] = item.text
            prefill.close()

            # rotate focus
            self.currentFocus = (self.currentFocus + 1) % 4
            for i in range(4):
                self.inputfocus[i].setTransparent(i!=self.currentFocus)
            self.updateOdds()
            self.validate()
            
            
        
    def updatePlayerSelection(self):
        players = shelve.open('playerdb')
        candidates = []
        if len(players) > 0:
            candidates = process.extractBests(self.searchString, players.keys(), score_cutoff=50, limit=6)
        print(candidates)
        players.close()
        for i in range(6):
            # skip the add player button
            if self.matchedNames[i].addPlayer:
                continue
            if i >= len(candidates):
                # reset remaining fields if there are not many candidates
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
        if type(event)==str:
            if event == 'bkspc':
                match  = re.search('0x[0-9][0-9]$', self.searchString)
                if match != None:
                    self.searchString = self.searchString[:-4] + chr(int(match.group(), 16))
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
        if self.searchString not in players.keys() and len(self.searchString)>3:
            self.matchedNames[-1].setText("Add "+capwords(self.searchString))
            self.matchedNames[-1].setColor(colours.RED_BROWN)
            self.matchedNames[-1].addPlayer = True
        else:
            self.matchedNames[-1].addPlayer = False
        players.close()

        # update list of selectable players
        self.updatePlayerSelection()
            
            
        
        
        self.placeholder.visible = len(self.searchString)==0
        self.searchText.renderText(capwords(self.searchString, " "))
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
        if p0 != '':
            team1.append(p0)
        if p1 != '':
            team1.append(p1)
        if p2 != '':
            team2.append(p2)
        if p3 != '':
            team2.append(p3)
        self.loadScreen(ScreenEnterOutcome(team1, team2))
        print("starting match")
        

    def swapHandler(self, item, event, clock):
        print("swapping "+item.text)
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
        if item.text == 'Auto':
            # there are really only 3 combinations that can be played
            p0 = self.selectedPlayers[0].message.lower()
            p1 = self.selectedPlayers[1].message.lower()
            p2 = self.selectedPlayers[2].message.lower()
            p3 = self.selectedPlayers[3].message.lower()

            players = shelve.open('playerdb')
            if p0 not in players or p1 not in players or p2 not in players or p3 not in players:
                # nothing to do
                return
            match1 = [(players[p0], players[p1]), (players[p2], players[p3])]
            match2 = [(players[p0], players[p2]), (players[p1], players[p3])]
            match3 = [(players[p0], players[p3]), (players[p1], players[p2])]
            q1 = trueskill.quality(match1)
            q2 = trueskill.quality(match2)
            q3 = trueskill.quality(match3)
            match = None
            if q1 > q2 and q1 > q3:
                self.selectedPlayers[0].setText(capwords(p0))
                self.selectedPlayers[1].setText(capwords(p1))
                self.selectedPlayers[2].setText(capwords(p2))
                self.selectedPlayers[3].setText(capwords(p3))
            elif q2 > q3:
                self.selectedPlayers[0].setText(capwords(p0))
                self.selectedPlayers[1].setText(capwords(p2))
                self.selectedPlayers[2].setText(capwords(p1))
                self.selectedPlayers[3].setText(capwords(p3))
            else:
                self.selectedPlayers[0].setText(capwords(p0))
                self.selectedPlayers[1].setText(capwords(p3))
                self.selectedPlayers[2].setText(capwords(p1))
                self.selectedPlayers[3].setText(capwords(p2))
            players.close()
            
        self.updateOdds()
        # remember player arrangement
        prefill = shelve.open('latestmatch')
        prefill['0'] = self.selectedPlayers[0].message.lower()
        prefill['1'] = self.selectedPlayers[1].message.lower()
        prefill['2'] = self.selectedPlayers[2].message.lower()
        prefill['3'] = self.selectedPlayers[3].message.lower()
        prefill.close()
        
            
            
            
        


