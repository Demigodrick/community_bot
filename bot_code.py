import time
import random
import pytz
from datetime import datetime, timedelta, timezone
import sqlite3
from disposable_email_domains import blocklist
import feedparser
from dateutil.relativedelta import relativedelta
from nio import AsyncClient, MatrixRoom
import toml
from config import settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import logging
import requests
import os
import re
import asyncio
import bot_strings
from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType, FeatureType


# logging stuff for healthcheck
LOG_FILE_PATH = 'resources/zippy.log'

log_level = getattr(logging, settings.DEBUG_LEVEL.upper(), logging.INFO)

logger = logging.getLogger()
logger.setLevel(log_level)

# write to healthcheck file
file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))

# write to stderr
stream_handler = logging.StreamHandler()
stream_handler.setLevel(log_level)
stream_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logging.info(f"Log level set to {settings.DEBUG_LEVEL}")

####################### N O T E S ###############################
#  Add in reports for messages (doesnt exist in pythorhead yet)
#  anti-spam measure for an ID?


def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE, request_timeout=10)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)

    return lemmy


def create_table(conn, table_name, table_definition):
    curs = conn.cursor()
    curs.execute(
        f'''CREATE TABLE IF NOT EXISTS {table_name} {table_definition}''')
    conn.commit()
    logging.debug(f"Checked/created {table_name} table")


def check_dbs():
    """
    Check the status of the configured databases and ensure they are accessible.

    This function is used to validate database connections and configurations.
    """
    try:
        with sqlite3.connect('resources/vote.db') as conn:
            # Create or check votes table
            create_table(
                conn,
                'votes',
                '(vote_id INT, username TEXT, vote_result TEXT, account_age TEXT)')

            # Create or check polls table
            create_table(
                conn,
                'polls',
                '(poll_id INTEGER PRIMARY KEY AUTOINCREMENT, poll_name TEXT, username TEXT, open TEXT)')

        with sqlite3.connect('resources/users.db') as conn:
            # Create or check users table
            create_table(
                conn,
                'users',
                '(local_user_id INT, public_user_id INT, username TEXT, has_posted INT, has_had_pm INT, email TEXT, subscribed INT)')

            # Create or check communities table
            create_table(
                conn,
                'communities',
                '(community_id INT, community_name TEXT)')

        with sqlite3.connect('resources/games.db') as conn:
            # create or check game deals table
            create_table(conn, 'deals', '(deal_name TEXT, deal_date TEXT)')

        with sqlite3.connect('resources/welcome/welcome.db') as conn:
            # create or check welcome messages table
            create_table(
                conn,
                'messages',
                '(community TEXT UNIQUE, message TEXT)')

        with sqlite3.connect('resources/mod_actions.db') as conn:
            # create or check new posts table
            create_table(
                conn,
                'new_posts',
                '(post_id INT, poster_id INT, mod_action STR)')

            # create or check new comments table
            create_table(
                conn,
                'new_comments',
                '(comment_id INT, comment_poster INT, mod_action STR)')

            # create or check community words table
            create_table(
                conn,
                'community_words',
                '(community TEXT UNIQUE, words TEXT, action TEXT)')

            # create or check user warnings table
            create_table(
                conn,
                'warnings',
                '(user_id INT, warning_reason TEXT, admin TEXT)')

            # create or check rss tables
        with sqlite3.connect('resources/rss.db') as conn:
            create_table(conn, 'feeds', '''
                (feed_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL UNIQUE,
                url_contains_filter TEXT,
                title_contains_filter TEXT,
                url_excludes_filter TEXT,
                title_excludes_filter TEXT,
                community TEXT,
                tag TEXT,
                body BOOL,
                last_updated TIMESTAMP)
            ''')

            create_table(conn, 'posts', '''
                (post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER,
                post_url TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                posted BOOLEAN DEFAULT 0,
                post_date TIMESTAMP,
                FOREIGN KEY(feed_id) REFERENCES feeds(feed_id))
            ''')

            # create or check reports tables
        with sqlite3.connect('resources/reports.db') as conn:
            create_table(
                conn,
                'post_reports',
                '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, post_id INT)')

            create_table(
                conn,
                'comment_reports',
                '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, comment_id INT)')

            # create_table(conn, 'message_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, message_id INT)')

        with sqlite3.connect('resources/autopost.db') as conn:
            create_table(
                conn,
                'com_posts',
                '(pin_id INTEGER PRIMARY KEY AUTOINCREMENT, community_id INT, mod_id INT, post_title TEXT, post_url TEXT, post_body TEXT, scheduled_post TIME, frequency TEXT, previous_post INT)')

        with sqlite3.connect('resources/giveaway.db') as conn:
            create_table(
                conn,
                'giveaways',
                '(giveaway_id INTEGER PRIMARY KEY, thread_id TEXT, status TEXT DEFAULT "active")')

            create_table(
                conn,
                'entrants',
                '(ticket_number INTEGER PRIMARY KEY AUTOINCREMENT, giveaway_id INTEGER, username TEXT, entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (giveaway_id) REFERENCES giveaways (giveaway_id), UNIQUE (giveaway_id, username))')

        logging.debug("All tables checked.")

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    except Exception as e:
        logging.error(f"Exception in _query: {e}")


def connect_to_vote_db():
    return sqlite3.connect('resources/vote.db')


def connect_to_rss_db():
    return sqlite3.connect('resources/rss.db')


def connect_to_users_db():
    return sqlite3.connect('resources/users.db')


def connect_to_welcome_db():
    return sqlite3.connect('resources/welcome/welcome.db')


def connect_to_reports_db():
    return sqlite3.connect('resources/reports.db')


def connect_to_autopost_db():
    return sqlite3.connect('resources/autopost.db')


def connect_to_mod_db():
    return sqlite3.connect('resources/mod_actions.db')


def connect_to_giveaway_db():
    return sqlite3.connect('resources/giveaway.db')


def execute_sql_query(connection, query, params=()):
    with connection:
        curs = connection.cursor()
        curs.execute(query, params)
        return curs.fetchone()


def check_version():
 # confirm to admin chat zippybot is up and running
    last_version_file = 'resources/last_ver'
    last_version = None
    current_time = datetime.now()
    time_string = current_time.strftime("%H:%M:%S")

    config = toml.load('.bumpversion.toml')
    current_version = config["tool"]["bumpversion"]["current_version"]

    if os.path.exists(last_version_file):
        with open(last_version_file, "r") as f:
            last_version = f.read().strip()

    if last_version != current_version:
        logging.info(f"Version updated: {last_version} -> {current_version}")
        with open(last_version_file, "w") as f:
            f.write(current_version)
        logging.debug("All tables checked.")

        if settings.STARTUP_WARNING and settings.MATRIX_FLAG:
            matrix_body = f"ZippyBot has been updated and has restarted at {time_string}. Version updated: {last_version} -> {current_version}"
            asyncio.run(send_matrix_message(matrix_body))
            return

    if settings.STARTUP_WARNING and settings.MATRIX_FLAG:

        matrix_body = f"ZippyBot has been rebooted at {time_string}. If you weren't expecting this, Zippy has recovered from a crash."
        asyncio.run(send_matrix_message(matrix_body))

    logging.info(f"Bot Version {current_version}")


def add_vote_to_db(pm_username, vote_id, vote_response, pm_account_age):
    try:
        with connect_to_vote_db() as conn:
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id, poll_name FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (vote_id,))

            if check_valid is None:
                logging.debug(
                    "Submitted vote_id did not match a valid poll_id")
                return "notvalid"

            # check poll is still open
            closed_query = '''SELECT poll_id, open FROM polls where poll_id=?'''
            check_open = execute_sql_query(conn, closed_query, (vote_id,))
            if check_open[1] == "0":
                return "closed"

            poll_name = check_valid[1]
            # Check if vote response is already recorded for this user/vote id
            vote_query = '''SELECT vote_id, username FROM votes WHERE vote_id=? AND username=?'''
            row = execute_sql_query(conn, vote_query, (vote_id, pm_username))

            if row:
                logging.debug("Matching vote found")
                return "duplicate"

            # If no duplicate votes, add new vote
            sqlite_insert_query = """INSERT INTO votes (vote_id, username, vote_result, account_age) VALUES (?, ?, ?, ?);"""
            data_tuple = (vote_id, pm_username, vote_response, pm_account_age)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added vote to database")
            return poll_name
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def create_poll(poll_name, pm_username):
    try:
        with connect_to_vote_db() as conn:
            isopen = True
            data_tuple = (poll_name, pm_username, isopen)
            sqlite_insert_query = """INSERT INTO polls (poll_name, username, open) VALUES (?, ?, ?);"""
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            # Get the ID of the poll just created
            poll_id_query = "SELECT last_insert_rowid()"
            poll_id = execute_sql_query(conn, poll_id_query)[0]

            logging.debug(
                f"Added poll to database with ID number {poll_id}")
            return poll_id
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def close_poll(poll_id):
    try:
        with connect_to_vote_db() as conn:
            set_open = "0"
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (poll_id,))

            if check_valid is None:
                logging.debug(
                    "Submitted vote_id did not match a valid poll_id")
                return "notvalid"

            sqlite_update_query = """UPDATE polls SET open = ? WHERE poll_id = ?;"""
            execute_sql_query(conn, sqlite_update_query, (set_open, poll_id))
            return "closed"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def count_votes(poll_id):
    try:
        with connect_to_vote_db() as conn:
            yes_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'yes' AND vote_id = ?;"
            no_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'no' AND vote_id = ?;"
            yes_count = execute_sql_query(conn, yes_query, (poll_id,))[0]
            no_count = execute_sql_query(conn, no_query, (poll_id,))[0]
            return yes_count, no_count

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def add_autopost_to_db(post_data):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = """
            INSERT INTO com_posts (community_id, mod_id, post_title, post_url, post_body, frequency, scheduled_post)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            values = (
                post_data['community'],
                post_data['mod_id'],
                post_data['title'],
                post_data['url'],
                post_data['body'],
                post_data['frequency'],
                post_data['scheduled_post']
            )
            cursor.execute(query, values)
            conn.commit()

            # Get the ID of the autopost just created
            autopost_id_query = "SELECT last_insert_rowid()"
            autopost_id = execute_sql_query(conn, autopost_id_query)[0]
            return autopost_id
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def delete_rss(feed_id, pm_sender):
    try:
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM feeds WHERE feed_id = ?", (feed_id,))
        feed = cursor.fetchone()
        if feed is None:
            return "no_exist"

        community = feed[6]

        output = lemmy.community.get(community)

        # check if user is moderator of community
        is_moderator = False

        for moderator_info in output['moderators']:
            if moderator_info['moderator']['id'] == pm_sender:
                is_moderator = True
                break

        if not is_moderator:
            return "not_mod"

        cursor.execute("DELETE FROM posts WHERE feed_id = ?", (feed_id,))
        cursor.execute("DELETE FROM feeds WHERE feed_id = ?", (feed_id,))
        conn.commit()
        logging.info("Feed and related posts deleted successfully.")
        return "deleted"

    except sqlite3.IntegrityError as e:
        logging.debug(f"Integrity error: {e}")
    except sqlite3.Error as e:
        logging.debug(f"Database error: {e}")
    except Exception as e:
        logging.debug(f"Unexpected error: {e}")


def delete_welcome(com_name, pm_sender):
    try:
        with connect_to_welcome_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE community = ?", (com_name,))
            row = cursor.fetchone()
            if row is None:
                return "no_exist"

        output = lemmy.community.get(name=com_name)
        is_moderator = False
        for moderator_info in output['moderators']:
            if moderator_info['moderator']['id'] == pm_sender:
                is_moderator = True
                break

        if not is_moderator:
            return "not_mod"

        cursor.execute("DELETE FROM messages WHERE community = ?", (com_name,))
        conn.commit()
        return "deleted"

    except sqlite3.IntegrityError as e:
        logging.debug(f"Integrity error: {e}")
    except sqlite3.Error as e:
        logging.debug(f"Database error: {e}")
    except Exception as e:
        logging.debug(f"Unexpected error: {e}")


def delete_autopost(pin_id, pm_sender, del_post):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM com_posts WHERE pin_id = ?"
            cursor.execute(query, (pin_id,))
            full_row = cursor.fetchone()

            community_name = full_row[1]
            mod_id = full_row[2]
            prev_post = full_row[8]

            # check it has not already been deleted
            if community_name is None:
                return "no id"

            # check if delete request came from original author
            if mod_id == pm_sender:
                query = "DELETE FROM com_posts WHERE pin_id = ?"
                cursor.execute(query, (pin_id,))
                conn.commit()
                if prev_post is not None:
                    if del_post:
                        lemmy.post.delete(prev_post, True)
                return "deleted"

            # not a match, check if sender is a mod of the community
            output = lemmy.community.get(name=community_name)

            is_moderator = False

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (pin_id,))
                    conn.commit()
                    if prev_post is not None:
                        if del_post:
                            lemmy.post.delete(prev_post, True)
                    return "deleted"

            if not is_moderator:
                return "not mod"

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def clear_notifications():
    try:
        notif = lemmy.comment.get_replies(True, 1)
        all_notifs = notif['replies']
    except BaseException:
        logging.info("Error with connection, retrying...")
        login()
        return

    for notif in all_notifs:
        reply_id = notif['comment_reply']['id']
        lemmy.comment.mark_as_read(reply_id, True)

def check_pms():
    try:
        pm = lemmy.private_message.list(True, 1)

        private_messages = pm['private_messages']
    except BaseException:
        logging.info(
            "Error with connection, skipping checking private messages...")
        return

    for pm_data in private_messages:
        pm_sender = pm_data['private_message']['creator_id']
        pm_username = pm_data['creator']['name']
        pm_context = pm_data['private_message']['content']
        pm_id = pm_data['private_message']['id']
        pm_account_age = pm_data['creator']['published']

        output = lemmy.user.get(pm_sender)
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['is_admin']

        # open to anyone on lemmy. handles urgent mod reports.
        split_context = pm_context.split(" -")

        # first make sure the pm isn't coming from zippy otherwise it'll put
        # zippy in a loop.
        if pm_sender == settings.BOT_ID:
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        # IMPORTANT keep this here - only put reply code above that you want
        # ANYONE ON LEMMY/FEDIVERSE TO BE ABLE TO ACCESS outside of your
        # instance when they message your bot.
        if user_local != settings.LOCAL:
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username} \n\n {bot_strings.LOCAL_ONLY_WARNING}\n \n {bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#help":
            pm_help(user_admin, pm_username, pm_id, pm_sender)
            continue
        
        if pm_context == "#autoposthelp":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.AUTOPOST_HELP}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == '#rsshelp':
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.RSS_HELP}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#rules":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.INS_RULES}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#credits":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.CREDITS}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#feedback":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\nThe access code for the feedback survey is {settings.SURVEY_CODE}\n\n You can access the survey by [clicking here]({bot_strings.FEEDBACK_URL}) and selecting the available survey.\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context in ["#unsubscribe", "#subscribe"]:
            status = "unsub" if pm_context == "#unsubscribe" else "sub"
            pm_sub(pm_sender, status, pm_username, pm_id)
            continue


        if pm_context.split(" -")[0] == "#takeover":
            if user_admin:
                community_name = pm_context.split("-")[1].strip()
                user_id = pm_context.split("-")[2].strip()

                if user_id == "self":
                    user_id = pm_id

                community_id = lemmy.discover_community(community_name)

                logging.info(
                    "Request for community " +
                    community_name +
                    " to be transferred to " +
                    user_id)

                if community_id is None:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". Sorry, I can't find the community you've requested.",
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                lemmy.community.add_mod_to_community(
                    True, community_id=int(community_id), person_id=int(user_id))
                lemmy.private_message.create(
                    "Confirmation: " +
                    community_name +
                    "(" +
                    str(community_id) +
                    ") has been taken over by user id " +
                    str(user_id),
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" ")[0] == "#vote":
            vote_id = pm_context.split(" ")[1]
            vote_response = pm_context.split(" ")[2]

            db_response = add_vote_to_db(
                pm_username, vote_id, vote_response, pm_account_age)

            if db_response == "duplicate":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Oops! It looks like you've already voted on this poll. Votes can only be counted once. "
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "notvalid":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Oops! It doesn't look like the poll you've tried to vote on exists. Please double check the vote ID and try again."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "closed":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Sorry, it appears the poll you're trying to vote on is now closed. Please double check the vote ID and try again."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            else:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Your vote has been counted on the '" +
                    db_response +
                    "' poll. Thank you for voting! "
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" @")[0] == "#poll":
            if user_admin:
                poll_name = pm_context.split("@")[1]
                poll_id = create_poll(poll_name, pm_username)
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Your poll has been created with ID number " +
                    str(poll_id) +
                    ". You can now give this ID to people and they can now cast a vote using the `#vote` operator."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". You need to be an instance admin in order to create a poll."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" @")[0] == "#closepoll":
            if user_admin:
                poll_id = pm_context.split("@")[1]
                if close_poll(poll_id) == "closed":
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". Your poll (ID = " +
                        poll_id +
                        ") has been closed"
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
                else:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". I couldn't close that poll due to an error."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

        if pm_context.split(" @")[0] == "#countpoll":
            if user_admin:
                poll_id = pm_context.split("@")[1]
                yes_votes, no_votes = count_votes(poll_id)
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". There are " +
                    str(yes_votes) +
                    " yes votes and " +
                    str(no_votes) +
                    " no votes on that poll."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" ")[0] == "#giveaway":
            if user_admin:
                thread_id = pm_context.split(" ")[1]
                add_giveaway_thread(thread_id)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" ")[0] == "#closegiveaway":
            if user_admin:
                thread_id = pm_context.split(" ")[1]
                close_giveaway_thread(thread_id)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" ")[0] == "#drawgiveaway":
            if user_admin:
                thread_id = pm_context.split(" ")[1]
                num_winners = pm_context.split(" ")[2]
                draw_status = draw_giveaway_thread(thread_id, num_winners)
                if draw_status == "min_winners":
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". There are too few entrants to draw your giveaway with that many winners. Please reduce the amount of winners or encourage more entrants!"
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                winners = draw_status
                winner_names = ', '.join(winners)
                comment_body = f"Congratulations to the winners of this giveaway: {winner_names}!\n\nThe winners of this giveaway have been drawn randomly by ZippyBot."
                lemmy.comment.create(int(thread_id), comment_body)
                lemmy.post.lock(int(thread_id), True)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        # broadcast messages
        if pm_context.split(" ")[0] == "#broadcast":
            if user_admin:
                message = pm_context.replace('#broadcast', "", 1)
                broadcast_message(message)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" ")[0] == "#rssdelete":
            feed_id = pm_context.split(" ")[1]
            status = delete_rss(feed_id, pm_sender)

            if status == "no_exist":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Sorry, there is not an RSS feed with that ID number. Please try again."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if status == "not_mod":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Sorry, you'll need to be a mod of this community before deleting an RSS feed."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if status == "deleted":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". The RSS feed has been deleted for this community."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" ")[0] == "#welcomedelete":
            com_name = pm_context.split(" ")[1]
            status = delete_welcome(com_name, pm_sender)

            if status == "no_exist":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Sorry, there is not a Welcome message associated with that community."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if status == "not_mod":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Sorry, you'll need to be a mod of this community before deleting the Welcome message."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if status == "deleted":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". The Welcome message has been deleted for this community."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        # mod action - add words to be scanned for community
        if pm_context.split(" ")[0] == "#comscan":

            parts = pm_context.split()
            filters = {
                'words': None,
                'community': None,
                'action': None
            }

            flag = None
            for part in parts:
                if part.startswith('-'):
                    flag = part
                elif flag:
                    if flag == '-w':
                        filters['words'] = part.split(',')
                    elif flag == '-a':
                        filters['action'] = part
                    elif flag == '-c':
                        filters['community'] = part
                    flag = None

            if not filters['community']:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". You will need to specify the community with the `-c` flag for this tool to work."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if not filters['words']:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". You will need to specify words in a comma seperated list, i.e. `-w word1,word2,word3`."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if not filters['action']:
                filters['action'] = "report"

            if filters['action'] != "report" and filters['action'] != "remove":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". You've not defined a valid action to take. Please ensure you either use `-a report` or `-a remove`."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            output = lemmy.community.get(name=filters['community'])

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    break

            if not is_moderator:
                # if pm_sender is not a moderator, send a private message
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". As you are not the moderator of this community, you are not able to use this tool for it."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            word_add_result = add_community_word(
                filters['community'],
                filters['words'],
                filters['action']
            )

            if word_add_result == "added":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Your list of words has been created/updated. ZippyBot will scan for these words and action them as requested."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        # mod action - add welcome message to community
        if pm_context.split(" ")[0] == "#welcome":
            try:

                filters = {
                    'community': None,
                    'message': None
                }

                c_index = pm_context.find('-c')
                m_index = pm_context.find('-m')

                # Extract community name
                if c_index != -1 and m_index != -1:
                    community_name = pm_context[c_index + 3:m_index].strip()
                    filters['community'] = community_name

                # Extract message, considering everything after "-m"
                if m_index != -1:
                    message = pm_context[m_index + 3:].strip(' “”"\'\n')
                    filters['message'] = message

                if not filters['message']:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". Sorry, you can't have a blank welcome message for a community. Please include some text, personalise the message and make it welcoming and friendly!"
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                output = lemmy.community.get(name=filters['community'])

                if output is None:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". The community you requested can't be found. Please double check the spelling and name and try again."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                for moderator_info in output['moderators']:
                    if moderator_info['moderator']['id'] == pm_sender:
                        is_moderator = True
                        break

                if not is_moderator:
                    # if pm_sender is not a moderator, send a private message
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". As you are not the moderator of this community, you are not able to set a welcome message for it."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                welcome_message_result = add_welcome_message(
                    filters['community'],
                    filters['message']
                )

                if welcome_message_result == "added":
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". I have successfully added the welcome message to the community. You can run this command again to change the message."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                continue
            except Exception as e:
                logging.error(f"An error occurred: {e}")

        # mod/admin action - create rss feed in community
        if pm_context.split(" ")[0] == "#rss":
            try:
                pattern = r'-(url|url_exc|url_inc|title_inc|title_exc|c|t|new_only|ignore)\s*(?:(?:"(.*?)")|(?:“(.*?)”)|([^\s]+))?(?=\s+-|$)'

                filters = {
                    'feed_url': None,
                    'url_excludes_filter': None,
                    'url_contains_filter': None,
                    'title_excludes_filter': None,
                    'title_contains_filter': None,
                    'community': None,
                    'tag': None
                }

                ignore_bozo_check = False
                new_only = False

                matches = re.findall(pattern, pm_context)

                for match in matches:
                    flag = match[0]
                    value = next((m for m in match[1:] if m), None)

                    if flag == 'url':
                        filters['feed_url'] = value
                    elif flag == 'url_exc':
                        filters['url_excludes_filter'] = value
                    elif flag == 'url_inc':
                        filters['url_contains_filter'] = value
                    elif flag == 'title_inc':
                        filters['title_contains_filter'] = value
                    elif flag == 'title_exc':
                        filters['title_excludes_filter']
                    elif flag == 'c':
                        filters['community'] = value
                    elif flag == 't':
                        filters['tag'] = value
                    elif flag == 'new_only':
                        new_only = True
                    elif flag == 'ignore':
                        ignore_bozo_check = True

                if not filters['feed_url']:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". You will need to include a link to an RSS feed for this to work."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                if not filters['community']:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". You will need to specify the community you want the RSS feed to be posted to with `-c community_name`."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                output = lemmy.community.get(name=filters['community'])

                if output is None:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". The community you requested can't be found. Please double check the spelling and name and try again."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                com_name = filters['community']
                filters['community'] = lemmy.discover_community(
                    filters['community'])

                # check if user is moderator of community
                is_moderator = False

                for moderator_info in output['moderators']:
                    if moderator_info['moderator']['id'] == pm_sender:
                        is_moderator = True
                        break

                if not is_moderator:
                    # if pm_sender is not a moderator, send a private message
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". As you are not the moderator of this community, you are not able to add an RSS feed to it."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                # check url is a valid rss feed
                feed_url = filters['feed_url']
                valid_rss = feedparser.parse(feed_url)
                if not ignore_bozo_check and (
                        valid_rss.bozo != 0 or 'title' not in valid_rss.feed):
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". I can't find a valid RSS feed in the URL you've provided. Please double check you're linking directly to an RSS feed."
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                else:
                    add_new_feed_result = add_new_feed(
                        filters['feed_url'],
                        filters['url_contains_filter'],
                        filters['url_excludes_filter'],
                        filters['title_contains_filter'],
                        filters['title_excludes_filter'],
                        filters['community'],
                        filters['tag']
                    )

                    if add_new_feed_result == "exists":
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            f". The RSS feed you're trying to add already exists in the [{com_name}](/c/{com_name}@{settings.INSTANCE}) community.",
                            pm_sender)
                    elif add_new_feed_result is None:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            ". An error occurred while adding the RSS feed. Please try again.",
                            pm_sender)
                    else:
                        feed_id = add_new_feed_result
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            f". I have successfully added the requested RSS feed to the [{com_name}](/c/{com_name}@{settings.INSTANCE}) community. The ID for this RSS feed is {add_new_feed_result} - please keep this safe as you'll need it if you want to delete the feed in the future.",
                            pm_sender)

                    lemmy.private_message.mark_as_read(pm_id, True)

                    if new_only:
                        with connect_to_rss_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag
                                FROM feeds
                                WHERE feed_url = ?
                                """, (feed_url,))

                            feed_details = cursor.fetchone()

                        if feed_details:
                            feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag = feed_details
                            posts = fetch_latest_posts(
                                feed_url,
                                url_contains_filter,
                                url_excludes_filter,
                                title_contains_filter,
                                title_excludes_filter,
                                community,
                                tag)
                            for post in posts:
                                insert_new_post(feed_id, post)

                continue
            except Exception as e:
                logging.error(f"An error occurred: {e}")

        # mod action - pin a post
        if pm_context.split(" ")[0] == '#autopost':
            # define the pattern to match each qualifier and its following
            # content
            pattern = r"-(c|t|b|u|d|h|f)\s+(\"[^\"]*\"|'[^']*'|[^\"\s-][^\s-]*)"

            # find all matches
            matches = re.findall(pattern, pm_context)

            post_data = {
                'community': None,
                'mod_id': None,
                'title': None,
                'url': None,
                'body': None,
                'day': None,
                'time': None,
                'frequency': None
            }

            # map the matches to the correct keys in the dictionary
            for key, value in matches:
                # If the value is wrapped in quotes, remove the quotes
                if value.startswith('"') and value.endswith(
                        '"') or value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                if key == 'c':
                    post_data['community'] = value
                elif key == 't':
                    post_data['title'] = value
                elif key == 'b':
                    post_data['body'] = value
                elif key == 'u':
                    post_data['url'] = value
                elif key == 'd':
                    post_data['day'] = value
                elif key == 'h':
                    post_data['time'] = value
                elif key == 'f':
                    post_data['frequency'] = value

            # check mandatory fields
            if post_data['community'] is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". In order to use this command, you will need to specify a community with the `-c` flag, i.e. `-c gaming`."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['title'] is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". In order to use this command, you will need to specify a title with the `-t` flag, i.e. `-t Weekly Thread`. You can also use the following commands in the title: \n\n"
                    "- %d (Day - i.e. 12) \n"
                    "- %m (Month - i.e. June) \n"
                    "- %y (Year - i.e. 2023) \n"
                    "- %w (Weekday - i.e. Monday) \n\n"
                    "For example, `Gaming Thread %w %d %m %y` would give you a title of `Gaming Thread Monday 12 June 2023`."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['day'] is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". In order to use this command, you will need to specify a day of the week with the `-d` flag, i.e. `-d monday`, or a specific date you want the first post to be posted in YYYYMMDD format, i.e. `-d 20230612."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['time'] is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". In order to use this command, you will need to specify a time with the `-h` flag, i.e. `-h 07:30` Remember all times are UTC!."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['frequency'] is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". In order to use this command, you will need to specify a post frequency with the `-f` flag, i.e. `-f weekly`. \n\n"
                    "You can use the following frequencies: \n"
                    "- once (the post will only happen once) \n"
                    "- weekly (every 7 days) \n"
                    "- fortnightly (every 14 days) \n"
                    "- 4weekly (every 28 days) \n"
                    "- monthly (once a month)"
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['frequency'] not in [
                    "once", "weekly", "fortnightly", "4weekly", "monthly"]:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". I couldn't find a valid frequency following the -f flag. \n\n"
                    "You can use the following frequencies: \n"
                    "- once (the post will only happen once) \n"
                    "- weekly (every 7 days) \n"
                    "- fortnightly (every 14 days) \n"
                    "- 4weekly (every 28 days) \n"
                    "- monthly (once a month)"
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # check community is real
            output = lemmy.community.get(name=post_data['community'])

            if output is None:
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". The community you requested can't be found. Please double check the spelling and name and try again."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # check if user is moderator of community
            is_moderator = False

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    break  # stop the loop as soon as we find a matching moderator

            if not is_moderator:
                # if pm_sender is not a moderator, send a private message
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". As you are not the moderator of this community, you are not able to create a scheduled post for it."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            post_data['mod_id'] = pm_sender

            date_format = "%Y%m%d"

            try:
                parsed_date = datetime.strptime(post_data['day'], date_format)
                # check if the date is in the past
                if parsed_date.date() < datetime.now().date():
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". The date of the post you scheduled is in the past. Unfortunately I don't have a time machine :( \n\n"
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
                else:
                    day_type = "date"
            except ValueError:
                # if it's not a date, check if it's a day of the week
                weekdays = [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday"]
                if post_data['day'].lower() in weekdays:
                    day_type = "day"
                else:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". Sorry, I can't work out when you want your post scheduled. Please pick a day of the week or specify a date you want recurring posts to start! Remember dates should be in YYYYMMDD format. \n\n"
                        "\n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

            # Convert the day, time, and frequency into a scheduled datetime
            if day_type == "day":
                if post_data['day'] and post_data['time']:
                    next_post_date = get_first_post_date(
                        post_data['day'], post_data['time'], post_data['frequency'])
                    post_data['scheduled_post'] = next_post_date
                    dtype = "Day"

            if day_type == "date":
                if post_data['day'] and post_data['time']:
                    datetime_string = f"{post_data['day']} {post_data['time']}"
                    datetime_obj = datetime.strptime(
                        datetime_string, '%Y%m%d %H:%M')
                    uk_timezone = pytz.timezone('UTC')
                    localized_datetime = uk_timezone.localize(datetime_obj)
                    post_data['scheduled_post'] = localized_datetime.astimezone(
                        pytz.utc)
                    next_post_date = post_data['scheduled_post']
                    dtype = "Date (YYYYMMDD)"

            # Insert into database
            auto_post_id = add_autopost_to_db(post_data)

            # fix for optional fields for PM purposes
            if post_data['url'] is None:
                post_data['url'] = ""
            if post_data['body'] is None:
                post_data['body'] = ""

            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                pm_username +
                ". \n\n"
                "The details for your scheduled post are as follows: \n\n"
                "- Community: " +
                post_data['community'] +
                "\n\n"
                "- Post Title: " +
                post_data['title'] +
                "\n"
                "- Post Body: " +
                post_data['body'] +
                "\n"
                "- Post URL: " +
                post_data['url'] +
                "\n"
                "- " +
                dtype +
                ": " +
                post_data['day'] +
                "\n"
                "- Time (UTC): " +
                post_data['time'] +
                "\n"
                "- Frequency: " +
                post_data['frequency'] +
                "\n"
                "- Your next post date is: " +
                str(next_post_date) +
                "\n\n"
                "- The ID for this autopost is: " +
                str(auto_post_id) +
                ". (Keep this safe as you will need it to cancel your autopost in the future, if you've set up for a repeating schedule.)"
                "\n \n" +
                bot_strings.PM_SIGNOFF,
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" ")[0] == "#autopostdelete":
            pin_id = pm_context.split(" ")[1]
            del_post = len(split_context) >= 3 and split_context[2] != ""

            delete_conf = delete_autopost(pin_id, pm_sender, del_post)

            if delete_conf == "deleted":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". Your pinned autopost (with ID " +
                    pin_id +
                    ") has been successfully deleted."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if delete_conf == "not deleted":
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if delete_conf == "no id":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". A scheduled post with this ID does not exist."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if delete_conf == "not mod":
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    pm_username +
                    ". As you are not the moderator of this community, you are not able to delete a scheduled post for it."
                    "\n \n" +
                    bot_strings.PM_SIGNOFF,
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context == "#purgevotes":
            if user_admin:
                if os.path.exists('resources/vote.db'):
                    os.remove('resources/vote.db')
                    check_dbs()
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context == "#purgeadminactions":
            if user_admin:
                if os.path.exists('resources/mod_actions.db'):
                    os.remove('resources/mod_actions.db')
                    check_dbs()
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

        if pm_context == "#purgerss":
            if user_admin:
                if os.path.exists('resources/rss.db'):
                    os.remove('resources/rss.db')
                    check_dbs()
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

        if pm_context.split(" ")[0] == "#reject":
            parts = pm_context.split("#")
            if len(parts) > 1 and parts[1].strip() == "reject":
                if pm_sender == 9532930:
                    user = parts[2].strip()
                    rejection = parts[3].strip()
                    reject_user(user, rejection)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

                else:
                    lemmy.private_message.create(
                        bot_strings.GREETING +
                        " " +
                        pm_username +
                        ". Sorry, you can't use this command. \n \n" +
                        bot_strings.PM_SIGNOFF,
                        pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

        if pm_context.split(" ")[0] == "#ban":
            if user_admin or pm_sender == 9532930:
                person_id = pm_context.split(" ")[1]
                lemmy.private_message.mark_as_read(pm_id, True)

                ban_result = ban_email(person_id)

                banned_user = lemmy.user.get(person_id)
                if banned_user:
                    banned_username = banned_user['person_view']['person']['name']

                if ban_result == "notfound":
                    matrix_body = f"The ban email has failed as the user ID couldn't be found ({person_id}). Make sure you're using the public ID (can be found in the URL when sending a PM)."
                    asyncio.run(send_matrix_message(matrix_body))
                elif ban_result == "sent":
                    matrix_body = f"The ban email for id {banned_username}({person_id}) was sent. Modlog here: https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}."
                    asyncio.run(send_matrix_message(matrix_body))
                else:
                    # Handles any other errors from ban_email
                    matrix_body = f"There was an error sending the ban email for id {person_id}. Please check Zippy's logs!"
                    asyncio.run(send_matrix_message(matrix_body))

                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context.split(" ")[0] == '#warn':
            if user_admin:
                parts = pm_context.split("#")
                if len(parts) > 1 and parts[1].strip() == "warn":
                    if len(parts) < 4:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            ". Your command is incomplete. Please provide a valid user ID and warning message.\n\n" +
                            bot_strings.PM_SIGNOFF,
                            pm_sender)
                        lemmy.private_message.mark_as_read(pm_id, True)
                        continue

                    person_id = int(parts[2].strip())
                    warn_message = parts[3].strip()

                    try:
                        person_id = int(parts[2].strip())
                        if person_id <= 0:
                            raise ValueError(
                                "User ID must be a positive integer.")
                    except ValueError:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            ". The provided user ID is invalid. Please provide a valid positive numeric user ID.\n\n" +
                            bot_strings.PM_SIGNOFF,
                            pm_sender)
                        lemmy.private_message.mark_as_read(pm_id, True)
                        continue

                    try:
                        warned_user = lemmy.user.get(person_id)
                    except Exception as e:
                        lemmy.private_message.create(
                            f"{bot_strings.GREETING} {pm_username}. Failed to retrieve user information: {str(e)}\n\n{bot_strings.PM_SIGNOFF}",
                            pm_sender)
                        lemmy.private_message.mark_as_read(pm_id, True)
                        continue

                    if warned_user:
                        warned_username = warned_user['person_view']['person']['name']
                    else:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            pm_username +
                            ". Sorry, I could not find the required user by their user id to issue a warning. Please double check and try again. \n \n" +
                            bot_strings.PM_SIGNOFF,
                            pm_sender)
                        lemmy.private_message.mark_as_read(pm_id, True)
                        continue

                    try:
                        log_warning(person_id, warn_message, pm_username)
                    except ValueError as e:
                        lemmy.private_message.create(
                            f"{bot_strings.GREETING} {pm_username}. Failed to log the warning: {str(e)}\n\n{bot_strings.PM_SIGNOFF}",
                            pm_sender)

                    warning_count = ordinal(get_warning_count(person_id))

                    lemmy.private_message.create(
                        f"Hello, {warned_username}. This is an official warning from the Lemmy.zip Admin Team. \n\n >{warn_message} \n\n *This is your {warning_count} warning.* \n\n --- \n\n This message cannot be replied to. If you wish to dispute this warning, please reach out to any member of the Admin team.",
                        int(person_id))
                    lemmy.private_message.mark_as_read(pm_id, True)
                    matrix_body = f"A warning has been issued by {pm_username} for user {warned_username} (User ID: {person_id}): `{warn_message}`. This is the {warning_count} warning for this user. This has been sent successfully."
                    asyncio.run(send_matrix_message(matrix_body))
                    continue

            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context.split(" ")[0] == '#lock':
            if user_admin:
                parts = pm_context.split("#")
                if len(parts) > 1 and parts[1].strip() == "lock":
                    thread_id = parts[2].strip()
                    warn_message = parts[3].strip() if len(parts) > 3 else None

                    output = lemmy.post.get(int(thread_id))

                    if output['post_view']['post']['local']:
                        lemmy.post.lock(int(thread_id), True)

                        if warn_message:
                            lemmy.comment.create(int(thread_id), warn_message)
                            time.sleep(2)  # in case of delay in posting?
                            get_comment = lemmy.comment.list(
                                post_id=int(thread_id))
                            latest_comment = max(
                                get_comment,
                                key=lambda x: x['comment']['id'],
                                default=None)['comment']['id']
                            lemmy.comment.distinguish(latest_comment, True)

                        else:
                            lemmy.comment.create(
                                int(thread_id), bot_strings.THREAD_LOCK_MESSAGE)
                            time.sleep(2)  # in case of delay in posting?
                            get_comment = lemmy.comment.list(
                                post_id=int(thread_id))
                            latest_comment = max(
                                get_comment,
                                key=lambda x: x['comment']['id'],
                                default=None)['comment']['id']
                            lemmy.comment.distinguish(latest_comment, True)

                        matrix_body = f"Thread locked by {pm_username}. Post: https://lemmy.zip/post/{thread_id} -> Comment: https://lemmy.zip/comment/{latest_comment}."
                        asyncio.run(send_matrix_message(matrix_body))

                        lemmy.private_message.mark_as_read(pm_id, True)
                        continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        # keep this at the bottom
        else:
            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                pm_username +
                ". Sorry, I did not understand your request. Please try again or use `#help` for a list of commands. \n \n" +
                bot_strings.PM_SIGNOFF,
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

def pm_help(user_admin, pm_username, pm_id, pm_sender):
    greeting = f"{bot_strings.GREETING} {pm_username}. "
    commands = bot_strings.BOT_COMMANDS  # Common part for all users
    
    # Add admin commands if user is an admin
    if user_admin:
        commands += bot_strings.BOT_ADMIN_COMMANDS
    
    # Add the signoff at the end
    commands += bot_strings.PM_SIGNOFF
    
    # Send the message
    lemmy.private_message.create(greeting + commands, pm_sender)
    
    # Mark the message as read
    lemmy.private_message.mark_as_read(pm_id, True)
    
def pm_sub(pm_sender, status, pm_username, pm_id):
    if broadcast_status(pm_sender, status) == "successful":
        message = bot_strings.UNSUB_MESSAGE if status == "unsub" else bot_strings.SUB_MESSAGE
        lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{message}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
       
    lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.SUB_ERROR}", pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return





    
    

def is_spam_email(email):

    suspicious_keywords = {"seo", "info", "sales", "media"}

    # Count the number of digits in the email
    num_count = sum(char.isdigit() for char in email)

    # Split the email address at '@' to extract the domain
    local_part, domain = email.split('@')

    # Logging the domain for debugging
    logging.info("Checking spam email with domain: " + domain)

    contains_suspicious_keyword = any(
        keyword in local_part.lower() for keyword in suspicious_keywords)

    # Check if the email is spam based on the number of digits or if the
    # domain is a known spam domain
    return num_count > 2 or domain in blocklist or contains_suspicious_keyword


def get_new_users():
    try:
        output = lemmy.admin.list_applications(unread_only="true")
        new_apps = output['registration_applications']
    except BaseException:
        logging.info("Error with connection, retrying...")
        login()
        return

    for output in new_apps:
        local_user_id = output['registration_application']['local_user_id']
        username = output['creator']['name']
        email = output['creator_local_user']['email']
        public_user_id = output['creator_local_user']['person_id']

        if update_registration_db(
                local_user_id,
                username,
                public_user_id,
                email) == "new_user":
            logging.debug("sending new user a pm")
            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                username +
                ". " +
                bot_strings.WELCOME_MESSAGE +
                bot_strings.PM_SIGNOFF,
                public_user_id)

            # Check if the email is from a known spam domain
            if is_spam_email(email):
                logging.info(
                    "User " +
                    username +
                    " tried to register with a potential spam email: " +
                    email)

                matrix_body = "New user " + username + " (https://" + settings.INSTANCE + "/u/" + username + ") with ID " + str(
                    public_user_id) + " has signed up with an email address that may be a temporary or spam email address: " + email
                asyncio.run(send_matrix_message(matrix_body))

            if settings.EMAIL_FUNCTION:
                welcome_email(email)

        continue


def update_registration_db(local_user_id, username, public_user_id, email):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            # search db for matching user id
            curs.execute(
                'SELECT local_user_id FROM users WHERE local_user_id=?', (local_user_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching ID found, ignoring")
                return "User ID already exists"

            # default user to subscribed list
            subscribed = 1

            logging.debug("User ID did not match an existing user ID, adding")
            sqlite_insert_query = "INSERT INTO users (local_user_id, public_user_id, username, email, subscribed) VALUES (?, ?, ?, ?, ?);"
            data_tuple = (
                local_user_id,
                public_user_id,
                username,
                email,
                subscribed)

            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new user to database")
            return "new_user"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"


def get_communities():
    try:
        communities = lemmy.community.list(
            limit=5, page=1, sort=SortType.New, type_=ListingType.Local)
        local_comm = communities

    except BaseException:
        logging.info("Error with connection, retrying...")
        login()
        return

    for communities in local_comm:
        community_id = communities['community']['id']
        community_name = communities['community']['name']

        find_mod = lemmy.community.get(community_id)

        if find_mod is None or find_mod.get('moderators') is None:
            logging.info("Unable to get moderator of community, skipping.")
            continue

        mods = find_mod['moderators']

        for find_mod in mods:
            mod_id = find_mod['moderator']['id']
            mod_name = find_mod['moderator']['name']

        if new_community_db(community_id, community_name) == "community":
            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                mod_name +
                ". Congratulations on creating your community, [" +
                community_name +
                "](/c/" +
                community_name +
                "@" +
                settings.INSTANCE +
                "). \n " +
                bot_strings.MOD_ADVICE +
                bot_strings.PM_SIGNOFF,
                mod_id)


def add_giveaway_thread(thread_id):
    try:
        with connect_to_giveaway_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO giveaways (thread_id) VALUES (?)', (thread_id,))
            conn.commit()
            giveaway_id = cursor.lastrowid
            return giveaway_id
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"


def close_giveaway_thread(thread_id):
    with connect_to_giveaway_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE giveaways SET status = ? WHERE thread_id = ?',
            ('closed',
             thread_id))
        conn.commit()


def draw_giveaway_thread(thread_id, num_winners):
    with connect_to_giveaway_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            'SELECT giveaway_id FROM giveaways WHERE thread_id = ?', (thread_id,))
        result = cursor.fetchone()

        giveaway_id = result[0]
        cursor.execute('''
                SELECT username FROM entrants
                WHERE giveaway_id = ?
                ORDER BY RANDOM()
            ''', (giveaway_id,))
        entrants = cursor.fetchall()

        if len(entrants) < int(num_winners):
            return "min_winners"
        usernames = [entrant[0] for entrant in entrants]
        random.shuffle(usernames)
        winners = random.sample(usernames, int(num_winners))
        return winners


def check_giveaways(
        thread_id,
        comment_poster,
        comment_username,
        creator_local):
    # check if post is in db
    with connect_to_giveaway_db() as conn:
        action_query = '''SELECT giveaway_id, status FROM giveaways WHERE thread_id=?'''
        thread_match = execute_sql_query(conn, action_query, (thread_id,))

        if thread_match:
            giveaway_id = thread_match[0]
            status = thread_match[1]

            if status == 'closed':
                return
            try:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO entrants (giveaway_id, username) VALUES (?, ?)',
                    (giveaway_id,
                     comment_username))
                conn.commit()
                ticket_number = cursor.lastrowid
                logging.info(
                    f"User '{comment_poster}' has entered giveaway '{giveaway_id}' with ticket number '{ticket_number}'")
                lemmy.private_message.create(
                    bot_strings.GREETING +
                    " " +
                    comment_username +
                    ". Your giveaway entry has been recorded! Your entry number is #" +
                    str(ticket_number) +
                    " - Good luck!",
                    comment_poster)
            except sqlite3.IntegrityError:
                logging.info(
                    f"User '{comment_poster}' has already entered giveaway '{giveaway_id}'")


def new_community_db(community_id, community_name):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            # search db to see if community exists in DB already
            curs.execute(
                'SELECT community_id FROM communities WHERE community_id=?', (community_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching community ID found, ignoring")
                return "Community ID already exists"

            logging.debug(
                "community ID did not match an existing community ID, adding")
            sqlite_insert_query = "INSERT INTO communities (community_id, community_name) VALUES (?, ?);"
            data_tuple = (community_id, community_name)

            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new community to database")
            return "community"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"


def connect_to_games_db():
    return sqlite3.connect('resources/games.db')


def welcome_email(email):
    message = MIMEMultipart()
    message['From'] = settings.SENDER_EMAIL
    message['To'] = email
    message['Subject'] = bot_strings.EMAIL_SUBJECT

    # use this for a simple text email, uncomment below:
    # body
    # body = bot_strings.EMAIL_SUBJECT + ".\n\n We've received your application and one of our Admins will manually verify your account shortly. \n\n Lemmy.zip prides itself on being a welcoming and inclusive Lemmy instance, and to help reduce spam we manually verify all accounts.\n\n Once your account is accepted, you will receive another email from us confirming this and then you'll be able to log in to your account using the details you set up. You won't be able to login until you've received this confirmation email.\n\n If you've not received an email confirming you have been accepted within a couple of hours, please email hello@lemmy.zip with your username, and we can look into the issue further. Please be patient with us!\n\n Thanks again for signing up to Lemmy.zip, we're excited to welcome you to the Fediverse :)\n\n PS - Once you've logged in, look out for a message from ZippyBot with a guide on how to get started!"
    # message.attach(MIMEText(body, 'plain'))

    # use this for sending a HTML email i.e. with pictures and colours.
    # html email - resources to be saved in the "resources" folder
    with open('resources/index.html', 'r', encoding='utf-8') as html_file:
        html_content = html_file.read()
    # Attach the HTML content to the email
    message.attach(MIMEText(html_content, 'html'))

    # Attach the image as an inline attachment
    with open('resources/images/image-1.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        # use content ids and change to img tag in html to match
        image.add_header('Content-ID', '<image-1>')
        message.attach(image)

    with open('resources/images/image-2.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        image.add_header('Content-ID', '<image-2>')
        message.attach(image)

    # initialise SMTP server - keep from here for either email type.
    try:
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
        server.sendmail(settings.SENDER_EMAIL, email, message.as_string())
        logging.info("Welcome email sent successfully")
    except Exception as e:
        logging.error("Error: Unable to send email.", str(e))
    finally:
        server.quit


def ban_email(person_id):
    with sqlite3.connect('resources/users.db') as conn:
        curs = conn.cursor()

        curs.execute(
            'SELECT email FROM users WHERE public_user_id = ?', (person_id,))
        id_match = curs.fetchone()

        # usr not in db
        if not id_match:
            return "notfound"

        email = id_match[0]

        message = MIMEMultipart()
        message['From'] = settings.SENDER_EMAIL
        message['To'] = email
        message['Subject'] = "Lemmy.zip - Account Ban"

        body = f"""
            <p>Hello, this is an automated message to let you know your Lemmy.zip account has received a ban.</p>
            <p>You can see the details and reason for this ban at this link:
            <a href="https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}">
            https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}</a>.</p>

            <p>If you would like to dispute this ban, please send an email to <a href="mailto:hello@lemmy.zip">hello@lemmy.zip</a>.
            During the period your account is banned for, you won't be able to access your account including logging in, posting, or voting. You can see our Terms of Service and Code of Conduct at
            <a href="https://legal.lemmy.zip">legal.lemmy.zip</a>.</p>

            <p><i>Please note, you cannot reply directly to this email. Please send appeals to hello@lemmy.zip.</i></p>
        """
        message.attach(MIMEText(body, 'html'))

        # send
        try:
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
                server.sendmail(
                    settings.SENDER_EMAIL,
                    email,
                    message.as_string())
                logging.info("Ban notification email sent successfully.")
                return "sent"
        except Exception as e:
            logging.error("Error: Unable to send email. " + str(e))
            return "error"


def steam_deals():
    # url of the RSS Feed
    rss_url = "http://www.reddit.com/r/steamdeals/new/.rss?sort=new"

    # parse feed
    feed = feedparser.parse(rss_url)

    # loop through 10 entries
    for entry in feed.entries[:10]:
        content_value = entry.content[0]['value']
        steam_url = re.search(
            r'https://store\.steampowered\.com/app/\d+/\w+/',
            str(content_value))

        deal_published = entry.published
        deal_title = entry.title

        if steam_url:
            steam_url = steam_url.group()
        else:
            logging.info(
                "No store.steampowered.com URL found in the steam deals entry.")
            add_deal_to_db(deal_title, deal_published)
            continue

        if add_deal_to_db(deal_title, deal_published) == "added":
            community_id = lemmy.discover_community("gamedeals")
            lemmy.post.create(
                community_id,
                name="Steam Deal: " +
                deal_title,
                url=steam_url)


def RSS_feed():
    try:
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag
                FROM feeds
            """)
            feeds = cursor.fetchall()

        for feed in feeds:
            feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag = feed
            posts = fetch_latest_posts(
                feed_url,
                url_contains_filter,
                url_excludes_filter,
                title_contains_filter,
                title_excludes_filter,
                community,
                tag)

            if posts == "URL access error":
                logging.error("Skipping RSS Feed due to URL access error.")
                continue

            if not isinstance(posts, list):
                logging.error(
                    f"Failed to fetch posts for feed URL {feed_url}. Error: {posts}")
                continue

            for post in posts:
                if insert_new_post(feed_id, post):
                    if tag:
                        post_title = f"[{tag}] " + post['title']
                    else:
                        post_title = post['title']
                    # actually post to lemmy here
                    logging.debug("Creating an RSS post.")
                    lemmy.post.create(
                        community_id=int(community),
                        name=post_title,
                        url=post['post_url'])
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def fetch_rss_feeds():
    try:
        logging.debug("Connecting to RSS DB to fetch RSS feeds")
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT feed_id, feed_url FROM feeds")
            feeds = cursor.fetchall()
        return feeds
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def fetch_latest_posts(
        feed_url,
        url_contains_filter=None,
        url_excludes_filter=None,
        title_contains_filter=None,
        title_excludes_filter=None,
        community=None,
        tag=None):
    try:
        logging.debug(f"Fetching latest RSS posts from {feed_url}.")
        # Stream=True to only fetch headers
        response = requests.get(feed_url, stream=True, timeout=10)
        if response.status_code == 404:
            logging.error(f"URL not found (404): {feed_url}")
            return "URL access error"

        if response.status_code == 403:
            logging.error(f"Access forbidden (403) to URL: {feed_url}")
            return "URL access error"

        if response.status_code != 200:
            logging.error(
                f"Failed to access URL {feed_url}. HTTP status code: {response.status_code}")
            return "URL access error"

        feed = feedparser.parse(feed_url)

        filtered_posts = []
        for entry in feed.entries[:3]:
            post_url = entry.link
            post_content = entry.title + ' ' + \
                entry.summary if hasattr(entry, 'summary') else entry.title

            # URL filter
            if url_contains_filter and not any(
                    filter_word in post_url for filter_word in url_contains_filter.split(',')):
                continue
            if url_excludes_filter and any(
                    filter_word in post_url for filter_word in url_excludes_filter.split(',')):
                continue

            # title filter
            if title_contains_filter and not any(
                    word in post_content for word in title_contains_filter.split(',')):
                continue
            if title_excludes_filter and any(
                    word in post_content for word in title_excludes_filter.split(',')):
                continue

            filtered_posts.append({
                'post_url': post_url,
                'title': entry.title,
                'description': entry.summary if hasattr(entry, 'summary') else '',
                'post_date': entry.published if hasattr(entry, 'published') else ''
            })
        return filtered_posts
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def insert_new_post(feed_id, post):
    try:
        logging.debug("Inserting new post to RSS DB")
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT post_id FROM posts WHERE post_url = ?", (post['post_url'],))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO posts (feed_id, post_url, title, description, posted, post_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (feed_id,
                     post['post_url'],
                     post['title'],
                     post['description'],
                     0,
                     post['post_date']))
                conn.commit()
                return True
        return False
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def add_new_feed(
        feed_url,
        url_contains_filter,
        url_excludes_filter,
        title_contains_filter,
        title_excludes_filter,
        community,
        tag):
    conn = connect_to_rss_db()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT feed_id FROM feeds WHERE feed_url = ? AND community = ?""",
        (feed_url,
         community))

    if cursor.fetchone():
        conn.close()
        return "exists"

    insert_query = """
    INSERT INTO feeds (feed_url, url_contains_filter, title_contains_filter, url_excludes_filter, title_excludes_filter, community, tag, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        feed_url,
        url_contains_filter,
        title_contains_filter,
        url_excludes_filter,
        title_excludes_filter,
        community,
        tag,
        datetime.now())

    try:
        cursor.execute(insert_query, values)
        conn.commit()
        feed_id = cursor.lastrowid
        return feed_id
    except sqlite3.IntegrityError as e:
        logging.debug(f"An error occurred: {e}")
        return None
    finally:
        conn.close()


def add_welcome_message(community, message):
    conn = connect_to_welcome_db()
    cursor = conn.cursor()

    insert_query = """
    INSERT OR REPLACE INTO messages (community, message)
    VALUES (?, ?)
    """

    values = (community, message)

    try:
        cursor.execute(insert_query, values)
        conn.commit()
        return "added"
    except sqlite3.IntegrityError as e:
        logging.debug(f"An error occurred: {e}")
        return None
    finally:
        conn.close()


def add_community_word(community, words, action):
    conn = connect_to_mod_db()
    cursor = conn.cursor()

    if isinstance(words, str):
        new_words_set = set(words.split(','))
    elif isinstance(words, list):
        new_words_set = set(words)

    # fetch current list of words
    cursor.execute(
        "SELECT words FROM community_words WHERE community = ?", (community,))
    result = cursor.fetchone()
    if result:
        # Assuming words are stored as a comma-separated string
        current_words = result[0].split(',')
    else:
        current_words = []

    updated_words_set = set(current_words).union(new_words_set)

    updated_words = ','.join(updated_words_set)

    if result:
        # Update the existing entry
        cursor.execute(
            "UPDATE community_words SET words = ? WHERE community = ? AND action = ?",
            (updated_words,
             community,
             action))
    else:
        # Insert a new entry if none existed
        cursor.execute(
            "INSERT INTO community_words (community, words, action) VALUES (?, ?, ?)",
            (community,
             updated_words,
             action))

    conn.commit()
    conn.close()

    return "added"


def add_deal_to_db(deal_title, deal_published):
    try:
        with connect_to_games_db() as conn:
            # Check if bundble already is in db
            deal_query = '''SELECT deal_name, deal_date FROM deals WHERE deal_name=? AND deal_date=?'''
            deal_match = execute_sql_query(
                conn, deal_query, (deal_title, deal_published,))

            if deal_match:
                return "duplicate"

            logging.debug("New deal to be added to DB")

            sqlite_insert_query = """INSERT INTO deals (deal_name, deal_date) VALUES (?,?);"""
            data_tuple = (deal_title, deal_published,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added deal to database")
            return "added"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def check_comments():
    recent_comments = lemmy.comment.list(
        limit=10, sort=SortType.New, type_=ListingType.Local)
    for comment in recent_comments:
        comment_id = comment['comment']['id']
        comment_text = comment['comment']['content']
        comment_poster = comment['creator']['id']

        # check if it has already been scanned
        if check_comment_db(comment_id) == "duplicate":
            continue

        # check if its a comment by a mod to delete a post
        if comment_text == "#delete":
            community = comment['community']['id']
            post = comment['post']['id']
            poster = comment['post']['creator_id']

            output = lemmy.community.get(id=community)

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == comment_poster:
                    if poster == settings.BOT_ID:
                        lemmy.post.delete(post_id=post, deleted=True)

        community_name = comment['community']['name']

        # check if a giveaway post
        if settings.GIVEAWAY_ENABLED:

            comment_username = comment['creator']['name']
            creator_local = comment['creator']['local']
            thread_id = comment['post']['id']
            account_age = comment['creator']['published']

            if creator_local:
                account_age = datetime.strptime(
                    account_age, '%Y-%m-%dT%H:%M:%S.%fZ')
                # this is temporary and fixed, needs putting into the giveaways
                # table and adding as a variable to the PM command, so it can
                # be used as part of the wider mod toolset.
                set_date = datetime(2024, 6, 5)
                difference = set_date - account_age

                if difference > timedelta(days=3):
                    check_giveaways(
                        thread_id,
                        comment_poster,
                        comment_username,
                        creator_local,
                        comment_id)

        # Initialize match flags for each post
        match_found_text = False

        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT words FROM community_words WHERE community = ?", (community_name,))
            result = cursor.fetchone()
            if result:
                db_words_set = set(result[0].split(','))

                text_words_set = set(comment_text.lower().split())

                match_found_text = bool(db_words_set & text_words_set)

        if match_found_text:
            lemmy.comment.report(
                comment_id,
                reason="Word in comment appears on community banned list - Automated report by " +
                bot_strings.BOT_NAME)
            mod_action = "Comment Flagged"
            logging.info("Word matching regex found in content, reported.")

        else:
            mod_action = "None"

        add_comment_to_db(comment_id, comment_poster, mod_action)

        # admin matrix report
        regex_pattern = re.compile(settings.SLUR_REGEX)
        match_found = False

        if re.search(regex_pattern, comment_text.lower()):
            match_found = True

        if match_found:
            matrix_body = "Word(s) matching banned list appearing in comment https://" + \
                settings.INSTANCE + "/comment/" + str(comment_id) + ". - Please review urgently."
            asyncio.run(send_matrix_message(matrix_body))
            break


def check_comment_db(comment_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT comment_id FROM new_comments WHERE comment_id=?'''
            comment_match = execute_sql_query(
                conn, action_query, (comment_id,))

            if comment_match:
                return "duplicate"

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"


def add_comment_to_db(comment_id, comment_poster, mod_action):
    try:
        logging.debug("Adding new comment to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_comments (comment_id, comment_poster, mod_action) VALUES (?,?,?);"""
            data_tuple = (comment_id, comment_poster, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added comment to db")
            return "added"

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"


def check_posts():
    recent_posts = lemmy.post.list(
        limit=10,
        sort=SortType.New,
        type_=ListingType.Local)
    for post in recent_posts:
        post_id = post['post']['id']
        post_title = post['post']['name']

        # check if post has already been scanned
        if check_post_db(post_id) == "duplicate":
            continue

        # Check if 'body' exists in the 'post' dictionary
        if 'body' in post['post']:
            post_text = post['post']['body']
        else:
            post_text = "No body found"

        poster_id = post['creator']['id']
        poster_name = post['creator']['name']
        community_name = post['community']['name']

        # Initialize match flags for each post
        match_found_text = False
        match_found_title = False

        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT words FROM community_words WHERE community = ?", (community_name,))
            result = cursor.fetchone()
            if result:
                db_words_set = set(result[0].split(','))

                text_words_set = set(post_text.lower().split())
                title_words_set = set(post_title.lower().split())

                # Check for word matches in text and title
                match_found_text = bool(db_words_set & text_words_set)
                match_found_title = bool(db_words_set & title_words_set)

        if match_found_text or match_found_title:
            lemmy.post.report(
                post_id,
                reason="Word in post by user " +
                poster_name +
                " appears on community slur list - Automated report by " +
                bot_strings.BOT_NAME)
            mod_action = "Post Flagged"
            logging.info(
                f"Word matching community ban list found in post by {poster_name}, reported.")
        else:
            mod_action = "None"

        add_post_to_db(post_id, poster_id, mod_action)

        # admin matrix report
        regex_pattern = re.compile(settings.SLUR_REGEX)
        match_found = False

        if re.search(regex_pattern, post_text.lower()):
            match_found = True
        if re.search(regex_pattern, post_title.lower()):
            match_found = True

        if match_found:
            matrix_body = "Word(s) matching banned list appearing in post https://" + \
                settings.INSTANCE + "/post/" + str(post_id) + ". - Please review urgently."
            asyncio.run(send_matrix_message(matrix_body))
            break


def check_post_db(post_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT post_id FROM new_posts WHERE post_id=?'''
            post_match = execute_sql_query(conn, action_query, (post_id,))

            if post_match:
                return "duplicate"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"


def add_post_to_db(post_id, poster_id, mod_action):
    try:
        logging.debug("Adding new post to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_posts (post_id, poster_id, mod_action) VALUES (?,?,?);"""
            data_tuple = (post_id, poster_id, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added post to db")
            return "added"

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"


def broadcast_message(message):
    # get lowest and highest local user ids first
    try:
        logging.debug("broadcasting message")
        with connect_to_users_db() as conn:
            cursor = conn.cursor()
            query = "SELECT public_user_id, username, subscribed FROM users ORDER BY local_user_id"
            cursor.execute(query)

            for row in cursor.fetchall():
                public_id, username, subscribed = row
                try:
                    if subscribed == 1:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            username +
                            ".\n \n" +
                            message +
                            "\n\n --- \n *This is an automated message. To unsubscribe, please reply to this message with* `#unsubscribe`.",
                            public_id)
                        time.sleep(0.2)
                except Exception as e:
                    logging.exception("Message failed to send to " + username)
    except sqlite3.Error as e:
        logging.error("SQLite error: %s", e)

    finally:
        if cursor:
            cursor.close()


def reject_user(user, rejection):
    with connect_to_users_db() as conn:
        query = "SELECT email from users WHERE local_user_id = ?"
        result = execute_sql_query(conn, query, (user,))

        email = result[0]
        logging.info("Rejection email sent to " + email)

        message = MIMEMultipart()
        message['From'] = settings.SENDER_EMAIL
        message['To'] = email
        message['Subject'] = "Lemmy.zip - Application Rejected"

        # use this for a simple text email, uncomment below:
        body = "We've rejected your Lemmy.zip application. In order to create an inclusive, active, and spam-free Lemmy instance, we manually review each application. If you think this was a mistake, please email us at hello@lemmy.zip from the email address you created your account with and make sure to include your username, and we'll take a look. \n\n Your account was rejected for the following reason: " + rejection
        message.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
            server.sendmail(settings.SENDER_EMAIL, email, message.as_string())
            logging.info("Rejection email sent successfully")
        except Exception as e:
            logging.error("Error: Unable to send email.", str(e))
        finally:
            server.quit


def broadcast_status(pm_sender, status):
    with connect_to_users_db() as conn:
        cursor = conn.cursor()

        if status == "unsub":
            query = "UPDATE users SET subscribed = 0 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()
            logging.debug("User unsubscribed successfully")


        if status == "sub":
            query = "UPDATE users SET subscribed = 1 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()
            logging.debug("User subscribed successfully")
            
    return "successful"


def post_reports():

    recent_reports = lemmy.post.report_list(limit=5, unresolved_only="true")

    # define words in the report that will trigger the urgent message
    serious_words = settings.SERIOUS_WORDS.split(',')

    if recent_reports:
        # recent_reports = lemmy.post.report_list(limit=10)
        for report in recent_reports:
            creator = report['creator']['name']
            creator_id = report['post_report']['creator_id']
            local_user = report['creator']['local']
            report_id = report['post_report']['id']
            report_reason = report['post_report']['reason']
            # activity pub id (i.e. home instance post url)
            ap_id = report['post']['ap_id']
            reported_content_id = report['post_report']['post_id']

            report_reason = report_reason.lower()

            local_post = re.search(settings.INSTANCE, str(ap_id))
            ## REPORTS ##
            # Against content on Local instance (either by a local user or
            # remote user)
            report_reply = None
            if local_post:
                # reporter is a local user
                if local_user:
                    report_reply = bot_strings.REPORT_LOCAL
                # reporter is from a different instance
                # else:
                    # report_reply = bot_strings.REPORT_REMOTE

            with connect_to_reports_db() as conn:
                check_reports = '''SELECT report_id FROM post_reports WHERE report_id=?'''
                report_match = execute_sql_query(
                    conn, check_reports, (report_id,))

                if not report_match:
                    # tables: 'post_reports', '(report_id INT, reporter_id INT,
                    # reporter_name TEXT, report_reason TEXT, post_id INT'
                    sqlite_insert_query = """INSERT INTO post_reports (report_id, reporter_id, reporter_name, report_reason, post_id) VALUES (?,?,?,?,?);"""
                    data_tuple = (
                        report_id,
                        creator_id,
                        creator,
                        report_reason,
                        reported_content_id,
                    )
                    execute_sql_query(conn, sqlite_insert_query, data_tuple)

                    if report_reply:
                        lemmy.private_message.create(
                            "Hello " +
                            creator +
                            ",\n\n" +
                            report_reply +
                            "\n \n" +
                            bot_strings.PM_SIGNOFF,
                            creator_id)

                    for word in serious_words:
                        if word in report_reason and settings.MATRIX_FLAG:
                            matrix_body = "Report from " + creator + " regarding a post at https://" + settings.INSTANCE + "/post/" + \
                                str(reported_content_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                            asyncio.run(send_matrix_message(matrix_body))
                            break


def comment_reports():
    recent_reports = lemmy.comment.report_list(limit=5, unresolved_only="true")

    # define words in the report that will trigger the urgent message
    serious_words = settings.SERIOUS_WORDS.split(',')

    if recent_reports:
        for report in recent_reports:
            creator = report['creator']['name']
            reporter_id = report['creator']['id']
            local_user = report['creator']['local']
            report_id = report['comment_report']['id']
            report_reason = report['comment_report']['reason']
            # activity pub id (i.e. home instance post url)
            ap_id = report['comment']['ap_id']
            reported_content_id = report['comment_report']['comment_id']

            report_reason = report_reason.lower()

            local_post = re.search(settings.INSTANCE, str(ap_id))

            ## REPORTS ##
            # Against content on Local instance (either by a local user or
            # remote user)
            report_reply = None
            if local_post:
                # reporter is a local user
                if local_user:
                    report_reply = bot_strings.REPORT_LOCAL
                # reporter is from a different instance
                # else:
                    # report_reply = bot_strings.REPORT_REMOTE
                else:
                    continue

            with connect_to_reports_db() as conn:
                check_reports = '''SELECT report_id FROM comment_reports WHERE report_id=?'''
                report_match = execute_sql_query(
                    conn, check_reports, (report_id,))

                if not report_match:
                    sqlite_insert_query = """INSERT INTO comment_reports (report_id, reporter_id, reporter_name, report_reason, comment_id) VALUES (?,?,?,?,?);"""
                    data_tuple = (
                        report_id,
                        reporter_id,
                        creator,
                        report_reason,
                        reported_content_id,
                    )
                    execute_sql_query(conn, sqlite_insert_query, data_tuple)

                    if report_reply:
                        lemmy.private_message.create(
                            "Hello " +
                            creator +
                            ",\n\n" +
                            report_reply +
                            "\n \n" +
                            bot_strings.PM_SIGNOFF,
                            reporter_id)

                    for word in serious_words:
                        if word in report_reason and settings.MATRIX_FLAG:
                            # write message to send to matrix
                            matrix_body = "Report from " + creator + " regarding a comment at https://" + settings.INSTANCE + "/comment/" + \
                                str(reported_content_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                            asyncio.run(send_matrix_message(matrix_body))
                            break


def check_reports():
    post_reports()
    comment_reports()


def get_first_post_date(day, time, frequency):
    # Map days to integers

    day = day.lower()

    days = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    today = datetime.now()
    today_weekday = today.weekday()
    target_weekday = days[day]

    if frequency == 'monthly':
        next_month = today + relativedelta(months=1)
        days_until_next = (target_weekday - next_month.weekday() + 7) % 7
        next_post_date = next_month + timedelta(days=days_until_next)
    else:
        days_until_next = (target_weekday - today_weekday + 7) % 7
        if days_until_next == 0 and frequency != 'once':
            frequency_mapping = {
                'once': 0,
                'weekly': 7,
                'fortnightly': 14,
                '4weekly': 28
            }
            days_until_next = frequency_mapping.get(frequency, 7)

        next_post_date = today + timedelta(days=days_until_next)

    post_time = datetime.strptime(time, "%H:%M").time()
    return datetime.combine(next_post_date.date(), post_time)


def calc_next_post_date(old_post_date, frequency):
    frequency_mapping = {
        'once': 0,
        'weekly': timedelta(days=7),
        'fortnightly': timedelta(days=14),
        '4weekly': timedelta(days=28),
        'monthly': relativedelta(months=1)
    }

    if frequency == 'once':
        return "delete"

    time_to_add = frequency_mapping.get(frequency, timedelta(days=7))

    new_post_date = old_post_date + time_to_add

    return new_post_date


def check_scheduled_posts():
    # First get current time/date in UTC
    current_utc = datetime.now(timezone.utc)

    # second connect to DB and check all rows for a matching time/data
    # parameter
    with connect_to_autopost_db() as conn:
        cursor = conn.cursor()
        query = "SELECT pin_id, scheduled_post FROM com_posts"
        cursor.execute(query)
        records = cursor.fetchall()

        one_minute = timedelta(minutes=1)

        # Process each record
        for record in records:
            record_id, stored_time_str = record
            stored_datetime = datetime.fromisoformat(stored_time_str)
            stored_datetime = stored_datetime.replace(tzinfo=timezone.utc)

            # check if the stored time is within 1 minute past current UTC
            # if current_utc - one_minute < stored_datetime <= current_utc:
            if stored_datetime <= current_utc:
                # Fetch the full row for the record_id
                full_row_query = "SELECT * FROM com_posts WHERE pin_id = ?"
                cursor.execute(full_row_query, (record_id,))
                full_row = cursor.fetchone()

                community_name = full_row[1]
                post_title = full_row[3]
                post_url = full_row[4]
                post_body = full_row[5]
                post_frequency = full_row[7]
                previous_post = full_row[8]

                if previous_post is not None:
                    lemmy.post.feature(
                        int(previous_post), False, FeatureType.Community)

                com_details = lemmy.community.get(name=community_name)

                if com_details is None:
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit()
                    continue

                if post_body is None:
                    post_body = ""
                # format body string
                post_body = post_body.replace(
                    "%m", current_utc.strftime("%B"))  # Month name
                post_body = post_body.replace(
                    "%d", current_utc.strftime("%d"))  # Day of the month
                post_body = post_body.replace(
                    "%y", current_utc.strftime("%Y"))  # Year
                post_body = post_body.replace(
                    "%w", current_utc.strftime("%A"))  # Day of the week

                # format title string
                post_title = post_title.replace(
                    "%m", current_utc.strftime("%B"))  # Month name
                post_title = post_title.replace(
                    "%d", current_utc.strftime("%d"))  # Day of the month
                post_title = post_title.replace(
                    "%y", current_utc.strftime("%Y"))  # Year
                post_title = post_title.replace(
                    "%w", current_utc.strftime("%A"))  # Day of the week

                com_id = com_details['community_view']['community']['id']
                # create post
                post_output = lemmy.post.create(
                    com_id, post_title, post_url, post_body)

                # get post ID
                previous_post = post_output['post_view']['post']['id']

                query = "UPDATE com_posts SET previous_post = ? WHERE pin_id = ?"
                cursor.execute(query, (previous_post, record_id))
                conn.commit()

                lemmy.post.feature(
                    previous_post, True, feature_type=FeatureType.Community)

                # need to work out when to make the next post
                old_post_date = stored_datetime
                next_post_date = calc_next_post_date(
                    old_post_date, post_frequency)
                # check for "once" posts
                if next_post_date == 'delete':
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit()
                    continue

                query = "UPDATE com_posts SET scheduled_post = ? WHERE pin_id = ?"
                cursor.execute(query, (next_post_date, record_id))
                conn.commit()

    # Close the database connection
    conn.close()


def log_warning(person_id, warning_message, admin):
    """
    Logs a warning into the 'warnings' table.

    Table Schema:
    - user_id (INT): ID of the person being warned.
    - warning_reason (TEXT): Reason for the warning.
    - admin (TEXT): Admin who issued the warning.
    """
    if not isinstance(person_id, int):
        raise ValueError("person_id must be an integer")
    if not warning_message or not isinstance(warning_message, str):
        raise ValueError("warning_message must be a non-empty string")
    if not admin or not isinstance(admin, str):
        raise ValueError("admin must be a non-empty string")

    try:
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO warnings (user_id, warning_reason, admin) VALUES (?, ?, ?);"""
            data_tuple = (person_id, warning_message, admin)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)
    except Exception as e:
        logging.info(f"Error logging warning: {e}")
        raise


def get_warning_count(person_id):
    """
    Retrieves the count of warnings for a specific user ID from the 'warnings' table.

    Args:
        person_id (int): The ID of the person whose warnings need to be counted.

    Returns:
        int: The count of warnings for the specified user.

    Raises:
        ValueError: If the person_id is not an integer.
        Exception: If there is a database-related error.
    """
    if not isinstance(person_id, int):
        raise ValueError("person_id must be an integer")

    try:
        with connect_to_mod_db() as conn:
            sqlite_select_query = """SELECT COUNT(*) FROM warnings WHERE user_id = ?;"""
            cursor = conn.cursor()
            cursor.execute(sqlite_select_query, (person_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return 0
    except Exception as e:
        logging.info(f"Error retrieving warning count: {e}")
        raise


async def send_matrix_message(matrix_body):
    client = AsyncClient(settings.MATRIX_URL, settings.MATRIX_ACCOUNT)

 # use an access token to log in
    client.access_token = settings.MATRIX_API_KEY

    room_id = settings.MATRIX_ROOM_ID

    # send a message to the room
    await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={
            "msgtype": "m.text",
            "body": matrix_body
        }
    )

    # log out
    await client.close()


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix
