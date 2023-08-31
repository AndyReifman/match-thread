#!/usr/bin/python3
'''
'  Andrew Reifman-Packett
'  Sept. 2019
'  Simple script to lock text posts after a match.
'''

import praw, datetime 
from time import sleep




def getTimestamp():
    dt = str(datetime.datetime.now().month) + '/' + str(datetime.datetime.now().day) + ' '
    hr = str(datetime.datetime.now().hour) if len(str(datetime.datetime.now().hour)) > 1 else '0' + str(datetime.datetime.now().hour)
    min = str(datetime.datetime.now().minute) if len(str(datetime.datetime.now().minute)) > 1 else '0' + str(datetime.datetime.now().minute)
    t = '[' + hr + ':' + min + '] '
    return dt + t

def loginBot():
    try:
        f = open('reddit.txt')
        admin,username,password,subreddit,user_agent,id,secret,redirect,refresh = f.readline().split('||',8)
        f.close()
        r = praw.Reddit(client_id=id,
             client_secret=secret,
             refresh_token=refresh.strip(),
             user_agent=user_agent)
        print(getTimestamp() + "OAuth session opened as /u/" + r.user.me().name)
        return r,admin,username,password,subreddit,user_agent,id,secret,redirect
    except Exception as e:
        print(getTimestamp() + str(e))
        print(getTimestamp() + "Setup error in Results \n")
        sleep(5)
        exit()


r,admin,username,password,subreddit,user_agent,id,secret,redirect = loginBot()
r.subreddit(subreddit).mod.update(link_type="link")
print("Text Posts locked\n")
sleep(54000)
r.subreddit(subreddit).mod.update(link_type="any")
r.subreddit(subreddit).mod.update(allow_polls="false")
r.subreddit(subreddit).mod.update(allow_videos="false")
r.subreddit(subreddit).mod.update(allowed_media_in_comments=[])
print("Text Posts unlocked\n")
