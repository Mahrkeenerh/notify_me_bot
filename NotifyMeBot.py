import praw, datetime, sys, json
from time import sleep
from threading import Thread


with open("config.json") as config_file:

    config_json = json.load(config_file)

    userAgent = config_json['userAgent']
    cID = config_json['cID']
    cSC = config_json['cSC']
    userN = config_json['userN']
    userP = config_json['userP']

reddit = praw.Reddit(user_agent=userAgent, 
    client_id=cID, 
    client_secret=cSC, 
    username=userN, 
    password=userP)

subreddit_list = []
watch_list = []
active_thread_id = 0


# load lists
def load():

    global subreddit_list, watch_list

    with open("data_list.json") as json_file:
        data = json.load(json_file)

        subreddit_list = data["subreddit_list"]
        watch_list = data["watch_list"]


# save lists
def save():

    global subreddit_list, watch_list

    with open("data_list.json", "w") as json_file:
        json.dump({"subreddit_list": subreddit_list, "watch_list": watch_list}, json_file)


# add new entry to search_list
def add(mention, subreddit):

    global subreddit_list, watch_list, active_thread_id

    keywords = mention.body.lower().strip().split()
    out = []

    # add all keywords
    for keyword in keywords:
        if "notify_me_bot" in keyword or keyword == "create":
            continue

        out.append(keyword)

    # no keywords
    if len(out) == 0 or (len(out) == 1 and out[0] == "all"):
        out = [""]

    watch_list.append([str(subreddit), str(mention.author), out])

    if out[0] == "":
        out = ["everything"]

    # add new subreddit to search
    if subreddit not in subreddit_list:
        subreddit_list.append(str(subreddit))

        # restart checking subreddits
        active_thread_id += 1
        Thread(target=check_subreddits, args=([active_thread_id])).start()

    # save lists
    save()
    
    return out


# cancel search
def cancel(mention, subreddit):

    global subreddit_list, watch_list

    keywords = mention.body.lower().strip().split()
    removed = 0

    keywods_copy = []

    for keyword in keywords:
        if "notify_me_bot" in keyword or keyword == "cancel":
            continue
            
        keywods_copy.append(keyword)

    # no keywords
    if len(keywods_copy) == 0:
        for item in watch_list:
            if item[1] == mention.author and item[0] == subreddit:
                watch_list.remove(item)
                removed += 1

    # remove entry if it contains the keyword
    else:
        for keyword in keywods_copy:
            for item in watch_list:
                if item[1] == mention.author and item[0] == subreddit and keyword in item[2]:
                    watch_list.remove(item)
                    removed += 1

    # clean up searching subreddits
    for item in subreddit_list:
        if item not in [x[0] for x in watch_list]:
            subreddit_list.remove(item)

            # restart checking subreddits
            active_thread_id += 1
            Thread(target=check_subreddits, args=([active_thread_id])).start()
            break

    # save lists
    save()

    return removed


# return subreddit
def get_subreddit(mention):

    if mention.subject == "post reply":
        return mention.subreddit

    return mention.subject.replace("re:", "").strip()


# check all mentions
def check_inbox():

    while True:
        try:
            new_mentions = []

            for mention in reddit.inbox.all():
                new_mentions.append(mention)
                lowercase_body = mention.body.lower()

                if not mention.new:
                    continue
                
                # it's a response
                if not ("u/notify_me_bot" in lowercase_body or mention.subject != "post reply"): 
                    continue

                subreddit = get_subreddit(mention)

                if "cancel" in lowercase_body:
                    removed = cancel(mention, subreddit)
                    if removed > 0:
                        mention.reply('Removed %d search listings.\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)' % (removed))

                    else:
                        mention.reply('No search listings were removed.\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)')
                    continue

                if "create" in lowercase_body:
                    keywords = add(mention, subreddit)
                    mention.reply('New search added:\n\nSubreddit: %s\n\nUser: %s\n\nKeywords: %s\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)' 
                        % (subreddit, mention.author, ", ".join(keywords)))

            reddit.inbox.mark_read(new_mentions)

        # reddit is not responding or something, idk, error - wait, try again
        except:
            print("\n", datetime.datetime.now())
            print("En error occured with inbox")
            print(sys.exc_info())
            sleep(60)


# check if bot should reply
def check_keywords(item, lowercase_body, lowercase_title):

    reply = True
    # must contain all keywords
    if "all" in item[2]:
        for keyword in item[2]:
            if keyword == "all":
                continue

            if keyword not in lowercase_body and keyword not in lowercase_title:
                reply = False
                break
    
    # must contain at least one keyword
    else:
        reply = False

        for keyword in item[2]:
            if keyword in lowercase_body or keyword in lowercase_title:
                reply = True
                break

    return reply


# search subreddits
def check_subreddits(id):

    global active_thread_id

    while True:
        try:
            print("\nStarting subreddits")
            # no search entries yet
            if not subreddit_list:
                sleep(10)
                continue

            subreddit = reddit.subreddit("+".join(subreddit_list))
            start_time = datetime.datetime.now()

            for submission in subreddit.stream.submissions():
                # there is a new active thread
                if active_thread_id != id:
                    return

                submission_time = datetime.datetime.fromtimestamp(submission.created_utc)

                # only check new posts
                if submission_time > start_time:
                    lowercase_title = submission.title
                    lowercase_body = submission.selftext

                    # loop through all watch lists
                    for item in watch_list:
                        if item[0] == submission.subreddit:
                            if submission.author != item[1] and check_keywords(item, lowercase_body, lowercase_title):
                                reddit.redditor(item[1]).message('notify_me_bot: %s' % (item[0]), 'You requested a notification, here is your post:\n\n%s\n\nTo cancel subreddit notifications, comment in r/%s: u/notify_me_bot cancel' % (submission.permalink, item[0]))

        # reddit is not responding or something, idk, error - wait, try again
        except:
            print("\n", datetime.datetime.now())
            print("En error occured with subreddits")
            print(sys.exc_info())
            sleep(60)


load()
Thread(target=check_subreddits, args=([active_thread_id])).start()
check_inbox()
