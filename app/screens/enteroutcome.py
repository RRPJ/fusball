from string import capwords
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
import shelve


class ScreenEnterOutcome(LcarsScreen):
    def __init__(self, team1, team2):
        self.team1 = team1
        self.team2 = team2
        
    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars-kickers-resultscreen.png"), layer=0)

        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4,708), (140, 40), "Cancel", self.cancelHandler), layer=1)
        

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
        
