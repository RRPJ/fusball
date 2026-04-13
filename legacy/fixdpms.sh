#!/bin/bash
# LEGACY - X11 DPMS (Display Power Management Signaling) for kiosk idle timeout.
# Kept for reference. Not used in modern deployments.

#logger "hello from fixdpms as $(whoami)"

# script is run as root. Su needed because root apparently has no permission on a user's x11
su kickers -c '/usr/bin/xset -display :0 dpms force suspend'
sleep 1
su kickers -c '/usr/bin/xset -display :0 dpms force on'
