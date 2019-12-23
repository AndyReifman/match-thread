#!/usr/bin/python3
# -*- coding: utf-8 -*-

import praw,urllib,http.cookiejar,re,logging,logging.handlers,datetime,requests,requests.auth,sys,json,unicodedata,os
from praw.models import Message

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
goal=0;pgoal=1;ogoal=1;mpen=3;yel=5;syel=5;red=6;subst=7;subo=12;subi=11;strms=10;lines=9;evnts=2
events = ['Sub','Goal','Yellow','Red']

def getTimestamp():
    dt = str(datetime.datetime.now().month) + '/' + str(datetime.datetime.now().day) + ' '
    hr = str(datetime.datetime.now().hour) if len(str(datetime.datetime.now().hour)) > 1 else '0' + str(datetime.datetime.now().hour)
    min = str(datetime.datetime.now().minute) if len(str(datetime.datetime.now().minute)) > 1 else '0' + str(datetime.datetime.now().minute)
    t = '[' + hr + ':' + min + '] '
    return dt + t

def setup():
     try:
        f = open('/root/reddit/sidebar/login.txt')
        fkey = open('/root/reddit/sidebar/2fakey.txt')
        admin,username,password,subreddit,user_agent,id,secret,redirect,refresh = f.readline().split('||',8)
        key = fkey.readline().rstrip()
        #totp = pyotp.TOTP(key)
        #password += ':'+totp.now()
        f.close()
        fkey.close()
        r = praw.Reddit(client_id=id,
             client_secret=secret,
             refresh_token=refresh.strip(),
             user_agent=user_agent)
        print(getTimestamp() + "OAuth session opened as /u/" + r.user.me().name)
        return r,admin,username,password,subreddit,user_agent,id,secret,redirect
    except (Exception, e):
        print(getTimestamp() + str(e))
        if str(e) == 'invalid_grant error processing request':
            print(getTimestamp() + 'Attempting to log in again.\n')
            time.sleep(5)
            loginBot()
            return
        print(getTimestamp() + "Setup error \n")

def getMatchInfo(matchID):
    lineAddress = "http://www.espnfc.us/match?gameId=" + matchID
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

def submitThread(sub,title):
    print(getTimestamp() + "Submitting " + title + "...",)
    try:
        thread = r.subreddit(sub).submit(title,selftext='**Venue:**\n\n**LINE-UPS**',send_replies=False)
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
                name = name.replace("!Goal"," ").strip()
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

def createThread(matchID):
    t1, t1id, t2, t2id, team1Start, team1Sub, team2Start, team2Sub, venue, ko_day, ko_time, status, comp = getMatchInfo(matchID)
    title = 'Post Match Thread: ' + t1 + ' vs ' + t2
    if comp != ''
        title += ' [' + comp + ']'
    result,thread = submitThread(sub,title)
    short = thread.shortlink
    #id = short[short.index('.it/')+4:].encode("utf8")
    id = short[short.index('.it/')+4:]
    score = updateScore(matchID,team1,team2,sub)
    newbody = score + '\n\n--------\n\n' + newbody

    data = matchID, t1, t2, id, reqr, sub
    
    markup = loadMarkup(sub)
    body = '#**' + status + ": " + t1 + ' vs ' + t2 + '**\n\n'
    body += score + '\n\n--------\n\n'
    body += '**Venue:** ' + venue + '\n\n'
    body += '[Follow us on Twitter](https://twitter.com/rslashgunners)\n\n'
    body += markup[lines] + ' '
    body = writeLineUps(sub,body,t1,t1id,t2,t2id,team1Start,team1Sub,team2Start,team2Sub)
    body += '\n\n------------\n\n' + markup[evnts] + ' **MATCH EVENTS** | *via [ESPNFC](http://www.espnfc.us/match?gameId=' + matchID + ')*\n\n'
    events = grabEvents(matchID,sub)
    body += '\n\n' + events






logger = logging.getLogger('a')
logger.setLevel(logging.INFO)
logfilename = 'pmt.log'
handler = logging.handlers.RotatingFileHandler(logfilename,maxBytes = 50000,backupCount = 5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.warning("[STARTUP]")
print(getTimestamp() + "[STARTUP]")

r,admin,username,password,subreddit,user_agent,id,secret,redirect = setup()
createThread(matchID)
