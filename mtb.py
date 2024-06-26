#!/usr/bin/python3
# -*- coding: utf-8 -*-

from collections import Counter
from itertools import groupby
from time import sleep

import datetime
import logging.handlers
import praw
import re
import requests
import requests.auth
import sys
import unicodedata
from bs4 import BeautifulSoup
from unidecode import unidecode

import pmt

# TO DO: 
# python 3
#  print(" ")
#  urllib2 to urllib
#  cookielib to http.cookiejar
#  s = f.read().decode('utf8') line not needed? python 3 decodes automatically
# use goal.com to bypass thread request
# switch from urllib2 to requests maybe
# deal with incorrect matching of non-existent game (eg using "City", etc) - ie better way of finding matches (nearest neighbour?)
# more robust handling of errors

# every minute, check mail, create new threads, update all current threads

# browser header (to avoid 405 error)
hdr = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
    'Accept-Encoding': 'none',
    'Accept-Language': 'en-US,en;q=0.8',
    'Connection': 'keep-alive'}

activeThreads = []
notify = False
messaging = True
spriteSubs = ['soccer', 'Gunners', 'fcbayern', 'soccerdev', 'mls']

# naughty list                
usrblacklist = ['dbawbaby',
                '12F12',
                'KYAmiibro']

# allowed to make multiple threads
usrwhitelist = ['spawnofyanni',
                'Omar_Til_Death',
                'eabryt']

# allowed to post early threads in given subreddit
timewhitelist = {'matchthreaddertest': ['spawnofyanni'],
                 'ussoccer': ['redravens'],
                 'coyssandbox': ['wardamnspurs'],
                 'eabryt': ['eabryt']}

# markup constants
# goal=0;pgoal=1;ogoal=1;mpen=3;yel=5;syel=5;red=6;subst=7;subo=12;subi=11;strms=10;lines=9;evnts=2
goal = 0
pgoal = 1
ogoal = 1
mpen = 1
yel = 5
syel = 5
red = 6
subst = 7
subo = 8
subi = 9
strms = 10
lines = 10
offs = 4
evnts = 2
events = ['sub', 'goal', 'yellow', 'red']


def getTimestamp():
    dt = str(datetime.datetime.now().month) + '/' + str(datetime.datetime.now().day) + ' '
    hr = str(datetime.datetime.now().hour) if len(str(datetime.datetime.now().hour)) > 1 else '0' + str(
        datetime.datetime.now().hour)
    min = str(datetime.datetime.now().minute) if len(str(datetime.datetime.now().minute)) > 1 else '0' + str(
        datetime.datetime.now().minute)
    t = '[' + hr + ':' + min + '] '
    return dt + t


def setup():
    try:
        f = open('login.txt')
        admin, username, password, subreddit, user_agent, id, secret, redirect = f.readline().split('||', 8)
        f.close()
        r = praw.Reddit(client_id=id,
                        client_secret=secret,
                        password=password,
                        user_agent=user_agent,
                        username=username)
        print(getTimestamp() + "OAuth session opened as /u/" + r.user.me().name)
        return r, admin, username, password, subreddit, user_agent, id, secret, redirect
    except:
        print(
            getTimestamp() + "Setup error: please ensure 'login.txt' file exists in its correct form (check readme for more info)\n")
        logger.exception("[SETUP ERROR:]")
        sleep(10)


# save activeThreads
def saveData():
    f = open('active_threads.txt', 'w+')
    s = ''
    for data in activeThreads:
        matchID, t1, t2, thread_id, reqr, sub = data
        s += matchID + '####' + str(unidecode(t1)) + '####' + str(unidecode(t2)) + '####' + str(
            thread_id) + '####' + str(reqr) + '####' + str(sub) + '&&&&'
    s = s[0:-4]  # take off last &&&&
    # f.write(str(s.encode('utf8')))
    f.write(str(s))
    f.close()


# read saved activeThreads data
def readData():
    f = open('active_threads.txt', 'r')
    # s = f.read().decode('utf8')
    s = f.read()
    info = s.split('&&&&')
    if info[0] != '':
        for d in info:
            [matchID, t1, t2, thread_id, reqr, sub] = d.split('####')
            # matchID = matchID.encode(
            #     'utf8')  # get rid of weird character at start - got to be a better way to do this...
            data = matchID, t1, t2, thread_id, reqr, sub
            activeThreads.append(data)
            logger.info("Active threads: %i - added %s vs %s (/r/%s)", len(activeThreads), t1, t2, sub)
            print(getTimestamp() + "Active threads: " + str(
                len(activeThreads)) + " - added " + t1 + " vs " + t2 + " (/r/" + sub + ")")
    f.close()


def resetAll():
    logger.info("[RESET ALL]")
    print(getTimestamp() + "Resetting all threads...")
    removeList = list(activeThreads)
    for data in removeList:
        activeThreads.remove(data)
        logger.info("Active threads: %i - removed %s vs %s (/r/%s)", len(activeThreads), data[1], data[2], data[5])
        print(getTimestamp() + "Active threads: " + str(len(activeThreads)) + " - removed " + data[1] + " vs " + data[
            2] + " (/r/" + data[5] + ")")
        saveData()
    print("complete.")


def flushMsgs():
    logger.info("[FLUSH MSGS]")
    print(getTimestamp() + "Flushing messages...")
    for msg in r.inbox.unread(limit=None):
        msg.mark_read()
    print("complete.")


def loadMarkup(subreddit):
    try:
        markup = [line.rstrip('\n') for line in open(subreddit + '.txt')]
    except:
        markup = [line.rstrip('\n') for line in open('soccer.txt')]
    return markup


def getRelatedSubreddits():
    page = r.subreddit('soccer').wiki['relatedsubreddits'].content_md
    subs = re.findall('/r/(.*?) ', page, re.DOTALL)
    subs = [s.replace('\r', '') for s in subs]
    subs = [s.replace('\n', '') for s in subs]
    subs = [s.replace('*', '') for s in subs]
    subs = [s.replace('#', '') for s in subs]
    subs.append(u'matchthreaddertest')
    subs.append(u'mlslounge')
    subs.append(u'wycombewanderersfc')
    subs.append(u'halamadrid')
    subs.append(u'bih')
    subs.append(u'soccerdev')
    subs.append(u'whufc')
    subs.append(u'coyssandbox')
    subs.append(u'Eabryt')
    subs = [x.lower() for x in subs]
    return subs


def getBotStatus():
    thread = r.submission('22ah8i')
    status = re.findall('bar-10-(.*?)\)', thread.selftext)
    msg = re.findall('\| \*(.*?)\*', thread.selftext)
    return status[0], msg[0]


# get current match time/status
def getStatus(matchID):
    # lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
    lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
    lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
    line_html = lineWebsite.text
    soup = BeautifulSoup(line_html, "lxml")
    # Maybe works: soup.find("div", {"class", "ScoreCell__Time Gamestrip__Time h9 clr-negative"}).text
    if lineWebsite.status_code == 200:
        status = re.findall('"det":"(.*?)"', line_html)[0]
        if ':' in status:
            return 'v'
        else:
            return status

    # return soup.findAll("div",{"class","MatchCommentary__Comment__Timestamp"})[:1][0].text if soup.findAll("div",{"class","MatchCommentary__Comment__Timestamp"}) else 'v'

    # if lineWebsite.status_code == 200:
    #     status = re.findall('<span class="game-time".*?>(.*?)<', line_html, re.DOTALL)
    #     if status == []:
    #         return 'v'
    #     else:
    #         return status[0]
    # else:
    #     return ''


def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])


def guessRightMatch(possibles):
    matchOn = []
    for matchID in possibles:
        status = getStatus(matchID)
        if len(status) > 0:
            matchOn.append(status[0].isdigit())
        else:
            matchOn.append(False)
    stati_int = [int(elem) for elem in matchOn]
    if sum(stati_int) == 1:
        guess = possibles[stati_int.index(1)]
    else:
        guess = possibles[0]
    return guess


def findMatchSite(team1, team2):
    # search for each word in each team name in the fixture list, return most frequent result
    print(getTimestamp() + "Finding ESPN site for " + team1 + " vs " + team2 + "...")
    try:
        t1 = team1.split()
        t2 = team2.split()
        linkList = []
        fixAddress = "http://www.espn.com/soccer/scoreboard"
        fixWebsite = requests.get(fixAddress, timeout=15, headers={'User-Agent': 'Custom'})
        fix_html = fixWebsite.text
        soup = BeautifulSoup(fix_html, "lxml")
        # Grab all the matches on the scoreboard page
        matches = soup.find("div", {"class", "PageLayout__Main"})
        # Find all the competition cards
        comps = matches.findAll("section", {"class", "Card gameModules"})
        # Loop through the comps and investigate each team to find matches.
        for comp in comps:
            matches = comp.findAll("section", {"class", "Scoreboard bg-clr-white flex flex-auto justify-between"})
            for match in matches:
                check = True
                matchID = \
                match.find("a", {"class", "AnchorLink Button Button--sm Button--anchorLink Button--alt mb4 w-100 mr2"})[
                    "href"].split("/")[-1] if match.find("a", {"class",
                                                               "AnchorLink Button Button--sm Button--anchorLink Button--alt mb4 w-100 mr2"}) else ''
                homeTeam, awayTeam = list(
                    map(lambda item: item.text, match.findAll("div", {"class", "ScoreCell__TeamName"})))
                if len(homeTeam) < 0:
                    check = False
                if len(awayTeam) < 0:
                    check = False
                if check:
                    for word in t1:
                        if remove_accents(homeTeam.lower()).find(remove_accents(word.lower())) != -1:
                            linkList.append(matchID)
                        if remove_accents(awayTeam.lower()).find(remove_accents(word.lower())) != -1:
                            linkList.append(matchID)
                    for word in t2:
                        if remove_accents(homeTeam.lower()).find(remove_accents(word.lower())) != -1:
                            linkList.append(matchID)
                        if remove_accents(awayTeam.lower()).find(remove_accents(word.lower())) != -1:
                            linkList.append(matchID)
        counts = Counter(linkList)
        if counts.most_common(1) != []:
            freqs = groupby(counts.most_common(), lambda x: x[1])
            possibles = []
            # freqs.next() is no longer valid in Python3 so we use next(freqs)
            for val, ct in next(freqs)[1]:
                possibles.append(val)
                if len(possibles) > 1:
                    mode = guessRightMatch(possibles)
                else:
                    mode = possibles[0]
            print("complete.")
            return mode
        else:
            print("complete.")
            return 'no match'
    except requests.exceptions.Timeout:
        print("ESPN access timeout")
        return 'no match'

        ### OLD CODE WE'RE REPLACING
        # matches = fix_html.split('window.espn.scoreboardData')[1]
        matches = matches.split('<body class="scoreboard')[0]
        names = matches.split('"text":"Statistics"')
        del names[-1]
        for match in names:
            check = True
            matchID = re.findall('"homeAway":.*?"href":".*?gameId=(.*?)",', match, re.DOTALL)[0][0:6]
            homeTeam = re.findall('"homeAway":"home".*?"team":{.*?"alternateColor".*?"displayName":"(.*?)"', match,
                                  re.DOTALL)
            if len(homeTeam) > 0:
                homeTeam = homeTeam[0]
            else:
                check = False
            awayTeam = re.findall('"homeAway":"away".*?"team":{.*?"alternateColor".*?"displayName":"(.*?)"', match,
                                  re.DOTALL)
            if len(awayTeam) > 0:
                awayTeam = awayTeam[0]
            else:
                check = False
            if check:
                for word in t1:
                    if remove_accents(homeTeam.lower()).find(remove_accents(word.lower())) != -1:
                        linkList.append(matchID)
                    if remove_accents(awayTeam.lower()).find(remove_accents(word.lower())) != -1:
                        linkList.append(matchID)
                for word in t2:
                    if remove_accents(homeTeam.lower()).find(remove_accents(word.lower())) != -1:
                        linkList.append(matchID)
                    if remove_accents(awayTeam.lower()).find(remove_accents(word.lower())) != -1:
                        linkList.append(matchID)
        counts = Counter(linkList)
        if counts.most_common(1) != []:
            freqs = groupby(counts.most_common(), lambda x: x[1])
            possibles = []
            # freqs.next() is no longer valid in Python3 so we use next(freqs)
            for val, ct in next(freqs)[1]:
                possibles.append(val)
                if len(possibles) > 1:
                    mode = guessRightMatch(possibles)
                else:
                    mode = possibles[0]
            print("complete.")
            return mode
        else:
            print("complete.")
            return 'no match'
    except requests.exceptions.Timeout:
        print("ESPN access timeout")
        return 'no match'


def getTeamIDs(matchID):
    try:
        # lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
        line_html = lineWebsite.text
        soup = BeautifulSoup(line_html, "lxml")
        return list(map(lambda item: item["href"].split("/")[-2], soup.findAll("a", {"class", "AnchorLink truncate"})))

        # teamIDs = re.findall('<div class="team-info">(.*?)</div>', line_html, re.DOTALL)
        # if teamIDs != []:
        #     t1id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"', teamIDs[0], re.DOTALL)
        #     t2id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"', teamIDs[1], re.DOTALL)
        #     if t1id != []:
        #         t1id = t1id[0]
        #     else:
        #         t1id = ''
        #     if t2id != []:
        #         t2id = t2id[0]
        #     else:
        #         t2id = ''
        #     return t1id, t2id
        # else:
        #     return '', ''
    except requests.exceptions.Timeout:
        return '', ''


def getPlayerInfo(player):
    playerName = player.find("a", {"class", "AnchorLink SoccerLineUpPlayer__Header__Name"}).text if player.find("a", {
        "class", "AnchorLink SoccerLineUpPlayer__Header__Name"}) else player.text
    tags = ''
    # Need to check if the player has done anything remarkable
    for tag in player.findAll("div", {"class", "SoccerLineUpPlayer__Header__IconWrapper"}):

        if tag.find("svg"):
            tags += '!sub ' if 'Substitution' in tag.find("svg")["aria-label"] else ''
            tags += '!goal ' if 'Goal' in tag.find("svg")["aria-label"] else ''
    playerText = tags + playerName
    return playerText


def getLineUps(matchID):
    try:
        # try to find line-ups
        # lineAddress = "http://www.espnfc.us/lineups?gameId=" + matchID
        lineAddress = "http://www.espn.com/soccer/lineups/_/gameId/" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
        line_html = lineWebsite.text
        soup = BeautifulSoup(line_html, "lxml")
        team1Starters, team2Starters = list(map(lambda item: item.find("tbody"), soup.findAll("div", {"class",
                                                                                                      "ResponsiveTable LineUps__PlayersTable"})))
        team1Subs, team2Subs = list(map(lambda item: item.find("tbody"),
                                        soup.findAll("div", {"class", "ResponsiveTable LineUps__SubstitutesTable"})))

        team1Start = []
        for row in team1Starters.findAll("tr"):
            players = row.findAll("div", {"class", "SoccerLineUpPlayer"})
            # Check if the player was subbed on/off
            if len(players) != 1:
                # player1 = players[0].find("a",{"class", "AnchorLink SoccerLineUpPlayer__Header__Name"})
                player1Text = getPlayerInfo(players[0])
                team1Start.append(player1Text)
                # player2 = players[1].find("a",{"class", "AnchorLink SoccerLineUpPlayer__Header__Name"})
                player2Text = getPlayerInfo(players[1])
                # player2Text += "!sub" + player2
                team1Start.append(player2Text)
            player = getPlayerInfo(row.find("a", {"class", "AnchorLink SoccerLineUpPlayer__Header__Name"}))
            team1Start.append(player)
        team1Sub = []
        for row in team1Subs.findAll("tr"):
            players = row.findAll("div", {"class", "SoccerLineUpPlayer"})
            player = getPlayerInfo(row.find("a", {"class", "AnchorLink SoccerLineUpPlayer__Header__Name"}))
            team1Sub.append(player)
        team2Start = []
        for row in team2Starters.findAll("tr"):
            players = row.findAll("div", {"class", "SoccerLineUpPlayer"})
            # Check if the player was subbed on/off
            if len(players) != 1:
                # player1 = players[0].find("a",{"class", "AnchorLink SoccerLineUpPlayer__Header__Name"})
                player1Text = getPlayerInfo(players[0])
                team2Start.append(player1Text)
                # player2 = players[1].find("a",{"class", "AnchorLink SoccerLineUpPlayer__Header__Name"})
                player2Text = '!sub ' + getPlayerInfo(players[1])
                # player2Text += "!sub" + player2
                team2Start.append(player2Text)
            player = getPlayerInfo(row.find("a", {"class", "AnchorLink SoccerLineUpPlayer__Header__Name"}))
            team2Start.append(player)
        team2Sub = []
        for row in team2Subs.findAll("tr"):
            player = getPlayerInfo(row.find("a", {"class", "AnchorLink SoccerLineUpPlayer__Header__Name"}))
            team2Sub.append(player)

        if not team1Start:
            team1Start = ["*Not available*"]
        if not team1Sub:
            team1Sub = ["*Not available*"]
        if not team2Start:
            team2Start = ["*Not available*"]
        if not team2Sub:
            team2Sub = ["*Not available*"]
        return team1Start, team1Sub, team2Start, team2Sub
    except IndexError:
        logger.warning("[INDEX ERROR:]")
        team1Start = ["*Not available*"]
        team1Sub = ["*Not available*"]
        team2Start = ["*Not available*"]
        team2Sub = ["*Not available*"]
        return team1Start, team1Sub, team2Start, team2Sub
    except ValueError:  # Teams probably aren't announced yet.
        logger.warning("[VALUE ERROR:]")
        team1Start = ["*Not available*"]
        team1Sub = ["*Not available*"]
        team2Start = ["*Not available*"]
        team2Sub = ["*Not available*"]
        return team1Start, team1Sub, team2Start, team2Sub

        # ### OLD Code
        # split = line_html.split('<div class="sub-module soccer">')  # [0]:nonsense [1]:team1 [2]:team2
        #
        # if len(split) > 1:
        #     team1StartBlock = split[1].split('Substitutes')[0]
        #     if len(split[1].split('Substitutes')) > 1:
        #         team1SubBlock = split[1].split('Substitutes')[1]
        #     else:
        #         team1SubBlock = ''
        #     team2StartBlock = split[2].split('Substitutes')[0]
        #     if len(split[2].split('Substitutes')) > 1:
        #         team2SubBlock = split[2].split('Substitutes')[1]
        #     else:
        #         team2SubBlock = ''
        #
        #     team1Start = []
        #     team2Start = []
        #     team1Sub = []
        #     team2Sub = []
        #
        #     t1StartInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team1StartBlock, re.DOTALL)
        #     t1SubInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team1SubBlock, re.DOTALL)
        #     t2StartInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team2StartBlock, re.DOTALL)
        #     t2SubInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team2SubBlock, re.DOTALL)
        #
        #     for playerInfo in t1StartInfo:
        #         playerInfo = playerInfo.replace('\t', '').replace('\n', '')
        #         playerNum = playerInfo[0:6]
        #         if '%' not in playerNum:
        #             playertext = ''
        #             if 'icon-soccer-substitution-before' in playerInfo:
        #                 playertext += '!sub '
        #             if 'icon-yellowcard' in playerInfo:
        #                 playertext += '!yellow '
        #             if 'icon-soccer-goal' in playerInfo:
        #                 playertext += '!goal '
        #             if 'icon-redcard' in playerInfo:
        #                 playertext += '!red '
        #             # playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
        #             playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
        #             playertext = unidecode(playertext).replace("-", " ", 1).title()
        #             team1Start.append(playertext)
        #     for playerInfo in t1SubInfo:
        #         playerInfo = playerInfo.replace('\t', '').replace('\n', '')
        #         playerNum = playerInfo[0:6]
        #         if '%' not in playerNum:
        #             playertext = ''
        #             if 'icon-yellowcard' in playerInfo:
        #                 playertext += '!yellow '
        #             if 'icon-soccer-goal' in playerInfo:
        #                 playertext += '!goal '
        #             # playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
        #             playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
        #             playertext = unidecode(playertext).replace("-", " ", 1).title()
        #             team1Sub.append(playertext)
        #     for playerInfo in t2StartInfo:
        #         playerInfo = playerInfo.replace('\t', '').replace('\n', '')
        #         playerNum = playerInfo[0:6]
        #         if '%' not in playerNum:
        #             playertext = ''
        #             if 'icon-soccer-substitution-before' in playerInfo:
        #                 playertext += '!sub '
        #             if 'icon-yellowcard' in playerInfo:
        #                 playertext += '!yellow '
        #             if 'icon-soccer-goal' in playerInfo:
        #                 playertext += '!goal '
        #             # playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
        #             playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
        #             playertext = unidecode(playertext).replace("-", " ", 1).title()
        #             team2Start.append(playertext)
        #     for playerInfo in t2SubInfo:
        #         playerInfo = playerInfo.replace('\t', '').replace('\n', '')
        #         playerNum = playerInfo[0:6]
        #         if '%' not in playerNum:
        #             playertext = ''
        #             if 'icon-yellowcard' in playerInfo:
        #                 playertext += '!yellow '
        #             if 'icon-soccer-goal' in playerInfo:
        #                 playertext += '!goal '
        #             # playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
        #             playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
        #             playertext = unidecode(playertext).replace("-", " ", 1).title()
        #             team2Sub.append(playertext)
        #     # if no players found:
        #     if team1Start == []:
        #         team1Start = ["*Not available*"]
        #     if team1Sub == []:
        #         team1Sub = ["*Not available*"]
        #     if team2Start == []:
        #         team2Start = ["*Not available*"]
        #     if team2Sub == []:
        #         team2Sub = ["*Not available*"]
        #     return team1Start, team1Sub, team2Start, team2Sub
        #
        # else:
        #     team1Start = ["*Not available*"]
        #     team1Sub = ["*Not available*"]
        #     team2Start = ["*Not available*"]
        #     team2Sub = ["*Not available*"]
        #     return team1Start, team1Sub, team2Start, team2Sub


# get venue, ref, lineups, etc from ESPN
def getMatchInfo(matchID):
    # lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
    lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
    print(getTimestamp() + "Finding ESPNFC info from " + lineAddress + "...", )
    try:
        lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
    except:
        lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
    line_html = lineWebsite.text
    soup = BeautifulSoup(line_html, "lxml")

    # get "fixed" versions of team names (ie team names from ESPNFC, not team names from match thread request)

    team1, team2 = list(map(lambda item: item.text, soup.findAll("h2", {"class",
                                                                        "ScoreCell__TeamName ScoreCell__TeamName--displayName truncate db"})))
    t1id, t2id = getTeamIDs(matchID)
    status = getStatus(matchID)
    ko_info = datetime.datetime.strptime(soup.find("div", {"class", "n8 GameInfo__Meta"}).find("span").text,
                                         "%I:%M %p, %B %d, %Y")
    ko_date, ko_day, ko_time = ko_info.date(), ko_info.day, ko_info.time()
    venue = soup.find("div", {"class", "n6 clr-gray-03 GameInfo__Location__Name--noImg"}).text or "?"
    comp = soup.find("div", {"ScoreCell__GameNote di"}).text.split(" ", 1)[1].split(",", 1)[0] or ""

    team1Start, team1Sub, team2Start, team2Sub = getLineUps(matchID)
    print("complete.")
    return (
        team1, t1id, team2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status,
        comp)

    #### OLD CODE We're replacing!!
    # team1fix = re.findall('<span class="long-name">(.*?)<', line_html, re.DOTALL)[0]
    # team2fix = re.findall('<span class="long-name">(.*?)<', line_html, re.DOTALL)[1]
    # t1id, t2id = getTeamIDs(matchID)
    #
    # if team1fix[-1] == ' ':
    #     team1fix = team1fix[0:-1]
    # if team2fix[-1] == ' ':
    #     team2fix = team2fix[0:-1]
    #
    # status = getStatus(matchID)
    # ko_date = re.findall('<span data-date="(.*?)T', line_html, re.DOTALL)
    # if ko_date != []:
    #     ko_date = ko_date[0]
    #     ko_day = ko_date[8:]
    #     ko_time = re.findall('<span data-date=".*?T(.*?)Z', line_html, re.DOTALL)[0]
    #     # above time is actually 4 hours from now (ESPN time in source code)
    # else:
    #     ko_day = ''
    #     ko_time = ''
    #
    # venue = re.findall('<div>VENUE: (.*?)<', line_html, re.DOTALL)
    # if venue != []:
    #     venue = venue[0]
    # else:
    #     venue = '?'
    #
    # compfull = re.findall('<div class="game-details header">(.*?)<', line_html, re.DOTALL)
    # if compfull != []:
    #     comp = re.sub('20.*? ', '', compfull[0]).strip(' \n\t\r')
    #     if comp.find(',') != -1:
    #         comp = comp[0:comp.index(',')]
    # else:
    #     comp = ''
    #
    # team1Start, team1Sub, team2Start, team2Sub = getLineUps(matchID)
    # print("complete.")
    # return (
    #     team1fix, t1id, team2fix, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status,
    #     comp)


def getSprite(teamID, sub):
    customCrestSubs = ['mls']
    crestFile = 'crests.txt'
    if sub in customCrestSubs:
        crestFile = sub + crestFile
    lines = [line.rstrip('\n') for line in open(crestFile)]
    for line in lines:
        if line != '' and not line.startswith('||'):
            line = line.split('\t')[len(line.split('\t')) - 1]
            split = line.split('::')
            EID = split[0]
            sprite = split[1]
            if EID == teamID:
                return sprite
    return ''


def writeLineUps(sub, body, t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub):
    markup = loadMarkup(sub)
    t1sprite = ''
    t2sprite = ''
    if sub.lower() in spriteSubs and getSprite(t1id, sub) != '' and getSprite(t2id, sub) != '':
        t1sprite = getSprite(t1id, sub) + ' '
        t2sprite = getSprite(t2id, sub) + ' '

    body += '**LINE-UPS**\n\n**' + t1sprite + t1 + '**\n\n'
    linestring = ''
    for name in team1Start:
        if any(event in name for event in events):
            temp = ''
            if '!sub' in name:
                temp += ' ('
            else:
                temp += ', '
            if '!sub' in name:
                temp += markup[subst]
                name = name.replace("!sub", "").strip()
            if '!yellow' in name:
                temp += markup[yel]
                name = name.replace("!yellow", "").strip()
            if '!red' in name:
                temp += markup[red]
                name = name.replace("!red", "").strip()
            if '!goal' in name:
                temp += markup[goal]
                name = name.replace("!goal", " ").strip()
            temp += name
            if 'subs' in temp:
                temp += ')'
            linestring += temp
        else:
            linestring += ', ' + name
    linestring = linestring[2:] + '.\n\n'
    body += linestring + '**Subs:** '
    body += ", ".join(x for x in team1Sub) + ".\n\n^____________________________\n\n"

    body += '**' + t2sprite + t2 + '**\n\n'
    linestring = ''
    for name in team2Start:
        if any(event in name for event in events):
            temp = ''
            if '!sub' in name:
                temp += ' ('
            else:
                temp += ', '
            if '!sub' in name:
                temp += markup[subst]
                name = name.replace("!sub", "").strip()
            if '!yellow' in name:
                temp += markup[yel]
                name = name.replace("!yellow", "").strip()
            if '!red' in name:
                temp += markup[red]
                name = name.replace("!red", "").strip()
            if '!goal' in name:
                temp += markup[goal]
                name = name.replace("!goal", " ").strip()
            temp += name
            if 'subs' in temp:
                temp += ')'
            linestring += temp
        else:
            linestring += ', ' + name
    linestring = linestring[2:] + '.\n\n'
    body += linestring + '**Subs:** '
    body += ", ".join(x for x in team2Sub) + "."

    return body


# def customLineUps(matchID,t1lineups,t2lineups):


def grabEvents(matchID, sub):
    markup = loadMarkup(sub)
    # lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
    lineAddress = "http://www.espn.com/soccer/commentary/_/gameId/" + matchID

    #    print getTimestamp() + "Grabbing events from " + lineAddress + "...",
    lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
    line_html = lineWebsite.text
    soup = BeautifulSoup(line_html, "lxml")
    try:
        if lineWebsite.status_code == 200:
            body = ""
            # split_all = line_html.split('<h1>Match Commentary</h1>')  # [0]:stuff [1]:commentary + key events
            # split = split_all[1].split('<h1>Key Events</h1>')  # [0]:commentary [1]: key events
            #
            # events = re.findall('<tr data-id=(.*?)</tr>', split[0], re.DOTALL)
            # events = events[::-1]

            events = soup.find("div", {"class", "Wrapper Card__Content MatchCommentary__Content"})


            # will only report goals (+ penalties, own goals), yellows, reds, subs
            supportedEvents = ['goal', 'goal---header', 'goal---free-kick', 'penalty---scored', 'own-goal',
                               'penalty---missed', 'penalty---saved', 'yellow-card', 'red-card', 'substitution', 'offside']
            for row in events.findAll("tr"):
                time = row.find("div",{"class","MatchCommentary__Comment__Timestamp"}).text.strip()
                event = row.find("div",{"class","MatchCommentary__Comment__GameDetails"}).text.strip()
                info = "**" + time + "** "
                try:
                    tag = row.find("div",{"class","MatchCommentary__Comment__PlayIcon"}).find("svg")["aria-label"]
                except TypeError:
                    tag = ""
                if tag.lower() in supportedEvents:
                    # time = re.findall('"time-stamp">(.*?)<', event, re.DOTALL)[0]
                    # time = time.strip()
                    # info = "**" + time + "** "
                    # event = re.findall('"game-details">(.*?)<', event, re.DOTALL)[0].strip()
                    if tag.lower().startswith('goal') or tag.lower() == 'penalty---scored' or tag.lower() == 'own-goal':
                        if tag.lower().startswith('goal'):
                            info += markup[goal] + ' **' + event + '**'
                        elif tag.lower() == 'penalty---scored':
                            info += markup[pgoal] + ' **' + event + '**'
                        else:
                            info += markup[ogoal] + ' **' + event + '**'
                    if tag.lower() == 'penalty---missed' or tag.lower() == 'penalty---saved':
                        info += markup[mpen] + ' **' + event + '**'
                    if tag.lower() == 'yellow-card':
                        info += markup[yel] + ' ' + event
                    if tag.lower() == 'red-card':
                        info += markup[red] + ' ' + event
                    if tag.lower() == 'substitution':
                        info += markup[subst] + ' ' + event
                    if tag.lower() == 'offside':
                        info += markup[offs] + ' ' + event
                    body += info + '\n\n'
                else:
                    if "- type" in tag.lower():
                        continue
                    info += event
                    body += info + '\n\n'
            #        print "complete."
            return body

        else:
            #        print "failed."
            return ""
    except:
        #        print "edit failed"
        logger.exception('[EDIT ERROR:]')
        return ""


def getTimes(ko):
    hour = f'{ko.hour:02}'
    minute = f'{ko.minute:02}'
    hour_i = int(hour)
    min_i = int(minute)

    now = datetime.datetime.now()
    return (hour_i, min_i, now)


# attempt submission to subreddit
def submitThread(sub, title):
    print(getTimestamp() + "Submitting " + title + "...", )
    try:
        thread = r.subreddit(sub).submit(title, selftext='**Venue:**\n\n**LINE-UPS**', send_replies=False)
        print("complete.")
        return True, thread
    except:
        print("failed.")
        logger.exception("[SUBMIT ERROR:]")
        return False, ''


# create a new thread using provided teams    
def createNewThread(team1, team2, reqr, sub):
    print(f'{getTimestamp()}Match requested by /u/{reqr}')
    matchID = findMatchSite(team1, team2)
    if matchID != 'no match':
        gotinfo = False
        while not gotinfo:
            try:
                t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status, comp = getMatchInfo(
                    matchID)
                gotinfo = True
            except requests.exceptions.Timeout:
                print(getTimestamp() + "ESPNFC access timeout for " + team1 + " vs " + team2)

        botstat, statmsg = getBotStatus()
        # don't make a post if there's some fatal error
        if botstat == 'red':
            print(getTimestamp() + "Denied " + t1 + " vs " + t2 + " request for - status set to red")
            logger.info("Denied %s vs %s request - status set to red", t1, t2)
            return 8, ''

        # only post to related subreddits
        relatedsubs = getRelatedSubreddits()
        if sub.lower() not in relatedsubs:
            print(getTimestamp() + "Denied post request to /r/" + sub + " - not related")
            logger.info("Denied post request to %s - not related", sub)
            return 6, ''

        # don't post if user is blacklisted
        if reqr in usrblacklist:
            print(getTimestamp() + "Denied post request from /u/" + reqr + " - blacklisted")
            logger.info("Denied post request from %s - blacklisted", reqr)
            return 9, ''

        # don't create a thread if the bot already made it or if user already has an active thread
        for d in activeThreads:
            matchID_at, t1_at, t2_at, id_at, reqr_at, sub_at = d
            if t1 == t1_at and sub == sub_at:
                print(
                    getTimestamp() + "Denied " + t1 + " vs " + t2 + " request for /r/" + sub + " - thread already exists")
                logger.info("Denied %s vs %s request for %s - thread already exists", t1, t2, sub)
                return 4, id_at
            if reqr == reqr_at and reqr not in usrwhitelist:
                print(getTimestamp() + "Denied post request from /u/" + reqr + " - has an active thread request")
                logger.info("Denied post request from %s - has an active thread request", reqr)
                return 7, ''

        # don't create a thread if the match is done (probably found the wrong match)
        if reqr != admin:
            if status.startswith('FT') or status == 'AET':
                print(getTimestamp() + "Denied " + t1 + " vs " + t2 + " request - match appears to be finished")
                logger.info("Denied %s vs %s request - match appears to be finished", t1, t2)
                return 3, ''

        # don't create a thread more than 10 minutes before kickoff
        if sub.lower() not in timewhitelist or sub.lower() in timewhitelist and reqr.lower() not in timewhitelist[
            sub.lower()]:
            hour_i, min_i, now = getTimes(ko_time)
            now_f = now + datetime.timedelta(minutes=10)
            if ko_day == '':
                return 1, ''
            if now_f.day < int(ko_day):
                print(getTimestamp() + "Denied " + t1 + " vs " + t2 + " request - more than 10 minutes to kickoff")
                logger.info("Denied %s vs %s request - more than 10 minutes to kickoff", t1, t2)
                return 2, ''
            if now_f.hour < hour_i:
                print(getTimestamp() + "Denied " + t1 + " vs " + t2 + " request - more than 10 minutes to kickoff")
                logger.info("Denied %s vs %s request - more than 10 minutes to kickoff", t1, t2)
                return 2, ''
            if (now_f.hour == hour_i) and (now_f.minute < min_i):
                print(getTimestamp() + "Denied " + t1 + " vs " + t2 + " request - more than 10 minutes to kickoff")
                logger.info("Denied %s vs %s request - more than 10 minutes to kickoff", t1, t2)
                return 2, ''

        title = 'Match Thread: ' + t1 + ' vs ' + t2
        if comp != '':
            title = title + ' [' + comp + ']'
        result, thread = submitThread(sub, title)

        # if subreddit was invalid, notify
        if result == False:
            return 5, ''

        short = thread.shortlink
        # id = short[short.index('.it/')+4:].encode("utf8")
        id = short[short.index('.it/') + 4:]
        redditstream = 'http://www.reddit-stream.com/comments/' + id

        data = matchID, t1, t2, id, reqr, sub
        activeThreads.append(data)
        saveData()
        print(getTimestamp() + "Active threads: " + str(
            len(activeThreads)) + " - added " + t1 + " vs " + t2 + " (/r/" + sub + ")")
        logger.info("Active threads: %i - added %s vs %s (/r/%s)", len(activeThreads), t1, t2, sub)

        if status == 'v':
            status = "0'"
        if status == '-':
            status = "FT"

        markup = loadMarkup(sub)

        if sub.lower() in spriteSubs:
            t1sprite = ''
            t2sprite = ''
            if getSprite(t1id, sub) != '' and getSprite(t2id, sub) != '':
                t1sprite = getSprite(t1id, sub)
                t2sprite = getSprite(t2id, sub)
            body = '#**' + status + ': ' + t1 + ' ' + t1sprite + ' [vs](#bar-3-white) ' + t2sprite + ' ' + t2 + '**\n\n'

        else:
            body = '#**' + status + ": " + t1 + ' vs ' + t2 + '**\n\n'
            body += '**Venue:** ' + venue + '\n\n'
            body += '[Auto-refreshing reddit comments link](' + redditstream + ')\n\n---------\n\n'
            body += '[Follow us on Twitter](https://twitter.com/rslashgunners)\n\n'
        body += '[Join us on Discord](https://discord.gg/erHA8y9)\n\n---------\n\n'

        body += markup[lines] + ' '
        body = writeLineUps(sub, body, t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub)

        # [^[Request ^a ^match ^thread]](http://www.reddit.com/message/compose/?to=MatchThreadder&subject=Match%20Thread&message=Team%20vs%20Team) ^| [^[Request ^a ^thread ^template]](http://www.reddit.com/message/compose/?to=MatchThreadder&subject=Match%20Info&message=Team%20vs%20Team) ^| [^[Current ^status ^/ ^bot ^info]](http://www.reddit.com/r/soccer/comments/22ah8i/introducing_matchthreadder_a_bot_to_set_up_match/)"

        body += '\n\n------------\n\n' + markup[
            evnts] + ' **MATCH EVENTS** | *via [ESPNFC](http://www.espnfc.us/commentary?gameId=' + matchID + ')*\n\n'

        if botstat != 'green':
            body += '*' + statmsg + '*\n\n'

        thread.edit(body)
        sleep(5)

        return 0, id
    else:
        print(getTimestamp() + "Could not find match info for " + team1 + " vs " + team2)
        logger.info("Could not find match info for %s vs %s", team1, team2)
        return 1, ''


# if the requester just wants a template
def createMatchInfo(team1, team2):
    matchID = findMatchSite(team1, team2)
    if matchID != 'no match':
        t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status, comp = getMatchInfo(
            matchID)

        markup = loadMarkup('soccer')

        body = '#**' + status + ": " + t1 + ' vs ' + t2 + '**\n\n'

        body += '**Venue:** ' + venue + '\n\n--------\n\n'
        body += markup[lines] + ' '
        body = writeLineUps('soccer', body, t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub)

        body += '\n\n------------\n\n' + markup[evnts] + ' **MATCH EVENTS**\n\n'

        logger.info("Provided info for %s vs %s", t1, t2)
        print(getTimestamp() + "Provided info for " + t1 + " vs " + t2)
        return 0, body
    else:
        return 1, ''


# delete a thread (on admin request)
def deleteThread(id):
    try:
        if '//' in id:
            id = re.findall('comments/(.*?)/', id)[0]
        thread = r.submission(id)
        for data in activeThreads:
            matchID, team1, team2, thread_id, reqr, sub = data
            if thread_id == id:
                thread.delete()
                activeThreads.remove(data)
                logger.info("Active threads: %i - removed %s vs %s (/r/%s)", len(activeThreads), team1, team2, sub)
                print(getTimestamp() + "Active threads: " + str(
                    len(activeThreads)) + " - removed " + team1 + " vs " + team2 + " (/r/" + sub + ")")
                saveData()
                return team1 + ' vs ' + team2
        return ''
    except:
        return ''


# remove incorrectly made thread if requester asks within 5 minutes of creation
def removeWrongThread(id, req):
    try:
        thread = r.submission(id)
        dif = datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(thread.created_utc)
        for data in activeThreads:
            matchID, team1, team2, thread_id, reqr, sub = data
            if thread_id == id:
                if reqr != req:
                    return 'req'
                if dif.days != 0 or dif.seconds > 300:
                    return 'time'
                thread.delete()
                activeThreads.remove(data)
                logger.info("Active threads: %i - removed %s vs %s (/r/%s)", len(activeThreads), team1, team2, sub)
                print(getTimestamp() + "Active threads: " + str(
                    len(activeThreads)) + " - removed " + team1 + " vs " + team2 + " (/r/" + sub + ")")
                saveData()
                return team1 + ' vs ' + team2
        return 'thread'
    except:
        return 'thread'


# default attempt to find teams: split input in half, left vs right    
def firstTryTeams(msg):
    t = msg.split()
    spl = len(t) // 2
    t1 = t[0:spl]
    t2 = t[spl + 1:]
    t1s = ''
    t2s = ''
    for word in t1:
        t1s += word + ' '
    for word in t2:
        t2s += word + ' '
    t1s = unidecode(t1s)
    t2s = unidecode(t2s)
    return [t1s, t2s]


# check for new mail, create new threads if needed
def checkAndCreate():
    if len(activeThreads) > 0:
        print(getTimestamp() + "Checking messages...")
    delims = [' x ', ' - ', ' v ', ' vs ']
    # unread_messages = []
    subdel = ' for '
    for msg in r.inbox.unread(limit=None):
        msg.mark_read()
        # if isinstance(msg, Message):
        #    unread_messages.append(msg)
        sub = subreddit
        if msg.subject.lower() == 'match thread':
            subreq = msg.body.split(subdel, 2)
            if subreq[0] != msg.body:
                sub = subreq[1].split('/')[-1]
                sub = sub.lower()
                sub = sub.strip()
            teams = firstTryTeams(subreq[0])
            for delim in delims:
                attempt = subreq[0].split(delim, 2)
                if attempt[0] != subreq[0]:
                    teams = attempt
            # euroteams = ['italy','republic of ireland','ireland','sweden','belgium','iceland','austria','hungary','portugal','switzerland','poland','croatia','wales','germany','spain','france','england']
            # if teams[0].lower() in euroteams or teams[1].lower() in euroteams:
            # msg.reply("Sorry, this bot can't be used for Euro 2016 matches. [Look here](https://www.reddit.com/r/soccer/wiki/matchthreads) for templates, tips, and example match threads from the past if you want to know how to you make your own match thread!\n\n--------------\n\n[^Why ^doesn't ^the ^bot ^work ^for ^Euro ^2016?](https://www.reddit.com/r/soccer/comments/4oun18/match_thread_switzerland_vs_france_euro_2016/d4fn9n8)")
            # print getTimestamp() + "Denied a Euro 2016 thread: " + msg.body
            # else:
            threadStatus, thread_id = createNewThread(teams[0], teams[1], msg.author.name, sub)
            if messaging:
                if threadStatus == 0:  # thread created successfully
                    print(getTimestamp() + username + " requested match thread. ")
                    msg.reply("[Here](http://www.reddit.com/r/" + sub + "/comments/" + str(
                        thread_id) + ") is a link to the thread you've requested. Thanks for using this "
                                     "bot!\n\n-------------------------\n\n*Did I create a thread for the wrong "
                                     "match? [Click here and press send](http://www.reddit.com/message/compose/?to="
                              + username + "&subject=delete&message=" + str(
                        thread_id) + ") to delete the thread (note: this will only work within five minutes of the "
                                     "thread's creation). This probably means that I can't find the right match - "
                                     "sorry!*")
                    if notify:
                        r.send_message(admin, "Match thread request fulfilled",
                                       "/u/" + msg.author.name + " requested " + teams[0] + " vs " + teams[
                                           1] + " in /r/" + sub + ". \n\n[Thread link](http://www.reddit.com/r/" + sub +
                                       "/comments/" + thread_id + ") | "
                                        "[Deletion link](http://www.reddit.com/message/compose/?to=" + username +
                                       "&subject=delete&message=" + thread_id + ")")
                if threadStatus == 1:  # not found
                    msg.reply(
                        "Sorry, I couldn't find info for that match. If the match you requested appears on [this "
                        "page](http://www.espnfc.us/scores), please let /u/eabryt know about this "
                        "error.\n\n-------------------------\n\n*Why not run your own match thread? [Look here]("
                        "https://www.reddit.com/r/soccer/wiki/matchthreads) for templates, tips, and example match "
                        "threads from the past if you're not sure how.*\n\n*You could also check out these match "
                        "thread creation tools from /u/afito and /u/Mamu7490:*\n\n*[RES Templates]("
                        "https://www.reddit.com/r/soccer/comments/3ndd7b/matchthreads_for_beginners_the_easy_way/)*\n"
                        "\n*[MTmate]("
                        "https://www.reddit.com/r/soccer/comments/3huyut/release_v09_of_mtmate_matchthread_generator"
                        "/)*")
                if threadStatus == 2:  # before kickoff
                    msg.reply(
                        "Please wait until at least 10 minutes to kickoff to send me a thread request, just in case "
                        "someone does end up making one themselves. Thanks!\n\n-------------------------\n\n*Why not "
                        "run your own match thread? [Look here](https://www.reddit.com/r/soccer/wiki/matchthreads) "
                        "for templates, tips, and example match threads from the past if you're not sure "
                        "how.*\n\n*You could also check out these match thread creation tools from /u/afito and "
                        "/u/Mamu7490:*\n\n*[RES Templates]("
                        "https://www.reddit.com/r/soccer/comments/3ndd7b/matchthreads_for_beginners_the_easy_way/)*\n"
                        "\n*[MTmate]("
                        "https://www.reddit.com/r/soccer/comments/3huyut/release_v09_of_mtmate_matchthread_generator"
                        "/)*")
                if threadStatus == 3:  # after full time - probably found the wrong match
                    msg.reply(
                        "Sorry, I couldn't find a currently live match with those teams - are you sure the match has "
                        "started (and hasn't finished)? If you think this is a mistake, it probably means I can't "
                        "find that match.\n\n-------------------------\n\n*Why not run your own match thread? [Look "
                        "here](https://www.reddit.com/r/soccer/wiki/matchthreads) for templates, tips, and example "
                        "match threads from the past if you're not sure how.*\n\n*You could also check out these "
                        "match thread creation tools from /u/afito and /u/Mamu7490:*\n\n*[RES Templates]("
                        "https://www.reddit.com/r/soccer/comments/3ndd7b/matchthreads_for_beginners_the_easy_way/)*\n"
                        "\n*[MTmate]("
                        "https://www.reddit.com/r/soccer/comments/3huyut/release_v09_of_mtmate_matchthread_generator"
                        "/)*")
                if threadStatus == 4:  # thread already exists
                    msg.reply(
                        "There is already a [match thread](http://www.reddit.com/r/" + sub + "/comments/" + thread_id +
                        ") for that game. Join the discussion there!")
                if threadStatus == 5:  # invalid subreddit
                    msg.reply(
                        "Sorry, I couldn't post to /r/" + sub + ". It may not exist, or I may have hit a posting limit.")
                if threadStatus == 6:  # sub blacklisted
                    msg.reply(
                        "Sorry, I can't post to /r/" + sub + ". Please message /u/" + admin +
                        " if you think this is a mistake.")
                if threadStatus == 7:  # thread limit
                    msg.reply("Sorry, you can only have one active thread request at a time.")
                if threadStatus == 8:  # status set to red
                    msg.reply(
                        "Sorry, the bot is currently unable to post threads. Check with /u/" + admin +
                        " for more info; this should hopefully be resolved soon.")
                if threadStatus == 9:  # Non-Arsenal team
                    msg.reply("Sorry, this bot only works for Arsenal matches.")

        if msg.subject.lower() == 'match info':
            teams = firstTryTeams(msg.body)
            for delim in delims:
                attempt = msg.body.split(delim, 2)
                if attempt[0] != msg.body:
                    teams = attempt
            threadStatus, text = createMatchInfo(teams[0], teams[1])
            if threadStatus == 0:  # successfully found info
                msg.reply(
                    "Below is the information for the match you've requested.\n\nIf you're using [RES]("
                    "http://redditenhancementsuite.com/), you can use the 'source' button below this message to "
                    "copy/paste the exact formatting code. If you aren't, you'll have to add the formatting "
                    "yourself.\n\n----------\n\n" + text)
            if threadStatus == 1:  # not found
                msg.reply(
                    "Sorry, I couldn't find info for that match. In the future I'll account for more matches around "
                    "the world.")

        if msg.subject.lower() == 'delete':
            if msg.author.name == admin:
                name = deleteThread(msg.body)
                if messaging:
                    if name != '':
                        msg.reply("Deleted " + name)
                    else:
                        msg.reply("Thread not found")
            else:
                name = removeWrongThread(msg.body, msg.author.name)
                if messaging:
                    if name == 'thread':
                        msg.reply("Thread not found - please double-check thread ID")
                    elif name == 'time':
                        msg.reply(
                            "This thread is more than five minutes old - thread deletion from now is an admin feature "
                            "only. You can message /u/" + admin + " if you'd still like the thread to be deleted.")
                    elif name == 'req':
                        msg.reply(
                            "Username not recognised. Only the thread requester and bot admin have access to this "
                            "feature.")
                    else:
                        msg.reply("Deleted " + name)
    if len(activeThreads) > 0:
        print(getTimestamp() + "All messages checked.")
    # r.inbox.mark_read(unread_messages)


def getExtraInfo(matchID):
    try:
        # lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15)
        line_html = lineWebsite.text
        info = re.findall('data-stat="note">(.*?)<', line_html, re.DOTALL)
        if info == []:
            return ''
        else:
            return info[0]
    except requests.exceptions.Timeout:
        return ''


# update score, scorers
def updateScore(matchID, t1, t2, sub):
    try:
        # lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15, headers={'User-Agent': 'Custom'})
        line_html = lineWebsite.text
        soup = BeautifulSoup(line_html, "lxml")
        try:
            leftScore, rightScore = list(map(lambda item: item.text, soup.findAll("div", {"class","Gamestrip__ScoreContainer flex flex-column items-center justify-center relative"})))
        except ValueError:  # Game has probably not started yet.
            leftScore, rightScore = '0', '0'
        info = getExtraInfo(matchID)
        status = getStatus(matchID)
        ESPNUpdating = True
        if status == 'v':
            status = "0'"
            ESPNUpdating = False

        #
        # leftInfo = re.findall('<div class="team-info players"(.*?)</div>', line_html, re.DOTALL)[0]
        # rightInfo = re.findall('<div class="team-info players"(.*?)</div>', line_html, re.DOTALL)[1]
        #
        # leftGoals = re.findall('data-event-type="goal"(.*?)</ul>', leftInfo, re.DOTALL)
        # rightGoals = re.findall('data-event-type="goal"(.*?)</ul>', rightInfo, re.DOTALL)
        allGoals = soup.find("div",{"class", "SoccerPerformers SoccerPerformers--Comparison SoccerPerformers--gamepackage"})
        if allGoals:
            leftGoals = allGoals.find("div",{"class","SoccerPerformers__Competitor--left"}).find("div",{"class","SoccerPerformers__Competitor__Info"})
            rightGoals = allGoals.find("div",{"class", "SoccerPerformers__Competitor--right"}).find("div",{"class","SoccerPerformers__Competitor__Info"})
        else:
            leftGoals, rightGoals = [],[]

        if leftGoals:
            leftScorers = leftGoals.find("ul").text
        else:
            leftScorers = []
        if rightGoals:
            rightScorers = rightGoals.find("ul").text
        else:
            rightScorers = []

        t1id, t2id = getTeamIDs(matchID)
        if sub.lower() in spriteSubs:
            t1sprite = ''
            t2sprite = ''
            if getSprite(t1id, sub) != '' and getSprite(t2id, sub) != '':
                t1sprite = getSprite(t1id, sub)
                t2sprite = getSprite(t2id, sub)
            text = '#**' + status + ': ' + t1 + ' ' + t1sprite + ' [' + leftScore + '-' + rightScore + '](#bar-3-white) ' + t2sprite + ' ' + t2 + '**\n\n'
        else:
            text = '#**' + status + ": " + t1 + ' ' + leftScore + '-' + rightScore + ' ' + t2 + '**\n\n'
        if not ESPNUpdating:
            text += '*If the match has started, ESPNFC might not be providing updates for this game.*\n\n'

        if info != '':
            text += '***' + info + '***\n\n'

        left = ''
        if leftScorers:
            left += f"*{t1} scorers: {leftScorers}* "

        right = ''
        if rightScorers:
            right += f"*{t2} scorers: {rightScorers}* "

        text += left + '\n\n' + right

        return text
    except requests.exceptions.Timeout:
        return '#**--**\n\n'



# update all current threads            
def updateThreads():
    toRemove = []

    for data in activeThreads:
        finished = False
        index = activeThreads.index(data)
        matchID, team1, team2, thread_id, reqr, sub = data
        thread = r.submission(thread_id)
        body = thread.selftext
        # print getTimestamp() + team1 + ' ' + team2
        venueIndex = body.index('**Venue:**')

        markup = loadMarkup(subreddit)

        # detect if finished
        if getStatus(matchID) == 'FT' or getStatus(matchID) == 'AET' or getStatus(matchID) == 'Abandoned':
            finished = True
        elif getStatus(matchID) == 'FT-Pens':
            info = getExtraInfo(matchID)
            if 'wins' in info or 'win' in info:
                info = info.replace('wins', 'win')
                finished = True

        # update lineups
        team1Start, team1Sub, team2Start, team2Sub = getLineUps(matchID)
        lineupIndex = body.index('**LINE-UPS**')
        bodyTilThen = body[venueIndex:lineupIndex]

        t1id, t2id = getTeamIDs(matchID)
        newbody = writeLineUps(sub, bodyTilThen, team1, t1id, team2, t2id, team1Start, team1Sub, team2Start, team2Sub)
        newbody += '\n\n------------\n\n' + markup[
            evnts] + ' **MATCH EVENTS** | *via [ESPNFC](http://www.espnfc.us/commentary?gameId=' + matchID + ')*\n\n'

        botstat, statmsg = getBotStatus()
        if botstat != 'green':
            newbody += '*' + statmsg + '*\n\n'

        # update scorelines
        score = updateScore(matchID, team1, team2, sub)
        newbody = score + '\n\n--------\n\n' + newbody

        events = grabEvents(matchID, sub)
        newbody += '\n\n' + events

        # save data
        if newbody != body:
            logger.info("Making edit to %s vs %s (/r/%s)", team1, team2, sub)
            print(getTimestamp() + "Making edit to " + team1 + " vs " + team2 + " (/r/" + sub + ")")
            thread.edit(newbody)
            saveData()
        newdata = matchID, team1, team2, thread_id, reqr, sub
        activeThreads[index] = newdata

        if finished:
            toRemove.append(newdata)

    for getRid in toRemove:
        activeThreads.remove(getRid)
        logger.info("Active threads: %i - removed %s vs %s (/r/%s)", len(activeThreads), getRid[1], getRid[2],
                    getRid[5])
        print(
            getTimestamp() + "Active threads: " + str(len(activeThreads)) + " - removed " + getRid[1] + " vs " + getRid[
                2] + " (/r/" + getRid[5] + ")")
        pmt.main(matchID)
        saveData()


logger = logging.getLogger('a')
logger.setLevel(logging.INFO)
logfilename = 'log.log'
handler = logging.handlers.RotatingFileHandler(logfilename, maxBytes=50000, backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.warning("[STARTUP]")
print(getTimestamp() + "[STARTUP]")

r, admin, username, password, subreddit, user_agent, id, secret, redirect = setup()
readData()

if len(sys.argv) > 1:
    if sys.argv[1] == '--reset':
        resetAll()
    if sys.argv[1] == '--flush':
        flushMsgs()

running = True
retries = 0
while running:
    try:
        if retries >= 60:
            resetAll()
            flushMsgs()
        checkAndCreate()
        updateThreads()
        retries = 0
        sleep(60)
    except KeyboardInterrupt:
        logger.warning("[MANUAL SHUTDOWN]")
        print(getTimestamp() + "[MANUAL SHUTDOWN]\n")
        running = False
    except praw.exceptions.APIException:
        retries += 1
        print(getTimestamp() + "API error, check log file [retries = " + str(retries) + "]")
        logger.exception("[API ERROR:]")
        sleep(60)
    except UnicodeDecodeError:
        retries += 1
        print(getTimestamp() + "UnicodeDecodeError, check log file [retries = " + str(retries) + "]")
        logger.exception("[UNICODE ERROR:]")
        flushMsgs()
    except UnicodeEncodeError:
        retries += 1
        print(getTimestamp() + "UnicodeEncodeError, check log file [retries = " + str(retries) + "]")
        logger.exception("[UNICODE ERROR:]")
        flushMsgs()
    except Exception:
        retries += 1
        print(getTimestamp() + "Unknown error, check log file [retries = " + str(retries) + "]")
        logger.exception("[UNKNOWN ERROR:]")
        sleep(60)
