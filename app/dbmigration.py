#!/bin/env python3
import trueskill
import shelve

playerdb = shelve.open('playerdb')
for p in playerdb:
    if type(playerdb[p]) != tuple:
        playerdb[p] = (playerdb[p], playerdb[p])
playerdb.close()
