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
import time

class ScreenLog(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_log.png"), layer=0)

        self.offset = 0
        self.textlines = []

        # interface buttons:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (24, 700), (140,48), "Back", self.backHandler ))

        with open('logfile.log', 'r') as log:
            lines = log.readlines()
        for i,line in enumerate(lines):
            newline = LcarsText(colours.WHITE, (0, 200), line[:-1], 20/19)
            self.textlines.append(newline)
            all_sprites.add(newline)
        self.scroll()

    def scroll(self):
        for i,item in enumerate(self.textlines):
            item.rect.top = 40+self.offset+i*22
            item.dirty = 1
        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEMOTION and event.buttons[0]==1:
            #pprint(event)
            dy = event.rel[1]
            self.offset += dy
            if self.offset > 0:
                self.offset = 0
            maxoffset = (len(self.textlines)-30)*22
            if self.offset < -maxoffset:
                self.offset = -maxoffset
            self.scroll()

            
