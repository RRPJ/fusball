from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from string import capwords
import subprocess
import sys


class ScreenPower(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_power.png"), layer=0)
        
        # interface buttons:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (24, 700), (140,48), "Back", self.backHandler ))
        all_sprites.add(LcarsButton2(colours.ORANGE,    (204,508), (188,92), "",     self.suspendHandler))
        all_sprites.add(LcarsButton2(colours.ORANGE,    (396,508), (188,92,), "",    self.powerHandler))
        all_sprites.add(LcarsButton2((117,121,138),     (588,508), (188,92), "",     self.exitHandler))

        # multiline text on buttons:
        all_sprites.add(LcarsText(colours.BLACK, (188, 266), "SUSPEND", 26/19))
        all_sprites.add(LcarsText(colours.BLACK, (218, 270), "TO RAM", 26/19))

        all_sprites.add(LcarsText(colours.BLACK, (188, 192+270), "POWER", 26/19))
        all_sprites.add(LcarsText(colours.BLACK, (218, 192+275), "DOWN", 26/19))

        all_sprites.add(LcarsText(colours.BLACK, (188, 2*192+260), "EXIT LCARS", 26/19))
        all_sprites.add(LcarsText(colours.BLACK, (218, 2*192+262), "(need kbd)", 26/19))

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

    def suspendHandler(self, item, event, clock):
        subprocess.run(['sudo','systemctl','suspend'])

    def powerHandler(self, item, event, clock):
        subprocess.run(['sudo','systemctl','poweroff'])

    def exitHandler(self, item, event, clock):
        sys.exit(0)
