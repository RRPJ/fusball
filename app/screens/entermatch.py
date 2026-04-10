import re
import shelve
import time
from functools import partial
from string import capwords

from fuzzywuzzy import process
from services.match_service import best_balanced_lineup, odds_ratio_for_teams
from services.player_store import (
    add_player_if_missing,
    add_recent_player,
    ensure_recent_players_initialized,
    player_exists,
    player_names,
    recent_player_names,
)
from ui.widgets.background import LcarsBackgroundImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen


def pos(x,y):
    return (768-y-32+4, x+4)


class ScreenEnterMatch(LcarsScreen):

    def setup(self, all_sprites):

        # load the most recently used player layout
        ensure_recent_players_initialized()

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

    def _selected_names_lower(self):
        """Return current slot selections normalized to lowercase."""
        return [player.message.lower() for player in self.selectedPlayers]

    def _build_teams(self):
        """Build team lists from UI slots using legacy offense/defense ordering."""
        p0, p1, p2, p3 = self._selected_names_lower()
        team1 = []
        team2 = []
        # Keep legacy slot mapping (A offense before A defense).
        if p1 != '':
            team1.append(p1)
        if p0 != '':
            team1.append(p0)
        if p2 != '':
            team2.append(p2)
        if p3 != '':
            team2.append(p3)
        return team1, team2

    def _is_valid_selection(self):
        """Check that both teams are balanced and contain unique players."""
        p0, p1, p2, p3 = self._selected_names_lower()

        team1 = set()
        team2 = set()
        if p0 != '':
            team1.add(p0)
        if p1 != '':
            team1.add(p1)
        if p2 != '':
            team2.add(p2)
        if p3 != '':
            team2.add(p3)

        return (
            len(team1) == len(team2)
            and len(team1) >= 1
            and len(team1) <= 2
            and len(team1.intersection(team2)) == 0
        )

    def validate(self):
        """Enable start only when the current selection is match-ready."""
        self.startMatchButton.setEnabled(self._is_valid_selection())

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
                    if not player_exists(tagname):
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
        """Refresh displayed odds for the currently selected lineups."""
        p0, p1, p2, p3 = self._selected_names_lower()
        with shelve.open('playerdb') as players:
            p, ratio = odds_ratio_for_teams(players, [p1, p0], [p2, p3])
        print("win probability: {}%".format(p * 100))
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
            add_player_if_missing(self.searchString)
            #self.updatePlayerSelection()

        print("choosing")
        self.selectedPlayers[self.currentFocus].setText(capwords(name))
        add_recent_player(name)
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
        """Populate candidate buttons from fuzzy search and recent-player history."""
        names = player_names()
        recentplayers = recent_player_names()
        candidates = []
        if len(names) > 0:
            candidates = process.extractBests(
                self.searchString, names, score_cutoff=50, limit=6)
        # remove candicates from recent to prevent double listing
        for c in candidates:
            print('c[0]:', c[0])
            if c[0] in recentplayers:
                recentplayers.remove(c[0])

        # remove already selected players
        for p in self._selected_names_lower():
            # recent players is easy
            if p in recentplayers:
                recentplayers.remove(p)
            # candidates are harder because they are tuples
            candidates = [c for c in candidates if c[0] != p]

        # remove already chosen players from suggestions
        for s in self._selected_names_lower():
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
        """Apply keyboard input and update add-player affordance and suggestions."""
        print("keyboard event forwarded to match screen: {}".format(event))
        # update the input field with the new text:
        if isinstance(event, str):
            if event == 'bkspc':
                match = re.search('0x[0-9][0-9]$', self.searchString)
                if match is not None:
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

        if not player_exists(self.searchString) and len(self.searchString.strip()) > 3:
            self.matchedNames[-1].setText("Add " + capwords(self.searchString))
            self.matchedNames[-1].setColor(colours.RED_BROWN)
            self.matchedNames[-1].addPlayer = True
        else:
            self.matchedNames[-1].addPlayer = False

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
        """Open the outcome screen with teams derived from current selection."""
        from screens.enteroutcome import ScreenEnterOutcome
        team1, team2 = self._build_teams()
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
        """Reorder selected players to the highest-quality balanced lineup."""
        # there are really only 3 combinations that teams can be assigned
        # there are 4 combinations of offense/defense for each.
        p0, p1, p2, p3 = self._selected_names_lower() # def A, off A, off B, def B
        with shelve.open('playerdb') as players:
            names = best_balanced_lineup(players, p0, p1, p2, p3)
        if names is None:
            return
        self.selectedPlayers[0].setText(capwords(names[0]))
        self.selectedPlayers[1].setText(capwords(names[1]))
        self.selectedPlayers[2].setText(capwords(names[2]))
        self.selectedPlayers[3].setText(capwords(names[3]))

        self.updateOdds()

