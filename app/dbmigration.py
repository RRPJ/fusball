#!/bin/env python3
import shelve

import trueskill as trueskill

playerdb = shelve.open("playerdb")
for p in playerdb:
    if type(playerdb[p]) != tuple:  # noqa: E721 - preserve legacy exact-type comparison
        playerdb[p] = (playerdb[p], playerdb[p])
playerdb.close()
