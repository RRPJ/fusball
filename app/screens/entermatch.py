from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen

from datasources.network import get_ip_address_string


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
        all_sprites.add(LcarsButton2(colours.BEIGE, (288, 348), (32,32), "leftright", glyph=True, handler=self.swapHandler))
        all_sprites.add(LcarsButton2(colours.BEIGE, (252, 348), (32,32), "leftright", glyph=True, handler=self.swapHandler))
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
        for i in range(6):
            all_sprites.add(LcarsButton2((127,127,127), (52, 200-36*i), (188, 32), ""))

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

    def capitalizeWord(self, inp):
        words = inp.split()
        def capfirst(word):
            if len(word)==0:
                return ''
            else:
                return word[0].upper() + word[1:]
        words = [capfirst(w) for w in words]
        return " ".join(words)
    
    def keyboardHandler(self, item, event, clock):
        print("keyboard event forwarded to match screen: {}".format(event))
        if type(event)==str:
            self.searchString = self.searchString + event
        else:
            if item.text == "clear":
                self.searchString = ""
            
            
        self.placeholder.visible = len(self.searchString)==0
        self.searchText.renderText(self.capitalizeWord(self.searchString))
        self.carret.rect.left = 284 + self.searchText.image.get_size()[0]
        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())
                        
    def startHandler(self, item, event, clock):
        pass

    def swapHandler(self, item, event, clock):
        print("swapping "+item.text)
        


