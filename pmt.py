#!/usr/bin/python3
# -*- coding: utf-8 -*-

from time import sleep

import datetime
import logging.handlers
import os
import praw
import re
import requests
import requests.auth
from unidecode import unidecode

# browser header (to avoid 405 error)
hdr = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
   'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
   'Accept-Encoding': 'none',
   'Accept-Language': 'en-US,en;q=0.8',
   'Connection': 'keep-alive'}


messaging = True
sub = 'gunners'
spriteSubs = ['soccer','Gunners','fcbayern','soccerdev','mls']

# markup constants
#goal=0;pgoal=1;ogoal=1;mpen=3;yel=5;syel=5;red=6;subst=7;subo=12;subi=11;strms=10;lines=9;evnts=2
goal=0;pgoal=1;ogoal=1;mpen=1;yel=5;syel=5;red=6;subst=7;subo=8;subi=9;strms=10;lines=10;evnts=2
events = ['Sub','Goal','Yellow','Red']

logger = logging.getLogger('a')
logger.setLevel(logging.INFO)
logfilename = 'log.log'
handler = logging.handlers.RotatingFileHandler(logfilename,maxBytes = 50000,backupCount = 5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.warning("[POST MATCH THREAD: STARTUP]")

def getTimestamp():
    dt = str(datetime.datetime.now().month) + '/' + str(datetime.datetime.now().day) + ' '
    hr = str(datetime.datetime.now().hour) if len(str(datetime.datetime.now().hour)) > 1 else '0' + str(datetime.datetime.now().hour)
    min = str(datetime.datetime.now().minute) if len(str(datetime.datetime.now().minute)) > 1 else '0' + str(datetime.datetime.now().minute)
    t = '[' + hr + ':' + min + '] '
    return dt + t

def setup():
    try:
        f = open('login.txt')
        admin,username,password,subreddit,user_agent,id,secret,redirect = f.readline().split('||',8)
        f.close()
        r = praw.Reddit(client_id=id,
                     client_secret=secret,
                     password=password,
                     user_agent=user_agent,
                     username=username)
        print(getTimestamp() + "OAuth session opened as /u/" + r.user.me().name)
        return r,admin,username,password,subreddit,user_agent,id,secret,redirect
    except:
        print(getTimestamp() + "Setup error: please ensure 'login.txt' file exists in its correct form (check readme for more info)\n")
        logger.exception("[SETUP ERROR:]")
        sleep(10)

def getTeamIDs(matchID):
    try:
        lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15)
        line_html = lineWebsite.text

        teamIDs = re.findall('<div class="team-info">(.*?)</div>', line_html, re.DOTALL)
        if teamIDs != []:
            t1id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"',teamIDs[0],re.DOTALL)
            t2id = re.findall('/(?:club|team)/.*?/.*?/(.*?)"',teamIDs[1],re.DOTALL)
            if t1id != []:
                t1id = t1id[0]
            else:
                t1id = ''
            if t2id != []:
                t2id = t2id[0]
            else:
                t2id = ''
            return t1id,t2id
        else:
            return '',''
    except requests.exceptions.Timeout:
        return '',''

def getStatus(matchID):
    #lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
    lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
    lineWebsite = requests.get(lineAddress, timeout=15)
    line_html = lineWebsite.text
    if lineWebsite.status_code == 200:
        status = re.findall('<span class="game-time".*?>(.*?)<',line_html,re.DOTALL)
        if status == []:
            return 'v'
        else:
            return status[0]
    else:
        return ''

def getLineUps(matchID):
    try:
        # try to find line-ups
        lineAddress = "http://www.espnfc.us/lineups?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15)
        line_html = lineWebsite.text
        split = line_html.split('<div class="sub-module soccer">') # [0]:nonsense [1]:team1 [2]:team2

        if len(split) > 1:
            team1StartBlock = split[1].split('Substitutes')[0]
            if len(split[1].split('Substitutes')) > 1:
                team1SubBlock = split[1].split('Substitutes')[1]
            else:
                team1SubBlock = ''
            team2StartBlock = split[2].split('Substitutes')[0]
            if len(split[2].split('Substitutes')) > 1:
                team2SubBlock = split[2].split('Substitutes')[1]
            else:
                team2SubBlock = ''

            team1Start = []
            team2Start = []
            team1Sub = []
            team2Sub = []

            t1StartInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team1StartBlock, re.DOTALL)
            t1SubInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team1SubBlock, re.DOTALL)
            t2StartInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team2StartBlock, re.DOTALL)
            t2SubInfo = re.findall('"accordion-item" data-id="(.*?)</div>', team2SubBlock, re.DOTALL)

            for playerInfo in t1StartInfo:
                playerInfo = playerInfo.replace('\t','').replace('\n','')
                playerNum = playerInfo[0:6]
                if '%' not in playerNum:
                    playertext = ''
                    if 'icon-soccer-substitution-before' in playerInfo:
                        playertext += '!sub '
                    if 'icon-yellowcard' in playerInfo:
                        playertext += '!yellow '
                    if 'icon-soccer-goal' in playerInfo:
                        playertext += '!goal '
                    if 'icon-redcard' in playerInfo:
                        playertext += '!red '
                    #playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
                    playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
                    playertext = unidecode(playertext).replace("-"," ", 1).title()
                    team1Start.append(playertext)
            for playerInfo in t1SubInfo:
                playerInfo = playerInfo.replace('\t','').replace('\n','')
                playerNum = playerInfo[0:6]
                if '%' not in playerNum:
                    playertext = ''
                    if 'icon-yellowcard' in playerInfo:
                        playertext += '!yellow '
                    if 'icon-soccer-goal' in playerInfo:
                        playertext += '!goal '
                    #playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
                    playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
                    playertext = unidecode(playertext).replace("-"," ", 1).title()
                    team1Sub.append(playertext)
            for playerInfo in t2StartInfo:
                playerInfo = playerInfo.replace('\t','').replace('\n','')
                playerNum = playerInfo[0:6]
                if '%' not in playerNum:
                    playertext = ''
                    if 'icon-soccer-substitution-before' in playerInfo:
                        playertext += '!sub '
                    if 'icon-yellowcard' in playerInfo:
                        playertext += '!yellow '
                    if 'icon-soccer-goal' in playerInfo:
                        playertext += '!goal '
                    #playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
                    playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
                    playertext = unidecode(playertext).replace("-"," ", 1).title()
                    team2Start.append(playertext)
            for playerInfo in t2SubInfo:
                playerInfo = playerInfo.replace('\t','').replace('\n','')
                playerNum = playerInfo[0:6]
                if '%' not in playerNum:
                    playertext = ''
                    if 'icon-yellowcard' in playerInfo:
                        playertext += '!yellow '
                    if 'icon-soccer-goal' in playerInfo:
                        playertext += '!goal '
                    #playertext += re.findall('<span class="name">(?!<)(.*?)[<|&]', playerInfo, re.DOTALL)[0]
                    playertext += re.findall('<span class="name">.*href=".*/(.*?)"\sdata', playerInfo, re.DOTALL)[0]
                    playertext = unidecode(playertext).replace("-"," ", 1).title()
                    team2Sub.append(playertext)
            # if no players found:
            if team1Start == []:
                team1Start = ["*Not available*"]
            if team1Sub == []:
                team1Sub = ["*Not available*"]
            if team2Start == []:
                team2Start = ["*Not available*"]
            if team2Sub == []:
                team2Sub = ["*Not available*"]
            return team1Start,team1Sub,team2Start,team2Sub

        else:
            team1Start = ["*Not available*"]
            team1Sub = ["*Not available*"]
            team2Start = ["*Not available*"]
            team2Sub = ["*Not available*"]
            return team1Start,team1Sub,team2Start,team2Sub
    except IndexError:
        logger.warning("[INDEX ERROR:]")
        team1Start = ["*Not available*"]
        team1Sub = ["*Not available*"]
        team2Start = ["*Not available*"]
        team2Sub = ["*Not available*"]
        return team1Start,team1Sub,team2Start,team2Sub


def getMatchInfo(matchID):
    lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
    lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
    print(getTimestamp() + "Finding ESPNFC info from " + lineAddress + "...",)
    lineWebsite = requests.get(lineAddress, timeout=15)
    line_html = lineWebsite.text

    # get "fixed" versions of team names (ie team names from ESPNFC, not team names from match thread request)
    team1fix = re.findall('<span class="long-name">(.*?)<', line_html, re.DOTALL)[0]
    team2fix = re.findall('<span class="long-name">(.*?)<', line_html, re.DOTALL)[1]
    t1id,t2id = getTeamIDs(matchID)

    if team1fix[-1]==' ':
        team1fix = team1fix[0:-1]
    if team2fix[-1]==' ':
        team2fix = team2fix[0:-1]

    status = getStatus(matchID)
    ko_date = re.findall('<span data-date="(.*?)T', line_html, re.DOTALL)
    if ko_date != []:
        ko_date = ko_date[0]
        ko_day = ko_date[8:]
    
        ko_time = re.findall('<span data-date=".*?T(.*?)Z', line_html, re.DOTALL)[0]
        # above time is actually 4 hours from now (ESPN time in source code)
    else:
        ko_day = ''
        ko_time = ''

    venue = re.findall('<div>VENUE: (.*?)<', line_html, re.DOTALL)
    if venue != []:
        venue = venue[0]
    else:
        venue = '?'

    compfull = re.findall('<div class="game-details header">(.*?)<', line_html, re.DOTALL)
    if compfull != []:
        comp = re.sub('20.*? ','',compfull[0]).strip(' \n\t\r')
        if comp.find(',') != -1:
            comp = comp[0:comp.index(',')]
    else:
        comp = ''

    team1Start,team1Sub,team2Start,team2Sub = getLineUps(matchID)
    print( "complete.")
    return (team1fix,t1id,team2fix,t2id,team1Start,team1Sub,team2Start,team2Sub,venue,ko_day,ko_time,status,comp)

def submitThread(sub,title,body,r):
    print(getTimestamp() + "Submitting " + title + "...",)
    try:
        thread = r.subreddit(sub).submit(title,selftext=body,send_replies=False)
        print("complete.")
        return True,thread
    except:
        print("failed.")
        logger.exception("[SUBMIT ERROR:]")
        return False,''

def loadMarkup(subreddit):
    try:
        markup = [line.rstrip('\n') for line in open(subreddit + '.txt')]
    except:
        markup = [line.rstrip('\n') for line in open('soccer.txt')]
    return markup

def writeLineUps(sub,body,t1,t1id,t2,t2id,team1Start,team1Sub,team2Start,team2Sub):
    markup = loadMarkup(sub)
    t1sprite = ''
    t2sprite = ''
    if sub.lower() in spriteSubs and getSprite(t1id,sub) != '' and getSprite(t2id,sub) != '':
        t1sprite = getSprite(t1id,sub) + ' '
        t2sprite = getSprite(t2id,sub) + ' '


    body += '**LINE-UPS**\n\n**' + t1sprite + t1 + '**\n\n'
    linestring = ''
    for name in team1Start:
        if any(event in name for event in events):
            temp = ''
            if '!Sub' in name:
                temp += ' ('
            else:
                temp += ', '
            if '!Sub' in name:
                temp += markup[subst]
                name = name.replace("!Sub","").strip()
            if '!Yellow' in name:
                temp += markup[yel]
                name = name.replace("!Yellow","").strip()
            if '!Red' in name:
                temp += markup[red]
                name = name.replace("!Red","").strip()
            if '!Goal' in name:
                temp += markup[goal]
                name = name.replace("!Goal","").strip()
            temp += ' ' + name
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
            if '!Sub' in name:
                temp += ' ('
            else:
                temp += ', '
            if '!Sub' in name:
                temp += markup[subst]
                name = name.replace("!Sub","").strip()
            if '!Yellow' in name:
                temp += markup[yel]
                name = name.replace("!Yellow","").strip()
            if '!Red' in name:
                temp += markup[red]
                name = name.replace("!Red","").strip()
            if '!Goal' in name:
                temp += markup[goal]
                name = name.replace("!Goal"," ").strip()
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

def grabEvents(matchID,sub):
    markup = loadMarkup(sub)
    lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
#    print getTimestamp() + "Grabbing events from " + lineAddress + "...",
    lineWebsite = requests.get(lineAddress, timeout=15)
    line_html = lineWebsite.text
    try:
        if lineWebsite.status_code == 200:
            body = ""
            split_all = line_html.split('<h1>Match Commentary</h1>') # [0]:stuff [1]:commentary + key events
            split = split_all[1].split('<h1>Key Events</h1>') # [0]:commentary [1]: key events

            events = re.findall('<tr data-id=(.*?)</tr>',split[1],re.DOTALL)
            events = events[::-1]

            # will only report goals (+ penalties, own goals), yellows, reds, subs
            supportedEvents = ['goal','goal---header','goal---free-kick','penalty---scored','own-goal','penalty---missed','penalty---saved','yellow-card','red-card','substitution','kickoff','halftime','end-regular-time']
            for text in events:
                tag = re.findall('data-type="(.*?)"',text,re.DOTALL)[0]
                if tag.lower() in supportedEvents:
                    time = re.findall('"time-stamp">(.*?)<',text,re.DOTALL)[0]
                    time = time.strip()
                    info = "**" + time + "** "
                    event = re.findall('"game-details">(.*?)<',text,re.DOTALL)[0].strip()
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
                        if event == '':
                            players = re.findall('</strong>(.*?)</span>',text,re.DOTALL)
                            event = 'Substitution, **ON:** ' +unidecode(players[0]) + '| **OFF:** ' + unidecode(players[1])
                        info += markup[subst] + ' ' + event
                    if tag.lower() == 'halftime' or tag.lower() == 'end-regular-time' or tag.lower() == 'kickoff':
                        info +=  markup[evnts] + ' ' + event
                    body += info + '\n\n'
            print("success.")
            return body

        else:
            print("failed.")
            return ""
    except:
        #print "edit failed"
        logger.exception('[EDIT ERROR:]')
        return ""



def updateScore(matchID, t1, t2, sub):
    try:
        #lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
        lineAddress = "http://www.espnfc.us/commentary?gameId=" + matchID
        lineWebsite = requests.get(lineAddress, timeout=15)
        line_html = lineWebsite.text
        leftScore = re.findall('data-stat="score">(.*?)<',line_html,re.DOTALL)[0].strip()
        rightScore = re.findall('data-stat="score">(.*?)<',line_html,re.DOTALL)[1].strip()
        scores = [leftScore,rightScore]
        #info = getExtraInfo(matchID)
        status = getStatus(matchID)
        ESPNUpdating = True
        if status == 'v':
            status = "0'"
            ESPNUpdating = False

        leftInfo = re.findall('<div class="team-info players"(.*?)</div>',line_html,re.DOTALL)[0]
        rightInfo = re.findall('<div class="team-info players"(.*?)</div>',line_html,re.DOTALL)[1]

        leftGoals = re.findall('data-event-type="goal"(.*?)</ul>',leftInfo,re.DOTALL)
        rightGoals = re.findall('data-event-type="goal"(.*?)</ul>',rightInfo,re.DOTALL)

        if leftGoals != []:
            leftScorers = re.findall('<li>(.*?)</li',leftGoals[0],re.DOTALL)
        else:
            leftScorers = []
        if rightGoals != []:
            rightScorers = re.findall('<li>(.*?)</li',rightGoals[0],re.DOTALL)
        else:
            rightScorers = []

        t1id,t2id = getTeamIDs(matchID)
        if sub.lower() in spriteSubs:
            t1sprite = ''
            t2sprite = ''
            if getSprite(t1id,sub) != '' and getSprite(t2id,sub) != '':
                t1sprite = getSprite(t1id,sub)
                t2sprite = getSprite(t2id,sub)
            text = '#**' + status + ': ' + t1 + ' ' + t1sprite + ' [' + leftScore + '-' + rightScore + '](#bar-3-white) ' + t2sprite + ' ' + t2 + '**\n\n'
        else:
            text = '#**' + status + ": " +  t1 + ' ' + leftScore + '-' + rightScore + ' ' + t2 + '**\n\n'
        if not ESPNUpdating:
            text += '*If the match has started, ESPNFC might not be providing updates for this game.*\n\n'

        #if info != '':
        #    text += '***' + info + '***\n\n'

        left = ''
        if leftScorers != []:
            left += "*" + t1 + " scorers: "
            for scorer in leftScorers:

                scorer = scorer[0:scorer.index('<')].strip(' \t\n\r') + ' ' + scorer[scorer.index('('):scorer.index('/')-1].strip(' \t\n\r')
                left += scorer + ", "
            left = left[0:-2] + "*"

        right = ''
        if rightScorers != []:
            right += "*" + t2 + " scorers: "
            for scorer in rightScorers:
                scorer = scorer[0:scorer.index('<')].strip(' \t\n\r') + ' ' + scorer[scorer.index('('):scorer.index('/')-1].strip(' \t\n\r')
                right += scorer + ", "
            right = right[0:-2] + "*"

        text += left + '\n\n' + right

        return scores,text
    except requests.exceptions.Timeout:
        return '#**--**\n\n'


def createThread(matchID,r):
    t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status, comp = getMatchInfo(matchID)
    scores, score = updateScore(matchID,t1,t2,sub)
    title = 'Post Match Thread: ' + t1 + ' ' + scores[0] + ' - ' + scores[1] + ' ' + t2
    if comp != '':
        title += ' [' + comp + ']'

    
    markup = loadMarkup(sub)
    body = score + '\n\n--------\n\n'
    body += '**Venue:** ' + venue + '\n\n'
    body += '[Follow us on Twitter](https://twitter.com/rslashgunners)\n\n'
    body += markup[lines] + ' '
    body = writeLineUps(sub,body,t1,t1id,t2,t2id,team1Start,team1Sub,team2Start,team2Sub)
    body += '\n\n------------\n\n' + markup[evnts] + ' **MATCH EVENTS** | *via [ESPNFC](http://www.espnfc.us/match?gameId=' + matchID + ')*\n\n'
    events = grabEvents(matchID,sub)
    body += '\n\n' + events

    result,thread = submitThread(sub,title,body,r)




def main(matchID):
    print(getTimestamp() + "[STARTUP]")
    r,admin,username,password,subreddit,user_agent,id,secret,redirect = setup()
    createThread(matchID,r)
    os.system('python lockPosts.py')
    return

