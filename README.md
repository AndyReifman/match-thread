match-thread-bot
================

This bot was originall forked from [aarkay](https://github.com/aarkay/match-thread-bot). It has been customized to run only in a specific subreddit and updated to use Python3


login.txt
-----

To run this bot, you must have a file called 'login.txt' in the same directory. This file should contain a single line with five pieces of information: your own username, your bot's username, the bot's password, the subreddit that the bot will be used in, and the bot's user agent. Each of these should be separated by a single colon. For example, if /u/iliketotestthings wanted to use this code to allow a bot called 'TestThreadBot' with the password 'ThisIsATestPassword' to post to the subreddit 'SubForTesting', the login.txt file would look like this:

    iliketotestthings:TestThreadBot:ThisIsATestPassword:SubForTesting:TestThreadBot v0.1 by /u/iliketotestthings

    
Your own username is used to give you access to the delete function, where you (as the bot-runner) can send your bot a message with 'delete' in the title and the thread ID (e.g. '2ftzab') in the message body, and the bot will delete that thread. This can be used for accidental or incorrect match thread creations - someone who requests a thread from the bot has access to this feature themselves, but only within five minutes of the thread's creation (to prevent abuse of the function).

The fifth detail, the bot's user agent, should be provided as per [reddit's API rules](https://github.com/reddit/reddit/wiki/API). Note that reddit asks new accounts to complete a captcha if they want to post anything and I haven't put anything in the code to get around that, so you'll need to figure out a way to get your bot account a lot of karma if you want it to work autonomously.

mtb.py
-----

In this file is the code used to run MatchThreadder - as long as you change the login.txt file appropriately, you should be able to run this file in its current form to have your own subreddit-specific version of the bot, although I haven't tested that at all. The bot checks for new messages every 60 seconds, and if any messages are titled 'Match Thread' or 'Match Info' it will attempt to find the appropriate info about that match.

If/when the bot runs into any HTTP errors (reddit is down, can't access goal.com, etc) it will sleep for 2 minutes and try again.

If a message is titled 'Match Thread', the bot will attempt to find info about the match and then post a match thread to the specified subreddit. If a message is titled 'Match Info', the bot will attempt to find info about the match and then reply to the user with a template for the match thread so the user can post and update the thread themselves.

pmt.py
-----

When a Match finishes and the match is removed from active matches it also makes a call to create a Post Match Thread. This will use the information in the `login.txt` file to know which subreddit to post to, but otherwise should work for any match.

Running in Docker
-----

It's pretty simple to dockerize the Match Thread Bot. You'll want a Dockerfile that's running `python3.6+`, install the required python libraries and run. For example
```
FROM python:3.6
ADD . /
RUN pip install --trusted-host pypi.python.org -r /requirements.txt
WORKDIR /

CMD ["python","./mtb.py"]
```
