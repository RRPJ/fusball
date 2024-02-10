from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from string import capwords
import subprocess
from pprint import pprint
import sys


class ScreenAbout(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        # all_sprites.add(LcarsBackgroundImage("assets/bg_about.png"), layer=0)
        
        # interface buttons:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4, 4), (140,68), "Back", self.backHandler ))
        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

