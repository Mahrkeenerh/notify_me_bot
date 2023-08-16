import asyncio
import datetime
import json
import psycopg2
import sys
import traceback
import tracemalloc

import asyncpraw
import asyncprawcore


tracemalloc.start()


reddit = None
cursor = None
watch_list = {}
watcher_sub_map = {}
user_watcher_map = {}
active_sub_id = 0

mentions_queue = []
directs_queue = []


def log_error(*args):
    print(f'\n{datetime.datetime.now()}')

    for i in args:
        print(i)

    print(traceback.print_exception(*sys.exc_info()))


def log_message(*args):
    print(f'\n{datetime.datetime.now()}')

    for i in args:
        print(i)


def save_time():
    with open('time.txt', 'w') as file:
        print(datetime.datetime.now().strftime('%y.%m.%d %H:%M:%S'), file=file)


def load_time():
    try:
        with open('time.txt') as file:
            return datetime.datetime.strptime(file.readline().strip(), '%y.%m.%d %H:%M:%S')

    except FileNotFoundError:
        save_time()
        return load_time()


async def sub_public(subreddit_name):
    try:
        if (await reddit.subreddit(subreddit_name, fetch=True)).subreddit_type == 'public':
            return True
    except asyncprawcore.exceptions.NotFound:
        return False

    return False


async def user_exists(user_name):
    try:
        await reddit.redditor(user_name).id

    except asyncprawcore.exceptions.NotFound:
        return False

    return True


def get_subreddit(subject):
    if subject in ['post reply', 'comment reply', 'username mention']:
        return 'comment'

    return subject.replace('r/', '').strip().lower()


async def create_watcher(mention, subreddit):
    global active_sub_id

    keywords = [i.strip() for i in mention.body.lower().strip().split(',')]

    requires_restart = False
    # add new subreddit to search
    if subreddit not in watch_list:
        watch_list[subreddit] = {}
        requires_restart = True

    str_author = str(mention.author).lower()
    cursor.execute(
        f'INSERT INTO watchers (username, subreddit, keywords) VALUES (%s, %s, %s) RETURNING watcher_id',
        (str_author, subreddit, ', '.join(keywords))
    )
    watcher_id = cursor.fetchall()[0][0]

    watch_list[subreddit][watcher_id] = [str_author, keywords]
    watcher_sub_map[watcher_id] = subreddit

    if str_author not in user_watcher_map:
        user_watcher_map[str_author] = set()

    user_watcher_map[str_author].add(watcher_id)

    if requires_restart:
        # restart checking subreddits
        active_sub_id += 1
        asyncio.create_task(check_subreddits(active_sub_id))

    mentions_queue.append({'mention': mention, 'message': f'New watcher created. ID: {watcher_id}\n\nSubreddit: {subreddit}\n\nKeywords: {", ".join(keywords)}\n\nKeyword count: {len(keywords)}'})


async def cancel_outer(mention):
    ids = [i.strip() for i in mention.body.replace('!', '').replace('cancel', '').strip().split(',')]

    if len(ids) == 1 and ids[0] == 'all':
        ids = user_watcher_map[str(mention.author).lower()]

    responses = [f'**Response{"s" if len(ids) > 1 else ""}:**']
    for id in ids:
        response = await cancel(mention, id)
        responses.append(response)

    # no ids, get id from subject
    if len(ids) == 0:
        id = mention.subject.replace('re:', '').replace('watcher', '').lower().split(':')[0].strip()
        response = await cancel(mention, id)
        responses.append(response)

    mentions_queue.append({'mention': mention, 'message': '\n\n---\n\n'.join(responses) + '\n\n---'})


async def cancel(mention, id):
    global active_sub_id

    try:
        id = int(id)
    except ValueError:
        return 'The ID must be a number.'

    if id not in watcher_sub_map:
        return 'Invalid ID.'

    str_author = str(mention.author).lower()

    if str_author in user_watcher_map and id not in user_watcher_map[str_author]:
        return 'You don\'t have permission to cancel this watcher.'

    cursor.execute(
        f'DELETE FROM watchers WHERE watcher_id = {id}',
    )

    subreddit = watcher_sub_map[id]
    del watcher_sub_map[id]
    del watch_list[subreddit][id]
    user_watcher_map[str_author].remove(id)

    if len(user_watcher_map[str_author]) == 0:
        del user_watcher_map[str_author]

    # remove subreddit if no watchers
    if not watch_list[subreddit]:
        del watch_list[subreddit]

        # restart checking subreddits
        active_sub_id += 1
        asyncio.create_task(check_subreddits(active_sub_id))

    return f'Watcher {id} canceled.'


async def list_watchers(mention):
    str_author = str(mention.author).lower()
    if str_author not in user_watcher_map:
        mentions_queue.append({'mention': mention, 'message': 'You don\'t have any active watchers.'})
        return

    watchers = user_watcher_map[str_author]

    message = 'Your watchers:\n\n'

    for watcher in watchers:
        message += f'---\n\n**ID: {watcher}**\n\nSubreddit: {watcher_sub_map[watcher]}\n\nKeywords: {", ".join(watch_list[watcher_sub_map[watcher]][watcher][1])}\n\n'

    message += '---'

    mentions_queue.append({'mention': mention, 'message': message})


async def check_inbox():
    log_message('Starting inbox')

    while True:
        try:
            new_mentions = []

            async for mention in reddit.inbox.unread():
                # TODO testing remove
                # if str(mention.author) != 'Mahrkeenerh1':
                #     continue

                new_mentions.append(mention)
                lowercase_body = mention.body.lower()

                # it's a response
                if not ('u/notify_me_bot' in lowercase_body or mention.subject != 'post reply'):
                    continue

                subject = mention.subject.replace('re:', '').strip().lower()

                # TODO catch replies to cancel

                # create advanced
                if lowercase_body.startswith('!advanced'):
                    subreddit = get_subreddit(subject.replace('!advanced', ''))
                    mentions_queue.append({'mention': mention, 'message': 'Nice catch, but this feature is not implemented yet.\n\nCheck [REWORK](https://www.reddit.com/user/notify_me_bot/comments/15ra4uf/rework_part_1/) for more info.'})
                    continue

                # cancel
                if lowercase_body.startswith('!cancel') or lowercase_body.startswith('cancel'):
                    await cancel_outer(mention)
                    continue

                # list
                if lowercase_body.startswith('!list'):
                    await list_watchers(mention)
                    continue

                # unknown command
                if lowercase_body.startswith('!'):
                    mentions_queue.append({'mention': mention, 'message': 'Sorry, I don\'t understand this command. Check if you have a typo or contact my creator [info_post](https://www.reddit.com/user/notify_me_bot/comments/mu01zx/introducing_myself/)'})
                    continue

                # comments
                subreddit = get_subreddit(subject)
                if subreddit == 'comment':
                    mentions_queue.append({'mention': mention, 'message': 'I don\'t respond to comments anymore.\n\nCheck [REWORK](https://www.reddit.com/user/notify_me_bot/comments/15ra4uf/rework_part_1/) for more info.'})
                    continue

                # not public
                if not await sub_public(subreddit):
                    mentions_queue.append({'mention': mention, 'message': 'Sorry, but the requested subreddit is not public, or doesn\'t exist.'})
                    continue

                # create simple watcher
                await create_watcher(mention, subreddit)
                continue

            await reddit.inbox.mark_read(new_mentions)
            await asyncio.sleep(10)

        # reddit is not responding or something, idk, error - wait, try again
        except:
            log_error('En error occured with inbox')
            await asyncio.sleep(60)


def check_keywords(keywords, lowercase_body, lowercase_title):
    reply = False

    for keyword in keywords:
        if keyword in lowercase_body or keyword in lowercase_title:
            reply = True
            break

    return reply


async def check_subreddits(my_id):
    while True:
        try:
            log_message('Starting subreddits', f'id: {active_sub_id}')

            # no search entries yet
            if not watch_list:
                log_message('No search entries yet')
                await asyncio.sleep(10)
                continue

            subreddit = await reddit.subreddit('+'.join(watch_list.keys()))
            last_time = load_time()

            async for submission in subreddit.stream.submissions():
                # there is a new active thread
                if active_sub_id != my_id:
                    return

                submission_time = datetime.datetime.fromtimestamp(submission.created_utc)

                # only check new posts
                if submission_time > last_time:
                    lowercase_title = str(submission.title).lower()
                    lowercase_body = str(submission.selftext).lower()
                    subreddit_name = str(submission.subreddit).lower()

                    responded_to = set()

                    # loop through all watch lists
                    for watcher_id, (user, keywords) in watch_list[subreddit_name].items():
                        if str(submission.author) != user and user not in responded_to and check_keywords(keywords, lowercase_body, lowercase_title):
                            save_time()
                            responded_to.add(user)
                            directs_queue.append({
                                'user': user,
                                'subject': f'Watcher {watcher_id}: {subreddit_name}',
                                'message': f'Notification for post: [{submission.permalink}]({"https://reddit.com" + submission.permalink})\n\nTo cancel, check [REWORK](https://www.reddit.com/user/notify_me_bot/comments/15ra4uf/rework_part_1/) for info. Simple cancelation will be added soon.\n\nKeywords: {", ".join(keywords)}'
                            })

        # reddit is not responding or something, idk, error - wait, try again
        except:
            log_error('En error occured with subreddits')
            await asyncio.sleep(60)


def build_watch_list():
    cursor.execute(
        f'SELECT watcher_id, username, subreddit, keywords FROM watchers',
    )

    for watcher_id, author, subreddit, keywords in cursor.fetchall():
        if subreddit not in watch_list:
            watch_list[subreddit] = {}

        watch_list[subreddit][watcher_id] = [author, keywords.split(', ')]
        watcher_sub_map[watcher_id] = subreddit

        if author not in user_watcher_map:
            user_watcher_map[author] = set()

        user_watcher_map[author].add(watcher_id)        


async def handle_mention_queue():
    while True:
        pos = 0

        if len(mentions_queue) != 0:
            log_message('Mention queue length:', len(mentions_queue))

        while mentions_queue and pos < len(mentions_queue):
            try:
                pos += 1
                if 'c' not in mentions_queue[pos - 1]:
                    mentions_queue[pos - 1]['c'] = 0

                await mentions_queue[pos - 1]['mention'].reply(mentions_queue[pos - 1]['message'])
                mentions_queue.pop(pos - 1)
                pos -= 1

            except asyncpraw.exceptions.RedditAPIException:
                if 'RATELIMIT' in ''.join(traceback.format_exception(*sys.exc_info())):
                    continue

                mentions_queue[pos - 1]['c'] += 1
                if mentions_queue[pos - 1]['c'] > 3:
                    mentions_queue.pop(pos - 1)
                    pos -= 1
                    log_error('Canceled message', mentions_queue[pos - 1]['mention'].author, mentions_queue[pos - 1]['mention'].subject, mentions_queue[pos - 1]['message'])

        await asyncio.sleep(10)


async def handle_direct_queue():
    while True:
        pos = 0

        if len(directs_queue) != 0:
            log_message('Direct queue length:', len(directs_queue))

        while directs_queue and pos < len(directs_queue):
            try:
                pos += 1
                if 'c' not in directs_queue[pos - 1]:
                    directs_queue[pos - 1]['c'] = 0

                redditor = await reddit.redditor(directs_queue[pos - 1]['user'])
                await redditor.message(directs_queue[pos - 1]['subject'], directs_queue[pos - 1]['message'])
                directs_queue.pop(pos - 1)
                pos -= 1

            except asyncpraw.exceptions.RedditAPIException:
                if 'RATELIMIT' in ''.join(traceback.format_exception(*sys.exc_info())):
                    continue

                directs_queue[pos - 1]['c'] += 1
                if directs_queue[pos - 1]['c'] > 3:
                    directs_queue.pop(pos - 1)
                    pos -= 1
                    log_error('Canceled message', directs_queue[pos - 1]['user'], directs_queue[pos - 1]['subject'], directs_queue[pos - 1]['message'])

        await asyncio.sleep(10)


async def main():
    global reddit, cursor

    with open('config.json') as config_file:
        config_json = json.load(config_file)

        db_connection = psycopg2.connect(
            host=config_json['db_host'],
            database=config_json['db_database'],
            user=config_json['db_user'],
            password=config_json['db_pass'],
            port=config_json['db_port']
        )
        db_connection.autocommit = True
        cursor = db_connection.cursor()

        reddit = asyncpraw.Reddit(
            client_id=config_json['cID'],
            client_secret=config_json['cSC'],
            user_agent=config_json['userAgent'],
            username=config_json['userN'],
            password=config_json['userP']
        )

        reddit.config.ratelimit_seconds = 60

    build_watch_list()

    await asyncio.gather(check_inbox(), check_subreddits(0), handle_mention_queue(), handle_direct_queue())


asyncio.run(main())
