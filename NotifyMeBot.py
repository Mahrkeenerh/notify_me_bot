import praw, datetime, sys, json, traceback
from time import sleep
from threading import Thread

from prawcore.exceptions import NotFound


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

file_lock = False
list_lock = False

subreddit_list = []
watch_list = []

queue_mentions = []
queue_directs = []

active_thread_id = 0


# logger for errors
def log_error(*args):

    print("\n", datetime.datetime.now())

    for i in args:
        print(i)

    print(traceback.print_exception(*sys.exc_info()))


# logger for messages
def log_message(*args):

    print("\n", datetime.datetime.now())

    for i in args:
        print(i)


# clean up data_list for subreddits
def purge_subreddits():

    global subreddit_list, watch_list, list_lock

    log_message("Purging subreddits", "Before:", len(subreddit_list))

    while list_lock:
        log_message("Subreddit purge sleeping")
        sleep(1)
    
    list_lock = True

    changed = False

    dupli_list = []

    for subreddit in subreddit_list:
        if not check_public(subreddit):
            changed = True

        else:
            dupli_list.append(subreddit)

    subreddit_list = dupli_list
    dupli_list = []

    for item in watch_list:
        if not check_public(item[0]):
            changed = True
        
        else:
            dupli_list.append(item)

    watch_list = dupli_list

    log_message("After:", len(subreddit_list))

    if changed:
        save()

    list_lock = False


# clean up data_list for users
def purge_users():

    global subreddit_list, watch_list, list_lock

    log_message("Purging users", "Before:", len(watch_list))

    while list_lock:
        log_message("User purge sleeping")
        sleep(1)
    
    list_lock = True

    changed = False

    dupli_list = []

    for item in watch_list:
        if not check_user(item[1]):
            changed = True

        else:
            dupli_list.append(item)

    watch_list = dupli_list
    dupli_list = []

    new_sub_list = [i[0] for i in watch_list]

    for subreddit in subreddit_list:
        if subreddit in new_sub_list:
            dupli_list.append(subreddit)

    subreddit_list = dupli_list

    log_message("After:", len(watch_list))

    if changed:
        save()

    list_lock = False


# load lists
def load():

    global subreddit_list, watch_list, file_lock

    while file_lock:
        log_message("File load sleeping")
        sleep(1)
    
    file_lock = True

    try:
        with open("data_list.json") as json_file:
            data = json.load(json_file)

            subreddit_list = data["subreddit_list"]
            watch_list = data["watch_list"]

    except FileNotFoundError:
        file_lock = False
        save()
        load()

    file_lock = False


# save lists
def save():

    global subreddit_list, watch_list, file_lock

    while file_lock:
        log_message("File save sleeping")
        sleep(1)
    
    file_lock = True

    with open("data_list.json", "w") as json_file:
        json.dump({"subreddit_list": subreddit_list, "watch_list": watch_list}, json_file)

    file_lock = False


# save current time
def save_time():

    with open("time.txt", "w") as file:
        print(datetime.datetime.now().strftime('%y.%m.%d %H:%M:%S'), file=file)


# load last known time
def load_time():

    try:
        with open("time.txt") as file:
            return datetime.datetime.strptime(file.readline().strip(), '%y.%m.%d %H:%M:%S')
    
    except FileNotFoundError:
        save_time()
        return load_time()
        

# check if subreddit is public
def check_public(subreddit_name):

    try:
        if reddit.subreddit(subreddit_name).subreddit_type == "public":
            return True

    except NotFound:
        return False

    return True


# check if user exists
def check_user(user_name):

    try:
        reddit.redditor(user_name).id
    
    except NotFound:
        return False

    return True


# add new entry to search_list
def add(mention, subreddit):

    global subreddit_list, watch_list, active_thread_id, list_lock

    while list_lock:
        log_message("Add sleeping")
        sleep(1)

    list_lock = True

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

    list_lock = False
    
    return out


# cancel search
def cancel(mention, subreddit):

    global subreddit_list, watch_list, active_thread_id, list_lock

    while list_lock:
        log_message("Cancel sleeping")
        sleep(1)

    list_lock = True

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

    list_lock = False

    return removed


# return subreddit (could be from a message or from post)
def get_subreddit(mention):

    if mention.subject == "post reply":
        return mention.subreddit

    return str(mention.subject).replace("re:", "").replace("r/", "").replace("notify_me_bot:", "").strip()


# check all mentions
def check_inbox():

    global queue_mentions

    while True:
        try:
            new_mentions = []

            for mention in reddit.inbox.unread():
                new_mentions.append(mention)
                lowercase_body = mention.body.lower()

                # it's a response
                if not ("u/notify_me_bot" in lowercase_body or mention.subject != "post reply"): 
                    continue

                subreddit = get_subreddit(mention)
                if not check_public(subreddit) and ("cancel" in lowercase_body or "create" in lowercase_body):
                    message_text = 'No actions were performed.\n\nCheck, if the subreddit exists and it is public.'

                    # try to send message, or garbage
                    try:
                        mention.reply(message_text)
                    except:
                        queue_mentions.append([mention, message_text])

                    continue

                if "cancel" in lowercase_body:
                    removed = cancel(mention, subreddit)

                    if removed > 0:
                        message_text = 'Removed %d search listings.\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)' % (removed)
                    else:
                        message_text = 'No search listings were removed.\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)'

                    # try to send message, or garbage
                    try:
                        mention.reply(message_text)
                    except:
                        queue_mentions.append([mention, message_text])

                    continue

                if "create" in lowercase_body:
                    keywords = add(mention, subreddit)
                    message_text = 'New search added:\n\nSubreddit: %s\n\nUser: %s\n\nKeywords: %s\n\nSuggestions? Source? Need help? [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)' % (subreddit, mention.author, ", ".join(keywords))
                    
                    # try to send message, or garbage
                    try:
                        mention.reply(message_text)
                    except:
                        queue_mentions.append([mention, message_text])

                    continue

            reddit.inbox.mark_read(new_mentions)

        # reddit is not responding or something, idk, error - wait, try again
        except:
            log_error*("En error occured with inbox")
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

    global active_thread_id, queue_directs

    while True:
        try:
            log_message("Starting subreddits", "id: " + str(active_thread_id))

            # no search entries yet
            if not subreddit_list:
                sleep(10)
                continue

            subreddit = reddit.subreddit("+".join(subreddit_list))
            last_time = load_time()

            for submission in subreddit.stream.submissions():
                # there is a new active thread
                if active_thread_id != id:
                    return

                submission_time = datetime.datetime.fromtimestamp(submission.created_utc)

                # only check new posts
                if submission_time > last_time:
                    lowercase_title = str(submission.title).lower()
                    lowercase_body = str(submission.selftext).lower()

                    # loop through all watch lists
                    for item in watch_list:
                        if item[0] == submission.subreddit:
                            if submission.author != item[1] and check_keywords(item, lowercase_body, lowercase_title):
                                message = ['notify_me_bot: %s' % (item[0]), 'You requested a notification, here is your post:\n\n%s\n\nTo cancel this subreddit notifications, reply: cancel' % (submission.permalink)]
                                
                                # try to send message, or garbage
                                try:
                                    save_time()
                                    reddit.redditor(item[1]).message(message[0], message[1])
                                except:
                                    queue_directs.append([item[1], message])

        # reddit is not responding or something, idk, error - wait, try again
        except:
            log_error("En error occured with subreddits")

            if "400" in "".join(traceback.format_exception(*sys.exc_info())):
                purge_subreddits()

            sleep(60)


# resend messages that didn't go through
def garbage_collection():

    global queue_mentions, queue_directs

    while True:
        pos = 0

        while pos < len(queue_mentions) and queue_mentions:
            try:
                pos += 1
                queue_mentions[pos - 1][0].reply(queue_mentions[pos - 1][1])
                queue_mentions.remove(queue_mentions[pos - 1])
                pos -= 1

            except:
                if "RATELIMIT" in "".join(traceback.format_exception(*sys.exc_info())):
                    continue

                else:
                    log_error("Message didn't still go through", "\nAuthor:", queue_directs[pos - 1][0].author, "\nBody:", queue_directs[pos - 1][0].body, "\nReply body:", queue_mentions[pos - 1][1])

        pos = 0

        while pos < len(queue_directs) and queue_directs:
            try:
                pos += 1
                reddit.redditor(queue_directs[pos - 1][0]).message(queue_directs[pos - 1][1][0], queue_directs[pos - 1][1][1])
                queue_directs.remove(queue_directs[pos - 1])
                pos -= 1

            except:
                if "RATELIMIT" in "".join(traceback.format_exception(*sys.exc_info())):
                    continue

                else:
                    log_error("Message didn't still go through", "\nUser:", queue_directs[pos - 1][0], "\nObject:", queue_directs[pos - 1][1][0], "\nReply body:", queue_directs[pos - 1][1][1])

                if "USER_DOESNT_EXIST" in "".join(traceback.format_exception(*sys.exc_info())):
                    queue_directs.remove(queue_directs[pos - 1])
                    purge_users()

        sleep(60)


log_message("Starting")

load()
purge_subreddits()
purge_users()

Thread(target=check_subreddits, args=([active_thread_id])).start()
Thread(target=garbage_collection, args=()).start()
check_inbox()
