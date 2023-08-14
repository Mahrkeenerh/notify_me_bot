import json
import psycopg2

with open('data_list.json') as f:
    data = json.load(f)

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

for watch in data['watch_list']:
    cursor.execute(
        f'INSERT INTO watchers (username, subreddit, keywords) VALUES (%s, %s, %s)'
        (watch[1].lower(), watch[0].lower(), ", ".join(watch[2]))
    )
