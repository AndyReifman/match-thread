#!/usr/bin/python3
# -*- coding: utf-8 -*-
import datetime
import logging.handlers
import os
import re
from collections import Counter
from itertools import groupby
from time import sleep

import praw
import requests
import requests.auth
import unicodedata
from bs4 import BeautifulSoup

# browser header (to avoid 405 error)
hdr = {
    'User-Agent':
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
    'Accept-Encoding': 'none',
    'Accept-Language': 'en-US,en;q=0.8',
    'Connection': 'keep-alive'}

messaging = True
sub = 'gunners'
spriteSubs = ['soccer', 'Gunners', 'fcbayern', 'soccerdev', 'mls']

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

logger = logging.getLogger('a')
logger.setLevel(logging.INFO)
logfilename = 'log.log'
handler = logging.handlers.RotatingFileHandler(logfilename, maxBytes=50000, backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.warning("[POST MATCH THREAD: STARTUP]")


def getTimestamp():
    dt = str(datetime.datetime.now().month) + '/' + str(datetime.datetime.now().day) + ' '
    hr = str(datetime.datetime.now().hour) if len(str(datetime.datetime.now().hour)) > 1 else '0' + str(
        datetime.datetime.now().hour)
    minute = str(datetime.datetime.now().minute) if len(str(datetime.datetime.now().minute)) > 1 else '0' + str(
        datetime.datetime.now().minute)
    t = '[' + hr + ':' + minute + '] '
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
            getTimestamp() +
            "Setup error: please ensure 'login.txt' file exists in its correct form (check readme for more info)\n")
        logger.exception("[SETUP ERROR:]")
        sleep(10)


def getTeamIDs(matchID):
    try:
        lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15)
        line_html = lineWebsite.text

        teamIDs = re.findall('<div class="team-info">(.*?)</div>', line_html, re.DOTALL)
        if teamIDs:
            t1id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"', teamIDs[0], re.DOTALL)
            t2id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"', teamIDs[1], re.DOTALL)
            if t1id:
                t1id = t1id[0]
            else:
                t1id = ''
            if t2id:
                t2id = t2id[0]
            else:
                t2id = ''
            return t1id, t2id
        else:
            return '', ''
    except requests.exceptions.Timeout:
        return '', ''


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
                matchID = match.find("a",
                                     {"class",
                                      "AnchorLink Button Button--sm Button--anchorLink Button--alt mb4 w-100 mr2"})[
                    "href"].split("/")[-1] if match.find("a", {"class",
                                                               "AnchorLink Button Button--sm Button--anchorLink "
                                                               "Button--alt mb4 w-100 mr2"}) else ''
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
        if counts.most_common(1):
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
                                                                        "ScoreCell__TeamName "
                                                                        "ScoreCell__TeamName--displayName truncate "
                                                                        "db"})))
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
        team1Starters, team2Starters = list(map(lambda item: item.find("tbody"),
                                                soup.findAll("div", {"class","ResponsiveTable LineUps__PlayersTable"})))
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


def submitThread(sub, title, body, r):
    print(getTimestamp() + "Submitting " + title + "...", )
    try:
        thread = r.subreddit(sub).submit(title, selftext=body, send_replies=False)
        print("complete.")
        return True, thread
    except:
        print("failed.")
        logger.exception("[SUBMIT ERROR:]")
        return False, ''


def loadMarkup(subreddit):
    try:
        markup = [line.rstrip('\n') for line in open(subreddit + '.txt')]
    except:
        markup = [line.rstrip('\n') for line in open('soccer.txt')]
    return markup


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
                               'penalty---missed', 'penalty---saved', 'yellow-card', 'red-card', 'substitution',
                               'offside']
            for row in events.findAll("tr"):
                time = row.find("div", {"class", "MatchCommentary__Comment__Timestamp"}).text.strip()
                event = row.find("div", {"class", "MatchCommentary__Comment__GameDetails"}).text.strip()
                info = "**" + time + "** "
                try:
                    tag = row.find("div", {"class", "MatchCommentary__Comment__PlayIcon"}).find("svg")["aria-label"]
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
            leftScore, rightScore = 0, 0
        info = getExtraInfo(matchID)
        status = getStatus(matchID)
        ESPNUpdating = True
        if status == 'v':
            status = "0'"
            ESPNUpdating = False
        if status == 'FT':
            leftScore = re.sub('[^0-9]','',leftScore)
            rightScore = re.sub('[^0-9]','',rightScore)


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
            left += f"*{t1} scorers: {leftScorers}*"

        right = ''
        if rightScorers:
            right += f"*{t2} scorers: {rightScorers}*"

        text += left + '\n\n' + right

        return [leftScore, rightScore], text
    except requests.exceptions.Timeout:
        return '#**--**\n\n'


def createThread(matchID, r):
    t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status, comp = getMatchInfo(
        matchID)
    scores, score = updateScore(matchID, t1, t2, sub)
    title = 'Post Match Thread: ' + t1 + ' ' + scores[0] + ' - ' + scores[1] + ' ' + t2
    if comp != '':
        title += ' [' + comp + ']'

    markup = loadMarkup(sub)
    body = score + '\n\n--------\n\n'
    body += '**Venue:** ' + venue + '\n\n'
    body += '[Follow us on Twitter](https://twitter.com/rslashgunners)\n\n'
    body += markup[lines] + ' '
    body = writeLineUps(sub, body, t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub)
    body += '\n\n------------\n\n' + markup[
        evnts] + ' **MATCH EVENTS** | *via [ESPNFC](http://www.espnfc.us/match?gameId=' + matchID + ')*\n\n'
    events = grabEvents(matchID, sub)
    body += '\n\n' + events

    result, thread = submitThread(sub, title, body, r)


def main(matchID):
    print(getTimestamp() + "[STARTUP]")
    r, admin, username, password, subreddit, user_agent, id, secret, redirect = setup()
    createThread(matchID, r)
    os.system('python lockPosts.py')
    return
