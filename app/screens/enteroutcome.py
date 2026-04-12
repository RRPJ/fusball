import math
import shelve
from functools import partial
from string import capwords

from odds import findRank, playerLevel
from services.match_history import append_match_history
from services.match_log import append_match_log
from services.match_service import calculate_rating_update, odds_ratio_for_teams
from ui.widgets.background import LcarsBackgroundImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen


def pos(x,y):
    return (768-y-32+4, x+4)


class ScreenEnterOutcome(LcarsScreen):
    """Result-entry screen that previews and persists rating changes."""

    def __init__(self, team1, team2):
        self.team1 = list(team1)
        self.team2 = list(team2)
        self.team1score = None
        self.team2score = None
        super().__init__()

    def _player_name_for_row(self, row):
        """Map a scoreboard row index to its player name or None."""
        team = [self.team1, self.team2][math.floor(row / 2)]
        if row % 2 >= len(team):
            return None
        return team[row % 2]

    def _add_score_buttons(self, all_sprites):
        """Create and register clickable score selectors for both teams."""
        self.scorebuttons1 = []
        self.scorebuttons2 = []
        for i in range(6):
            b1 = LcarsButton2((127,127,127), (400,388+36*i), (96,32), str(i), partial(self.scoreHandler, 0, i))
            b2 = LcarsButton2((127,127,127), (500,388+36*i), (96,32), str(i), partial(self.scoreHandler, 1, i))
            self.scorebuttons1.append(b1)
            self.scorebuttons2.append(b2)
            all_sprites.add(b1, layer=1)
            all_sprites.add(b2, layer=1)

    def _add_fixed_labels(self, all_sprites):
        """Render static player name labels in both score and stats areas."""
        all_sprites.add(LcarsText(colours.BLACK, pos(316, 352), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(508, 352), capwords(self.team2[0]), 20/19))
        if len(self.team1)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(316, 316), capwords(self.team1[1]), 20/19))
        if len(self.team2)>1:
            all_sprites.add(LcarsText(colours.BLACK, pos(508, 316), capwords(self.team2[1]), 20/19))

        all_sprites.add(LcarsText(colours.BLACK, pos(200, 140), capwords(self.team1[0]), 20/19))
        all_sprites.add(LcarsText(colours.BLACK, pos(200, 68), capwords(self.team2[0]), 20/19))
        if len(self.team2) > 1:
            all_sprites.add(LcarsText(colours.BLACK, pos(200, 32), capwords(self.team2[1]), 20/19))
        if len(self.team1) > 1:
            all_sprites.add(LcarsText(colours.BLACK, pos(200, 104), capwords(self.team1[1]), 20/19))

    def _add_odds_display(self, all_sprites):
        """Compute and render pre-match odds and likelihood placeholders."""
        with shelve.open('playerdb') as players:
            p, ratio = odds_ratio_for_teams(players, self.team1, self.team2)
        print("win probability: {}%".format(p * 100))
        print("selected ratio: {}".format(ratio))
        all_sprites.add(LcarsText(colours.BLACK, pos(160, 460), str(ratio.split(':')[0]), 20/19, alignright=True))
        all_sprites.add(LcarsText(colours.BLACK, pos(180, 460), str(ratio.split(':')[1]), 20/19))

        self.lhtext1 = LcarsText(colours.BLACK, pos(160, 408), '', 20/19, alignright=True)
        self.lhtext2 = LcarsText(colours.BLACK, pos(180, 408), '', 20/19)
        all_sprites.add(self.lhtext1)
        all_sprites.add(self.lhtext2)

    def _init_text_grid(self, all_sprites):
        """Initialize the before/after stats matrix shown on the result screen."""
        xs = [384, 428, 532, 636, 724, 768, 872, 976]
        ys = [140, 104, 68, 32]
        self.textLabels = [[None for y in ys] for x in xs]

        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                self.textLabels[i][j] = LcarsText(colours.BLACK, pos(x, y), "?", 20/19)
                all_sprites.add(self.textLabels[i][j])

    def _prefill_before_values(self):
        """Fill the left half of the stats matrix with current persisted ratings."""
        with shelve.open('playerdb') as players:
            for row in range(4):
                name = self._player_name_for_row(row)
                if name is None or name not in players:
                    continue
                player = players[name]
                self.textLabels[0][row].setText(findRank(players, name))
                self.textLabels[1][row].setText("{:.2f}/{:.2f}".format(player[0].mu, player[0].sigma))
                self.textLabels[2][row].setText("{:.2f}/{:.2f}".format(player[1].mu, player[1].sigma))
                self.textLabels[3][row].setText("{:d}".format(round(playerLevel(player))))

    def _update_score_button_colors(self, buttons, score, active_color):
        """Highlight score buttons up to the selected value."""
        for i in range(6):
            buttons[i].setColor(active_color if i <= score else (127,127,127))

    def _set_save_enabled(self):
        """Allow saving only for valid foosball end states (winner reaches 5)."""
        minscore = min(self.team1score, self.team2score)
        maxscore = max(self.team1score, self.team2score)
        self.saveButton.setEnabled(maxscore == 5 and minscore != 5)

    def _update_after_values(self, updated):
        """Fill the right half of the stats matrix with projected updated ratings."""
        for row in range(4):
            name = self._player_name_for_row(row)
            if name is None:
                continue
            player = updated[name]
            self.textLabels[4][row].setText(findRank(updated, name))
            self.textLabels[5][row].setText("{:.2f}/{:.2f}".format(player[0].mu, player[0].sigma))
            self.textLabels[6][row].setText("{:.2f}/{:.2f}".format(player[1].mu, player[1].sigma))
            self.textLabels[7][row].setText("{:d}".format(round(playerLevel(player))))

    def _apply_rating_update(self, players):
        """Persist computed rating updates for all players in both teams."""
        for team in (self.team1, self.team2):
            for name in team:
                players[name] = self.ratingupdate[name]

    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars-kickers-resultscreen.png"), layer=0)

        print("drawing labels: {} against {}".format(self.team1, self.team2))


        # buttons
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (4,708), (140, 40), "Cancel", self.cancelHandler), layer=1)
        self._add_score_buttons(all_sprites)

        self.saveButton = LcarsButton2(colours.ORANGE,   (740,520), (120, 68), "Save Result", self.saveHandler)
        self.saveButton.setEnabled(False)
        all_sprites.add(self.saveButton, layer=1)

        self._add_fixed_labels(all_sprites)
        self._add_odds_display(all_sprites)
        self._init_text_grid(all_sprites)
        self._prefill_before_values()




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

    def scoreHandler(self, team, score, item, event, clock):
        """Handle score selection, compute updates, and refresh after-preview values."""
        # enable save button
        #self.saveButton.setEnabled(True)
        # highlight score
        if team==0:
            self.team1score = score
            self._update_score_button_colors(self.scorebuttons1, self.team1score, colours.RED_BROWN)
        else:
            self.team2score = score
            self._update_score_button_colors(self.scorebuttons2, self.team2score, colours.BLUE)



        if self.team1score is not None and self.team2score is not None:
            self._set_save_enabled()
            with shelve.open('playerdb') as players:
                updated = calculate_rating_update(
                    players,
                    self.team1,
                    self.team2,
                    self.team1score,
                    self.team2score,
                )

            self.ratingupdate = updated
            self._update_after_values(updated)


    def saveHandler(self, item, event, clock):
        """Persist rating updates, append audit log entry, then return to match entry."""
        winningteam = self.team1 if self.team1score > self.team2score else self.team2
        db_path = 'playerdb'
        with shelve.open('playerdb') as players:
            before_ratings = {
                name: players[name]
                for team in (self.team1, self.team2)
                for name in team
            }

            # update offensive and defensive skills
            self._apply_rating_update(players)

            after_ratings = {
                name: players[name]
                for team in (self.team1, self.team2)
                for name in team
            }
        try:
            append_match_log(
                'logfile.log',
                self.team1,
                self.team2,
                winningteam,
                before_ratings,
                after_ratings,
            )
            append_match_history(
                '.',
                self.team1,
                self.team2,
                winningteam,
                self.team1score,
                self.team2score,
                before_ratings,
                after_ratings,
                source='kiosk',
            )
        except Exception:
            with shelve.open(db_path) as players:
                for name, rating in before_ratings.items():
                    players[name] = rating
            raise
        # return to match screen:
        from screens.entermatch import ScreenEnterMatch
        self.loadScreen(ScreenEnterMatch())


