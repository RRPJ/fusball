from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from string import capwords
import shelve
import trueskill
import math
import subprocess
from odds import win_probability, findRank, playerLevel
from datasources.network import get_ip_address_string


class ScreenMain(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_main.png"), layer=0)

        
        self.title = LcarsTitle(colours.WHITE, (768-568-32, 268), 260, "")
        all_sprites.add(self.title)
        
        # interface buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 708), (140,40), "Power",       self.powerHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 192), (140,80), "Enter Match", self.enterMatchHandler, ), layer=1)
        all_sprites.add(LcarsButton2(colours.PURPLE   , (4, 144), (140,44), "System Log",  self.logHandler), layer=1)
        #all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 92), (140,48),  "Ranking"     ), layer=1)
        # all_sprites.add(LcarsText((0,0,0), (647,89), "Ranking", 20/19), layer=5)
        # all_sprites.add(LcarsButton2(colours.ORANGE   , (4, 40), (140,48),  "About",       self.aboutHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.BLUE     , (336, 92), (140,48), "Next",       self.nextHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.BLUE     , (192, 92), (140,48), "Prev",       self.prevHandler), layer=1)

        self.namebuttons = []
        self.ranklabels = []
        self.levellabels = []
        self.offenselabels = []
        self.defenselabels = []
        colour = (0,0,0)
        for i in range(10):
            # label and rounded stub for rank
            self.ranklabels.append(LcarsRoundStub(colour, (240+36*i, 264), ""))
            all_sprites.add(self.ranklabels[-1])
            # player name
            self.namebuttons.append(LcarsButton2(colour, (316, 496-36*i), (188,32), '', None))
            all_sprites.add(self.namebuttons[-1])
            # player level
            self.levellabels.append(LcarsButton2(colour, (508, 496-36*i), (68,32), '', None))
            all_sprites.add(self.levellabels[-1])
            # offensive field
            self.offenselabels.append(LcarsButton2(colour, (580, 496-36*i), (92,32), '', None))
            all_sprites.add(self.offenselabels[-1])
            # defensive
            self.defenselabels.append(LcarsButton2(colour, (676, 496-36*i), (92,32), '', None))
            all_sprites.add(self.defenselabels[-1])

        
        self.page = 0
        self.updateRanking()
        
        #self.ip_address = LcarsText(colours.BLACK, (444, 520), get_ip_address_string())
        #all_sprites.add(self.ip_address, layer=1)

        # date display
        self.stardate = LcarsText((153,153,153), (292-24-5,4), "2311.05 17:54:32", 1.65, otherfont=True)
        self.lastClockUpdate = 0
        all_sprites.add(self.stardate, layer=1)

        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()

        
    def updateRanking(self):
        if self.page == 0:
            self.title.setText("TOP 10")
        else:
            self.title.setText("TOP {}-{}".format(self.page*10, self.page*10+9))
            
        players = shelve.open('playerdb')
        ranked = sorted(players.items(), key=lambda kv:playerLevel(kv[1]), reverse=True)
        # user buttons:
        colorindex = 0
        prevrank = ""
        for i in range(self.page*10, (self.page + 1) * 10):
            # name field
            if i < len(ranked):
                name,rating = ranked[i]
                rank = findRank(players, name)
            else:
                name = ''
                rating = (trueskill.Rating(), trueskill.Rating())
                rank = '-'
                
            if rank != prevrank:
                colorindex = (colorindex + 1) % 4
                prevrank = rank
        
            colour = [colours.BLUE, colours.PEACH, colours.BEIGE, colours.WHITE][colorindex]

            self.ranklabels[i % 10].setText(rank)
            self.ranklabels[i % 10].setColour(colour)
            
            self.namebuttons[i % 10].setText(capwords(name))
            self.namebuttons[i % 10].setColor(colour)

            level = str(round(playerLevel(rating))) if i < len(ranked) else ''
            self.levellabels[i % 10].setText(level)
            self.levellabels[i % 10].setColor(colour)

            offense = "{:.2f}/{:.2f}".format(rating[0].mu, rating[0].sigma) if i < len(ranked) else ''
            defense = "{:.2f}/{:.2f}".format(rating[1].mu, rating[1].sigma) if i < len(ranked) else ''
            self.offenselabels[i % 10].setText(offense)
            self.defenselabels[i % 10].setText(defense)
            self.offenselabels[i % 10].setColor(colour)
            self.defenselabels[i % 10].setColor(colour)

        players.close()
        
        
    def update(self, screenSurface, fpsClock):
        if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
            self.stardate.setText(datetime.now().strftime("%d%m.%y %H:%M:%S"))
            self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.beep1.play()

        if event.type == pygame.MOUSEBUTTONUP:
            return False

    def hideInfoText(self):
        if self.info_text[0].visible:
            for sprite in self.info_text:
                sprite.visible = False

    def showInfoText(self):
        for sprite in self.info_text:
            sprite.visible = True


    def nextHandler(self, item, event, clock):
        self.page += 1
        self.updateRanking()

    def prevHandler(self, item, event, clock):
        if self.page > 0:
            self.page -= 1
            self.updateRanking()


    def playerClickedHandler(self, number, item, event, clock):
        print("player {} clicked".format(number))
        
    def powerHandler(self, item, event, clock):
        from screens.power import ScreenPower
        self.loadScreen(ScreenPower())

        #
        
        #pygame.image.save(item.image, "/home/kickers/screenshot.png")


    def enterMatchHandler(self, item, event, clock):
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())

    def logHandler(self, item, event, clock):
        from screens.log import ScreenLog
        self.loadScreen(ScreenLog())


    def allRankingHandler(self, item, event, clock):
        pass

    def aboutHandler(self, item, event, clock):
        from screens.about import ScreenAbout
        self.loadScreen(ScreenAbout())

    
    def gaugesHandler(self, item, event, clock):
        self.hideInfoText()
        self.sensor_gadget.visible = False
        self.dashboard.visible = True
        self.weather.visible = False

    def sensorsHandler(self, item, event, clock):
        self.hideInfoText()
        self.sensor_gadget.visible = True
        self.dashboard.visible = False
        self.weather.visible = False

    def weatherHandler(self, item, event, clock):
        self.hideInfoText()
        self.sensor_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = True

    def homeHandler(self, item, event, clock):
        self.showInfoText()
        self.sensor_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        
    def logoutHandler(self, item, event, clock):
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())


