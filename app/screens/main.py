from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen

from datasources.network import get_ip_address_string


class ScreenMain(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_main.png"), layer=0)

        # interface buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 708), (140,40), "Power",       self.powerHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 192), (140,80), "Enter Match", self.enterMatchHandler, ), layer=1)
        all_sprites.add(LcarsButton2(colours.PURPLE   , (4, 144), (140,44), "System Log",  self.logHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 92), (140,48),  "Ranking",     ), layer=1)
        all_sprites.add(LcarsButton2(colours.ORANGE   , (4, 40), (140,48),  "About",       self.aboutHandler), layer=1)
        all_sprites.add(LcarsButton2(colours.BLUE     , (320, 92), (156,48), "View All",   self.allRankingHandler), layer=1)


        # user buttons:
        for i in range(10):
            # name field
            colour = colours.RED_BROWN if i==0 else colours.GREY_BLUE
            all_sprites.add(LcarsButton2(colour, (316, 496-36*i), (188,32), "Player name", partial(self.playerClickedHandler, i)))
            # mu field
            all_sprites.add(LcarsButton2(colour, (508, 496-36*i), (68,32), "sig", partial(self.playerClickedHandler, i)))
            # sigma field
            colour = random.choice([colours.PEACH, colours.BEIGE, colours.WHITE, colours.BLUE])
            all_sprites.add(LcarsButton2(colour, (580, 496-36*i), (92,32), "mu", partial(self.playerClickedHandler, i)))

        # rank numbers:
        for i in range(3):
            all_sprites.add(LcarsText((0,0,0), (245+36*i, 300), str(i+1), 20/19))
        
        #self.ip_address = LcarsText(colours.BLACK, (444, 520), get_ip_address_string())
        #all_sprites.add(self.ip_address, layer=1)

        # date display
        self.stardate = LcarsText((153,153,153), (292-24-5,4), "2311.05 17:54:32", 1.65, otherfont=True)
        self.lastClockUpdate = 0
        all_sprites.add(self.stardate, layer=1)

        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()

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




    def playerClickedHandler(self, number, item, event, clock):
        print("player {} clicked".format(number))
        
    def powerHandler(self, item, event, clock):
        pass

    def enterMatchHandler(self, item, event, clock):
        pass

    def logHandler(self, item, event, clock):
        pass

    def allRankingHandler(self, item, event, clock):
        pass

    def aboutHandler(self, item, event, clock):
        pass

    
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


