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


class ScreenEnterMatch(LcarsScreen):
    def setup(self, all_sprites):

        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_match.png"), layer=0)

        # large interface buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 708), (140,40), "Back",       self.backHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.ORANGE, (928, 528), (92, 60), "Start Match", self.startHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.BEIGE, (64,348), (40,32), "Auto", self.swapHandler))

        # the small buttons for rearranging players:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (324, 348), (32,32), "clear", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (288, 348), (32,32), "leftright", glyph=True, handler=self.swapHandler, glyphoffset=(0,5)))
        all_sprites.add(LcarsButton2(colours.BEIGE, (252, 348), (32,32), "leftright", glyph=True, handler=self.swapHandler, glyphoffset=(0,-5)))
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

        # placeholders for names:
        self.matchedNamed = []
        for i in range(6):
            newbutton = LcarsButton2((127,127,127), (52, 200-36*i), (188, 32), "", handler=partial(self.playerClicked, i))
            newbutton.addPlayer = False
            self.matchedNamed.append(newbutton)
            all_sprites.add(newbutton)

        self.searchString = ""
        
    def update(self, screenSurface, fpsClock):
        #if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
        #    self.stardate.setText(datetime.now().strftime("%d%m.%y %H:%M:%S"))
        #    self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            #self.beep1.play()
            pass

        if event.type == pygame.MOUSEBUTTONUP:
            return False

    def playerClicked(self, index, item, event, clock):
        print("player {} clicked: {}".format(index, item.text))
        if item.addPlayer:
            print("adding")
            players = shelve.open("playerdb")
            players[item.text] = {'mu': 25, 'sigma': 25/3}
            players.close()
        else:
            print("choosing")
        
        
        
    def keyboardHandler(self, item, event, clock):
        print("keyboard event forwarded to match screen: {}".format(event))
        # update the input field with the new text:
        if type(event)==str:
            if event == 'bkspc':
                self.searchString = self.searchString[:-1]
            elif event == 'enter':
                # todo: figure out what this does
                pass
            else:
                self.searchString = self.searchString + event
        else:
            if item.text == "clear":
                self.searchString = ""
        
        # list selectable players
        players = shelve.open('playerdb')
        if len(players) > 0:
            candidates = process.extract(self.searchString, players.keys())
            print(candidates)

        if self.searchString not in players.keys() and len(self.searchString)>0:
            self.matchedNamed[-1].setText("Add "+capwords(self.searchString))
            self.matchedNamed[-1].setColor(colours.RED_BROWN)
            self.matchedNamed[-1].addPlayer = True
        else:
            self.matchedNamed[-1].setText("")
            self.matchedNamed[-1].setColor((127,127,127))
            self.matchedNamed[-1].addPlayer = False
            
            
        
        
        self.placeholder.visible = len(self.searchString)==0
        self.searchText.renderText(capwords(self.searchString, " "))
        self.carret.rect.left = 284 + self.searchText.image.get_size()[0]
        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())
                        
    def startHandler(self, item, event, clock):
        pass

    def swapHandler(self, item, event, clock):
        print("swapping "+item.text)
        


