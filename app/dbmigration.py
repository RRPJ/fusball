#!/bin/env python3
import trueskill
import shelve

playerdb = shelve.open('playerdb')
for p in playerdb:
    playerdb[p] = (playerdb[p], playerdb[p])
playerdb.close()
